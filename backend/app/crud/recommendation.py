from uuid import uuid4

from sqlmodel import Session, select

from app.models.recommendation import Interaction
from app.models.user import UserPaperLike, UserPaperScrap


def create_request_id() -> str:
    return str(uuid4())


def get_interaction(
    session: Session,
    *,
    user_id: int,
    request_id: str,
    paper_id: int,
) -> Interaction | None:
    return session.exec(
        select(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.request_id == request_id,
            Interaction.paper_id == paper_id,
        )
    ).first()


def get_or_create_interaction(
    session: Session,
    *,
    user_id: int,
    request_id: str,
    paper_id: int,
    surface: str,
    position: int,
) -> Interaction:
    interaction = get_interaction(
        session,
        user_id=user_id,
        request_id=request_id,
        paper_id=paper_id,
    )
    if interaction is not None:
        return interaction

    interaction = Interaction(
        user_id=user_id,
        request_id=request_id,
        paper_id=paper_id,
        surface=surface,
        position=position,
        interaction_type=0,
        visible_ms=0,
        visible_ratio_max=0,
    )
    session.add(interaction)
    session.flush()
    return interaction


def apply_interaction_event(
    session: Session,
    *,
    user_id: int,
    event_type: str,
    request_id: str,
    paper_id: int,
    surface: str,
    position: int,
    visible_ms: int | None = None,
    visible_ratio_max: float | None = None,
    dwell_ms: int | None = None,
) -> Interaction:
    interaction = get_or_create_interaction(
        session,
        user_id=user_id,
        request_id=request_id,
        paper_id=paper_id,
        surface=surface,
        position=position,
    )

    if event_type == "impression":
        if visible_ms is not None:
            interaction.visible_ms = max(interaction.visible_ms, visible_ms)
        if visible_ratio_max is not None:
            interaction.visible_ratio_max = max(float(interaction.visible_ratio_max), visible_ratio_max)
    elif event_type == "view":
        interaction.interaction_type = max(interaction.interaction_type, 1)
        if dwell_ms is not None:
            interaction.dwell_ms = max(interaction.dwell_ms or 0, dwell_ms)
    elif event_type == "like":
        interaction.is_liked = True
        _upsert_user_paper_like(session, user_id=user_id, paper_id=paper_id)
    elif event_type == "unlike":
        interaction.is_liked = False
        _delete_user_paper_like(session, user_id=user_id, paper_id=paper_id)
    elif event_type == "save":
        interaction.is_scrapped = True
        _upsert_user_paper_scrap(session, user_id=user_id, paper_id=paper_id)
    elif event_type == "unsave":
        interaction.is_scrapped = False
        _delete_user_paper_scrap(session, user_id=user_id, paper_id=paper_id)

    session.add(interaction)
    return interaction


def _upsert_user_paper_like(session: Session, *, user_id: int, paper_id: int) -> None:
    existing = session.get(UserPaperLike, (user_id, paper_id))
    if existing is None:
        session.add(UserPaperLike(user_id=user_id, paper_id=paper_id))


def _delete_user_paper_like(session: Session, *, user_id: int, paper_id: int) -> None:
    existing = session.get(UserPaperLike, (user_id, paper_id))
    if existing is not None:
        session.delete(existing)


def _upsert_user_paper_scrap(session: Session, *, user_id: int, paper_id: int) -> None:
    existing = session.get(UserPaperScrap, (user_id, paper_id))
    if existing is None:
        session.add(UserPaperScrap(user_id=user_id, paper_id=paper_id))


def _delete_user_paper_scrap(session: Session, *, user_id: int, paper_id: int) -> None:
    existing = session.get(UserPaperScrap, (user_id, paper_id))
    if existing is not None:
        session.delete(existing)
