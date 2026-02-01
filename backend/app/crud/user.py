from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from typing import Optional

from app.models.user import User
from app.core.enums import AuthProvider
from app.api.deps import SessionDep


def create_user(
    session: SessionDep,
    provider: AuthProvider,
    provider_sub: str,
    email: str,
    name: str
) -> Optional[User]:
    user = User(
        provider=provider,
        provider_sub=provider_sub,
        email=email,
        name=name,
    )
    session.add(user)
    try:
        session.flush()
        session.commit()
        session.refresh(user)
        return user
    except IntegrityError:
        session.rollback()
        return None


def get_user_by_sub(
        session: SessionDep,
        provider: AuthProvider,
        provider_sub: str
) -> Optional[User]:
    user = session.exec(
        select(User).where(
            User.provider == provider,
            User.provider_sub == provider_sub
        )
    ).first()
    return user