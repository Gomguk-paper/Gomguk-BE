from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from modules.ingestion.semantic_scholar_citation_papers import fill_papers_citations_for_nulls


with DAG(
    dag_id="papers_citation_update_fast",
    start_date=datetime(2026, 2, 1),
    schedule=None,
    catchup=False,
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["papers", "citation", "fast"],
) as dag:

    @task(task_id="pull_papers_citation")
    def pull_papers_citation_task():
        hook = PostgresHook(postgres_conn_id="db")
        fill_papers_citations_for_nulls(hook=hook, batch_size=500, sleep_seconds=1.0)

    pull_papers_citation_task()
