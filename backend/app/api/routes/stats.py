from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import SessionDep
from app.models.analytics import DailyActiveUserStat, FunnelStat, RetentionStat

router = APIRouter()


# =========================
# Response Schemas
# =========================
class DailyActiveUserStatOut(BaseModel):
    stat_date: date
    active_users: int
    new_users: int
    returning_users: int
    calculated_at: datetime


class DauStatsResponse(BaseModel):
    items: list[DailyActiveUserStatOut]
    count: int


class RetentionStatOut(BaseModel):
    cohort_date: date
    retention_day: int
    cohort_size: int
    retained_users: int
    retention_rate: float
    calculated_at: datetime


class RetentionStatsResponse(BaseModel):
    items: list[RetentionStatOut]
    count: int


class FunnelStatOut(BaseModel):
    stat_date: date
    funnel_name: str
    step_name: str
    step_order: int
    user_count: int
    conversion_rate: float
    calculated_at: datetime


class FunnelStatsResponse(BaseModel):
    items: list[FunnelStatOut]
    count: int


# =========================
# Helpers
# =========================
def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _default_start_date() -> date:
    return _utc_today() - timedelta(days=6)


def _default_end_date() -> date:
    return _utc_today()


def _default_cohort_date() -> date:
    return _utc_today() - timedelta(days=1)


def _to_dau_stat_out(row: DailyActiveUserStat) -> DailyActiveUserStatOut:
    return DailyActiveUserStatOut(
        stat_date=row.stat_date,
        active_users=row.active_users,
        new_users=row.new_users,
        returning_users=row.returning_users,
        calculated_at=row.calculated_at,
    )


def _to_retention_stat_out(row: RetentionStat) -> RetentionStatOut:
    return RetentionStatOut(
        cohort_date=row.cohort_date,
        retention_day=row.retention_day,
        cohort_size=row.cohort_size,
        retained_users=row.retained_users,
        retention_rate=float(row.retention_rate),
        calculated_at=row.calculated_at,
    )


def _to_funnel_stat_out(row: FunnelStat) -> FunnelStatOut:
    return FunnelStatOut(
        stat_date=row.stat_date,
        funnel_name=row.funnel_name,
        step_name=row.step_name,
        step_order=row.step_order,
        user_count=row.user_count,
        conversion_rate=float(row.conversion_rate),
        calculated_at=row.calculated_at,
    )


# =========================
# Routes
# =========================
@router.get(
    "/dau",
    summary="List daily active user stats",
    response_model=DauStatsResponse,
    responses={
        500: {"description": "Internal Server Error"},
    },
)
def list_dau_stats(
    session: SessionDep,
    start_date: date = Query(default_factory=_default_start_date),
    end_date: date = Query(default_factory=_default_end_date),
):
    stmt = select(DailyActiveUserStat)

    stmt = stmt.where(DailyActiveUserStat.stat_date >= start_date)
    stmt = stmt.where(DailyActiveUserStat.stat_date <= end_date)

    rows = session.exec(
        stmt.order_by(DailyActiveUserStat.stat_date.asc())
    ).all()

    return DauStatsResponse(
        items=[_to_dau_stat_out(row) for row in rows],
        count=len(rows),
    )


@router.get(
    "/retention",
    summary="List retention stats",
    response_model=RetentionStatsResponse,
    responses={
        500: {"description": "Internal Server Error"},
    },
)
def list_retention_stats(
    session: SessionDep,
    cohort_date: date = Query(default_factory=_default_cohort_date),
):
    rows = session.exec(
        select(RetentionStat).where(
            RetentionStat.cohort_date == cohort_date
        ).order_by(
            RetentionStat.cohort_date.asc(),
            RetentionStat.retention_day.asc(),
        )
    ).all()

    return RetentionStatsResponse(
        items=[_to_retention_stat_out(row) for row in rows],
        count=len(rows),
    )


@router.get(
    "/funnel",
    summary="List funnel stats",
    response_model=FunnelStatsResponse,
    responses={
        500: {"description": "Internal Server Error"},
    },
)
def list_funnel_stats(
    session: SessionDep,
    start_date: date = Query(default_factory=_default_start_date),
    end_date: date = Query(default_factory=_default_end_date),
    funnel_name: str | None = Query(None),
):
    stmt = select(FunnelStat)

    stmt = stmt.where(FunnelStat.stat_date >= start_date)
    stmt = stmt.where(FunnelStat.stat_date <= end_date)
    if funnel_name:
        stmt = stmt.where(FunnelStat.funnel_name == funnel_name)

    rows = session.exec(
        stmt.order_by(
            FunnelStat.stat_date.asc(),
            FunnelStat.funnel_name.asc(),
            FunnelStat.step_order.asc(),
        )
    ).all()

    return FunnelStatsResponse(
        items=[_to_funnel_stat_out(row) for row in rows],
        count=len(rows),
    )
