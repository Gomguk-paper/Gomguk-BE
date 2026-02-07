import logging
import requests
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

# --- 상수 설정 (Config 대체) ---
BUCKET_NAME = "papers"
TIMEOUT_SECONDS = 60
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/pdf"
}


def sync_pdfs_to_minio(paper_list):
    """
    논문 리스트의 pdf_url을 다운로드하여 MinIO(S3) 'papers' 버킷에 저장합니다.
    저장 경로: s3://papers/paper_{id}.pdf
    """

    # 1. S3Hook 초기화 (Airflow Connection 'minio_s3' 사용)
    try:
        s3_hook = S3Hook(aws_conn_id='minio_s3')

        # 버킷 없으면 생성
        if not s3_hook.check_for_bucket(BUCKET_NAME):
            s3_hook.create_bucket(BUCKET_NAME)
            print(f"INFO: Created bucket '{BUCKET_NAME}'")

    except Exception as e:
        logging.error(f"FATAL: S3Hook Init Failed: {e}")
        raise

    results = []
    print(f"INFO: Start syncing PDFs for {len(paper_list)} papers...")

    for paper in paper_list:
        paper_id = paper['pool_id']
        pdf_url = paper['pdf_url']

        if not pdf_url:
            logging.warning(f"SKIP: No PDF URL for paper {paper_id}")
            results.append({"id": paper_id, "minio_pdf_path": None})
            continue

        file_name = f"paper_{paper_id}.pdf"

        try:
            print(f"DEBUG: Downloading PDF for {paper_id} from {pdf_url}...")

            # 2. PDF 다운로드 (Requests)
            # verify=False: Arxiv 등 일부 사이트 SSL 문제 방지 (필요시 True 권장)
            response = requests.get(
                pdf_url,
                headers=HEADERS,
                timeout=TIMEOUT_SECONDS,
                verify=False
            )

            if response.status_code == 200:
                pdf_bytes = response.content

                # 3. MinIO 업로드
                s3_hook.load_bytes(
                    bytes_data=pdf_bytes,
                    key=file_name,
                    bucket_name=BUCKET_NAME,
                    replace=True
                )

                # S3 URI 반환
                s3_uri = f"s3://{BUCKET_NAME}/{file_name}"

                results.append({
                    "id": paper_id,
                    "minio_pdf_path": s3_uri
                })
                print(f"SUCCESS: Uploaded {file_name} to MinIO")

            else:
                logging.error(f"FAIL: Download failed for {paper_id}. Status: {response.status_code}")
                results.append({"id": paper_id, "minio_pdf_path": None})

        except Exception as e:
            logging.error(f"FAIL: PDF sync error for {paper_id}: {e}")
            results.append({"id": paper_id, "minio_pdf_path": None})
            continue

    return results