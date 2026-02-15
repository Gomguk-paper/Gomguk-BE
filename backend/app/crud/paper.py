from __future__ import annotations

from collections import defaultdict
from typing import Optional, Any, Literal

from sqlalchemy import func, select as sa_select
from sqlmodel import select

from app.api.deps import SessionDep
from app.core.enums import Site, SummaryStyle
from app.models.paper import Paper, PaperTag, PaperSummary
from app.models.user import UserPaperLike, UserPaperScrap
from app.schemas.paper import PaperOut


SortKey = Literal["popular", "recent", "recommend"]
S3_PAPERS_PREFIX = "s3://papers/"
PAPERS_PUBLIC_BASE = "http://gomguk.cloud/papers/"


# =========================
# Counts (single paper)
# =========================
def get_like_count_by_paper_id(session: SessionDep, paper_id: int) -> int:
    return session.exec(
        sa_select(func.count())
        .select_from(UserPaperLike)
        .where(UserPaperLike.paper_id == paper_id)
    ).scalar_one()


def get_scrap_count_by_paper_id(session: SessionDep, paper_id: int) -> int:
    return session.exec(
        sa_select(func.count())
        .select_from(UserPaperScrap)
        .where(UserPaperScrap.paper_id == paper_id)
    ).scalar_one()


# =========================
# Utils
# =========================
def _source_to_str(source: Any) -> str:
    return getattr(source, "value", str(source))


