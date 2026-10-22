"""LLM 제공자. mock / gemini / anthropic이 모두 같은 모양이다.

    generate(system_prompt, user_message, timeout) -> (text, Usage)

SDK import는 그 제공자를 쓸 때만 함수 안에서 한다. (requirements에만 있고 쓰지 않는 제공자가
설치되지 않아도 서버가 뜨게 하려고)

제공자 선택과 모델 이름의 근거는 services/agent/README.md의 'LLM 제공자 결정'에 적어 두었다.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from core.errors import AppError
from services.agent import config

logger = logging.getLogger(__name__)

PROVIDER_MOCK = "mock"
PROVIDER_GEMINI = "gemini"
PROVIDER_ANTHROPIC = "anthropic"


@dataclass(frozen=True)
class Usage:
    """토큰 사용량. DB에 저장하지 않고 실행 기록 파일에만 남긴다."""

    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmError(Exception):
    """LLM 호출 실패. 서비스는 대체 문장으로 떨어진다."""


class LlmTimeoutError(LlmError):
    """제한 시간 초과."""


class LlmRateLimitedError(LlmError):
    """호출 한도 초과(429)."""


class LlmClient(Protocol):
    """LLM 제공자 한 개."""

    name: str
    model: str

    def generate(
        self, system_prompt: str, user_message: str, timeout: float
    ) -> tuple[str, Usage]: ...


class MockLlm:
    """API 키 없이 돌리는 가짜 제공자. 규칙으로 JSON을 만든다.

    입력 JSON에 steps가 있으면 STEP 메모, stats가 있으면 DAILY로 본다.
    """

    name = PROVIDER_MOCK
    model = "mock"

    def generate(
        self, system_prompt: str, user_message: str, timeout: float
    ) -> tuple[str, Usage]:
        try:
            data = json.loads(user_message)
        except (ValueError, TypeError) as error:
            raise LlmError(f"mock이 입력을 읽지 못했습니다: {error}") from error
        if "steps" in data:
            text = json.dumps(self._memos(data["steps"]), ensure_ascii=False)
        elif "stats" in data:
            text = json.dumps(self._daily(data), ensure_ascii=False)
        else:
            raise LlmError("mock이 모르는 입력입니다.")
        return text, Usage(input_tokens=len(user_message), output_tokens=len(text))

    def _memos(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        memos = []
        for step in steps:
            attempts = step.get("attempts") or []
            scores = [a.get("score") for a in attempts if a.get("score") is not None]
            issues: list[str] = []
            for attempt in attempts:
                for issue in attempt.get("issues") or []:
                    if issue not in issues:
                        issues.append(issue)
            parts = [f"{len(attempts)}번 시도"]
            if issues:
                parts.append(f"{issues[0]} {sum(1 for a in attempts if issues[0] in (a.get('issues') or []))}번")
            if len(scores) >= 2:
                parts.append(f"{scores[0]:g}점에서 {scores[-1]:g}점")
            elif scores:
                parts.append(f"{scores[0]:g}점")
            memo = f"{step.get('step_name', '스텝')}: " + ", ".join(parts)
            memos.append(
                {
                    "exercise_step_id": step.get("exercise_step_id"),
                    "memo": memo[: config.MAX_STEP_MEMO_LENGTH],
                }
            )
        return memos

    def _daily(self, data: dict[str, Any]) -> dict[str, Any]:
        stats = data.get("stats") or {}
        candidates = data.get("focus_candidates") or []
        sentences = [
            f"오늘 운동 {stats.get('record_count', 0)}회, "
            f"자세 배우기 {stats.get('step_attempt_count', 0)}번 하셨어요."
        ]
        if data.get("camera_check_steps"):
            sentences.append("일부 스텝은 카메라에 몸이 다 담기지 않았어요.")
        sentences.append("오늘도 움직여 주셔서 좋았어요.")
        focus = None
        if candidates:
            first = candidates[0]
            reason = first.get("step_description") or "다음에 조금 더 신경 써 보면 좋아요."
            if first.get("issues"):
                reason = f"카메라로 보니 {first['issues'][0]}이 있었어요. {reason}"
            focus = {
                "step_id": first.get("exercise_step_id"),
                "reason": reason[: config.MAX_SUMMARY_LENGTH],
            }
        return {
            "summary": " ".join(sentences)[: config.MAX_SUMMARY_LENGTH],
            "next_focus": focus,
        }


class GeminiLlm:
    """google-genai. 무료 등급으로 비교해 볼 때 쓴다.

    무료 등급은 입력·출력이 구글 제품 개선에 쓰일 수 있어 가짜 데이터만 넣는다.
    (README의 'LLM 제공자 결정' 참고)
    """

    name = PROVIDER_GEMINI

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key

    def generate(
        self, system_prompt: str, user_message: str, timeout: float
    ) -> tuple[str, Usage]:
        if not self._api_key:
            raise LlmError("GEMINI_API_KEY가 없습니다.")
        from google import genai
        from google.genai import errors, types

        try:
            # attempts=1: 한 번만 시도한다. SDK가 503·429를 자동 재시도하면 리포트 전체 제한 시간을
            # 먹고, 재시도 전에 서버의 Retry-After만큼 잠들기도 한다. 실패는 바로 대체 문장으로
            # 떨어지는 편이 낫다. (AnthropicLlm의 max_retries=0과 같은 이유)
            # interactions.create는 쓰지 않는다. Client가 attempts=0을 1로 바꾸고 interactions 쪽은
            # 그 값을 '재시도 횟수'로 읽어서, 재시도를 끌 수 없다. (google-genai 2.32.0에서 확인)
            client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(
                    timeout=int(timeout * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            response = client.models.generate_content(
                model=self.model,
                contents=user_message,
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )
        except errors.ClientError as error:
            if getattr(error, "code", None) == 429:
                raise LlmRateLimitedError(str(error)) from error
            raise LlmError(str(error)) from error
        except errors.APIError as error:
            raise LlmError(str(error)) from error
        except Exception as error:
            # 제한 시간 초과는 SDK가 쓰는 HTTP 라이브러리의 예외로 올라온다. 그 라이브러리를
            # 직접 import하지 않으려고 클래스 이름으로 가린다.
            if "Timeout" in type(error).__name__:
                raise LlmTimeoutError(str(error)) from error
            raise LlmError(str(error)) from error

        usage = response.usage_metadata
        return response.text or "", Usage(
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )


class AnthropicLlm:
    """Claude API. 개발과 운영 모두 이 제공자를 쓴다. (README의 'LLM 제공자 결정' 참고)"""

    name = PROVIDER_ANTHROPIC

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key

    def generate(
        self, system_prompt: str, user_message: str, timeout: float
    ) -> tuple[str, Usage]:
        if not self._api_key:
            raise LlmError("ANTHROPIC_API_KEY가 없습니다.")
        import anthropic

        # max_retries=0: SDK가 429를 자동 재시도하면 리포트 전체 제한 시간을 먹는다.
        # 한도 초과는 바로 대체 문장으로 떨어지는 편이 낫다.
        client = anthropic.Anthropic(
            api_key=self._api_key, timeout=timeout, max_retries=0
        )
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                # 짧은 문장 생성이라 낮은 effort로 충분하다. (기본값은 medium)
                output_config={"effort": "low"},
            )
        except anthropic.RateLimitError as error:
            raise LlmRateLimitedError(str(error)) from error
        except anthropic.APITimeoutError as error:
            raise LlmTimeoutError(str(error)) from error
        except anthropic.APIConnectionError as error:
            raise LlmError(str(error)) from error
        except anthropic.APIStatusError as error:
            raise LlmError(str(error)) from error

        if response.stop_reason == "refusal":
            raise LlmError("모델이 응답을 거절했습니다.")
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return text, Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


def build_llm_client() -> LlmClient:
    """AGENT_LLM_PROVIDER에 맞는 제공자를 만든다. FastAPI 밖에서도 쓴다.

    운영(AGENT_APP_ENV=prod)에서 허용 목록에 없는 제공자를 쓰면 에이전트 API만 503으로 막는다.
    팀 서버 전체를 멈추지는 않는다.
    """
    provider = config.llm_provider()
    if config.app_env() == "prod" and provider not in config.prod_providers():
        logger.error(
            "운영 환경에서 허용되지 않은 LLM 제공자입니다: provider=%s, 허용=%s",
            provider,
            ",".join(config.prod_providers()),
        )
        raise AppError(
            503,
            "AGENT_MISCONFIGURED",
            "지금은 리포트를 만들 수 없어요. 잠시 후 다시 시도해 주세요.",
        )

    model = config.llm_model()
    if provider == PROVIDER_GEMINI:
        return GeminiLlm(
            model=model or config.DEFAULT_GEMINI_MODEL, api_key=config.gemini_api_key()
        )
    if provider == PROVIDER_ANTHROPIC:
        return AnthropicLlm(
            model=model or config.DEFAULT_ANTHROPIC_MODEL,
            api_key=config.anthropic_api_key(),
        )
    return MockLlm()


def get_llm_client() -> LlmClient:
    """라우터용 의존성. 테스트는 dependency_overrides로 가짜 제공자를 끼운다."""
    return build_llm_client()
