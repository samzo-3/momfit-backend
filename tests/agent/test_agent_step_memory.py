"""STEP 기억 쓰기 검사. 가짜 LLM과 가짜 팀 테이블 리더를 쓴다."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models.agent.agent_feedback import FEEDBACK_TYPE_STEP, AgentFeedback
from models.exercise import Exercise
from models.exercise_step import ExerciseStep
from models.exercise_step_record import ExerciseStepRecord
from models.user import User
from repositories.agent.team_activity_reader import (
    FixtureTeamActivityReader,
    StepRecordOwner,
    StepRecordRow,
    StepRow,
)
from services.agent import step_memory
from services.agent.llm import LlmError, Usage
from services.agent.step_memory import refresh_step_memories, update_step_memory

DAY = date(2026, 10, 19)
BASE = datetime(2026, 10, 19, 1, 0)  # KST 10:00
PROFILE = "side_step_front_2d_v1"


class FakeLlm:
    """부른 입력을 모아 두고 미리 정한 답을 돌려주는 가짜 제공자."""

    name = "fake"
    model = "fake-1"

    def __init__(self, responses: list[str] | None = None, error: Exception | None = None):
        self.calls: list[dict] = []
        self._responses = list(responses or [])
        self._error = error

    def generate(self, system_prompt: str, user_message: str, timeout: float):
        self.calls.append(
            {"system": system_prompt, "user": user_message, "timeout": timeout}
        )
        if self._error is not None:
            raise self._error
        text = self._responses.pop(0) if self._responses else "[]"
        return text, Usage(input_tokens=10, output_tokens=20)


class StubReader:
    """팀 테이블 대신 메모리 목록을 읽는다. 실제 기록처럼 다뤄 메모를 저장한다."""

    real_records = True

    def __init__(self, step_records: list[StepRecordRow], steps: list[StepRow], user_id: int = 1):
        self.step_records = step_records
        self.steps = steps
        self.user_id = user_id

    def list_exercise_records(self, user_id, day):
        return []

    def list_step_records(self, user_id, day):
        return [row for row in self.step_records if row.created_at.date() == day]

    def get_step_record(self, step_record_id):
        for row in self.step_records:
            if row.id == step_record_id:
                return StepRecordOwner(
                    id=row.id,
                    user_id=self.user_id,
                    exercise_id=row.exercise_id,
                    exercise_step_id=row.exercise_step_id,
                    created_at=row.created_at,
                )
        return None

    def get_steps(self, step_ids):
        wanted = set(step_ids)
        return [row for row in self.steps if row.id in wanted]

    def get_exercises(self, ids):
        return []

    def get_correction_cues(self, event_codes, exercise_step_id, exercise_id):
        return {}

    def list_daily_scores(self, user_id, start_day, end_day):
        return []


def _attempt(
    rid: int,
    step_id: int,
    *,
    score: float | None = 60.0,
    status: str | None = "FAIL",
    codes: tuple[str, ...] = ("ARMS_NOT_OPEN_ENOUGH",),
    modified_minutes: int | None = None,
    record_status: str = "NON_PASS",
) -> StepRecordRow:
    created = BASE + timedelta(minutes=rid)
    return StepRecordRow(
        id=rid,
        exercise_id=1,
        exercise_step_id=step_id,
        status=record_status,
        step_score=score,
        created_at=created,
        modified_at=created
        if modified_minutes is None
        else created + timedelta(minutes=modified_minutes),
        evaluation_status=status,
        feedback_codes=codes,
        tracking_status="VALID",
        measurement_profile_version=PROFILE,
        criteria_version=None,
    )


STEPS = [
    StepRow(id=12, exercise_id=1, step_order=2, step_name="오른쪽 스텝", step_description="설명"),
    StepRow(id=13, exercise_id=1, step_order=3, step_name="왼쪽 스텝", step_description="설명"),
]


@pytest.fixture()
def user(db_session: Session) -> User:
    row = User(nickname="맘핏", email="mom@example.com", onboarding_completed=True)
    db_session.add(row)
    # 메모가 가리킬 스텝 기록(_store)이 기대는 운동과 스텝
    db_session.add(Exercise(id=1, exercise_name="사이드 스텝", video_url="/media/guide.mp4"))
    db_session.flush()
    db_session.add_all(
        ExerciseStep(
            id=step.id,
            exercise_id=1,
            step_order=step.step_order,
            step_name=step.step_name,
            clip_video_url="/media/step.mp4",
        )
        for step in STEPS
    )
    db_session.commit()
    return row


def _store(db: Session, user: User, attempts: list[StepRecordRow]) -> None:
    """메모의 exercise_step_records_id FK가 가리킬 스텝 기록을 팀 모델로 넣는다. 이미 있으면 넘어간다.

    이 파일의 검사는 시도를 리더 없이 바로 넘기므로, 넣는 행은 FK를 채우는 용도일 뿐이다.
    """
    for attempt in attempts:
        if db.get(ExerciseStepRecord, attempt.id) is not None:
            continue
        db.add(
            ExerciseStepRecord(
                id=attempt.id,
                user_id=user.id,
                exercise_id=attempt.exercise_id,
                exercise_step_id=attempt.exercise_step_id,
                status=attempt.status,
                step_score=None if attempt.step_score is None else Decimal(str(attempt.step_score)),
                step_report={},
                created_at=attempt.created_at,
                modified_at=attempt.modified_at or attempt.created_at,
            )
        )
    db.flush()


def _memos(db: Session) -> list[AgentFeedback]:
    return (
        db.query(AgentFeedback)
        .filter(AgentFeedback.feedback_type == FEEDBACK_TYPE_STEP)
        .order_by(AgentFeedback.id)
        .all()
    )


def _refresh(db: Session, user: User, attempts, llm, memos=None, save=True):
    from repositories.agent import agent_feedback_repository
    from repositories.agent.team_activity_reader import report_date_of

    _store(db, user, attempts)
    return refresh_step_memories(
        db,
        user_id=user.id,
        day=DAY,
        step_records=attempts,
        steps=STEPS,
        memos=memos
        if memos is not None
        else agent_feedback_repository.list_step_memos(db, user.id, report_date_of(DAY)),
        llm=llm,
        save=save,
    )


def test_같은_스텝을_여러_번_시도해도_오늘_메모는_하나다(
    db_session: Session, user: User
) -> None:
    attempts = [_attempt(rid, 12, score=50.0 + rid) for rid in range(1, 6)]
    llm = FakeLlm(['[{"exercise_step_id": 12, "memo": "오른쪽 스텝: 5번 중 3번 양팔 벌림 부족"}]'])

    outcome = _refresh(db_session, user, attempts, llm)
    db_session.commit()

    rows = _memos(db_session)
    assert len(rows) == 1
    # 메모가 어느 시도까지 반영했는지 알려 주는 표시는 오늘 마지막 시도 번호다.
    assert rows[0].exercise_step_records_id == 5
    assert rows[0].report_date == datetime(2026, 10, 19, 0, 0)
    assert outcome.memos[12] == "오른쪽 스텝: 5번 중 3번 양팔 벌림 부족"


def test_판정_결과가_없는_스텝은_LLM을_부르지_않고_코드가_쓴다(
    db_session: Session, user: User
) -> None:
    attempts = [
        _attempt(1, 12, score=52.0, status="NOT_EVALUATED", codes=()),
        _attempt(2, 12, score=88.0, status="NOT_EVALUATED", codes=(), record_status="PASS"),
    ]
    llm = FakeLlm()

    outcome = _refresh(db_session, user, attempts, llm)
    db_session.commit()

    assert llm.calls == []
    assert outcome.llm_calls == 0
    # 통과 횟수는 스텝 기록 status(PASS)를 센 것이다. CV 판정이 없어도 셀 수 있다.
    assert outcome.memos[12] == (
        "오른쪽 스텝: 2번 시도 중 1번 통과, 52점에서 88점, 자세 판정 결과 없음"
    )


def test_점수도_판정도_없으면_점수_없음으로_쓴다(db_session: Session, user: User) -> None:
    attempts = [
        _attempt(
            1, 12, score=None, status="NOT_EVALUATED", codes=(), record_status="NOT_EVALUATED"
        )
    ]

    outcome = _refresh(db_session, user, attempts, FakeLlm())

    assert outcome.memos[12] == "오른쪽 스텝: 1번 시도 중 0번 통과, 점수 없음, 자세 판정 결과 없음"


def test_메모가_최신이면_다시_쓰지_않는다(db_session: Session, user: User) -> None:
    attempts = [_attempt(1, 12)]
    llm = FakeLlm(['[{"exercise_step_id": 12, "memo": "첫 메모"}]'])
    _refresh(db_session, user, attempts, llm)
    db_session.commit()

    again = FakeLlm(['[{"exercise_step_id": 12, "memo": "두 번째 메모"}]'])
    outcome = _refresh(db_session, user, attempts, again)
    db_session.commit()

    assert again.calls == []
    assert outcome.refreshed_step_ids == ()
    assert len(_memos(db_session)) == 1
    assert outcome.memos[12] == "첫 메모"


def test_새_시도가_생기면_그_스텝만_갱신한다(db_session: Session, user: User) -> None:
    attempts = [_attempt(1, 12), _attempt(2, 13)]
    first = FakeLlm(
        [
            '[{"exercise_step_id": 12, "memo": "12 첫 메모"},'
            ' {"exercise_step_id": 13, "memo": "13 첫 메모"}]'
        ]
    )
    _refresh(db_session, user, attempts, first)
    db_session.commit()

    attempts.append(_attempt(3, 12, score=70.0))
    second = FakeLlm(['[{"exercise_step_id": 12, "memo": "12 새 메모"}]'])
    outcome = _refresh(db_session, user, attempts, second)
    db_session.commit()

    sent = json.loads(second.calls[0]["user"])
    assert [step["exercise_step_id"] for step in sent["steps"]] == [12]
    assert outcome.refreshed_step_ids == (12,)
    assert outcome.memos[12] == "12 새 메모"
    assert outcome.memos[13] == "13 첫 메모"


def test_번호가_같아도_수정_시각이_메모보다_늦으면_갱신한다(
    db_session: Session, user: User
) -> None:
    attempts = [_attempt(1, 12)]
    _refresh(db_session, user, attempts, FakeLlm(['[{"exercise_step_id": 12, "memo": "첫 메모"}]']))
    # 메모는 그 운동 세션 중에 쓰였다. (created_at 기본값은 '지금'이라 시도 시각과 맞춰 둔다)
    _memos(db_session)[0].created_at = BASE + timedelta(minutes=5)
    db_session.commit()

    # 같은 행에 점수와 판정이 나중에 채워지면 번호는 그대로인데 메모만 낡는다.
    later = [_attempt(1, 12, score=80.0, modified_minutes=600)]
    llm = FakeLlm(['[{"exercise_step_id": 12, "memo": "채워진 뒤 메모"}]'])
    outcome = _refresh(db_session, user, later, llm)
    db_session.commit()

    assert len(llm.calls) == 1
    assert outcome.memos[12] == "채워진 뒤 메모"
    assert len(_memos(db_session)) == 2


def test_여러_스텝을_묶어도_LLM은_한_번만_부른다(db_session: Session, user: User) -> None:
    attempts = [_attempt(1, 12), _attempt(2, 13)]
    llm = FakeLlm(
        [
            '[{"exercise_step_id": 12, "memo": "12 메모"},'
            ' {"exercise_step_id": 13, "memo": "13 메모"}]'
        ]
    )

    outcome = _refresh(db_session, user, attempts, llm)
    db_session.commit()

    assert len(llm.calls) == 1
    assert outcome.llm_calls == 1
    assert len(_memos(db_session)) == 2


def test_보내지_않은_스텝이나_건강_단어가_든_메모는_저장하지_않는다(
    db_session: Session, user: User
) -> None:
    attempts = [_attempt(1, 12), _attempt(2, 13)]
    llm = FakeLlm(
        [
            '[{"exercise_step_id": 12, "memo": "배가 아프다고 하셨어요"},'
            ' {"exercise_step_id": 99, "memo": "보내지 않은 스텝"},'
            ' {"exercise_step_id": 13, "memo": "13 메모"}]'
        ]
    )

    outcome = _refresh(db_session, user, attempts, llm)
    db_session.commit()

    assert outcome.memos == {13: "13 메모"}
    assert [row.step_summary for row in _memos(db_session)] == ["13 메모"]
    assert len(outcome.failures) == 2


def test_LLM_입력에_측정_수치와_교정_문장이_들어가지_않는다(
    db_session: Session, user: User
) -> None:
    attempts = [_attempt(1, 12)]
    llm = FakeLlm(['[{"exercise_step_id": 12, "memo": "메모"}]'])

    _refresh(db_session, user, attempts, llm)

    sent = llm.calls[0]["user"]
    assert "measured_metrics" not in sent
    assert "metric_results" not in sent
    assert "right_shoulder_angle" not in sent
    # 상태 설명('무엇이 부족했나')만 보낸다. 교정 방법(voice_cues)은 보내지 않는다.
    assert "양팔 벌림 부족" in sent
    assert "벌려 주세요" not in sent


def test_save가_False면_메모를_돌려주기만_하고_저장하지_않는다(
    db_session: Session, user: User
) -> None:
    attempts = [_attempt(1, 12), _attempt(2, 13, status="NOT_EVALUATED", codes=())]
    llm = FakeLlm(['[{"exercise_step_id": 12, "memo": "12 메모"}]'])

    outcome = _refresh(db_session, user, attempts, llm, save=False)
    db_session.commit()

    assert outcome.memos == {
        12: "12 메모",
        13: "왼쪽 스텝: 1번 시도 중 0번 통과, 60점, 자세 판정 결과 없음",
    }
    assert _memos(db_session) == []


def test_LLM_호출이_실패하면_메모를_저장하지_않고_넘어간다(
    db_session: Session, user: User
) -> None:
    attempts = [_attempt(1, 12)]
    llm = FakeLlm(error=LlmError("호출 실패"))

    outcome = _refresh(db_session, user, attempts, llm)
    db_session.commit()

    assert _memos(db_session) == []
    assert outcome.memos == {}
    assert outcome.failures == ("호출 실패",)


class _SessionContext:
    """update_step_memory가 자체 세션 대신 테스트 세션을 쓰도록 하는 SessionLocal 대역."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __call__(self) -> "_SessionContext":
        return self

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *_args: object) -> None:
        return None


