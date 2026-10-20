"""카카오 로그인 REST API 클라이언트. 표준 라이브러리(urllib)만 사용한다."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
USER_ME_URL = "https://kapi.kakao.com/v2/user/me"
UNLINK_URL = "https://kapi.kakao.com/v1/user/unlink"

# 카카오 콘솔의 동의 항목에서 닉네임을 켜야 한다.
SCOPE = "profile_nickname"
TIMEOUT_SECONDS = 10


class KakaoError(Exception):
    """카카오 API 호출이나 응답 처리에 실패했다. 토큰·코드 같은 값은 메시지에 담지 않는다."""


class KakaoNotConfigured(KakaoError):
    """카카오 로그인에 필요한 환경변수가 설정되지 않았다."""


@dataclass(frozen=True)
class KakaoProfile:
    """카카오에서 받은 사용자 정보. 닉네임만 수집한다."""

    id: str
    nickname: str | None


class KakaoClient:
    """카카오 인가·토큰·사용자 정보·연결 해제 API 호출."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        admin_key: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._admin_key = admin_key

    def authorize_url(self, state: str) -> str:
        """카카오 인가 페이지 주소를 만든다."""
        self._require(self._client_id, self._redirect_uri)
        query = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    def exchange_code(self, code: str) -> str:
        """인가 코드를 access 토큰으로 교환한다. 토큰은 저장하지 않고 이 요청에서만 쓴다."""
        self._require(self._client_id, self._client_secret, self._redirect_uri)
        body = self._request(
            "POST",
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "code": code,
            },
        )
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise KakaoError("카카오 토큰 응답에 access_token이 없습니다.")
        return token

    def fetch_profile(self, access_token: str) -> KakaoProfile:
        """회원번호와 닉네임을 조회한다."""
        body = self._request(
            "GET", USER_ME_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        kakao_id = body.get("id")
        if not isinstance(kakao_id, int):
            raise KakaoError("카카오 사용자 응답에 id가 없습니다.")
        profile = (body.get("kakao_account") or {}).get("profile") or {}
        nickname = profile.get("nickname")
        return KakaoProfile(
            id=str(kakao_id),
            nickname=nickname if isinstance(nickname, str) else None,
        )

    def unlink(self, kakao_user_id: str) -> None:
        """서비스 앱 어드민 키로 사용자의 카카오 연결을 끊는다."""
        self._require(self._admin_key)
        self._request(
            "POST",
            UNLINK_URL,
            headers={"Authorization": f"KakaoAK {self._admin_key}"},
            data={"target_id_type": "user_id", "target_id": kakao_user_id},
        )

    @staticmethod
    def _require(*values: str) -> None:
        if not all(values):
            raise KakaoNotConfigured("카카오 환경변수가 설정되지 않았습니다.")

    @staticmethod
    def _request(
        method: str,
        url: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(
            url, data=encoded, method=method, headers=headers or {}
        )
        if encoded is not None:
            request.add_header(
                "Content-Type", "application/x-www-form-urlencoded;charset=utf-8"
            )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            # 응답 본문에는 오류 설명만 있지만, 안전하게 상태 코드만 남긴다.
            raise KakaoError(f"카카오 API 오류 (HTTP {error.code})") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise KakaoError("카카오 API에 연결하지 못했습니다.") from None
        except ValueError:
            raise KakaoError("카카오 API 응답을 해석하지 못했습니다.") from None
        if not isinstance(payload, dict):
            raise KakaoError("카카오 API 응답 형식이 올바르지 않습니다.")
        return payload


@lru_cache
def get_kakao_client() -> KakaoClient:
    """설정에서 만든 카카오 클라이언트. FastAPI 의존성으로 쓰며, 테스트에서는 교체한다.

    설정이 비어 있어도 만들어지고, 실제로 호출할 때 KakaoNotConfigured가 발생한다.
    (카카오를 쓰지 않는 요청이 설정 때문에 실패하지 않게 하기 위해서다.)
    """
    return KakaoClient(
        client_id=settings.kakao_client_id,
        client_secret=settings.kakao_client_secret,
        redirect_uri=settings.kakao_redirect_uri,
        admin_key=settings.kakao_admin_key,
    )
