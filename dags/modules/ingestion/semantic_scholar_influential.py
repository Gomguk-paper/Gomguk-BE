from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Tuple

import requests
from psycopg2.extras import execute_batch
from airflow.providers.postgres.hooks.postgres import PostgresHook
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
    base_sleep: float = 2.0,
    max_sleep: float = 120.0,
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
            logger.warning("S2 server error %s. attempt=%s/%s wait=%ss", resp.status_code, attempt, max_retries, wait)
            time.sleep(wait)
            sleep = min(sleep * 2, max_sleep)
            continue

        resp.raise_for_status()

    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError("Semantic Scholar request failed with retries exhausted.")


def fill_influential_citations_for_nulls(
    hook: PostgresHook,
    batch_size: int = 200,          # 더 줄여도 됨(예: 100)
    sleep_seconds: float = 2.0,     # 배치 간 텀 증가 권장
) -> None:
    """
    influential_citation_count IS NULL 대상만 조회 후 채움.
    단, S2에서 매핑이 안 되는 논문들도 많기 때문에:
      - 값을 못 채워도 influential_citation_updated_at은 NOW()로 찍어서
        같은 배치를 무한 반복하지 않게 한다.
    """
    conn = hook.get_conn()
    conn.autocommit = False

    # "count가 NULL이고 updated_at도 NULL"만 대상으로 하면
    # 이미 한 번 시도한(업데이트 타임만 찍힌) 논문은 제외됨.
    select_sql = """
        SELECT id, external_id
        FROM public.paper_pool
        WHERE source = 'arxiv'
          AND influential_citation_count IS NULL
          AND influential_citation_updated_at IS NULL
        ORDER BY id
        LIMIT %s
    """

    update_count_sql = """
        UPDATE public.paper_pool
        SET influential_citation_count = %s,
            influential_citation_updated_at = NOW()
        WHERE id = %s
    """

    # 매핑 실패/값 없음인 경우에도 "시도함" 표시만 찍기
    mark_attempt_sql = """
        UPDATE public.paper_pool
        SET influential_citation_updated_at = NOW()
        WHERE id = %s
    """

    try:
        with conn.cursor() as cur:
            total_updated = 0
            total_marked = 0

            while True:
                cur.execute(select_sql, (batch_size,))
                rows: List[Tuple[int, str]] = cur.fetchall()
                if not rows:
                    logger.info("No more rows to attempt for influential citations.")
                    break

                id_by_arxiv: Dict[str, int] = {external_id: pid for (pid, external_id) in rows}
                s2_ids = [f"arxiv:{external_id}" for (_, external_id) in rows]

                resp = _post_with_retry(
                    S2_BATCH_URL,
                    params={"fields": "externalIds,influentialCitationCount"},
                    json_body={"ids": s2_ids},
                    headers=_s2_headers(),
                    timeout=30,
                    max_retries=8,
                    base_sleep=2.0,
                    max_sleep=120.0,
                )
                data = resp.json()

                updates: List[Tuple[int, int]] = []
                updated_ids: set[int] = set()

                for item in data:
                    if not item:
                        continue
                    external_ids = item.get("externalIds") or {}
                    arxiv_id = external_ids.get("ArXiv")
                    if not arxiv_id:
                        continue

                    count = item.get("influentialCitationCount")
                    if count is None:
                        continue

                    paper_id = id_by_arxiv.get(arxiv_id)
                    if paper_id is None:
                        continue

                    updates.append((int(count), int(paper_id)))
                    updated_ids.add(int(paper_id))

                # 1) 업데이트 가능한 건 업데이트
                if updates:
                    execute_batch(cur, update_count_sql, updates, page_size=200)
                    total_updated += len(updates)

                # 2) 나머지(매핑 실패/값 없음)는 "시도함" 표시만 찍어서 무한루프 방지
                to_mark = [(pid,) for (pid, _) in rows if pid not in updated_ids]
                if to_mark:
                    execute_batch(cur, mark_attempt_sql, to_mark, page_size=200)
                    total_marked += len(to_mark)

                conn.commit()

                logger.info(
                    "Influential batch done. fetched=%s updated=%s marked_attempt=%s",
                    len(rows), len(updates), len(to_mark),
                )

                time.sleep(sleep_seconds)

            logger.info(
                "Completed influential fill. total_updated=%s total_marked_attempt=%s",
                total_updated, total_marked,
            )

    except Exception:
        conn.rollback()
        logger.exception("Failed updating influential citation counts")
        raise
    finally:
        conn.close()
