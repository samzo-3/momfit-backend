"""오늘의 운동 리포트 API 검사. 가짜 LLM과 fixture 리더를 의존성으로 끼운다."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models.agent.agent_feedback import (
    FEEDBACK_TYPE_DAILY,
    FEEDBACK_TYPE_STEP,
    AgentFeedback,
)
from models.user import User
from repositories.agent.team_activity_reader import (
    FixtureTeamActivityReader,
    get_team_activity_reader,
)
from services.agent.llm import (
    LlmError,
    LlmRateLimitedError,
    LlmTimeoutError,
    Usage,
    get_llm_client,
)
from tests.helpers import signup_payload

DAILY_REPORT = "/api/agent/daily-report"
# 코드가 숫자만으로 쓰는 대체 문장의 꼬리. 대체로 떨어졌는지 응답만 보고 구분할 때 쓴다.
FALLBACK_TAIL = "자세한 안내는 잠시 후 다시 확인해 주세요."
EMPTY_DAY = "2026-10-21"
RECORD_DAY = "2026-10-19"
NO_SCORE_DAY = "2026-10-20"


class ScriptedLlm:
    """STEP 메모는 받은 스텝에 맞춰 돌려주고, DAILY는 시험하고 싶은 답으로 바꿔 끼운다."""

    name = "fake"
    model = "fake-1"

    def __init__(self, daily: str | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._daily = daily
        self._error = error

    def generate(self, system_prompt: str, user_message: str, timeout: float):
        payload = json.loads(user_message)
        self.calls.append(payload)
        if "steps" in payload:
            memos = [
                {
                    "exercise_step_id": step["exercise_step_id"],
                    "memo": f"{step['step_name']} 메모",
                }
                for step in payload["steps"]
            ]
            return json.dumps(memos, ensure_ascii=False), Usage(10, 20)
        if self._error is not None:
            raise self._error
        if self._daily is not None:
            return self._daily, Usage(10, 20)
        candidates = payload["focus_candidates"]
        focus = (
            {
                "step_id": candidates[0]["exercise_step_id"],
                "reason": "다음에는 이 스텝에 조금 더 신경 써 봐요.",
            }
            if candidates
            else None
        )
        return (
            json.dumps(
                {"summary": "오늘도 꾸준히 해 주셨어요.", "next_focus": focus},
                ensure_ascii=False,
            ),
            Usage(10, 20),
        )


def _token(client: TestClient) -> str:
    response = client.post("/api/auth/signup", json=signup_payload())
    assert response.status_code == 201
    return response.json()["access_token"]


def _use(llm: ScriptedLlm, scenario: str = "evaluated") -> None:
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_team_activity_reader] = (
        lambda: FixtureTeamActivityReader.from_scenario(scenario)
    )


def _report(client: TestClient, token: str, day: str | None = RECORD_DAY):
    body = {} if day is None else {"date": day}
    return client.post(
        DAILY_REPORT, json=body, headers={"Authorization": f"Bearer {token}"}
    )


def _rows(db: Session, feedback_type: str) -> list[AgentFeedback]:
    return (
        db.query(AgentFeedback)
        .filter(AgentFeedback.feedback_type == feedback_type)
        .order_by(AgentFeedback.id)
        .all()
    )


def test_기록이_있으면_한마디와_다음_집중_스텝을_돌려주고_저장한다(
    client: TestClient, db_session: Session
) -> None:
    token = _token(client)
    llm = ScriptedLlm()
    _use(llm)

    response = _report(client, token)

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == RECORD_DAY
    assert body["summary"] == "오늘도 꾸준히 해 주셨어요."
    assert body["next_focus"] == {
        "step_id": 12,
        "reason": "다음에는 이 스텝에 조금 더 신경 써 봐요.",
    }
    assert body["provider"] == "fake"
    assert body["model"] == "fake-1"
    assert body["prompt_version"] == "daily-v2"
    assert body["latency_ms"] is not None
    assert body["stats"]["record_count"] == 3
    assert body["stats"]["completed_count"] == 3
    assert body["stats"]["step_attempt_count"] == 7
    assert body["stats"]["exercises"][0]["sets"] == [
        {"completed_sets": 6, "target_sets": 10},
        {"completed_sets": 7, "target_sets": 10},
        {"completed_sets": 8, "target_sets": 10},
    ]
    assert [step["pass_count"] for step in body["stats"]["steps"]] == [2, 1]
    # STEP 메모와 DAILY가 함께 저장된다.
    assert len(_rows(db_session, FEEDBACK_TYPE_STEP)) == 2
    daily = _rows(db_session, FEEDBACK_TYPE_DAILY)
    assert len(daily) == 1
    assert "다음 집중 스텝: 오른쪽 스텝" in daily[0].today_summary


def test_응답에는_대체_이유를_넣지_않는다(client: TestClient) -> None:
    token = _token(client)
    _use(ScriptedLlm())

    body = _report(client, token).json()

    assert set(body) == {
        "date",
        "stats",
        "safety_notice",
        "summary",
        "next_focus",
        "prompt_version",
        "provider",
        "model",
        "latency_ms",
    }


def test_후보가_없는_날은_다음_집중_스텝이_비고_대체_문장으로_떨어지지_않는다(
    client: TestClient, db_session: Session
) -> None:
    token = _token(client)
    llm = ScriptedLlm()
    _use(llm, scenario="not_evaluated_unscored")

    body = _report(client, token, NO_SCORE_DAY).json()

    assert body["next_focus"] is None
    assert body["summary"] == "오늘도 꾸준히 해 주셨어요."
    assert FALLBACK_TAIL not in body["summary"]
    # 점수도 판정도 없는 날은 후보가 0개인 게 정상이다.
    assert body["stats"]["steps"][0]["last_score"] is None
    assert len(_rows(db_session, FEEDBACK_TYPE_DAILY)) == 1


def test_기록이_없는_날은_LLM을_부르지_않고_저장하지_않는다(
    client: TestClient, db_session: Session
) -> None:
    token = _token(client)
    llm = ScriptedLlm()
    _use(llm)

    body = _report(client, token, EMPTY_DAY).json()

    assert llm.calls == []
    assert body["next_focus"] is None
    assert body["provider"] is None
    assert body["model"] is None
    assert body["prompt_version"] is None
    assert body["latency_ms"] is None
    assert body["stats"]["record_count"] == 0
    assert db_session.query(AgentFeedback).count() == 0


def test_건강정보_동의가_없으면_LLM을_부르지_않고_대체_문장을_쓴다(
    client: TestClient, db_session: Session
) -> None:
    token = _token(client)
    user = db_session.query(User).one()
    user.health_data_agreed_at = None
    db_session.commit()
    llm = ScriptedLlm()
    _use(llm)

    body = _report(client, token).json()

    assert llm.calls == []
    assert body["provider"] is None
    assert FALLBACK_TAIL in body["summary"]
    assert body["next_focus"] is None
    assert len(_rows(db_session, FEEDBACK_TYPE_DAILY)) == 1


@pytest.mark.parametrize(
    ("daily", "error"),
    [
        ('{"summary": "진단 결과를 알려 드릴게요."}', None),
        ('{"summary": "오늘은 배가 아프셨죠?"}', None),
        ('{"summary": "좋아요", "next_focus": {"step_id": 999, "reason": "없는 스텝"}}', None),
        ("JSON이 아닌 답", None),
        ('{"summary": ""}', None),
        (None, LlmTimeoutError("시간 초과")),
        (None, LlmRateLimitedError("호출 한도 초과")),
        (None, LlmError("알 수 없는 실패")),
    ],
)
def test_출력_검사나_호출이_실패하면_대체_문장을_쓴다(
    client: TestClient, db_session: Session, daily: str | None, error: Exception | None
) -> None:
    token = _token(client)
    llm = ScriptedLlm(daily=daily, error=error)
    _use(llm)

    body = _report(client, token).json()

    assert FALLBACK_TAIL in body["summary"]
    assert body["next_focus"] is None
    # LLM을 불렀으니 실제로 부른 값은 채운다.
    assert body["provider"] == "fake"
    assert body["prompt_version"] == "daily-v2"
    # 대체 문장도 화면에 보여 준 한마디라서 저장한다.
    assert len(_rows(db_session, FEEDBACK_TYPE_DAILY)) == 1


def test_안전_안내는_모든_응답에_들어간다(client: TestClient) -> None:
    token = _token(client)
    _use(ScriptedLlm())
    notice = "운동 중 어지러움, 복통, 출혈 같은 증상이 있었다면 운동을 멈추고 담당 의료진과 상의해 주세요."

    for day in (RECORD_DAY, EMPTY_DAY):
        body = _report(client, token, day).json()
        assert body["safety_notice"] == notice

    _use(ScriptedLlm(daily="JSON이 아닌 답"))
    assert _report(client, token).json()["safety_notice"] == notice


def test_날짜를_비우면_오늘로_본다(client: TestClient) -> None:
    from core.clock import today_kst

    token = _token(client)
    _use(ScriptedLlm())

    body = _report(client, token, day=None).json()

    assert body["date"] == today_kst().isoformat()


def test_같은_날_다시_요청하면_새_행이_쌓인다(
    client: TestClient, db_session: Session
) -> None:
    token = _token(client)
    _use(ScriptedLlm())

    _report(client, token)
    _report(client, token)

    rows = _rows(db_session, FEEDBACK_TYPE_DAILY)
    assert len(rows) == 2
    assert rows[-1].id > rows[0].id


def test_두_번째_요청은_STEP_메모를_다시_쓰지_않는다(client: TestClient) -> None:
    token = _token(client)
    llm = ScriptedLlm()
    _use(llm)

    _report(client, token)
    first_calls = len(llm.calls)
    _report(client, token)

    # 첫 요청은 STEP 묶음 1번 + DAILY 1번, 두 번째 요청은 DAILY 1번만 부른다.
    assert first_calls == 2
    assert len(llm.calls) == 3


def test_로그인하지_않으면_401이다(client: TestClient) -> None:
    response = client.post(DAILY_REPORT, json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_운동_기록_테이블이_없으면_에이전트_API만_503이다(
    client: TestClient, db_session: Session
) -> None:
    from models.exercise_record import ExerciseRecord
    from repositories.agent.team_activity_reader import SqlTeamActivityReader

    token = _token(client)
    # 팀 모델이 생겨 create_all이 테이블을 만든다. 테이블이 없는 DB를 이 테스트 안에서 만든다.
    ExerciseRecord.__table__.drop(db_session.get_bind())
    app.dependency_overrides[get_llm_client] = lambda: ScriptedLlm()
    app.dependency_overrides[get_team_activity_reader] = lambda: SqlTeamActivityReader(
        db_session
    )

    response = _report(client, token)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_DATA_UNAVAILABLE"
    # 팀 API는 그대로 동작해야 한다.
    assert client.get("/api/health").status_code == 200


def test_운영에서_허용되지_않은_제공자면_에이전트_API만_503이다(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _token(client)
    monkeypatch.setenv("AGENT_APP_ENV", "prod")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("AGENT_PROD_PROVIDERS", "anthropic")
    app.dependency_overrides[get_team_activity_reader] = (
        lambda: FixtureTeamActivityReader.from_scenario("evaluated")
    )

    response = _report(client, token)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AGENT_MISCONFIGURED"
    assert client.get("/api/health").status_code == 200
