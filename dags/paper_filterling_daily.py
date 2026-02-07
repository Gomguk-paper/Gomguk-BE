from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator  # [추가]

from modules.filtering.gemini_runner import run_filtering_process

with DAG(
        dag_id='paper_filtering_daily',
        start_date=datetime(2024, 1, 1),
        schedule='0 2 * * *',  # 매일 02:00 실행
        catchup=False,
        tags=['papers', 'ai', 'filtering'],
) as dag:
    # 1. 필터링 수행
    filtering_task = PythonOperator(
        task_id='gemini_paper_filtering',
        python_callable=run_filtering_process
    )

    # 2. 콘텐츠 업데이트 DAG 트리거
    trigger_update_task = TriggerDagRunOperator(
        task_id='trigger_content_update',
        trigger_dag_id='papers_content_update',
        reset_dag_run=True,
        wait_for_completion=False
    )

    # 3. 실행 순서 연결
    filtering_task >> trigger_update_task