def test_update_step_memory는_자기_연결을_연다(
    db_session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = [_attempt(1, 12), _attempt(2, 12, score=70.0)]
    _store(db_session, user, attempts)
    db_session.commit()
    reader = StubReader(attempts, STEPS, user_id=user.id)
    llm = FakeLlm(['[{"exercise_step_id": 12, "memo": "배경 작업 메모"}]'])
    monkeypatch.setattr("db.session.SessionLocal", _SessionContext(db_session))
    monkeypatch.setattr(step_memory, "build_team_activity_reader", lambda db: reader)
    monkeypatch.setattr(step_memory, "build_llm_client", lambda: llm)

    update_step_memory(2)

    rows = _memos(db_session)
    assert [row.step_summary for row in rows] == ["배경 작업 메모"]
    assert rows[0].exercise_step_records_id == 2
    assert rows[0].user_id == user.id


def test_update_step_memory는_가짜_기록_모드에서_아무것도_쓰지_않는다(
    db_session: Session, user: User, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm = FakeLlm(['[{"exercise_step_id": 12, "memo": "쓰면 안 되는 메모"}]'])
    monkeypatch.setattr("db.session.SessionLocal", _SessionContext(db_session))
    monkeypatch.setattr(
        step_memory,
        "build_team_activity_reader",
        lambda db: FixtureTeamActivityReader.from_scenario("evaluated"),
    )
    monkeypatch.setattr(step_memory, "build_llm_client", lambda: llm)

    with caplog.at_level("INFO"):
        update_step_memory(15)

    assert llm.calls == []
    assert _memos(db_session) == []
    assert "15" in caplog.text


def test_update_step_memory는_예외를_밖으로_던지지_않고_번호를_로그에_남긴다(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def explode(db):
        raise RuntimeError("읽기 실패")

    monkeypatch.setattr("db.session.SessionLocal", _SessionContext(db_session))
    monkeypatch.setattr(step_memory, "build_team_activity_reader", explode)

    with caplog.at_level("ERROR"):
        update_step_memory(777)

    assert "777" in caplog.text


def test_update_step_memory는_없는_기록_번호를_받으면_조용히_넘어간다(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("db.session.SessionLocal", _SessionContext(db_session))
    monkeypatch.setattr(
        step_memory, "build_team_activity_reader", lambda db: StubReader([], STEPS)
    )

    with caplog.at_level("WARNING"):
        update_step_memory(404)

    assert "404" in caplog.text
    assert _memos(db_session) == []
