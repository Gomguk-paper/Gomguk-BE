from datetime import datetime, timedelta
from airflow.decorators import dag, task

default_args = {
    'owner': 'dongbin',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}


@dag(
    dag_id='papers_content_update',
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=['papers', 'summary update', 'tag update', 'minio']
)
def paper_update_pipeline():
    @task
    def get_pending_papers():
        """1. 업로드 대상 논문 조회 """
        from modules.update.paper_fetcher import get_pending_papers_from_db

        return get_pending_papers_from_db()

    @task
    def gen_clickbait_summary(paper_list):
        """2. 기본 어그로형 요약 생성 (hook, point, detail)"""
        from modules.update.summary_generator import generate_summaries
        return generate_summaries(paper_list)

    @task
    def assign_paper_tags(paper_list):
        """3. 태그 부여"""
        from modules.update.tag_generator import generate_tags

        return generate_tags(paper_list)

    @task
    def gen_summary_image_to_minio(summary_list):
        """4. 요약 기반 이미지 생성 및 MinIO 저장"""
        from modules.update.image_generator import generate_and_upload_images

        return generate_and_upload_images(summary_list)

    @task
    def sync_pdf_to_minio(paper_list):
        """5. 원본 PDF 다운로드 및 MinIO 저장"""
        from modules.update.pdf_processor import sync_pdfs_to_minio

        return sync_pdfs_to_minio(paper_list)

    @task
    def upsert_paper_records(papers_data, summary_data, tag_data, image_data, pdf_data):
        """6. 모든 가공 데이터를 모아 CRUD 테이블(papers/tags/paper_tags/paper_summaries) 업데이트"""
        from modules.update.db_updater import upsert_paper_records as db_upsert
        db_upsert(papers_data, summary_data, tag_data, image_data, pdf_data)

    # --- 데이터 흐름 정의 ---
    papers = get_pending_papers()

    # 병렬 처리 및 의존성 주입
    summaries = gen_clickbait_summary(papers)
    tags = assign_paper_tags(papers)
    pdfs = sync_pdf_to_minio(papers)

    # 요약 결과가 나와야 이미지 생성 가능
    images = gen_summary_image_to_minio(summaries)

    # 모든 가공이 완료된 후 최종 업데이트
    upsert_paper_records(papers, summaries, tags, images, pdfs)


# DAG 객체 생성
paper_update_pipeline_dag = paper_update_pipeline()