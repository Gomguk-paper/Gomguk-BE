from __future__ import annotations

from collections import defaultdict
from typing import Optional, Any, Literal

from sqlalchemy import func, or_, select as sa_select, text as sa_text
from sqlmodel import select

from app.api.deps import SessionDep
from app.core.enums import Site
from app.models.paper import Paper, PaperTag
from app.models.user import UserPaperLike, UserPaperScrap
from app.schemas.paper import PaperOut


SortKey = Literal["popular", "recent"]
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
        citation_count=paper.citation_count,
    )


# =========================
# PaperOut (batched for a page)
# =========================
def get_paper_outs_by_ids(
    session: SessionDep,
    *,
    user_id: int,
    paper_ids: list[int],
    scores_map: Optional[dict[int, tuple[float, float, float]]] = None,
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

    outs: list[PaperOut] = []
    for pid in paper_ids:
        p = paper_map.get(pid)
        if p is None:
            continue

        scores = scores_map.get(pid) if scores_map else None
        outs.append(
            PaperOut(
                id=p.id,
                title=p.title,
                short=p.short,
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
                citation_count=p.citation_count,
                recommend_score=round(scores[0], 4) if scores else None,
                trending_score=round(scores[1], 4) if scores else None,
                freshness_score=round(scores[2], 4) if scores else None,
            )
        )

    return outs


# =========================
# Global trending
# =========================
def get_top_global_trending_papers(
    session: SessionDep,
    *,
    limit: int,
    offset: int = 0,
) -> list[tuple[int, float]]:
    """
    전역 트렌딩 점수(popularity) 기준 상위 paper 목록 반환.
    returns: [(paper_id, trending_score), ...]
    """
    sql = sa_text("""
    WITH paper_popularity AS (
        SELECT
            p.id AS paper_id,
            LEAST(
                LN(1 + COALESCE(lc.cnt, 0) + 2 * COALESCE(sc.cnt, 0)) / LN(101),
                1.0
            ) AS trending_score
        FROM papers p
        LEFT JOIN (
            SELECT l.paper_id, COUNT(*) AS cnt
            FROM user_paper_likes l
            GROUP BY l.paper_id
        ) lc ON lc.paper_id = p.id
        LEFT JOIN (
            SELECT s.paper_id, COUNT(*) AS cnt
            FROM user_paper_scraps s
            GROUP BY s.paper_id
        ) sc ON sc.paper_id = p.id
    )
    SELECT paper_id, trending_score
    FROM paper_popularity
    ORDER BY trending_score DESC, paper_id DESC
    OFFSET :off LIMIT :lim
    """)

    rows = session.execute(sql, {"off": offset, "lim": limit}).all()
    return [(int(row[0]), float(row[1])) for row in rows]


# =========================
# Recommendation scoring
# =========================
def _recommend_paper_ids(
    session: SessionDep,
    *,
    user_id: int,
    limit: int,
    offset: int,
    q: Optional[str] = None,
    tag: Optional[int] = None,
    source: Optional[Site] = None,
) -> tuple[list[int], int, dict[int, tuple[float, float, float]]]:
    """
    추천 점수 기반 논문 ID 반환.
    score = 0.40 * tag_similarity + 0.25 * citation_norm + 0.25 * freshness - 0.10 * view_penalty

    Returns:
        (paper_ids, total, scores_map)
        scores_map: {paper_id: (recommend_score, trending_score, freshness_score)}

    Cold-start: 이력 0건이면 tag_similarity=0 → 인기+최신 기반 정렬로 자연 fallback.
    """
    filters = []
    params: dict[str, Any] = {"user_id": user_id, "lim": limit, "off": offset}

    if q:
        filters.append("p.title ILIKE :q")
        params["q"] = f"%{q}%"
    if tag is not None:
        filters.append(
            "EXISTS (SELECT 1 FROM paper_tags ft"
            " WHERE ft.paper_id = p.id AND ft.tag_id = :filter_tag)"
        )
        params["filter_tag"] = tag
    if source is not None:
        filters.append("p.source = :source")
        params["source"] = _source_to_str(source)

    where_clause = " AND ".join(filters) if filters else "TRUE"

    sql = sa_text(f"""
    WITH user_tag_profile_raw AS (
        -- 인터랙션 기반 (좋아요/스크랩)
        SELECT pt.tag_id, SUM(w) AS preference
        FROM (
            SELECT paper_id, 1.0 AS w FROM user_paper_likes WHERE user_id = :user_id
            UNION ALL
            SELECT paper_id, 1.5 AS w FROM user_paper_scraps WHERE user_id = :user_id
        ) interactions
        JOIN paper_tags pt ON pt.paper_id = interactions.paper_id
        GROUP BY pt.tag_id

        UNION ALL

        -- 온보딩 태그 (user.meta['tag_prefs'])
        SELECT (key::int) AS tag_id, (value::numeric) AS preference
        FROM users u, jsonb_each_text(COALESCE(u.meta->'tag_prefs', '{{}}'::jsonb))
        WHERE u.id = :user_id
    ),
    user_tag_profile AS (
        SELECT tag_id, SUM(preference) AS preference
        FROM user_tag_profile_raw
        GROUP BY tag_id
    ),
    profile_norm AS (
        SELECT GREATEST(COALESCE(SUM(preference), 0), 1.0) AS total_pref FROM user_tag_profile
    ),
    candidates AS (
        SELECT p.id AS paper_id, p.published_at, p.citation_count
        FROM papers p
        WHERE {where_clause}
    ),
    paper_tag_score AS (
        SELECT c.paper_id,
               LEAST(COALESCE(SUM(utp.preference), 0) / pn.total_pref, 1.0) AS tag_sim
        FROM candidates c
        LEFT JOIN paper_tags pt ON pt.paper_id = c.paper_id
        LEFT JOIN user_tag_profile utp ON utp.tag_id = pt.tag_id
        CROSS JOIN profile_norm pn
        GROUP BY c.paper_id, pn.total_pref
    ),
    paper_citation_raw AS (
        SELECT c.paper_id,
               LN(COALESCE(c.citation_count, 0) + 1)
               / SQRT(GREATEST(1, EXTRACT(YEAR FROM NOW()) - EXTRACT(YEAR FROM c.published_at)) + 8)
               AS raw_cite
        FROM candidates c
    ),
    paper_citation AS (
        SELECT paper_id,
               raw_cite / GREATEST(MAX(raw_cite) OVER(), 1e-9) AS citation_norm
        FROM paper_citation_raw
    ),
    paper_freshness AS (
        SELECT c.paper_id,
               1.0 / POWER(1 + EXTRACT(EPOCH FROM (NOW() - c.published_at)) / 86400.0, 0.5) AS freshness
        FROM candidates c
    ),
    paper_view_penalty AS (
        SELECT c.paper_id,
               CASE
                   WHEN v.last_viewed_at IS NULL THEN 0
                   WHEN v.last_viewed_at > NOW() - INTERVAL '24 hours' THEN 1.0
                   WHEN v.last_viewed_at > NOW() - INTERVAL '7 days' THEN 0.5
                   ELSE 0.2
               END AS view_pen
        FROM candidates c
        LEFT JOIN user_paper_views v
            ON v.paper_id = c.paper_id AND v.user_id = :user_id
    ),
    scored AS (
        SELECT
            ts.paper_id,
            0.40 * COALESCE(ts.tag_sim, 0)
            + 0.25 * COALESCE(pc.citation_norm, 0)
            + 0.25 * COALESCE(pf.freshness, 0)
            - 0.10 * COALESCE(vp.view_pen, 0) AS score,
            COALESCE(pc.citation_norm, 0) AS trending,
            COALESCE(pf.freshness, 0) AS freshness
        FROM paper_tag_score ts
        JOIN paper_citation pc ON pc.paper_id = ts.paper_id
        JOIN paper_freshness pf ON pf.paper_id = ts.paper_id
        JOIN paper_view_penalty vp ON vp.paper_id = ts.paper_id
    )
    SELECT paper_id, score, COUNT(*) OVER() AS total, trending, freshness
    FROM scored
    ORDER BY score DESC, paper_id DESC
    OFFSET :off LIMIT :lim
    """)

    rows = session.execute(sql, params).all()

    if not rows:
        return [], 0, {}

    paper_ids = [row[0] for row in rows]
    total = rows[0][2]
    # {paper_id: (recommend_score, trending_score, freshness_score)}
    scores_map = {
        row[0]: (float(row[1]), float(row[3]), float(row[4]))
        for row in rows
    }

    return paper_ids, total, scores_map


# =========================
# Sorting (only for /papers/)
# =========================
def _apply_list_sort(stmt, *, sort: SortKey):
    """
    /papers/ 전용 정렬 (popular / recent)
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

    # recent (default)
    return stmt.order_by(Paper.published_at.desc(), Paper.id.desc())


# =========================
# Pages: /papers/ and /papers/feed
# =========================
def list_paper_outs_page(
    session: SessionDep,
    *,
    user_id: int,
    q: Optional[str],
    tags: Optional[list[int]],
    source: Optional[Site],
    sort: SortKey,
    limit: int,
    offset: int,
) -> tuple[list[PaperOut], int]:
    """
    /papers/ 목록 조회
    - 필터(q/tag/source) 적용
    - sort 적용(popular/recent)
    - limit/offset 페이징
    - PaperOut은 배치로 조립
    """
    base = select(Paper)

    if tags:
        normalized_tags = list(dict.fromkeys(tags))
        tag_subq = (
            select(PaperTag.paper_id)
            .where(PaperTag.tag_id.in_(normalized_tags))
            .group_by(PaperTag.paper_id)
            .having(func.count(func.distinct(PaperTag.tag_id)) == len(normalized_tags))
            .subquery()
        )
        base = base.join(tag_subq, tag_subq.c.paper_id == Paper.id)

    if q:
        pattern = f"%{q}%"
        base = base.where(or_(Paper.title.ilike(pattern), Paper.short.ilike(pattern)))

    if source is not None:
        base = base.where(Paper.source == source)

    base = _apply_list_sort(base, sort=sort)

    page_stmt = base.offset(offset).limit(limit)
    papers = session.exec(page_stmt).all()
    paper_ids = [p.id for p in papers]

    # total (필터 반영)
    subq = base.subquery()
    total = session.exec(sa_select(func.count()).select_from(subq)).scalar_one()

    return get_paper_outs_by_ids(session, user_id=user_id, paper_ids=paper_ids), total


def feed_paper_outs_page(
    session: SessionDep,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[PaperOut], int]:
    """
    /papers/feed — 추천 점수 기반 개인화 피드.
    Cold-start 사용자는 인기+최신 기반으로 자연 fallback.
    """
    paper_ids, total, scores_map = _recommend_paper_ids(
        session,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return get_paper_outs_by_ids(
        session, user_id=user_id, paper_ids=paper_ids, scores_map=scores_map,
    ), total
