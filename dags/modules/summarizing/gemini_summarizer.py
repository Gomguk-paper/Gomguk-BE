import json
import asyncio
import random
import os
import logging
from airflow.models import Variable
from airflow.providers.postgres.hooks.postgres import PostgresHook

try:
    from google import genai
    from google.genai import types
except ImportError:
    logging.warning("google-genai library not found.")


# ==========================================
# 1. Config Loader
# ==========================================
def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, '..', '..', 'configs', 'paper_summarize_config.json')
    config_path = os.path.normpath(config_path)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    config['prompts']['system_prompt'] = "\n".join(config['prompts']['system_prompt'])
    config['prompts']['user_prompt_template'] = "\n".join(config['prompts']['user_prompt_template'])

    try:
        api_key = Variable.get("gemini_api_key")
        config['gemini_config']['api_key'] = api_key
    except KeyError:
        raise ValueError("Airflow Variable 'gemini_api_key' is not set.")

    return config


# ==========================================
# 2. Database Functions
# ==========================================
def get_db_connection():
    hook = PostgresHook(postgres_conn_id='db')
    return hook.get_conn()


def fetch_recommended_papers(conn, limit=None):
    """추천된 논문 중 아직 papers 테이블에 없는 것을 조회"""
    cursor = conn.cursor()
    query = """
    SELECT p.id, p.title, p.summary as abstract, p.authors, p.published_at,
           p.pdf_href, p.source
    FROM paper_pool p
    JOIN paper_evaluation_log log ON log.paper_id = p.id
    WHERE log.is_recommended = true
      AND NOT EXISTS (SELECT 1 FROM papers WHERE raw_url = p.pdf_href)
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    return rows


def save_paper_and_summary(conn, paper_data, summary_data):
    """papers와 paper_summaries 테이블에 저장"""
    cursor = conn.cursor()
    try:
        # 1. papers 테이블에 INSERT
        insert_paper_query = """
        INSERT INTO papers (title, short, authors, published_at, image_url, raw_url, source, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """
        # authors: jsonb -> text[] 변환
        authors = paper_data.get('authors', [])
        if isinstance(authors, str):
            authors = json.loads(authors)
        if not isinstance(authors, list):
            authors = []

        cursor.execute(insert_paper_query, (
            paper_data['title'],
            summary_data['title'],  # short = AI 생성 TITLE
            authors,
            paper_data['published_at'],
            '',  # image_url 빈 문자열
            paper_data['pdf_href'],
            paper_data['source']
        ))
        paper_id = cursor.fetchone()[0]

        # 2. paper_summaries 테이블에 INSERT
        insert_summary_query = """
        INSERT INTO paper_summaries (paper_id, hook, points, detailed, style, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        """
        cursor.execute(insert_summary_query, (
            paper_id,
            summary_data['title'],  # hook = AI 생성 TITLE
            [summary_data['hook']],  # points = [HOOK] 배열로 감싸기
            summary_data['summary'],  # detailed = SUMMARY
            'plain'
        ))

        conn.commit()
        return paper_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


# ==========================================
# 3. Async Logic
# ==========================================
async def summarize_paper_async(client, config, paper, semaphore):
    """Gemini API로 논문 요약 생성"""
    exec_settings = config['execution_settings']
    async with semaphore:
        system_prompt = config['prompts']['system_prompt']
        user_template = config['prompts']['user_prompt_template']
        model_name = config['gemini_config']['model_name']

        prompt = user_template.format(
            title=paper['title'],
            abstract=paper['abstract'][:2000] if paper['abstract'] else ''
        )
        full_prompt = f"{system_prompt}\n\n{prompt}"

        attempt = 0
        while attempt <= exec_settings['max_retries']:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                result = json.loads(response.text)
                return {
                    'paper': paper,
                    'summary': result,
                    'success': True
                }
            except Exception as e:
                attempt += 1
                if attempt > exec_settings['max_retries']:
                    logging.error(f"❌ [Paper {paper['id']}] Failed. Error: {e}")
                    return {
                        'paper': paper,
                        'summary': None,
                        'success': False,
                        'error': str(e)
                    }
                sleep_time = (exec_settings['initial_delay'] * (
                    exec_settings['backoff_factor'] ** (attempt - 1))) + random.uniform(0, 1)
                await asyncio.sleep(sleep_time)


async def main_async_logic(limit=None):
    config = load_config()
    client = genai.Client(api_key=config['gemini_config']['api_key'])
    conn = get_db_connection()

    try:
        # limit 우선순위: 파라미터 > config > None
        effective_limit = limit or config['execution_settings'].get('limit')

        logging.info("1. Fetching recommended papers...")
        papers = fetch_recommended_papers(conn, effective_limit)
        logging.info(f"-> Found {len(papers)} papers to summarize")

        if not papers:
            logging.info("No papers to summarize.")
            return

        semaphore = asyncio.Semaphore(config['execution_settings']['concurrency_limit'])

        # 2. 비동기로 요약 생성
        logging.info("2. Generating summaries with Gemini API...")
        tasks = [summarize_paper_async(client, config, p, semaphore) for p in papers]
        results = await asyncio.gather(*tasks)

        # 3. 결과 저장
        success_count = 0
        fail_count = 0
        for result in results:
            if result['success']:
                try:
                    paper_id = save_paper_and_summary(conn, result['paper'], result['summary'])
                    logging.info(f"✅ Saved paper ID: {paper_id} - {result['summary'].get('title', '')}")
                    success_count += 1
                except Exception as e:
                    logging.error(f"❌ Failed to save paper {result['paper']['id']}: {e}")
                    fail_count += 1
            else:
                fail_count += 1

        logging.info(f"📊 Summary complete: {success_count} success, {fail_count} failed")

        return success_count, fail_count

    finally:
        if conn:
            conn.close()


# ==========================================
# 4. Entry Point for Airflow
# ==========================================
def run_summarizing_process(**context):
    # Airflow Variable에서 limit 가져오기 (옵션)
    try:
        limit = Variable.get("summarize_limit", default_var=None)
        if limit:
            limit = int(limit)
    except (KeyError, ValueError):
        limit = None

    result = asyncio.run(main_async_logic(limit))

    # 결과 확인: 전부 실패한 경우만 예외 발생
    if result:
        success_count, fail_count = result
        if fail_count > 0 and success_count == 0:
            raise Exception(f"모든 논문 요약 실패: {fail_count}개 실패")
        elif fail_count > 0:
            logging.warning(f"⚠️ 일부 논문 요약 실패: {success_count}개 성공, {fail_count}개 실패")
