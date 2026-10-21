"""DB 모드 검사. 팀 모델(develop #15)로 테스트 DB에 행을 넣고 SqlTeamActivityReader로 리포트를 만든다.

넣는 행은 services/agent/fixtures의 행 그대로다. 그래서 fixture 모드와 DB 모드가 같은 결과를 내는지도
함께 확인한다.
"""

import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from core.clock import utc_now
from models.agent.agent_feedback import (
    FEEDBACK_TYPE_DAILY,
    FEEDBACK_TYPE_STEP,
    AgentFeedback,
)
from models.exercise_step_record import ExerciseStepRecord
from models.user import User
from repositories.agent.team_activity_reader import (
    FixtureTeamActivityReader,
    SqlTeamActivityReader,
)
from services.agent.daily_report import DailyReportResult, build_daily_report
from services.agent.llm import Usage
from services.agent.report_stats import SetProgress
from tests.agent.agent_seed import seed_scenario

RECORD_DAY = date(2026, 10, 19)
MIXED_DAY = date(2026, 10, 20)


class CapturingLlm:
    """STEP 메모는 받은 스텝에 맞춰 돌려주고, DAILY는 첫 후보를 고른다. 받은 입력을 모아 둔다."""

    name = "fake"
    model = "fake-1"

    def __init__(self) -> None:
        self.daily_payloads: list[dict] = []

    def generate(self, system_prompt: str, user_message: str, timeout: float):
        payload = json.loads(user_message)
        if "steps" in payload:
            memos = [
                {"exercise_step_id": step["exercise_step_id"], "memo": f"{step['step_name']} 메모"}
                for step in payload["steps"]
            ]
            return json.dumps(memos, ensure_ascii=False), Usage(10, 20)
        self.daily_payloads.append(payload)
        candidates = payload["focus_candidates"]
        focus = (
            {"step_id": candidates[0]["exercise_step_id"], "reason": "이 스텝에 신경 써 봐요."}
            if candidates
            else None
        )
        answer = {"summary": "오늘도 꾸준히 해 주셨어요.", "next_focus": focus}
        return json.dumps(answer, ensure_ascii=False), Usage(10, 20)


@pytest.fixture()
def user(db_session: Session) -> User:
    row = User(
        nickname="맘핏",
        email="mom@example.com",
        due_date=date(2026, 12, 25),
        onboarding_completed=True,
        terms_agreed_at=utc_now(),
        health_data_agreed_at=utc_now(),
    )
    db_session.add(row)
    db_session.commit()
    return row


def _report(db: Session, user: User, day: date, reader) -> tuple[DailyReportResult, dict]:
    llm = CapturingLlm()
    result = build_daily_report(db, user, day, reader, llm)
    return result, llm.daily_payloads[-1]


def _feedback(db: Session, feedback_type: str) -> list[AgentFeedback]:
    return (
        db.query(AgentFeedback)
        .filter(AgentFeedback.feedback_type == feedback_type)
        .order_by(AgentFeedback.id)
        .all()
    )


def test_DB_모드_리포트의_숫자가_맞다(db_session: Session, user: User) -> None:
    seed_scenario(db_session, user.id, "evaluated")

    result, payload = _report(db_session, user, RECORD_DAY, SqlTeamActivityReader(db_session))

    stats = result.stats
    assert (stats.record_count, stats.completed_count, stats.incomplete_count) == (3, 3, 0)
    assert stats.total_minutes == 36
    exercise = stats.exercises[0]
    assert (exercise.best_score, exercise.first_score, exercise.last_score) == (80.0, 60.0, 80.0)
    # total_score는 완료 세트 × 세트당 점수(10점)다.
    assert exercise.sets == (
        SetProgress(completed_sets=6, target_sets=10),
        SetProgress(completed_sets=7, target_sets=10),
        SetProgress(completed_sets=8, target_sets=10),
    )
    assert stats.step_attempt_count == 7
    right, left = stats.steps
    assert (right.exercise_step_id, right.attempt_count, right.last_score) == (12, 5, 86.0)
    assert (left.exercise_step_id, left.attempt_count, left.last_score) == (13, 2, 90.0)
    assert (right.pass_count, left.pass_count) == (2, 1)
    assert right.evaluation_counts == {"PASS": 2, "FAIL": 3, "UNAVAILABLE": 0, "NOT_EVALUATED": 0}
    assert right.feedback_code_counts == {"ARMS_NOT_OPEN_ENOUGH": 3, "RIGHT_ARM_TOO_LOW": 1}

    assert result.next_focus is not None and result.next_focus.step_id == 12
    corrections = {
        item["exercise_step_id"]: item["corrections"] for item in payload["focus_candidates"]
    }
    # 스텝 전용 안내가 운동 전용보다 먼저다. message가 빈 스텝 전용 안내(108)는 건너뛰고 103을 쓴다.
    assert corrections[12] == ["팔을 어깨 높이까지 활짝 벌려 주세요.", "오른팔을 조금 더 올려 주세요."]
    # STUDY가 아닌 안내(109, EXERCISE)는 쓰지 않는다.
    assert corrections[13] == ["왼발을 한 걸음 더 옆으로 내밀어 주세요."]

    memos = _feedback(db_session, FEEDBACK_TYPE_STEP)
    assert [memo.exercise_step_records_id for memo in memos] == [15, 17]
    daily = _feedback(db_session, FEEDBACK_TYPE_DAILY)
    assert len(daily) == 1 and daily[0].exercise_step_records_id is None


