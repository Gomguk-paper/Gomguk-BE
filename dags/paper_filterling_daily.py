from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

from modules.filtering.gemini_runner import run_filtering_process

with DAG(
    dag_id='paper_filterling_daily',
    start_date=datetime(2024, 1, 1),
    schedule='0 2 * * *',  # 매일 02:00 실행
    catchup=False,
    tags=['papers', 'ai', 'filtering'],
) as dag:
    filtering_task = PythonOperator(
        task_id='gemini_paper_filtering',
        python_callable=run_filtering_process
    )