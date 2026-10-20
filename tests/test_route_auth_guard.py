"""등록된 모든 라우트가 인증 가드를 갖췄는지 실제 호출로 검사한다.

FastAPI에는 모든 요청에 걸리는 보안 필터 체인이 없고, 엔드포인트마다 `Depends(...)`로 가드를 선언해야
보호된다. 새 API가 가드를 빼먹으면 누구나 호출할 수 있으므로, 이 테스트가 그것을 CI에서 잡는다.
(라우트 목록은 OpenAPI 스키마에서 읽는다. FastAPI 내부 구조에 기대지 않아 버전이 바뀌어도 깨지지 않는다.
`include_in_schema=False`로 숨긴 라우트는 검사되지 않으니 그렇게 만들지 않는다.)

새 라우트를 추가했는데 이 테스트가 실패했다면:
- 로그인이 필요한 API: `Depends(get_onboarded_user)`를 추가한다. (온보딩 전에도 써야 하면 `get_current_user`를 쓰고
  아래 ONBOARDING_EXEMPT_ROUTES에 추가한다)
- 로그인 없이 호출하는 API: 아래 PUBLIC_ROUTES에 이유와 함께 추가한다.
"""

import re

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.helpers import kakao_login

# 로그인 없이 호출하는 라우트: (메서드, 경로) -> 공개인 이유
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/api/health"): "상태 확인",
    ("GET", "/api/auth/check-login-id"): "가입 전 아이디 중복 확인",
    ("POST", "/api/auth/signup"): "가입",
    ("POST", "/api/auth/login"): "로그인",
    ("GET", "/api/auth/restore"): "탈퇴 유예 계정의 복구 화면 정보(로그인 직후 받은 복구용 쿠키로 확인)",
    ("POST", "/api/auth/restore"): "탈퇴 유예 계정 복구(복구용 쿠키로 확인)",
    ("POST", "/api/auth/refresh"): "refresh 쿠키로 새 토큰 발급",
    ("POST", "/api/auth/logout"): "refresh 쿠키로 로그인 폐기(access가 만료돼도 가능해야 함)",
    ("POST", "/api/auth/email/send-code"): "가입·비밀번호 재설정 전 이메일 인증",
    ("POST", "/api/auth/email/verify-code"): "가입·비밀번호 재설정 전 이메일 인증",
    ("POST", "/api/auth/password/reset"): "로그인하지 못하는 사용자의 비밀번호 재설정",
    ("GET", "/api/auth/kakao/login"): "카카오 인가 페이지로 이동",
    ("GET", "/api/auth/kakao/callback"): "카카오가 사용자를 돌려보내는 주소",
}

# 로그인만 하면 되고 온보딩 완료까지는 요구하지 않는 라우트 (온보딩 자체를 위한 API)
ONBOARDING_EXEMPT_ROUTES: set[tuple[str, str]] = {
    ("GET", "/api/users/me"),
    ("PATCH", "/api/users/me"),
    ("POST", "/api/users/me/onboarding"),
    ("DELETE", "/api/users/me"),
}


def _registered_routes() -> list[tuple[str, str]]:
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    ]


ROUTES = _registered_routes()
PROTECTED_ROUTES = [route for route in ROUTES if route not in PUBLIC_ROUTES]
ONBOARDED_ROUTES = [
    route for route in PROTECTED_ROUTES if route not in ONBOARDING_EXEMPT_ROUTES
]


def _url(path: str) -> str:
    # 경로 매개변수는 아무 값으로 채운다. 가드는 본문·경로 검증보다 먼저 실행된다.
    return re.sub(r"\{[^}]+\}", "1", path)


def test_라우트_목록을_읽을_수_있다() -> None:
    # 목록이 비어 있으면 아래 검사가 아무것도 검사하지 않고 통과해 버린다.
    assert ("GET", "/api/health") in ROUTES
    assert ("GET", "/api/users/me") in PROTECTED_ROUTES


def test_허용_목록에_남은_항목은_모두_실제_라우트다() -> None:
    stale = sorted((PUBLIC_ROUTES.keys() | ONBOARDING_EXEMPT_ROUTES) - set(ROUTES))

    assert stale == [], f"더 이상 없는 라우트가 허용 목록에 남아 있습니다: {stale}"


def test_공개_목록과_온보딩_예외_목록이_겹치지_않는다() -> None:
    assert PUBLIC_ROUTES.keys().isdisjoint(ONBOARDING_EXEMPT_ROUTES)


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
def test_보호_라우트는_토큰_없이_호출하면_401이다(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, _url(path))

    assert response.status_code == 401, (
        f"{method} {path}에 인증 가드가 없습니다. Depends(get_onboarded_user)를 추가하거나, "
        "의도한 공개 API라면 PUBLIC_ROUTES에 이유와 함께 추가하세요."
    )
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(("method", "path"), ONBOARDED_ROUTES)
def test_보호_라우트는_온보딩_전_사용자를_막는다(
    client: TestClient, method: str, path: str
) -> None:
    # 카카오로 처음 로그인한 사용자는 온보딩을 마치지 않은 상태다.
    kakao_login(client)
    token = client.post("/api/auth/refresh").json()["access_token"]

    response = client.request(
        method, _url(path), headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403, (
        f"{method} {path}가 온보딩 완료를 확인하지 않습니다. "
        "get_current_user 대신 get_onboarded_user를 쓰세요."
    )
    assert response.json()["error"]["code"] == "ONBOARDING_REQUIRED"
