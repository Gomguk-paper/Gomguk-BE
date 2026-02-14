from datetime import datetime, timedelta
from airflow.decorators import dag, task

default_args = {
    "owner": "dongbin",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
}


@dag(
    dag_id="papers_multi_prompt_summary_test",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["papers", "summary", "multi-prompt", "test"],
)
def paper_multi_prompt_summary_test_pipeline():
    @task
    def get_target_papers():
        from modules.update.multi_summary_db import get_registered_styles, get_papers_missing_styles

        styles = get_registered_styles()
        # 테스트용: 최대 5개 논문만 처리
        return get_papers_missing_styles(styles=styles, limit=5)

    @task
    def generate_summaries(paper_list):
        from modules.update.multi_summary_generator import generate_multi_prompt_summaries

        return generate_multi_prompt_summaries(paper_list)

    @task
    def upsert_summaries(summary_items):
        from modules.update.multi_summary_db import upsert_multi_prompt_summaries

        upsert_multi_prompt_summaries(summary_items)

    papers = get_target_papers()
    summaries = generate_summaries(papers)
    upsert_summaries(summaries)


paper_multi_prompt_summary_test_pipeline_dag = paper_multi_prompt_summary_test_pipeline()
