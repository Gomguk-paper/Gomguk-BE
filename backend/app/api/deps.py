from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models import User
from app.schemas.token_payload import TokenPayload


reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/token",
    auto_error=False,
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[Optional[str], Depends(reusable_oauth2)]


def _auth_required() -> None:
    # 명세서 에러 포맷 고정
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "AUTH_REQUIRED", "message": "Login required."}},
    )


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    # 토큰 없음 -> 401 AUTH_REQUIRED
    if not token:
        _auth_required()

    # 토큰 검증 실패(만료/위조/서명불일치 등) -> 401 AUTH_REQUIRED (명세: 없음/만료/유효하지 않음)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        _auth_required()

    # 사용자 없음 -> 401 AUTH_REQUIRED (로그인 상태가 아니라고 취급)
    user = session.get(User, token_data.sub)
    if not user:
        _auth_required()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
