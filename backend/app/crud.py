from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from typing import Optional

from app.models.user import User
from app.models.paper import Paper
from app.schemas.PaperRead import PaperRead
from app.core.enums import AuthProvider
from app.api.deps import SessionDep


def create_user(
    session: SessionDep,
    provider: AuthProvider,
    provider_sub: str,
    email: str,
    nickname: str
) -> Optional[User]:
    user = User(
        provider=provider,
        provider_sub=provider_sub,
        email=email,
        nickname=nickname,
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

def get_paper_by_id(
        session: SessionDep,
        paper_id: int
) -> Optional[PaperRead]:
    paper = session.exec(
        select(Paper)
        .where(Paper.id == paper_id)
        .options(selectinload(Paper.tags))
    ).first()

    paper_read = PaperRead(
        id=paper.id,
        title=paper.title,
        short=paper.short,
        authors=list(paper.authors or []),
        published_at=paper.published_at,
        image_url=paper.image_url,
        raw_url=paper.raw_url,
        source=paper.source,
        tags=[t.name for t in (paper.tags or [])],
    )
    return paper_read