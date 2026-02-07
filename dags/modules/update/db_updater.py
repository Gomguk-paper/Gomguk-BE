import logging
from datetime import datetime
from airflow.providers.postgres.hooks.postgres import PostgresHook
from psycopg2.extras import Json


def upsert_paper_records(papers, summaries, tags, images, pdfs):
    """
    수집 및 가공된 모든 데이터를 취합하여 DB에 저장합니다.
    Target Tables: papers, paper_summaries, tags, paper_tags
    """

    # 1. 데이터 병합 (pool_id 기준)
    # 모든 리스트를 id를 Key로 하는 Dict로 변환하여 접근성 확보
    merged_data = {}

    def merge_list(source_list, key_name=None):
        for item in source_list:
            pid = item.get('id') or item.get('pool_id')
            if pid not in merged_data:
                merged_data[pid] = {}

            if key_name:
                merged_data[pid][key_name] = item
            else:
                # papers 리스트의 경우 메인 데이터이므로 update
                merged_data[pid].update(item)

    # 각 데이터 병합
    merge_list(papers)  # 메인 메타데이터
    merge_list(summaries, 'summary_data')
    merge_list(tags, 'tag_data')
    merge_list(images, 'image_data')
    merge_list(pdfs, 'pdf_data')

    logging.info(f"INFO: Merged data for {len(merged_data)} papers. Starting DB transaction...")

    # 2. DB 연결 및 트랜잭션 시작
    hook = PostgresHook(postgres_conn_id='db')
    inserted_count = 0

    with hook.get_conn() as conn:
        with conn.cursor() as cursor:
            for pid, data in merged_data.items():
                try:
                    # 필수 데이터 확인 (요약이나 태그 실패 시 저장 스킵 여부 결정)
                    # 여기서는 최대한 저장하는 방향으로 진행

                    # --- [Step 1] Tags 처리 (Get or Create) ---
                    # 태그 이름 리스트 추출
                    tag_names = data.get('tag_data', {}).get('tags', [])
                    tag_db_ids = []

                    for tag_name in tag_names:
                        # 1-1. 태그 존재 여부 확인
                        cursor.execute("SELECT id, count FROM public.tags WHERE name = %s", (tag_name,))
                        res = cursor.fetchone()

                        if res:
                            # 존재하면 ID 확보 및 count 증가
                            tag_id, current_count = res
                            cursor.execute("UPDATE public.tags SET count = count + 1 WHERE id = %s", (tag_id,))
                            tag_db_ids.append(tag_id)
                        else:
                            # 없으면 새로 생성
                            cursor.execute("""
                                INSERT INTO public.tags (name, description, count, created_at)
                                VALUES (%s, %s, 1, NOW())
                                RETURNING id
                            """, (tag_name, tag_name))  # description은 일단 name과 동일하게
                            tag_id = cursor.fetchone()[0]
                            tag_db_ids.append(tag_id)

                    # --- [Step 2] Papers 테이블 Insert ---
                    # short 컬럼에는 abstract(요약문)가 들어감
                    # source는 'arxiv'로 고정 (ENUM 타입 캐스팅 필요할 수 있음)

                    # PDF, Image 경로가 없으면 빈 문자열 혹은 Default 이미지 처리
                    minio_pdf = data.get('pdf_data', {}).get('minio_pdf_path', '')
                    minio_img = data.get('image_data', {}).get('minio_img_path', '')

                    if not minio_pdf:
                        logging.warning(f"SKIP: Paper {pid} has no PDF. Skipping DB insert.")
                        continue

                    cursor.execute("""
                        INSERT INTO public.papers 
                        (title, short, authors, published_at, image_url, raw_url, created_at, source, paper_pool_id)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW(), 'arxiv', %s)
                        RETURNING id
                    """, (
                        data['title'],
                        data['abstract'],  # short 컬럼
                        data['authors'],  # List[str] -> text[] (psycopg2가 자동변환)
                        data['published_at'],
                        minio_img,
                        minio_pdf,
                        pid  # paper_pool_id
                    ))

                    new_paper_id = cursor.fetchone()[0]

                    # --- [Step 3] Paper Summaries Insert ---
                    summary_content = data.get('summary_data', {}).get('summary', {})
                    if summary_content:
                        cursor.execute("""
                            INSERT INTO public.paper_summaries
                            (paper_id, hook, points, detailed, style, created_at)
                            VALUES (%s, %s, %s, %s, 'basic_aggro', NOW())
                        """, (
                            new_paper_id,
                            summary_content.get('hook', ''),
                            summary_content.get('points', []),  # text[]
                            summary_content.get('detail', '')
                        ))

                    # --- [Step 4] Paper Tags (Junction) Insert ---
                    for tid in tag_db_ids:
                        cursor.execute("""
                            INSERT INTO public.paper_tags (paper_id, tag_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, (new_paper_id, tid))

                    conn.commit()  # 한 논문 성공 시 커밋 (배치 단위 커밋을 원하면 루프 밖으로 이동)
                    inserted_count += 1
                    print(f"SUCCESS: Inserted Paper {pid} (ID: {new_paper_id})")

                except Exception as e:
                    conn.rollback()  # 해당 논문 처리 중 에러나면 롤백
                    logging.error(f"FAIL: DB Insert failed for paper {pid}: {e}")
                    continue

    logging.info(f"DONE: Successfully inserted {inserted_count} papers.")