def test_DB_모드는_일시정지_기록과_측정_불가_스텝을_나눠_센다(
    db_session: Session, user: User
) -> None:
    seed_scenario(db_session, user.id, "evaluated")

    result, payload = _report(db_session, user, MIXED_DAY, SqlTeamActivityReader(db_session))

    stats = result.stats
    assert (stats.record_count, stats.completed_count, stats.incomplete_count) == (2, 1, 1)
    # 일시정지 기록은 ended_at이 없어 운동 시간에서 빠진다.
    assert stats.total_minutes == 12
    assert stats.exercises[0].sets == (
        SetProgress(completed_sets=7, target_sets=10),
        SetProgress(completed_sets=3, target_sets=10),
    )
    assert [(step.exercise_step_id, step.pass_count) for step in stats.steps] == [
        (11, 1),
        (12, 2),
        (13, 0),
    ]
    assert [item["exercise_step_id"] for item in payload["camera_check_steps"]] == [13]


@pytest.mark.parametrize(
    ("scenario", "day"),
    [
        ("evaluated", RECORD_DAY),
        ("evaluated", MIXED_DAY),
        ("not_evaluated_scored", MIXED_DAY),
        ("not_evaluated_unscored", MIXED_DAY),
    ],
)
def test_fixture_모드와_DB_모드는_같은_결과를_낸다(
    db_session: Session, user: User, scenario: str, day: date
) -> None:
    seed_scenario(db_session, user.id, scenario)

    # fixture 모드는 agent_feedback을 읽지도 쓰지도 않아서, 먼저 돌려도 DB 모드에 끼어들지 않는다.
    from_fixture, fixture_payload = _report(
        db_session, user, day, FixtureTeamActivityReader.from_scenario(scenario)
    )
    assert db_session.query(AgentFeedback).count() == 0
    from_db, db_payload = _report(db_session, user, day, SqlTeamActivityReader(db_session))

    assert from_db.stats == from_fixture.stats
    assert db_payload == fixture_payload
    assert from_db.next_focus == from_fixture.next_focus
    assert (from_fixture.saved, from_db.saved) == (False, True)


def test_step_report가_비어_있으면_판정_없음으로_본다(db_session: Session, user: User) -> None:
    seed_scenario(db_session, user.id, "not_evaluated_unscored")
    # 팀 API는 step_report를 보내지 않으면 {}로 저장한다.
    db_session.add(
        ExerciseStepRecord(
            id=70,
            user_id=user.id,
            exercise_id=1,
            exercise_step_id=11,
            status="NON_PASS",
            step_score=Decimal("60.00"),
            step_report={},
            created_at=datetime(2026, 10, 20, 1, 30),
            modified_at=datetime(2026, 10, 20, 1, 30),
        )
    )
    db_session.commit()
    reader = SqlTeamActivityReader(db_session)

    attempt = next(row for row in reader.list_step_records(user.id, MIXED_DAY) if row.id == 70)
    result, _ = _report(db_session, user, MIXED_DAY, reader)

    assert (attempt.evaluation_status, attempt.feedback_codes) == (None, ())
    assert attempt.has_evaluation() is False
    step = next(item for item in result.stats.steps if item.exercise_step_id == 11)
    assert step.evaluation_counts["NOT_EVALUATED"] == 1
    # 판정이 없으니 STEP 메모는 LLM이 아니라 코드가 쓴다.
    memo = next(
        row for row in _feedback(db_session, FEEDBACK_TYPE_STEP) if row.exercise_step_records_id == 70
    )
    assert memo.step_summary == "준비 자세: 1번 시도 중 0번 통과, 60점, 자세 판정 결과 없음"


@pytest.mark.parametrize("source", ["fixture", "db"])
def test_message가_빈_교정_문장은_건너뛴다(
    db_session: Session, user: User, source: str
) -> None:
    seed_scenario(db_session, user.id, "evaluated")
    reader = (
        FixtureTeamActivityReader.from_scenario("evaluated")
        if source == "fixture"
        else SqlTeamActivityReader(db_session)
    )

    cues = reader.get_correction_cues(["RIGHT_ARM_TOO_LOW", "LEFT_ARM_TOO_LOW"], 12, 1)

    # 스텝 전용 안내(108)는 message가 비어 있어 운동 전용 안내(103)로 내려간다.
    assert cues["RIGHT_ARM_TOO_LOW"].message == "오른팔을 조금 더 올려 주세요."
    # 꺼 둔 안내(107)는 처음부터 고르지 않는다.
    assert "LEFT_ARM_TOO_LOW" not in cues


def test_스텝_기록을_지우면_그_STEP_메모만_함께_지워진다(
    db_session: Session, user: User
) -> None:
    # FK 검사는 tests/agent/conftest.py가 SQLite에서도 켜 둔다.
    seed_scenario(db_session, user.id, "evaluated")
    _report(db_session, user, RECORD_DAY, SqlTeamActivityReader(db_session))

    db_session.delete(db_session.get(ExerciseStepRecord, 15))
    db_session.commit()

    # 스텝 12의 메모(15번 기록)만 지워지고, 스텝 13의 메모와 DAILY(번호 없음)는 남는다.
    assert [m.exercise_step_records_id for m in _feedback(db_session, FEEDBACK_TYPE_STEP)] == [17]
    assert len(_feedback(db_session, FEEDBACK_TYPE_DAILY)) == 1
