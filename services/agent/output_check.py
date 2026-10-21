"""LLM 출력 검사. 통과한 것만 저장하고 화면에 보여 준다.

검사는 LLM이 쓴 문장에만 한다. 코드가 붙이는 고정 안전 안내에는 하지 않는다.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from services.agent import config

# 대체 문장을 쓴 이유. API 응답에는 넣지 않고 서비스 내부 결과와 로그에만 쓴다.
REASON_OUTPUT_CHECK = "OUTPUT_CHECK"
REASON_LLM_ERROR = "LLM_ERROR"
REASON_TIMEOUT = "TIMEOUT"
REASON_RATE_LIMIT = "RATE_LIMIT"
REASON_NO_CONSENT = "NO_CONSENT"
REASON_NO_RECORDS = "NO_RECORDS"
# 지난 날짜라 다시 만들지 않고, 저장한 리포트도 쓸 수 없어 숫자만 썼다.
REASON_PAST_DAY = "PAST_DAY"

_WHITESPACE = re.compile(r"\s+")
_FENCE_START = re.compile(r"^```[A-Za-z]*\n?")
_FENCE_END = re.compile(r"\n?```$")


@dataclass(frozen=True)
class NextFocus:
    """다음 집중 스텝. step_id는 반드시 코드가 준 후보 안에 있어야 한다."""

    step_id: int
    reason: str


@dataclass(frozen=True)
class DailyOutput:
    """검사를 통과한 DAILY 출력."""

    summary: str
    next_focus: NextFocus | None


@dataclass(frozen=True)
class CheckFailure:
    """검사 실패. detail은 로그에만 남긴다."""

    detail: str


def _squeeze(text: str) -> str:
    """공백을 모두 지운다. 건강 단어는 공백을 지운 뒤 부분 문자열로 찾는다."""
    return _WHITESPACE.sub("", text)


def find_banned_term(text: str) -> str | None:
    """의학적 판단 표현이 있으면 그 단어를 돌려준다."""
    squeezed = _squeeze(text)
    for term in config.banned_terms():
        if _squeeze(term) in squeezed:
            return term
    return None


def find_health_term(text: str) -> str | None:
    """건강·증상 단어가 있으면 그 단어를 돌려준다."""
    squeezed = _squeeze(text)
    for term in config.health_terms():
        if _squeeze(term) in squeezed:
            return term
    return None


def _forbidden_term(text: str) -> str | None:
    return find_banned_term(text) or find_health_term(text)


def load_json(text: str) -> Any:
    """LLM 출력을 JSON으로 읽는다. 코드 블록 표시가 붙어 와도 벗겨 낸다."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_END.sub("", _FENCE_START.sub("", cleaned).strip())
    return json.loads(cleaned)


def check_daily(
    text: str, candidate_step_ids: tuple[int, ...]
) -> DailyOutput | CheckFailure:
    """DAILY 출력을 검사한다.

    후보가 없으면 next_focus는 null이어야 한다. 후보가 있는데 null을 받으면 그대로 받아들이고
    다음 집중 스텝만 비워 둔다. (한마디 자체는 쓸 수 있으므로 대체 문장으로 떨어뜨리지 않는다)
    """
    try:
        data = load_json(text)
    except (ValueError, TypeError) as error:
        return CheckFailure(f"JSON으로 읽을 수 없음: {error}")
    if not isinstance(data, dict):
        return CheckFailure("JSON 객체가 아님")

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return CheckFailure("summary가 비어 있음")
    summary = summary.strip()
    if len(summary) > config.MAX_SUMMARY_LENGTH:
        return CheckFailure(f"summary가 {config.MAX_SUMMARY_LENGTH}자를 넘음")
    term = _forbidden_term(summary)
    if term:
        return CheckFailure(f"summary에 금지 단어: {term}")

    raw_focus = data.get("next_focus")
    if raw_focus is None:
        return DailyOutput(summary=summary, next_focus=None)
    if not candidate_step_ids:
        return CheckFailure("후보가 없는데 next_focus를 보냄")
    if not isinstance(raw_focus, dict):
        return CheckFailure("next_focus가 객체가 아님")

    step_id = raw_focus.get("step_id")
    if not isinstance(step_id, int) or isinstance(step_id, bool):
        return CheckFailure("next_focus.step_id가 정수가 아님")
    if step_id not in candidate_step_ids:
        return CheckFailure(f"next_focus.step_id가 후보 밖: {step_id}")
    reason = raw_focus.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return CheckFailure("next_focus.reason이 비어 있음")
    reason = reason.strip()
    if len(reason) > config.MAX_SUMMARY_LENGTH:
        return CheckFailure(f"next_focus.reason이 {config.MAX_SUMMARY_LENGTH}자를 넘음")
    term = _forbidden_term(reason)
    if term:
        return CheckFailure(f"next_focus.reason에 금지 단어: {term}")

    return DailyOutput(
        summary=summary, next_focus=NextFocus(step_id=step_id, reason=reason)
    )


def check_step_memos(
    text: str, requested_step_ids: tuple[int, ...]
) -> tuple[dict[int, str], tuple[str, ...]]:
    """STEP 메모 묶음을 검사한다.

    통과한 메모만 돌려준다. 실패한 스텝은 저장하지 않고, 다음 따라잡기 때 다시 시도한다.
    """
    try:
        data = load_json(text)
    except (ValueError, TypeError) as error:
        return {}, (f"JSON으로 읽을 수 없음: {error}",)
    if isinstance(data, dict) and "memo" in data:
        data = [data]
    if not isinstance(data, list):
        return {}, ("JSON 배열이 아님",)

    memos: dict[int, str] = {}
    failures: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            failures.append("항목이 객체가 아님")
            continue
        step_id = item.get("exercise_step_id")
        if not isinstance(step_id, int) or isinstance(step_id, bool):
            failures.append("exercise_step_id가 정수가 아님")
            continue
        if step_id not in requested_step_ids:
            failures.append(f"보내지 않은 스텝: {step_id}")
            continue
        memo = item.get("memo")
        if not isinstance(memo, str) or not memo.strip():
            failures.append(f"스텝 {step_id}: memo가 비어 있음")
            continue
        memo = memo.strip()
        if len(memo) > config.MAX_STEP_MEMO_LENGTH:
            failures.append(
                f"스텝 {step_id}: memo가 {config.MAX_STEP_MEMO_LENGTH}자를 넘음"
            )
            continue
        term = _forbidden_term(memo)
        if term:
            failures.append(f"스텝 {step_id}: memo에 금지 단어 {term}")
            continue
        memos[step_id] = memo
    return memos, tuple(failures)