def _papers_s3_to_http(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith(S3_PAPERS_PREFIX):
        return PAPERS_PUBLIC_BASE + url[len(S3_PAPERS_PREFIX):]
    return url


def _points_to_short(points: list[str]) -> str:
    clean_points = [p.strip() for p in points if p and p.strip()]
    return "\n".join(clean_points)


def _get_latest_basic_aggro_summary_map(
    session: SessionDep,
    *,
    paper_ids: list[int],
) -> dict[int, PaperSummary]:
    if not paper_ids:
        return {}

    summary_rows = session.exec(
        select(PaperSummary)
        .where(PaperSummary.paper_id.in_(paper_ids), PaperSummary.style == SummaryStyle.basic_aggro)
        .order_by(PaperSummary.paper_id.asc(), PaperSummary.created_at.desc(), PaperSummary.id.desc())
    ).all()

    latest_by_paper_id: dict[int, PaperSummary] = {}
    for row in summary_rows:
        if row.paper_id not in latest_by_paper_id:
            latest_by_paper_id[row.paper_id] = row
    return latest_by_paper_id


# =========================
# PaperOut (single paper)
# =========================
def get_paper_out_by_id(
    session: SessionDep,
    *,
    user_id: int,
    paper_id: int,
) -> Optional[PaperOut]:
    """
    단건 PaperOut 조립 (디버그/상세용)
    """
    paper = session.exec(select(Paper).where(Paper.id == paper_id)).first()
    if paper is None:
        return None

    tag_ids = session.exec(
        select(PaperTag.tag_id)
        .where(PaperTag.paper_id == paper_id)
        .order_by(PaperTag.tag_id.asc())
    ).all()

    is_liked = (
        session.exec(
            select(UserPaperLike).where(
                UserPaperLike.user_id == user_id,
                UserPaperLike.paper_id == paper_id,
            )
        ).first()
        is not None
    )

    is_scrapped = (
        session.exec(
            select(UserPaperScrap).where(
                UserPaperScrap.user_id == user_id,
                UserPaperScrap.paper_id == paper_id,
            )
        ).first()
        is not None
    )

    like_count = get_like_count_by_paper_id(session, paper_id)
    scrap_count = get_scrap_count_by_paper_id(session, paper_id)

    return PaperOut(
        id=paper.id,
        title=paper.title,
        short=paper.short,
        authors=paper.authors,
        year=paper.published_at.year,
        image_url=_papers_s3_to_http(paper.image_url),
        raw_url=_papers_s3_to_http(paper.raw_url),
        source=_source_to_str(paper.source),
        tags=list(tag_ids),
        is_liked=is_liked,
        is_scrapped=is_scrapped,
        like_count=like_count,
        scrap_count=scrap_count,
    )


# =========================
# PaperOut (batched for a page)
# =========================
def get_paper_outs_by_ids(
    session: SessionDep,
    *,
    user_id: int,
    paper_ids: list[int],
    use_basic_aggro_display: bool = False,
) -> list[PaperOut]:
    """
    paper_ids(한 페이지)를 받아 PaperOut 리스트를 배치로 조립.
    - 페이지당 쿼리 수를 고정시키는 목적.
    - 반환 순서는 paper_ids 입력 순서를 따른다.
    """
    if not paper_ids:
        return []

    # papers
    papers = session.exec(select(Paper).where(Paper.id.in_(paper_ids))).all()
    paper_map = {p.id: p for p in papers}

    # tags
    tag_rows = session.exec(
        select(PaperTag.paper_id, PaperTag.tag_id)
        .where(PaperTag.paper_id.in_(paper_ids))
        .order_by(PaperTag.paper_id.asc(), PaperTag.tag_id.asc())
    ).all()
    tags_map: dict[int, list[int]] = defaultdict(list)
    for pid, tid in tag_rows:
        tags_map[pid].append(tid)

    # liked ids (user)
    liked_ids = set(
        session.exec(
            select(UserPaperLike.paper_id).where(
                UserPaperLike.user_id == user_id,
                UserPaperLike.paper_id.in_(paper_ids),
            )
        ).all()
    )

    # scrapped ids (user)
    scrapped_ids = set(
        session.exec(
            select(UserPaperScrap.paper_id).where(
                UserPaperScrap.user_id == user_id,
                UserPaperScrap.paper_id.in_(paper_ids),
            )
        ).all()
    )

    # like counts (global)
    like_rows = session.exec(
        select(UserPaperLike.paper_id, func.count().label("cnt"))
        .where(UserPaperLike.paper_id.in_(paper_ids))
        .group_by(UserPaperLike.paper_id)
    ).all()
    like_count_map = {pid: cnt for pid, cnt in like_rows}

    # scrap counts (global)
    scrap_rows = session.exec(
        select(UserPaperScrap.paper_id, func.count().label("cnt"))
        .where(UserPaperScrap.paper_id.in_(paper_ids))
        .group_by(UserPaperScrap.paper_id)
    ).all()
    scrap_count_map = {pid: cnt for pid, cnt in scrap_rows}

    summary_map = (
        _get_latest_basic_aggro_summary_map(session, paper_ids=paper_ids)
        if use_basic_aggro_display
        else {}
    )

    outs: list[PaperOut] = []
    for pid in paper_ids:
        p = paper_map.get(pid)
        if p is None:
            continue

        title = p.title
        short = p.short

        summary = summary_map.get(pid)
        if summary is not None:
            if summary.hook and summary.hook.strip():
                title = summary.hook.strip()
            points_short = _points_to_short(summary.points or [])
            if points_short:
                short = points_short

        outs.append(
            PaperOut(
                id=p.id,
                title=title,
                short=short,
                authors=p.authors,
                year=p.published_at.year,
                image_url=_papers_s3_to_http(p.image_url),
                raw_url=_papers_s3_to_http(p.raw_url),
                source=_source_to_str(p.source),
                tags=tags_map.get(pid, []),
                is_liked=(pid in liked_ids),
                is_scrapped=(pid in scrapped_ids),
                like_count=like_count_map.get(pid, 0),
                scrap_count=scrap_count_map.get(pid, 0),
            )
        )

    return outs


# =========================
# Sorting (only for /papers/)
# =========================
def _apply_list_sort(stmt, *, sort: SortKey):
    """
    /papers/ 전용 정렬
    - popular: 좋아요 수 desc (동률이면 추가 정렬 없음)
    - recent: published_at desc, id desc
    - recommend: (임시) recent 동일
    """
    if sort == "popular":
        like_counts = (
            select(
                UserPaperLike.paper_id,
                func.count().label("like_cnt"),
            )
            .group_by(UserPaperLike.paper_id)
            .subquery()
        )
        # 좋아요 없는 paper도 포함되게 outer join
        return stmt.outerjoin(like_counts, like_counts.c.paper_id == Paper.id).order_by(
            like_counts.c.like_cnt.desc().nullslast()
        )

    # recommend는 아직 미구현 → recent 동일
    return stmt.order_by(Paper.published_at.desc(), Paper.id.desc())


# =========================
# Pages: /papers/ and /papers/feed (temporary = recent)
# =========================
def list_paper_outs_page(
    session: SessionDep,
    *,
    user_id: int,
    q: Optional[str],
    tag: Optional[int],
    source: Optional[Site],
    sort: SortKey,
    limit: int,
    offset: int,
    use_basic_aggro_display: bool = False,
) -> tuple[list[PaperOut], int]:
    """
    /papers/ 목록 조회
    - 필터(q/tag/source) 적용
    - sort 적용(popular/recent/recommend(=recent))
    - limit/offset 페이징
    - PaperOut은 배치로 조립
    """
    base = select(Paper)

    if tag is not None:
        base = (
            select(Paper)
            .join(PaperTag, PaperTag.paper_id == Paper.id)
            .where(PaperTag.tag_id == tag)
        )

    if q:
        base = base.where(Paper.title.ilike(f"%{q}%"))

    if source is not None:
        base = base.where(Paper.source == source)

    base = _apply_list_sort(base, sort=sort)

    page_stmt = base.offset(offset).limit(limit)
    papers = session.exec(page_stmt).all()
    paper_ids = [p.id for p in papers]

    # total (필터 반영)
    subq = base.subquery()
    total = session.exec(sa_select(func.count()).select_from(subq)).scalar_one()

    return (
        get_paper_outs_by_ids(
            session,
            user_id=user_id,
            paper_ids=paper_ids,
            use_basic_aggro_display=use_basic_aggro_display,
        ),
        total,
    )


def feed_paper_outs_page(
    session: SessionDep,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[PaperOut], int]:
    """
    /papers/feed 임시 구현:
    - 추천시스템 아직 없음 → /papers/의 recent와 동일하게 최신순 페이징
    """
    outs, total = list_paper_outs_page(
        session,
        user_id=user_id,
        q=None,
        tag=None,
        source=None,
        sort="recent",
        limit=limit,
        offset=offset,
        use_basic_aggro_display=False,
    )
    return outs, total
