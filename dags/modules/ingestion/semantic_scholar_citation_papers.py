from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Tuple

import requests
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Variable
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", re.IGNORECASE)


def _get_s2_api_key() -> str | None:
    try:
        return Variable.get("SEMANTIC_SCHOLAR_API_KEY")
    except Exception:
        return os.getenv("SEMANTIC_SCHOLAR_API_KEY")


def _s2_headers() -> Dict[str, str]:
    api_key = _get_s2_api_key()
    return {"x-api-key": api_key} if api_key else {}


def _normalize_arxiv_id(raw: str | None) -> str | None:
    if not raw:
        return None

    value = raw.strip()
    if not value:
        return None

    if value.lower().startswith("arxiv:"):
        value = value.split(":", 1)[1].strip()

    value = value.removesuffix(".pdf")
    return value or None


def _extract_arxiv_id_from_raw_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    match = ARXIV_URL_RE.search(raw_url)
    if not match:
        return None
    return _normalize_arxiv_id(match.group(1))


def _candidate_keys(arxiv_id: str | None) -> List[str]:
    normalized = _normalize_arxiv_id(arxiv_id)
    if not normalized:
        return []

    keys = [normalized]
    base = normalized.split("v", 1)[0] if "v" in normalized else normalized
    if base != normalized:
        keys.append(base)
    return keys


def _post_with_retry(
    url: str,
    *,
    params: Dict[str, str],
    json_body: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int = 30,
    max_retries: int = 8,
    base_sleep: float = 1.0,
    max_sleep: float = 60.0,
) -> requests.Response:
    sleep = base_sleep
    last_resp: requests.Response | None = None

    for attempt in range(1, max_retries + 1):
        resp = requests.post(url, params=params, headers=headers, json=json_body, timeout=timeout)
        last_resp = resp

        if resp.status_code < 400:
            return resp

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after and retry_after.isdigit()) else sleep
            wait = min(wait, max_sleep)
            logger.warning("S2 rate limited (429). attempt=%s/%s wait=%ss", attempt, max_retries, wait)
            time.sleep(wait)
            sleep = min(sleep * 2, max_sleep)
            continue

        if 500 <= resp.status_code < 600:
            wait = min(sleep, max_sleep)
            logger.warning(
                "S2 server error %s. attempt=%s/%s wait=%ss",
                resp.status_code,
                attempt,
                max_retries,
                wait,
            )
            time.sleep(wait)
            sleep = min(sleep * 2, max_sleep)
            continue

        resp.raise_for_status()

    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError("Semantic Scholar request failed with retries exhausted.")


def fill_papers_citations_for_nulls(
    hook: PostgresHook,
    batch_size: int = 200,
    sleep_seconds: float = 1.0,
) -> None:
    """
    papers.citation_count IS NULL 인 arxiv 논문을 대상으로 citationCount를 채운다.
    업데이트가 불가능한 행도 citation_updated_at을 남겨 무한 반복을 방지한다.
    """
    conn = hook.get_conn()
    conn.autocommit = False

    select_sql = """
        SELECT p.id, p.raw_url, pp.external_id
        FROM public.papers p
        LEFT JOIN public.paper_pool pp ON pp.id = p.paper_pool_id
        WHERE p.source = 'arxiv'
          AND p.citation_count IS NULL
          AND p.citation_updated_at IS NULL
        ORDER BY p.id
        LIMIT %s
    """

    update_count_sql = """
        UPDATE public.papers
        SET citation_count = %s,
            citation_updated_at = NOW()
        WHERE id = %s
    """

    mark_attempt_sql = """
        UPDATE public.papers
        SET citation_updated_at = NOW()
        WHERE id = %s
    """

    try:
        with conn.cursor() as cur:
            total_updated = 0
            total_marked = 0

            while True:
                cur.execute(select_sql, (batch_size,))
                rows: List[Tuple[int, str | None, str | None]] = cur.fetchall()
                if not rows:
                    logger.info("No more rows to attempt for papers citation update.")
                    break

                paper_id_by_key: Dict[str, int] = {}
                s2_ids: List[str] = []

                for paper_id, raw_url, external_id in rows:
                    arxiv_id = _normalize_arxiv_id(external_id) or _extract_arxiv_id_from_raw_url(raw_url)
                    if not arxiv_id:
                        continue

                    s2_ids.append(f"arxiv:{arxiv_id}")
                    for key in _candidate_keys(arxiv_id):
                        paper_id_by_key.setdefault(key, int(paper_id))

                updates: List[Tuple[int, int]] = []
                updated_ids: set[int] = set()

                if s2_ids:
                    resp = _post_with_retry(
                        S2_BATCH_URL,
                        params={"fields": "externalIds,citationCount"},
                        json_body={"ids": s2_ids},
                        headers=_s2_headers(),
                        timeout=30,
                        max_retries=8,
                        base_sleep=1.0,
                        max_sleep=60.0,
                    )
                    data = resp.json()

                    for item in data:
                        if not item:
                            continue

                        count = item.get("citationCount")
                        if count is None:
                            continue

                        external_ids = item.get("externalIds") or {}
                        arxiv_id = _normalize_arxiv_id(external_ids.get("ArXiv"))
                        if not arxiv_id:
                            continue

                        paper_id = None
                        for key in _candidate_keys(arxiv_id):
                            paper_id = paper_id_by_key.get(key)
                            if paper_id is not None:
                                break

                        if paper_id is None:
                            continue

                        updates.append((int(count), int(paper_id)))
                        updated_ids.add(int(paper_id))

                if updates:
                    execute_batch(cur, update_count_sql, updates, page_size=200)
                    total_updated += len(updates)

                to_mark = [(paper_id,) for (paper_id, _, _) in rows if paper_id not in updated_ids]
                if to_mark:
                    execute_batch(cur, mark_attempt_sql, to_mark, page_size=200)
                    total_marked += len(to_mark)

                conn.commit()
                logger.info(
                    "Papers citation batch done. fetched=%s updated=%s marked_attempt=%s",
                    len(rows),
                    len(updates),
                    len(to_mark),
                )
                time.sleep(sleep_seconds)

            logger.info(
                "Completed papers citation fill. total_updated=%s total_marked_attempt=%s",
                total_updated,
                total_marked,
            )

    except Exception:
        conn.rollback()
        logger.exception("Failed updating papers citation counts")
        raise
    finally:
        conn.close()
