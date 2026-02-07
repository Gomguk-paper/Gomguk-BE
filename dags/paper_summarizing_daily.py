from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

from modules.summarizing.gemini_summarizer import run_summarizing_process

with DAG(
    dag_id='paper_summarizing_daily',
    start_date=datetime(2024, 1, 1),
    schedule='0 3 * * *',  # 매일 03:00 실행 (필터링 후 1시간 뒤)
    catchup=False,
    tags=['papers', 'ai', 'summarizing'],
) as dag:

    summarize_task = PythonOperator(
        task_id='gemini_paper_summarizing',
        python_callable=run_summarizing_process
    )
