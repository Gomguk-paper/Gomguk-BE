from __future__ import annotations

import logging
from typing import Dict, List, Optional

import arxiv
from psycopg2.extras import Json, execute_values
from airflow.providers.postgres.hooks.postgres import PostgresHook

logger = logging.getLogger(__name__)

# 업로드하신 pullingArxiv.ipynb에서 추출한 CS 카테고리 키(40개)
CS_CATEGORIES: Dict[str, str] = {
    "cs.AI": "Artificial Intelligence",
    "cs.AR": "Hardware Architecture",
    "cs.CC": "Computational Complexity",
    "cs.CE": "Computational Engineering, Finance, and Science",
    "cs.CG": "Computational Geometry",
    "cs.CL": "Computation and Language",
    "cs.CR": "Cryptography and Security",
    "cs.CV": "Computer Vision and Pattern Recognition",
    "cs.CY": "Computers and Society",
    "cs.DB": "Databases",
    "cs.DC": "Distributed, Parallel, and Cluster Computing",
    "cs.DL": "Digital Libraries",
    "cs.DM": "Discrete Mathematics",
    "cs.DS": "Data Structures and Algorithms",
    "cs.ET": "Emerging Technologies",
    "cs.FL": "Formal Languages and Automata Theory",
    "cs.GL": "General Literature",
    "cs.GR": "Graphics",
    "cs.GT": "Computer Science and Game Theory",
    "cs.HC": "Human-Computer Interaction",
    "cs.IR": "Information Retrieval",
    "cs.IT": "Information Theory",
    "cs.LG": "Machine Learning",
    "cs.LO": "Logic in Computer Science",
    "cs.MA": "Multiagent Systems",
    "cs.MM": "Multimedia",
    "cs.MS": "Mathematical Software",
    "cs.NA": "Numerical Analysis",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.NI": "Networking and Internet Architecture",
    "cs.OH": "Other Computer Science",
    "cs.OS": "Operating Systems",
    "cs.PF": "Performance",
    "cs.PL": "Programming Languages",
    "cs.RO": "Robotics",
    "cs.SC": "Symbolic Computation",
    "cs.SD": "Sound",
    "cs.SE": "Software Engineering",
    "cs.SI": "Social and Information Networks",
    "cs.SY": "Systems and Control",
}


INSERT_SQL = """
INSERT INTO public.paper_pool
(source, external_id, title, authors, summary, primary_category, categories,
 published_at, updated_at, pdf_href, comment)
VALUES %s
ON CONFLICT (source, external_id) DO NOTHING
"""


def _clean_arxiv_id(short_id: str) -> str:
    # e.g. "2501.01234v2" -> "2501.01234"
    return short_id.split("v")[0]


def pull_arxiv_recent_into_paper_pool(
    hook: PostgresHook,
    max_results_per_category: int = 2000,
    categories: Optional[List[str]] = None,
) -> None:
    """
    모든(또는 지정한) Arxiv cs.* 카테고리에서 최근 논문 max_results_per_category개를 조회하여,
    paper_pool에 없는 것만 저장합니다.
    """
    target_categories = categories if categories else list(CS_CATEGORIES.keys())

    client = arxiv.Client(page_size=2000, delay_seconds=3.0, num_retries=5)

    conn = hook.get_conn()
    conn.autocommit = False

    total_inserted_estimate = 0

    try:
        with conn.cursor() as cur:
            for cat_code in target_categories:
                logger.info("Start fetching arXiv category=%s limit=%s", cat_code, max_results_per_category)

                search = arxiv.Search(
                    query=f"cat:{cat_code}",
                    max_results=max_results_per_category,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                    sort_order=arxiv.SortOrder.Descending,
                )

                rows = []
                for result in client.results(search):
                    external_id = _clean_arxiv_id(result.get_short_id())

                    rows.append(
                        (
                            "arxiv",
                            external_id,
                            result.title,
                            Json([a.name for a in result.authors]),
                            result.summary,
                            result.primary_category,
                            Json(list(result.categories) if result.categories else []),
                            result.published,
                            result.updated,
                            result.pdf_url,
                            result.comment,
                        )
                    )

                if not rows:
                    logger.info("No results for category=%s", cat_code)
                    continue

                # bulk insert, conflict ignore
                execute_values(cur, INSERT_SQL, rows, page_size=2000)
                conn.commit()

                total_inserted_estimate += len(rows)
                logger.info("Fetched=%s rows for category=%s (insert attempted; conflicts ignored)", len(rows), cat_code)

        logger.info("Completed arXiv pulling. total_fetched=%s", total_inserted_estimate)

    except Exception:
        conn.rollback()
        logger.exception("Failed pulling arXiv and inserting into paper_pool")
        raise
    finally:
        conn.close()
