from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from modules.ingestion.arxiv_pull import pull_arxiv_recent_into_paper_pool
from modules.ingestion.semantic_scholar_influential import fill_influential_citations_for_nulls
from modules.ingestion.semantic_scholar_citation import fill_citations_for_nulls


with DAG(
    dag_id="paper_ingestion_test_one_category",
    start_date=datetime(2026, 2, 1),
    schedule=None,  # 수동 실행용
    catchup=False,
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["test", "ingestion", "paper_pool"],
) as dag:

    @task(task_id="pull_arxiv_recent_one_category")
    def pull_arxiv_recent_one_category():
        hook = PostgresHook(postgres_conn_id="db")

        test_category = ["cs.AI"]

        pull_arxiv_recent_into_paper_pool(
            hook=hook,
            max_results_per_category=2000,
            categories=test_category,
        )

    @task(task_id="pull_influential_citation")
    def pull_influential_citation_task():
        hook = PostgresHook(postgres_conn_id="db")
        # influential_citation_count IS NULL 인 것만 채움
        fill_influential_citations_for_nulls(hook=hook, batch_size=500)

    @task(task_id="pull_citation")
    def pull_citation_task():
        hook = PostgresHook(postgres_conn_id="db")
        # citation_count IS NULL 인 것만 채움
        fill_citations_for_nulls(hook=hook, batch_size=500)

    pull_arxiv_recent_one_category() >> pull_influential_citation_task() >> pull_citation_task()


