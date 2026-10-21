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

# --- 팀 코드에서 가져온 값 -------------------------------------------------
# 팀 모델·스키마가 정한 값을 옮겨 왔다. 팀 코드가 바뀌면 이 블록만 고친다. 코드 곳곳에 흩어 두지 않는다.

# exercise_step_records의 CV 결과 JSON 컬럼.
# (develop #9 기준: models/exercise_step_record.py. CV 명세서의 step_report_json이 아니다)
STEP_REPORT_COLUMN = "step_report"
# 점수 범위. 이 범위를 벗어난 값은 집계에서 버린다.
# (develop #9 기준: schemas/exercise_step_record.py의 step_score 0~100,
#  services/exercise_record_score.py의 total_score 100점 상한)
SCORE_MIN = 0.0
SCORE_MAX = 100.0
# exercise_records.status. IN_PROGRESS / PAUSED / COMPLETED 중 하나다.
# (develop #9 기준: schemas/exercise_record.py)
EXERCISE_STATUS_COMPLETED = "COMPLETED"
# exercise_step_records.status. 시도 하나의 통과 여부이고 PASS / NON_PASS / NOT_EVALUATED 중 하나다.
# PASS는 80점 이상일 때만 저장된다. (develop #9 기준: schemas/exercise_step_record.py)
STEP_STATUS_PASS = "PASS"
# voice_cues.category. 자세 배우기 안내만 교정 문장으로 쓴다. TRACKING / EXERCISE / STUDY 중 하나다.
# (develop #9 기준: schemas/voice_cue.py, repositories/voice_cue_repository.py)
VOICE_CUE_CATEGORY_STUDY = "STUDY"

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
    """fixture | db. 팀 테이블에 실제 기록이 없는 개발 환경을 위해 기본은 fixture다."""
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
