from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models import User
from app.schemas.token_payload import TokenPayload

# Swagger에서 "Bearer token" 입력칸이 뜨는 스키마
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
CredDep = Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)]


def _auth_required() -> None:
    # 명세서 에러 포맷 고정
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "AUTH_REQUIRED", "message": "Login required."}},
    )


def get_current_user(session: SessionDep, credentials: CredDep) -> User:
    # Authorization 헤더 자체가 없음
    if credentials is None or not credentials.credentials:
        _auth_required()

    token = credentials.credentials

    # 토큰 검증 실패(만료/위조/서명불일치 등)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        _auth_required()

    # 사용자 없음 -> 401 AUTH_REQUIRED
    # token_data.sub 가 "1" 같은 문자열이면 int로 바꿔서 get 해야 안전함
    try:
        user_id = int(token_data.sub)
    except Exception:
        _auth_required()

    user = session.get(User, user_id)
    if not user:
        _auth_required()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
