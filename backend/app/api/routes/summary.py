from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser
from app.core.enums import SummaryStyle
from app.models.paper import Paper, PaperSummary

router = APIRouter()


# =========================
# Response Schemas
# =========================
class SummaryResponse(BaseModel):
    style: str
    hook: str
    points: list[str]
    detailed: str


# =========================
# Helpers
# =========================
def _style_to_str(style: Any) -> str:
    return style.value if hasattr(style, "value") else str(style)


def _parse_summary_style(style: str) -> SummaryStyle:
    """
    Query로 들어온 style(str)을 SummaryStyle로 변환.
    - enum value 매칭 우선 (ex: "plain")
    - 실패 시 enum name 매칭도 시도 (ex: "PLAIN")
    """
    try:
        return SummaryStyle(style)
    except Exception:
        try:
            return SummaryStyle[style.upper()]
        except Exception:
            raise HTTPException(status_code=422, detail="INVALID_STYLE")


# =========================
# Routes
# =========================
@router.get(
    "/{paper_id}",
    summary="특정 논문의 요약 조회",
    response_model=SummaryResponse,
    responses={
        401: {"description": "AUTH_REQUIRED (토큰 없음/만료/유효하지 않음)"},
        404: {"description": "NOT_FOUND (paper 또는 summary 없음)"},
        500: {"description": "Internal Server Error"},
    },
)
def get_summary(
    session: SessionDep,
    user: CurrentUser,
    paper_id: int,
    style: str = Query("plain"),
):
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    style_enum = _parse_summary_style(style)

    stmt = (
        select(PaperSummary)
        .where(PaperSummary.paper_id == paper_id)
        .where(PaperSummary.style == style_enum)
        .order_by(PaperSummary.created_at.desc())
    )
    s = session.exec(stmt).first()
    if s is None:
        raise HTTPException(status_code=404, detail="Summary not found")

    return SummaryResponse(
        style=_style_to_str(s.style),
        hook=s.hook,
        points=s.points or [],
        detailed=s.detailed,
    )
