from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.schemas.token_payload import TokenPayload

router = APIRouter()

# =========================
# Constants
# =========================
# 명세서: expires_in = 900 (15분)
ACCESS_TOKEN_EXPIRES_IN = 900


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
    # 명세서 에러 포맷을 detail에 담아서 반환
    # (프로젝트에 전역 exception handler가 있으면 여기 구조 그대로 응답으로 내보내면 됨)
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _issue_access_token(subject: str | int) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ACCESS_TOKEN_EXPIRES_IN)

    payload: dict[str, Any] = {
        "sub": str(subject),
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
        return TokenPayload(**payload)
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


# =========================
# Routes
# =========================
@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses={
        401: {"model": ErrorResponse},
    },
)
def refresh_access_token(
    refresh_token: Optional[str] = Cookie(default=None),
) -> RefreshResponse:
    """
    refresh 쿠키로 access token 재발급

    - Auth: Cookie `refresh_token` (HttpOnly)
    - Response: 200 { access_token, token_type, expires_in }
    - Errors:
      - 401 AUTH_REQUIRED (쿠키 없음)
      - 401 INVALID_REFRESH (위조/서명 불일치 등)
      - 401 REFRESH_EXPIRED (만료)
    """
    if not refresh_token:
        raise _error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Login required.",
        )

    token_data = _decode_refresh_token(refresh_token)
    access_token = _issue_access_token(token_data.sub)

    return RefreshResponse(access_token=access_token)


from starlette.responses import Response  # 파일 상단 import 추가

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    refresh_token: Optional[str] = Cookie(default=None),
) -> Response:
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)

    # refresh_token 쿠키 Path가 /api 일 수도 있고 / 일 수도 있어서 둘 다 삭제
    resp.delete_cookie(
        key="refresh_token",
        path="/api",
        secure=True,
        httponly=True,
        samesite="none",
    )
    resp.delete_cookie(
        key="refresh_token",
        path="/",
        secure=True,
        httponly=True,
        samesite="none",
    )
    return resp

