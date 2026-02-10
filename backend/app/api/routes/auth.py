from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Cookie, HTTPException, status
from jwt import PyJWTError
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ValidationError
from starlette.responses import Response

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.enums import EventType
from app.crud.event import create_event
from app.schemas.token_payload import TokenPayload

router = APIRouter()

# =========================
# Constants
# =========================
ACCESS_TOKEN_EXPIRES_IN = 900  # seconds (15m)

# 쿠키 기반 인증 강제: access/refresh 모두 쿠키로만 운용
ACCESS_COOKIE_KEY = "access_token"
REFRESH_COOKIE_KEY = "refresh_token"

# oauth 라우터에서 발급한 옵션과 "통일"하는 걸 권장
COOKIE_PATH = "/api"
COOKIE_SAMESITE = "lax"


# =========================
# Response Schemas
# =========================
class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRES_IN


# =========================
# Helpers
# =========================
def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _issue_access_token(subject: str | int) -> str:
    """
    access token 발급 (JWT)
    - sub는 문자열로 고정 (PyJWT subject 검증 + TokenPayload 통일)
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ACCESS_TOKEN_EXPIRES_IN)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_refresh_token(refresh_token: str) -> TokenPayload:
    """
    refresh token 디코드/검증
    - 서명/만료 검증
    - TokenPayload 스키마 검증
    """
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        token = TokenPayload(**payload)
        return token

    except ExpiredSignatureError:
        raise _error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="REFRESH_EXPIRED",
            message="Refresh token expired.",
        )
    except (PyJWTError, InvalidTokenError, ValidationError):
        # InvalidSubjectError 등도 PyJWTError로 잡히는 게 안전
        raise _error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_REFRESH",
            message="Invalid refresh token.",
        )


def _secure_cookie() -> bool:
    backend_public_url = getattr(settings, "BACKEND_PUBLIC_URL", "").rstrip("/")
    return backend_public_url.startswith("https://")


def _set_access_cookie(response: Response, access_token: str) -> None:
    secure_cookie = _secure_cookie()
    response.set_cookie(
        key=ACCESS_COOKIE_KEY,
        value=access_token,
        httponly=True,
        secure=secure_cookie,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )


def _delete_auth_cookies(response: Response) -> None:
    """
    access/refresh 쿠키 삭제.
    - 현재 운영값(COOKIE_PATH=/api) 삭제
    - 과거 호환(/) 삭제도 함께 수행
    """
    secure_cookie = _secure_cookie()

    for path in (COOKIE_PATH, "/"):
        response.delete_cookie(
            key=ACCESS_COOKIE_KEY,
            path=path,
            secure=secure_cookie,
            httponly=True,
            samesite=COOKIE_SAMESITE,
        )
        response.delete_cookie(
            key=REFRESH_COOKIE_KEY,
            path=path,
            secure=secure_cookie,
            httponly=True,
            samesite=COOKIE_SAMESITE,
        )


# =========================
# Routes
# =========================
@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Access token 재발급",
    description=(
        "refresh_token(HttpOnly 쿠키)로 access token(JWT)을 재발급합니다.\n\n"
        "- Auth: Cookie `refresh_token`\n"
        "- Response: 200 `{access_token, token_type, expires_in}` + access_token 쿠키 갱신\n"
        "- Errors:\n"
        "  - 401 `AUTH_REQUIRED` (쿠키 없음)\n"
        "  - 401 `INVALID_REFRESH` (위조/서명 불일치 등)\n"
        "  - 401 `REFRESH_EXPIRED` (만료)\n"
        "  - 500"
    ),
)
def refresh_access_token(
    response: Response,  # ✅ 쿠키 갱신용
    session: SessionDep,
    refresh_token: Optional[str] = Cookie(default=None),
) -> RefreshResponse:
    if not refresh_token:
        raise _error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Login required.",
        )

    token_data = _decode_refresh_token(refresh_token)
    access_token = _issue_access_token(token_data.sub)

    # ✅ 쿠키 기반 인증 강제: access_token 쿠키를 반드시 갱신
    _set_access_cookie(response, access_token)

    try:
        create_event(
            session,
            user_id=int(token_data.sub),
            event_type=EventType.refresh_token,
            meta={"source": "auth_refresh"},
        )
        session.commit()
    except Exception:
        # 토큰 재발급 자체는 성공시키고, 이벤트 기록 실패는 무시
        pass

    return RefreshResponse(access_token=access_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="로그아웃",
    description=(
        "로그아웃 처리: access_token, refresh_token 쿠키를 삭제합니다.\n\n"
        "- Auth: Cookie refresh_token (있으면 이벤트 기록, 없어도 성공 처리)\n"
        "- Response: 204\n"
        "- Errors:\n"
        "  - 500"
    ),
)
def logout(
    session: SessionDep,
    refresh_token: Optional[str] = Cookie(default=None),
) -> Response:
    # refresh_token이 있으면 sub를 뽑아 이벤트 기록 (만료 여부는 무시)
    if refresh_token:
        try:
            payload = jwt.decode(
                refresh_token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                options={"verify_exp": False},
            )
            sub = payload.get("sub")
            if sub:
                create_event(
                    session,
                    user_id=int(sub),
                    event_type=EventType.logout,
                    meta={"source": "auth_logout"},
                )
                session.commit()
        except Exception:
            # 로그아웃은 절대 실패하면 안 되므로 무시
            pass

    resp = Response(status_code=status.HTTP_204_NO_CONTENT)

    # ✅ access/refresh 모두 삭제
    _delete_auth_cookies(resp)

    return resp
