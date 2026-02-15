from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from pydantic import ValidationError
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models import User
from app.schemas.token_payload import TokenPayload

ACCESS_COOKIE_KEY = "access_token"
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]


def _auth_required() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "AUTH_REQUIRED", "message": "Login required."}},
    )


def get_current_user(
    request: Request,
    session: SessionDep,
    bearer_credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    token = request.cookies.get(ACCESS_COOKIE_KEY)
    if not token and bearer_credentials:
        token = bearer_credentials.credentials.strip()
        # Swagger authorize input may include "Bearer " prefix by mistake.
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if not token:
        _auth_required()

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (PyJWTError, ValidationError):
        _auth_required()

    try:
        user_id = int(token_data.sub)
    except Exception:
        _auth_required()

    user = session.get(User, user_id)
    if not user:
        _auth_required()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
