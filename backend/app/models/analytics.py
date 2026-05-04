from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DailyActiveUserStat(SQLModel, table=True):
    __tablename__ = "daily_active_user_stats"

    stat_date: date = Field(sa_column=Column(Date, primary_key=True, nullable=False))
    active_users: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0, server_default="0"))
    new_users: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0, server_default="0"))
    returning_users: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0, server_default="0"))
    calculated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RetentionStat(SQLModel, table=True):
    __tablename__ = "retention_stats"
    __table_args__ = (
        UniqueConstraint("cohort_date", "retention_day", name="uq_retention_stats_cohort_day"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cohort_date: date = Field(sa_column=Column(Date, nullable=False, index=True))
    retention_day: int = Field(sa_column=Column(Integer, nullable=False))
    cohort_size: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0, server_default="0"))
    retained_users: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0, server_default="0"))
    retention_rate: float = Field(default=0, sa_column=Column(Numeric(6, 4), nullable=False, default=0, server_default="0"))
    calculated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class FunnelStat(SQLModel, table=True):
    __tablename__ = "funnel_stats"
    __table_args__ = (
        UniqueConstraint("stat_date", "funnel_name", "step_name", name="uq_funnel_stats_date_step"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    stat_date: date = Field(sa_column=Column(Date, nullable=False, index=True))
    funnel_name: str = Field(sa_column=Column(String(length=100), nullable=False))
    step_name: str = Field(sa_column=Column(String(length=100), nullable=False))
    step_order: int = Field(sa_column=Column(Integer, nullable=False))
    user_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0, server_default="0"))
    # Current default funnel: login -> view -> save.
    conversion_rate: float = Field(default=0, sa_column=Column(Numeric(6, 4), nullable=False, default=0, server_default="0"))
    calculated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
