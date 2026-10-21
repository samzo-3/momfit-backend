"""오늘의 운동 리포트 요청·응답 형식."""

# 필드 이름이 date여서 datetime.date를 모듈째로 쓴다.
# (class 안에서 date = None이 먼저 묶여 date | None이 깨진다)
import datetime

from pydantic import BaseModel, ConfigDict


class DailyReportRequest(BaseModel):
    """POST /api/agent/daily-report 요청. date를 비우면 오늘(KST)이다."""

    model_config = ConfigDict(extra="forbid")

    date: datetime.date | None = None


class ExerciseSummaryResponse(BaseModel):
    """일반 운동 하나의 오늘 요약."""

    model_config = ConfigDict(from_attributes=True)

    exercise_id: int
    exercise_name: str
    target_reps: int | None
    record_count: int
    best_score: float | None
    first_score: float | None
    last_score: float | None


class StepSummaryResponse(BaseModel):
    """자세 배우기 스텝 하나의 오늘 요약."""

    model_config = ConfigDict(from_attributes=True)

    exercise_step_id: int
    step_name: str
    attempt_count: int
    best_score: float | None
    last_score: float | None
    evaluation_counts: dict[str, int]
    feedback_code_counts: dict[str, int]


class StatsResponse(BaseModel):
    """오늘 하루 숫자. 모두 코드가 팀 테이블에서 계산한 값이다."""

    model_config = ConfigDict(from_attributes=True)

    exercise_count: int
    record_count: int
    completed_count: int
    incomplete_count: int
    total_minutes: int
    exercises: list[ExerciseSummaryResponse]
    step_attempt_count: int
    steps: list[StepSummaryResponse]
    pregnancy_week: int | None


class NextFocusResponse(BaseModel):
    """다음 집중 스텝. 후보가 없으면 응답에서 null이다."""

    model_config = ConfigDict(from_attributes=True)

    step_id: int
    reason: str


class DailyReportResponse(BaseModel):
    """POST /api/agent/daily-report 응답.

    LLM을 아예 부르지 않았으면 prompt_version·provider·model·latency_ms가 null이다.
    대체 문장을 쓴 이유는 응답에 넣지 않는다. (서버 로그와 시나리오 실행 기록에만 남는다)
    """

    model_config = ConfigDict(from_attributes=True)

    date: datetime.date
    stats: StatsResponse
    safety_notice: str
    summary: str
    next_focus: NextFocusResponse | None
    prompt_version: str | None
    provider: str | None
    model: str | None
    latency_ms: int | None
