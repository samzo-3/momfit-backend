"""에이전트 설정과 팀 확인 대기 중인 가정값.

팀의 core/config.py는 건드리지 않는다. 에이전트 설정은 모두 여기서 os.getenv로 읽는다.
환경변수는 쓸 때마다 읽는다. (테스트에서 monkeypatch로 바꿔 끼울 수 있게 함수로 둔다)
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = AGENT_DIR / "prompts"
RULES_DIR = AGENT_DIR / "rules"
FIXTURES_DIR = AGENT_DIR / "fixtures"
RUNS_DIR = AGENT_DIR / "runs"

# --- 팀 답을 기다리는 가정 -------------------------------------------------
# 팀이 확정하면 이 블록만 고친다. 코드 곳곳에 흩어 두지 않는다.

# CV 명세서는 step_report_json, 팀 최종 ERD는 step_report다. (확인 중)
STEP_REPORT_COLUMN = "step_report"
# 점수 범위. 이 범위를 벗어난 값은 집계에서 버린다.
SCORE_MIN = 0.0
SCORE_MAX = 100.0
# exercise_records.status에 저장되는 값. 한글인지 영문 코드인지 확인 중.
EXERCISE_STATUS_COMPLETED = "완료"
# exercise_step_records.status에 저장되는 값. 지금 집계에 쓰지는 않지만 함께 확인 중이다.
STEP_STATUS_IN_PROGRESS = "진행중"
STEP_STATUS_RESTARTED = "재시작"
STEP_STATUS_COMPLETED = "완료"
# voice_cues.category에 저장되는 값. 자세 배우기 모드 공통 안내를 고를 때 쓴다.
VOICE_CUE_CATEGORY_LEARN = "자세 배우기 모드"

# --- 에이전트 자체 한계값 ---------------------------------------------------

MAX_SUMMARY_LENGTH = 300
MAX_STEP_MEMO_LENGTH = 120
MAX_FOCUS_CANDIDATES = 2
MAX_ISSUES_PER_CANDIDATE = 2

# 제공자별 기본 모델. AGENT_LLM_MODEL이 있으면 그 값이 이긴다.
# (확인일 2026-10-21 · services/agent/README.md의 'LLM 제공자 결정' 참고)
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-5-5"


# --- 환경변수 ---------------------------------------------------------------


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def data_source() -> str:
    """fixture | db. 팀의 운동 기록 테이블이 아직 없어 기본은 fixture다."""
    return _env("AGENT_DATA_SOURCE", "fixture").lower()


def fixture_scenario() -> str:
    """fixture 모드에서 쓸 시나리오 이름. services/agent/fixtures/scenario_{이름}.json"""
    return _env("AGENT_FIXTURE_SCENARIO", "evaluated").lower()


def llm_provider() -> str:
    """mock | gemini | anthropic."""
    return _env("AGENT_LLM_PROVIDER", "mock").lower()


def llm_model() -> str:
    """비어 있으면 제공자별 기본 모델을 쓴다."""
    return _env("AGENT_LLM_MODEL", "")


def llm_timeout_seconds() -> float:
    """LLM 호출 하나의 제한 시간."""
    return float(_env("AGENT_LLM_TIMEOUT_SECONDS", "10"))


def report_timeout_seconds() -> float:
    """리포트 하나가 LLM에 쓸 수 있는 전체 제한 시간."""
    return float(_env("AGENT_REPORT_TIMEOUT_SECONDS", "25"))


def app_env() -> str:
    """dev | prod. prod에서는 허용된 제공자만 쓸 수 있다."""
    return _env("AGENT_APP_ENV", "dev").lower()


def prod_providers() -> tuple[str, ...]:
    """운영에서 허용하는 LLM 제공자 목록."""
    raw = _env("AGENT_PROD_PROVIDERS", "anthropic")
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


def gemini_api_key() -> str:
    return _env("GEMINI_API_KEY", "")


def anthropic_api_key() -> str:
    return _env("ANTHROPIC_API_KEY", "")


# --- 프롬프트와 규칙 파일 ---------------------------------------------------


@dataclass(frozen=True)
class Prompt:
    """프롬프트 한 개. 파일 첫 줄이 버전이고, 그 줄은 LLM에 보내지 않는다."""

    version: str
    text: str


@lru_cache(maxsize=None)
def load_prompt(name: str) -> Prompt:
    """prompts/{name}.md를 읽는다."""
    raw = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    first_line, _, body = raw.partition("\n")
    return Prompt(version=first_line.strip(), text=body.strip())


@lru_cache(maxsize=None)
def load_rules(name: str) -> dict:
    """rules/{name}.json을 읽는다."""
    return json.loads((RULES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def feedback_labels() -> dict[str, str]:
    """피드백 코드 -> 상태 설명('무엇이 부족했나'). 교정 방법은 voice_cues에서 온다."""
    return dict(load_rules("feedback_codes")["codes"])


def banned_terms() -> tuple[str, ...]:
    """의학적 판단 표현. LLM 출력에 있으면 버린다."""
    return tuple(load_rules("banned_output")["terms"])


def health_terms() -> tuple[str, ...]:
    """건강·증상 단어. LLM 출력에 있으면 버린다."""
    return tuple(load_rules("health_terms")["terms"])


def safety_notice() -> str:
    """모든 응답에 넣는 고정 안전 안내. 코드가 붙이므로 금지어·건강 단어 검사를 하지 않는다."""
    return load_prompt("safety_notice").text
