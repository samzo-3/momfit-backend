"""에이전트 시나리오 실행기.

    python -m scripts.agent.run_scenarios

현재 .env의 LLM 제공자로 가짜 기록 시나리오를 돌려 "시나리오 | 기대 | 실제 | 일치 | summary" 표를
보여 주고, services/agent/runs/{날짜시각}_{제공자}.md에 실행 기록을 남긴다.

- 팀 DB를 건드리지 않는다. 시나리오마다 메모리 SQLite를 새로 만들어 쓴다.
- 기록은 AGENT_DATA_SOURCE와 상관없이 services/agent/fixtures를 쓴다.
- provider, model, 프롬프트 버전, latency_ms, 토큰 수는 DB에 저장하지 않고 이 파일에만 남는다.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime

os.environ.setdefault("JWT_SECRET", "run-scenarios-does-not-issue-tokens")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import models  # noqa: F401,E402  (create_all이 모든 모델을 알 수 있도록 import)
from core.clock import KST, utc_now  # noqa: E402
from db.base import Base  # noqa: E402
from models.user import User  # noqa: E402
from repositories.agent.team_activity_reader import (  # noqa: E402
    FixtureTeamActivityReader,
)
from services.agent import config  # noqa: E402
from services.agent.daily_report import DailyReportResult, build_daily_report  # noqa: E402
from services.agent.llm import build_llm_client  # noqa: E402
from services.agent.output_check import REASON_NO_RECORDS  # noqa: E402

NORMAL = "정상"


@dataclass(frozen=True)
class Scenario:
    """돌려 볼 시나리오 하나와 기대 결과."""

    title: str
    fixture: str
    day: date
    expected_reason: str
    expected_focus: bool


SCENARIOS = (
    Scenario("판정 있음 · 운동 3회", "evaluated", date(2026, 10, 19), NORMAL, True),
    Scenario("판정 있음 · 측정 불가 섞임", "evaluated", date(2026, 10, 20), NORMAL, True),
    Scenario("기록 없는 날", "evaluated", date(2026, 10, 21), REASON_NO_RECORDS, False),
    Scenario(
        "지금 실데이터 · 판정 없음, 점수 있음",
        "not_evaluated_scored",
        date(2026, 10, 20),
        NORMAL,
        True,
    ),
    Scenario(
        "지금 실데이터 · 점수까지 없음",
        "not_evaluated_unscored",
        date(2026, 10, 20),
        NORMAL,
        False,
    ),
)


def _fresh_session() -> Session:
    """시나리오마다 비어 있는 메모리 DB를 새로 만든다."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _demo_user(db: Session) -> User:
    """임신 주차와 동의가 채워진 데모 사용자. fixture 모드의 사용자 정보 자리다."""
    user = User(
        nickname="데모",
        email="demo@example.com",
        due_date=date(2026, 12, 25),
        exercise_level="low",
        onboarding_completed=True,
        terms_agreed_at=utc_now(),
        health_data_agreed_at=utc_now(),
    )
    db.add(user)
    db.commit()
    return user


def _run(scenario: Scenario, llm) -> DailyReportResult:
    db = _fresh_session()
    try:
        return build_daily_report(
            db,
            _demo_user(db),
            scenario.day,
            FixtureTeamActivityReader.from_scenario(scenario.fixture),
            llm,
        )
    finally:
        db.close()


def _actual(result: DailyReportResult) -> str:
    return result.fallback_reason or NORMAL


def _matched(scenario: Scenario, result: DailyReportResult) -> bool:
    return (
        _actual(result) == scenario.expected_reason
        and (result.next_focus is not None) == scenario.expected_focus
    )


def _expected_label(scenario: Scenario) -> str:
    focus = "다음 집중 스텝 있음" if scenario.expected_focus else "다음 집중 스텝 없음"
    return f"{scenario.expected_reason} · {focus}"


def _actual_label(result: DailyReportResult) -> str:
    focus = "다음 집중 스텝 있음" if result.next_focus else "다음 집중 스텝 없음"
    return f"{_actual(result)} · {focus}"


def _table(rows: list[tuple[Scenario, DailyReportResult]]) -> list[str]:
    lines = [
        "| 시나리오 | 기대 | 실제 | 일치 | LLM 호출 | latency_ms | 입력 토큰 | 출력 토큰 | summary |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scenario, result in rows:
        summary = result.summary.replace("\n", " ").replace("|", "/")
        lines.append(
            f"| {scenario.title} | {_expected_label(scenario)} | {_actual_label(result)} "
            f"| {'O' if _matched(scenario, result) else 'X'} | {result.llm_calls} "
            f"| {result.latency_ms if result.latency_ms is not None else '-'} "
            f"| {result.input_tokens if result.input_tokens is not None else '-'} "
            f"| {result.output_tokens if result.output_tokens is not None else '-'} "
            f"| {summary} |"
        )
    return lines


def _details(rows: list[tuple[Scenario, DailyReportResult]]) -> list[str]:
    lines: list[str] = []
    for scenario, result in rows:
        lines.append("")
        lines.append(f"### {scenario.title} ({scenario.fixture} · {scenario.day})")
        lines.append("")
        lines.append(f"- 한마디: {result.summary}")
        if result.next_focus:
            lines.append(
                f"- 다음 집중 스텝: {result.next_focus.step_id} — {result.next_focus.reason}"
            )
        else:
            lines.append("- 다음 집중 스텝: 없음")
        lines.append(
            f"- 숫자: 운동 {result.stats.record_count}회(완료 {result.stats.completed_count}, "
            f"미완료 {result.stats.incomplete_count}), {result.stats.total_minutes}분, "
            f"자세 배우기 {result.stats.step_attempt_count}번, "
            f"임신 {result.stats.pregnancy_week}주"
        )
        lines.append(f"- 저장: {'했음' if result.saved else '안 함'}")
    return lines


def main() -> None:
    llm = build_llm_client()
    rows = [(scenario, _run(scenario, llm)) for scenario in SCENARIOS]

    now = datetime.now(KST)
    prompts = ", ".join(
        f"{name}={config.load_prompt(name).version}"
        for name in ("step_memory_system", "daily_system", "safety_notice")
    )
    header = [
        "# 에이전트 시나리오 실행 기록",
        "",
        f"- 실행 시각: {now:%Y-%m-%d %H:%M:%S} (KST)",
        f"- 제공자: {llm.name} / 모델: {llm.model}",
        f"- 프롬프트: {prompts}",
        "- 기록: services/agent/fixtures (가짜 데이터)",
        "",
    ]
    report = header + _table(rows) + _details(rows) + [""]

    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RUNS_DIR / f"{now:%Y%m%d-%H%M%S}_{llm.name}.md"
    path.write_text("\n".join(report), encoding="utf-8")

    print("\n".join(_table(rows)))
    print()
    failed = [scenario.title for scenario, result in rows if not _matched(scenario, result)]
    print(f"일치하지 않은 시나리오: {', '.join(failed) if failed else '없음'}")
    print(f"실행 기록: {path}")


if __name__ == "__main__":
    main()
