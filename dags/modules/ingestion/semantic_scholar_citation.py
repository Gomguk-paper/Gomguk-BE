# modules/ingestion/semantic_scholar_citation.py

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Tuple

import requests
from psycopg2.extras import execute_batch
from airflow.providers.postgres.hooks.postgres import PostgresHook

# Airflow 3.x 권장 (airflow.models.Variable.get deprecated 대응)
from airflow.sdk import Variable

logger = logging.getLogger(__name__)

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"


def _get_s2_api_key() -> str | None:
    try:
        return Variable.get("SEMANTIC_SCHOLAR_API_KEY")
    except Exception:
        return os.getenv("SEMANTIC_SCHOLAR_API_KEY")


def _s2_headers() -> Dict[str, str]:
    api_key = _get_s2_api_key()
    return {"x-api-key": api_key} if api_key else {}


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
    """
    429/5xx 등에서 재시도.
    - 429이면 Retry-After 우선 준수
    - 그 외는 지수 백오프
    """
    sleep = base_sleep
    last_resp: requests.Response | None = None

    for attempt in range(1, max_retries + 1):
        resp = requests.post(url, params=params, headers=headers, json=json_body, timeout=timeout)
        last_resp = resp

        # success
        if resp.status_code < 400:
            return resp

        # 429: Too Many Requests
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after and retry_after.isdigit()) else sleep
            wait = min(wait, max_sleep)
            logger.warning("S2 rate limited (429). attempt=%s/%s wait=%ss", attempt, max_retries, wait)
            time.sleep(wait)
            sleep = min(sleep * 2, max_sleep)
            continue

        # 5xx: server errors -> retry
        if 500 <= resp.status_code < 600:
            wait = min(sleep, max_sleep)
            logger.warning("S2 server error %s. attempt=%s/%s wait=%ss", resp.status_code, attempt, max_retries, wait)
            time.sleep(wait)
            sleep = min(sleep * 2, max_sleep)
            continue

        # other 4xx -> fail fast
        resp.raise_for_status()

    # retries exhausted
    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError("Semantic Scholar request failed with retries exhausted, but no response object.")


def fill_citations_for_nulls(
    hook: PostgresHook,
    batch_size: int = 200,          # 500 -> 200 권장
    sleep_seconds: float = 1.0,     # 배치 간 텀
) -> None:
    """
    paper_pool에서 citation_count IS NULL 인 arxiv 논문만 대상으로
    Semantic Scholar batch API로 citationCount를 채웁니다.
    """
    conn = hook.get_conn()
    conn.autocommit = False

    select_sql = """
        SELECT id, external_id
        FROM public.paper_pool
        WHERE source = 'arxiv'
          AND citation_count IS NULL
        ORDER BY id
        LIMIT %s
    """

    update_sql = """
        UPDATE public.paper_pool
        SET citation_count = %s,
            citation_updated_at = NOW()
        WHERE id = %s
    """

    try:
        with conn.cursor() as cur:
            total_updated = 0

            while True:
                cur.execute(select_sql, (batch_size,))
                rows: List[Tuple[int, str]] = cur.fetchall()
                if not rows:
                    logger.info("No more rows to update for citations.")
                    break

                id_by_arxiv: Dict[str, int] = {external_id: pid for (pid, external_id) in rows}
                s2_ids = [f"arxiv:{external_id}" for (_, external_id) in rows]

                params = {"fields": "externalIds,citationCount"}

                resp = _post_with_retry(
                    S2_BATCH_URL,
                    params=params,
                    json_body={"ids": s2_ids},
                    headers=_s2_headers(),
                    timeout=30,
                    max_retries=8,
                    base_sleep=1.0,
                    max_sleep=60.0,
                )
                data = resp.json()

                updates: List[Tuple[int, int]] = []
                for item in data:
                    if not item:
                        continue
                    external_ids = item.get("externalIds") or {}
                    arxiv_id = external_ids.get("ArXiv")
                    if not arxiv_id:
                        continue

                    count = item.get("citationCount")
                    if count is None:
                        continue

                    paper_id = id_by_arxiv.get(arxiv_id)
                    if paper_id is None:
                        continue

                    updates.append((int(count), int(paper_id)))

                if updates:
                    execute_batch(cur, update_sql, updates, page_size=200)
                    conn.commit()
                    total_updated += len(updates)
                    logger.info("Updated citationCount rows=%s (batch fetched=%s)", len(updates), len(rows))
                else:
                    conn.commit()
                    logger.warning("No citation updates mapped in this batch (batch fetched=%s).", len(rows))

                time.sleep(sleep_seconds)

            logger.info("Completed citation fill. total_updated=%s", total_updated)

    except Exception:
        conn.rollback()
        logger.exception("Failed updating citation counts")
        raise
    finally:
        conn.close()
