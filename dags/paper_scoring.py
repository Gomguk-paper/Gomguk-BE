from datetime import datetime
from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

# 1. DAG 정의
# schedule_interval=None : Trigger 될 때만 실행
# template_searchpath : SQL 파일이 위치한 경로 지정 (/opt/airflow/dags/...)
with DAG(
    dag_id='paper_scoring',
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    template_searchpath='/opt/airflow/dags/modules/scoring',
    tags=['papers', 'score', 'manual'],
) as dag:

    # 2. 첫 번째 태스크: 카테고리 가중치 계산 (Truncate & Insert)
    calc_weights = SQLExecuteQueryOperator(
        task_id='calc_category_weights',
        conn_id='db',
        sql='1_calc_category_weights.sql'
    )

    # 3. 두 번째 태스크: 논문 점수 업데이트 (Update)
    update_scores = SQLExecuteQueryOperator(
        task_id='update_paper_scores',
        conn_id='db',
        sql='2_update_paper_scores.sql'
    )

    # 4. 실행 순서 설정 (가중치 계산 -> 점수 업데이트)
    calc_weights >> update_scores