"""팀 운동 기록 테이블 읽기 전용 계층.

팀 테이블 모양은 develop #15의 팀 모델을 따른다. 실데이터가 없는 개발 환경에서도 돌릴 수 있게
읽는 쪽을 Protocol로 두고, SQL 리더와 fixture 리더를 함께 둔다. 두 리더는 같은 결과를 내야 한다.

- 팀 테이블은 읽기만 한다. 쓰기는 agent_feedback 하나뿐이다. (agent_feedback_repository)
- 팀 모델 클래스는 import하지 않는다. SQLAlchemy text()로 SELECT만 한다.
- step_report에서는 판정에 쓰는 세 값과 버전 두 개만 꺼낸다. measured_metrics와
  metric_results의 수치는 읽지 않는다. (LLM에 보내지 않도록 이 경계에서 버린다)
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from fastapi import Depends
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.clock import KST
from core.errors import AppError
from db.session import get_db
from services.agent import config

# step_report 안에서 읽는 값 (CV 팀 'JSON 스키마 명세서' 8~11절)
TRACKING_STATUS_UNAVAILABLE = "UNAVAILABLE"
EVALUATION_STATUS_NOT_EVALUATED = "NOT_EVALUATED"
EVALUATION_STATUS_PASS = "PASS"
EVALUATION_STATUS_FAIL = "FAIL"
EVALUATION_STATUS_UNAVAILABLE = "UNAVAILABLE"
EVALUATION_STATUSES = (
    EVALUATION_STATUS_PASS,
    EVALUATION_STATUS_FAIL,
    EVALUATION_STATUS_UNAVAILABLE,
    EVALUATION_STATUS_NOT_EVALUATED,
)
# 판정이 실제로 내려진 상태. 이 중 하나거나 피드백 코드가 있으면 '판정 결과가 있다'고 본다.
DECIDED_EVALUATION_STATUSES = (
    EVALUATION_STATUS_PASS,
    EVALUATION_STATUS_FAIL,
    EVALUATION_STATUS_UNAVAILABLE,
)


# --- 날짜 다루기 -------------------------------------------------------------
# '오늘'은 core.clock.today_kst() 기준이다. DB 시각은 팀 규칙대로 naive UTC로 보고,
# KST 하루를 UTC 범위로 바꿔 조회한다.


def kst_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """KST 하루[day 00:00, 다음 날 00:00)를 naive UTC 범위로 바꾼다."""
    start_kst = datetime.combine(day, time.min, tzinfo=KST)
    start_utc = (start_kst - start_kst.utcoffset()).replace(tzinfo=None)
    return start_utc, start_utc + timedelta(days=1)


def kst_day_of(moment: datetime) -> date:
    """naive UTC 시각이 KST로 어느 날짜인지 돌려준다."""
    return (moment + timedelta(hours=9)).date()


def report_date_of(day: date) -> datetime:
    """agent_feedback.report_date에 저장할 값. KST 날짜의 00:00을 naive로 둔다."""
    return datetime.combine(day, time.min)


# --- 읽어 오는 줄 -----------------------------------------------------------


def tracking_unavailable_code() -> str:
    """관절 인식 불가 피드백 코드. rules/feedback_codes.json이 단일 출처다."""
    return str(config.load_rules("feedback_codes")["tracking_unavailable_code"])


@dataclass(frozen=True)
class ExerciseRow:
    """exercises 한 줄."""

    id: int
    exercise_name: str


@dataclass(frozen=True)
class StepRow:
    """exercise_steps 한 줄."""

    id: int
    exercise_id: int
    step_order: int | None
    step_name: str
    step_description: str | None


@dataclass(frozen=True)
class ExerciseRecordRow:
    """exercise_records 한 줄. is_completed와 user_goal은 읽지 않는다."""

    id: int
    exercise_id: int
    exercise_criteria_version_id: int | None
    total_score: float | None
    completed_sets: int | None
    status: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    modified_at: datetime | None


@dataclass(frozen=True)
class StepRecordRow:
    """exercise_step_records 한 줄.

    step_report에서 꺼낸 값만 들고 있고, 관절 수치는 들고 있지 않다.
    """

    id: int
    exercise_id: int
    exercise_step_id: int
    status: str | None
    step_score: float | None
    created_at: datetime
    modified_at: datetime | None
    evaluation_status: str | None
    feedback_codes: tuple[str, ...]
    tracking_status: str | None
    measurement_profile_version: str | None
    criteria_version: str | None

    def is_unavailable(self) -> bool:
        """카메라가 관절을 못 잡아 측정하지 못한 시도인지."""
        return (
            self.evaluation_status == EVALUATION_STATUS_UNAVAILABLE
            or self.tracking_status == TRACKING_STATUS_UNAVAILABLE
            or tracking_unavailable_code() in self.feedback_codes
        )

    def has_evaluation(self) -> bool:
        """판정 결과가 있는 시도인지. 없으면 STEP 메모를 코드가 쓴다."""
        return bool(self.feedback_codes) or (
            self.evaluation_status in DECIDED_EVALUATION_STATUSES
        )


@dataclass(frozen=True)
class StepRecordOwner:
    """스텝 기록 한 건의 주인과 날짜. update_step_memory가 번호만 받고 찾을 때 쓴다."""

    id: int
    user_id: int
    exercise_id: int
    exercise_step_id: int
    created_at: datetime


@dataclass(frozen=True)
class CorrectionCue:
    """voice_cues에서 고른 교정 방법 한 줄('어떻게 고치나')."""

    event_code: str
    message: str


@dataclass(frozen=True)
class DailyStepScore:
    """날짜별·스텝별 점수 요약. 다음에 붙일 기억 꺼내기 도구가 쓴다."""

    exercise_step_id: int
    attempt_count: int
    best_score: float | None
    last_score: float | None
    measurement_profile_version: str | None
    criteria_version: str | None


@dataclass(frozen=True)
class DailyScoreRow:
    """하루 요약 한 줄."""

    day: date
    record_count: int
    exercise_criteria_version_ids: tuple[int | None, ...]
    steps: tuple[DailyStepScore, ...]


# --- 값 다듬기 --------------------------------------------------------------


def _score(value: Any) -> float | None:
    """점수를 float으로 바꾼다. 없거나 범위를 벗어나면 None으로 둔다."""
    if value is None:
        return None
    number = float(value) if isinstance(value, (int, float, Decimal, str)) else None
    if number is None or not config.SCORE_MIN <= number <= config.SCORE_MAX:
        return None
    return number


def _count(value: Any) -> int | None:
    """완료 세트 수를 int로 바꾼다. 없거나 음수면 None으로 둔다."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _moment(value: Any) -> datetime | None:
    """DB·fixture의 시각 값을 naive datetime으로 바꾼다."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    return datetime.fromisoformat(str(value)).replace(tzinfo=None)


def _step_report_fields(raw: Any) -> dict[str, Any]:
    """step_report에서 판정 세 값과 버전 두 개만 꺼낸다.

    measured_metrics와 metric_results는 읽지 않는다. criteria_version은 지금 CV 명세의
    사용자 JSON에 없어서 보통 None이다.
    없거나({}·None) 깨진 step_report는 판정 없음으로 본다. 팀 API는 step_report를 비우면
    {}로 저장한다. (develop #9 기준: schemas/exercise_step_record.py)
    """
    if raw is None:
        report: Any = {}
    elif isinstance(raw, (str, bytes, bytearray)):
        try:
            report = json.loads(raw)
        except (ValueError, TypeError):
            report = {}
    else:
        report = raw
    if not isinstance(report, dict) or not report:
        return {
            "evaluation_status": None,
            "feedback_codes": (),
            "tracking_status": None,
            "measurement_profile_version": None,
            "criteria_version": None,
        }

    evaluation = report.get("evaluation_result") or {}
    tracking = report.get("tracking_info") or {}
    codes = evaluation.get("feedback_codes") or []
    return {
        "evaluation_status": evaluation.get("status"),
        "feedback_codes": tuple(str(code) for code in codes),
        "tracking_status": tracking.get("tracking_status"),
        "measurement_profile_version": report.get("measurement_profile_version"),
        "criteria_version": report.get("criteria_version"),
    }


def _build_exercise_record(row: dict[str, Any]) -> ExerciseRecordRow:
    return ExerciseRecordRow(
        id=int(row["id"]),
        exercise_id=int(row["exercise_id"]),
        exercise_criteria_version_id=(
            None
            if row.get("exercise_criteria_version_id") is None
            else int(row["exercise_criteria_version_id"])
        ),
        total_score=_score(row.get("total_score")),
        completed_sets=_count(row.get("completed_sets")),
        status=row.get("status"),
        started_at=_moment(row.get("started_at")),
        ended_at=_moment(row.get("ended_at")),
        created_at=_moment(row["created_at"]),
        modified_at=_moment(row.get("modified_at")),
    )


def _build_step_record(row: dict[str, Any]) -> StepRecordRow:
    fields = _step_report_fields(row.get(config.STEP_REPORT_COLUMN))
    return StepRecordRow(
        id=int(row["id"]),
        exercise_id=int(row["exercise_id"]),
        exercise_step_id=int(row["exercise_step_id"]),
        status=row.get("status"),
        step_score=_score(row.get("step_score")),
        created_at=_moment(row["created_at"]),
        modified_at=_moment(row.get("modified_at")),
        **fields,
    )


def _pick_cues(
    rows: list[dict[str, Any]], exercise_step_id: int, exercise_id: int
) -> dict[str, CorrectionCue]:
    """event_code별로 하나만 고른다. 그 스텝 전용 → 그 운동 전용 → 모드 공통 순이다.

    message가 비어 있는 안내는 교정 문장으로 쓸 수 없어 건너뛴다. 그러면 다음 순위 안내가 쓰인다.
    """

    def rank(row: dict[str, Any]) -> int:
        if row.get("exercise_step_id") == exercise_step_id:
            return 0
        if row.get("exercise_id") == exercise_id and row.get("exercise_step_id") is None:
            return 1
        return 2

    chosen: dict[str, tuple[int, CorrectionCue]] = {}
    for row in rows:
        if not (row.get("message") or "").strip():
            continue
        code = str(row["event_code"])
        candidate = (rank(row), CorrectionCue(event_code=code, message=row["message"]))
        if code not in chosen or candidate[0] < chosen[code][0]:
            chosen[code] = candidate
    return {code: cue for code, (_, cue) in chosen.items()}


def _group_daily(
    records: list[ExerciseRecordRow], step_records: list[StepRecordRow]
) -> list[DailyScoreRow]:
    """날짜(KST)별로 묶는다."""
    days = sorted(
        {kst_day_of(record.created_at) for record in records}
        | {kst_day_of(step.created_at) for step in step_records}
    )
    rows: list[DailyScoreRow] = []
    for day in days:
        day_records = [r for r in records if kst_day_of(r.created_at) == day]
        day_steps = [s for s in step_records if kst_day_of(s.created_at) == day]
        by_step: dict[int, list[StepRecordRow]] = {}
        for step in day_steps:
            by_step.setdefault(step.exercise_step_id, []).append(step)
        step_scores = []
        for step_id, attempts in sorted(by_step.items()):
            attempts = sorted(attempts, key=lambda item: (item.created_at, item.id))
            scores = [a.step_score for a in attempts if a.step_score is not None]
            # 버전은 마지막 시도 기준이다. 하루 안에서 버전이 바뀌면 마지막 값을 쓴다.
            step_scores.append(
                DailyStepScore(
                    exercise_step_id=step_id,
                    attempt_count=len(attempts),
                    best_score=max(scores) if scores else None,
                    last_score=scores[-1] if scores else None,
                    measurement_profile_version=attempts[-1].measurement_profile_version,
                    criteria_version=attempts[-1].criteria_version,
                )
            )
        rows.append(
            DailyScoreRow(
                day=day,
                record_count=len(day_records),
                exercise_criteria_version_ids=tuple(
                    dict.fromkeys(r.exercise_criteria_version_id for r in day_records)
                ),
                steps=tuple(step_scores),
            )
        )
    return rows


# --- 읽는 쪽 ----------------------------------------------------------------


class TeamActivityReader(Protocol):
    """팀 운동 기록을 읽는 방법. SQL 리더와 fixture 리더가 같은 모양을 따른다."""

    # 팀 DB의 실제 기록이면 True다. 에이전트는 실제 기록일 때만 agent_feedback을 읽고 쓴다.
    # (가짜 기록으로 만든 메모·리포트가 실제 사용자 계정에 쌓이지 않게 하고, STEP 메모의
    #  exercise_step_records_id FK가 DB에 없는 가짜 기록 번호를 가리키지 않게 한다)
    real_records: bool

    def list_exercise_records(
        self, user_id: int, day: date
    ) -> list[ExerciseRecordRow]: ...

    def list_step_records(self, user_id: int, day: date) -> list[StepRecordRow]: ...

    def get_step_record(self, step_record_id: int) -> StepRecordOwner | None: ...

    def get_steps(self, step_ids: list[int]) -> list[StepRow]: ...

    def get_exercises(self, ids: list[int]) -> list[ExerciseRow]: ...

    def get_correction_cues(
        self, event_codes: list[str], exercise_step_id: int, exercise_id: int
    ) -> dict[str, CorrectionCue]: ...

    def list_daily_scores(
        self, user_id: int, start_day: date, end_day: date
    ) -> list[DailyScoreRow]: ...


class SqlTeamActivityReader:
    """팀 MySQL 테이블을 SELECT만 한다. 테이블이 없으면 503 AGENT_DATA_UNAVAILABLE."""

    real_records = True

    def __init__(self, db: Session) -> None:
        self._db = db

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        statement = text(sql)
        for name, value in params.items():
            if isinstance(value, (list, tuple)):
                statement = statement.bindparams(bindparam(name, expanding=True))
        try:
            result = self._db.execute(statement, params)
            return [dict(row) for row in result.mappings()]
        except SQLAlchemyError as error:
            # 팀 테이블이 없거나 모양이 다르면 에이전트만 503으로 막고 팀 서버는 살려 둔다.
            self._db.rollback()
            raise AppError(
                503,
                "AGENT_DATA_UNAVAILABLE",
                "운동 기록을 읽을 수 없어 리포트를 만들지 못했어요.",
            ) from error

    def list_exercise_records(self, user_id: int, day: date) -> list[ExerciseRecordRow]:
        start, end = kst_day_bounds_utc(day)
        rows = self._rows(
            """
            SELECT id, exercise_id, exercise_criteria_version_id, total_score,
                   completed_sets, status, started_at, ended_at, created_at, modified_at
              FROM exercise_records
             WHERE user_id = :user_id
               AND created_at >= :start AND created_at < :end
             ORDER BY created_at, id
            """,
            {"user_id": user_id, "start": start, "end": end},
        )
        return [_build_exercise_record(row) for row in rows]

    def list_step_records(self, user_id: int, day: date) -> list[StepRecordRow]:
        start, end = kst_day_bounds_utc(day)
        rows = self._rows(
            f"""
            SELECT id, exercise_id, exercise_step_id, step_result_status AS status, step_score,
                   {config.STEP_REPORT_COLUMN}, created_at, modified_at
              FROM exercise_step_records
             WHERE user_id = :user_id
               AND created_at >= :start AND created_at < :end
             ORDER BY created_at, id
            """,
            {"user_id": user_id, "start": start, "end": end},
        )
        return [_build_step_record(row) for row in rows]

    def get_step_record(self, step_record_id: int) -> StepRecordOwner | None:
        rows = self._rows(
            """
            SELECT id, user_id, exercise_id, exercise_step_id, created_at
              FROM exercise_step_records
             WHERE id = :id
            """,
            {"id": step_record_id},
        )
        if not rows:
            return None
        row = rows[0]
        return StepRecordOwner(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            exercise_id=int(row["exercise_id"]),
            exercise_step_id=int(row["exercise_step_id"]),
            created_at=_moment(row["created_at"]),
        )

    def get_steps(self, step_ids: list[int]) -> list[StepRow]:
        if not step_ids:
            return []
        rows = self._rows(
            """
            SELECT id, exercise_id, step_order, step_name, step_description
              FROM exercise_steps
             WHERE id IN :ids
             ORDER BY exercise_id, step_order, id
            """,
            {"ids": list(step_ids)},
        )
        return [
            StepRow(
                id=int(row["id"]),
                exercise_id=int(row["exercise_id"]),
                step_order=row.get("step_order"),
                step_name=row["step_name"],
                step_description=row.get("step_description"),
            )
            for row in rows
        ]

    def get_exercises(self, ids: list[int]) -> list[ExerciseRow]:
        if not ids:
            return []
        rows = self._rows(
            """
            SELECT id, exercise_name
              FROM exercises
             WHERE id IN :ids
             ORDER BY id
            """,
            {"ids": list(ids)},
        )
        return [
            ExerciseRow(
                id=int(row["id"]),
                exercise_name=row["exercise_name"],
            )
            for row in rows
        ]

    def get_correction_cues(
        self, event_codes: list[str], exercise_step_id: int, exercise_id: int
    ) -> dict[str, CorrectionCue]:
        if not event_codes:
            return {}
        # 팀의 STUDY 조회 범위와 같다: 전체 공통 + 운동별 공통 + 스텝별 안내.
        # (develop #9 기준: repositories/voice_cue_repository.py의 list_active_by_scope)
        rows = self._rows(
            """
            SELECT event_code, message, exercise_step_id, exercise_id
              FROM voice_cues
             WHERE is_active = :is_active
               AND category = :category
               AND event_code IN :codes
               AND (exercise_id = :exercise_id OR exercise_id IS NULL)
               AND (exercise_step_id = :step_id OR exercise_step_id IS NULL)
            """,
            {
                "is_active": True,
                "category": config.VOICE_CUE_CATEGORY_STUDY,
                "codes": list(event_codes),
                "step_id": exercise_step_id,
                "exercise_id": exercise_id,
            },
        )
        return _pick_cues(rows, exercise_step_id, exercise_id)

    def list_daily_scores(
        self, user_id: int, start_day: date, end_day: date
    ) -> list[DailyScoreRow]:
        start, _ = kst_day_bounds_utc(start_day)
        _, end = kst_day_bounds_utc(end_day)
        record_rows = self._rows(
            """
            SELECT id, exercise_id, exercise_criteria_version_id, total_score,
                   completed_sets, status, started_at, ended_at, created_at, modified_at
              FROM exercise_records
             WHERE user_id = :user_id
               AND created_at >= :start AND created_at < :end
             ORDER BY created_at, id
            """,
            {"user_id": user_id, "start": start, "end": end},
        )
        step_rows = self._rows(
            f"""
            SELECT id, exercise_id, exercise_step_id, step_result_status AS status, step_score,
                   {config.STEP_REPORT_COLUMN}, created_at, modified_at
              FROM exercise_step_records
             WHERE user_id = :user_id
               AND created_at >= :start AND created_at < :end
             ORDER BY created_at, id
            """,
            {"user_id": user_id, "start": start, "end": end},
        )
        return _group_daily(
            [_build_exercise_record(row) for row in record_rows],
            [_build_step_record(row) for row in step_rows],
        )


class FixtureTeamActivityReader:
    """services/agent/fixtures/의 가짜 기록을 읽는다.

    fixture 모드에서는 로그인한 사용자와 상관없이 데모 기록을 쓴다. 임신 주차와 동의 같은
    사용자 정보는 서비스가 실제 users에서 읽는다. agent_feedback은 읽지도 쓰지도 않는다.
    """

    real_records = False

    def __init__(self, catalog: dict[str, Any], scenario: dict[str, Any]) -> None:
        self._exercises = catalog["exercises"]
        self._steps = catalog["exercise_steps"]
        self._cues = catalog["voice_cues"]
        self._records = scenario.get("exercise_records", [])
        self._step_records = scenario.get("exercise_step_records", [])

    @classmethod
    def from_scenario(cls, scenario: str | None = None) -> "FixtureTeamActivityReader":
        name = scenario or config.fixture_scenario()
        directory: Path = config.FIXTURES_DIR
        catalog = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
        path = directory / f"scenario_{name}.json"
        if not path.exists():
            raise AppError(
                503,
                "AGENT_DATA_UNAVAILABLE",
                "에이전트 데모 기록을 찾을 수 없어 리포트를 만들지 못했어요.",
            )
        return cls(catalog, json.loads(path.read_text(encoding="utf-8")))

    def list_exercise_records(self, user_id: int, day: date) -> list[ExerciseRecordRow]:
        rows = [_build_exercise_record(row) for row in self._records]
        return sorted(
            (row for row in rows if kst_day_of(row.created_at) == day),
            key=lambda row: (row.created_at, row.id),
        )

    def list_step_records(self, user_id: int, day: date) -> list[StepRecordRow]:
        rows = [_build_step_record(row) for row in self._step_records]
        return sorted(
            (row for row in rows if kst_day_of(row.created_at) == day),
            key=lambda row: (row.created_at, row.id),
        )

    def get_step_record(self, step_record_id: int) -> StepRecordOwner | None:
        for row in self._step_records:
            if int(row["id"]) == step_record_id:
                return StepRecordOwner(
                    id=int(row["id"]),
                    user_id=int(row["user_id"]),
                    exercise_id=int(row["exercise_id"]),
                    exercise_step_id=int(row["exercise_step_id"]),
                    created_at=_moment(row["created_at"]),
                )
        return None

    def get_steps(self, step_ids: list[int]) -> list[StepRow]:
        wanted = set(step_ids)
        return [
            StepRow(
                id=int(row["id"]),
                exercise_id=int(row["exercise_id"]),
                step_order=row.get("step_order"),
                step_name=row["step_name"],
                step_description=row.get("step_description"),
            )
            for row in self._steps
            if int(row["id"]) in wanted
        ]

    def get_exercises(self, ids: list[int]) -> list[ExerciseRow]:
        wanted = set(ids)
        return [
            ExerciseRow(
                id=int(row["id"]),
                exercise_name=row["exercise_name"],
            )
            for row in self._exercises
            if int(row["id"]) in wanted
        ]

    def get_correction_cues(
        self, event_codes: list[str], exercise_step_id: int, exercise_id: int
    ) -> dict[str, CorrectionCue]:
        wanted = set(event_codes)
        rows = [
            row
            for row in self._cues
            if row.get("is_active")
            and row.get("category") == config.VOICE_CUE_CATEGORY_STUDY
            and row.get("event_code") in wanted
            and row.get("exercise_id") in (exercise_id, None)
            and row.get("exercise_step_id") in (exercise_step_id, None)
        ]
        return _pick_cues(rows, exercise_step_id, exercise_id)

    def list_daily_scores(
        self, user_id: int, start_day: date, end_day: date
    ) -> list[DailyScoreRow]:
        records = [
            row
            for row in (_build_exercise_record(item) for item in self._records)
            if start_day <= kst_day_of(row.created_at) <= end_day
        ]
        steps = [
            row
            for row in (_build_step_record(item) for item in self._step_records)
            if start_day <= kst_day_of(row.created_at) <= end_day
        ]
        return _group_daily(records, steps)


def build_team_activity_reader(db: Session) -> TeamActivityReader:
    """AGENT_DATA_SOURCE에 맞는 리더를 만든다. FastAPI 밖에서도 쓴다."""
    if config.data_source() == "db":
        return SqlTeamActivityReader(db)
    return FixtureTeamActivityReader.from_scenario()


def get_team_activity_reader(db: Session = Depends(get_db)) -> TeamActivityReader:
    """라우터용 의존성. 테스트는 dependency_overrides로 fixture 리더를 끼운다."""
    return build_team_activity_reader(db)

