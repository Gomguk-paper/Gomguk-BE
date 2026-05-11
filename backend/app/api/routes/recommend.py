from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.crud.recommendation import apply_interaction_event
from app.models.paper import Paper

router = APIRouter()

InteractionEventType = Literal["impression", "view", "like", "unlike", "save", "unsave"]
InteractionSurface = Literal["feed", "search"]


class InteractionBulkEvent(BaseModel):
    type: InteractionEventType
    request_id: str = Field(min_length=1, max_length=255)
    paper_id: int = Field(ge=1)
    surface: InteractionSurface = "feed"
    position: int = Field(0, ge=0)
    visible_ms: int | None = Field(None, ge=0)
    visible_ratio_max: float | None = Field(None, ge=0.0, le=1.0)
    dwell_ms: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def set_type_defaults(self) -> "InteractionBulkEvent":
        if self.type == "impression":
            if self.visible_ms is None:
                self.visible_ms = 0
            if self.visible_ratio_max is None:
                self.visible_ratio_max = 0.0
        return self


class InteractionBulkBody(BaseModel):
    events: list[InteractionBulkEvent] = Field(default_factory=list, max_length=500)


class InteractionBulkResponse(BaseModel):
    processed_count: int


@router.post(
    "/interaction/bulk",
    response_model=InteractionBulkResponse,
    summary="Bulk upsert recommendation interactions",
    responses={
        401: {"description": "AUTH_REQUIRED"},
        404: {"description": "PAPER_NOT_FOUND"},
        422: {"description": "Validation Error"},
        500: {"description": "Internal Server Error"},
    },
)
def bulk_interactions(
    session: SessionDep,
    user: CurrentUser,
    body: InteractionBulkBody,
) -> InteractionBulkResponse:
    if not body.events:
        return InteractionBulkResponse(processed_count=0)

    paper_ids = sorted({event.paper_id for event in body.events})
    existing_paper_ids = set(
        session.exec(select(Paper.id).where(Paper.id.in_(paper_ids))).all()
    )
    missing_paper_ids = [paper_id for paper_id in paper_ids if paper_id not in existing_paper_ids]
    if missing_paper_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PAPER_NOT_FOUND", "paper_ids": missing_paper_ids},
        )

    for event in body.events:
        apply_interaction_event(
            session,
            user_id=user.id,
            event_type=event.type,
            request_id=event.request_id,
            paper_id=event.paper_id,
            surface=event.surface,
            position=event.position,
            visible_ms=event.visible_ms,
            visible_ratio_max=event.visible_ratio_max,
            dwell_ms=event.dwell_ms,
        )

    session.commit()
    return InteractionBulkResponse(processed_count=len(body.events))
