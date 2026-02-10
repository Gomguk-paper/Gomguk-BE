from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Cookie, HTTPException, status
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
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        token = TokenPayload(**payload)

        # typ 방어 (명세에 명시된 refresh 쿠키만 허용)
        typ = getattr(token, "typ", None)
        if typ != "refresh":
            raise _error(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="INVALID_REFRESH",
                message="Invalid refresh token.",
            )

        return token

    except ExpiredSignatureError:
        raise _error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="REFRESH_EXPIRED",
            message="Refresh token expired.",
        )
    except (InvalidTokenError, ValidationError):
        raise _error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_REFRESH",
            message="Invalid refresh token.",
        )


def _secure_cookie() -> bool:
    backend_public_url = getattr(settings, "BACKEND_PUBLIC_URL", "").rstrip("/")
    return backend_public_url.startswith("https://")


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
        "- Response: 200 `{access_token, token_type, expires_in}`\n"
        "- Errors:\n"
        "  - 401 `AUTH_REQUIRED` (쿠키 없음)\n"
        "  - 401 `INVALID_REFRESH` (위조/서명 불일치/typ 불일치 등)\n"
        "  - 401 `REFRESH_EXPIRED` (만료)\n"
        "  - 500"
    ),
)
def refresh_access_token(
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
        "로그아웃 처리: refresh_token 쿠키를 삭제합니다.\n\n"
        "- Auth: Cookie `refresh_token` (있으면 삭제, 없어도 성공 처리)\n"
        "- Response: 204\n"
        "  - Set-Cookie: `refresh_token=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=None`\n"
        "- Errors:\n"
        "  - 500"
    ),
)
def logout(
    session: SessionDep,
    refresh_token: Optional[str] = Cookie(default=None),
) -> Response:
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
            pass  # 로그아웃은 절대 실패하면 안 되므로 무시

    secure_cookie = _secure_cookie()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)

    resp.delete_cookie(
        key="refresh_token",
        path="/",
        secure=secure_cookie,
        httponly=True,
        samesite="none",
    )

    # (과거 코드에서 /api로 발급한 적이 있다면 호환 삭제)
    resp.delete_cookie(
        key="refresh_token",
        path="/api",
        secure=secure_cookie,
        httponly=True,
        samesite="none",
    )

    return resp
