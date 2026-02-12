import json
import math
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
    config_path = os.path.join(base_dir, 'paper_filter_config.json')
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


def save_evaluation_results(conn, results):
    if not results: return
    cursor = conn.cursor()

    # ai_tags 컬럼 제거됨
    query = """
    INSERT INTO paper_evaluation_log 
    (paper_id, category_code, is_recommended, ai_reason)
    VALUES (%s, %s, %s, %s)
    """

    data = []
    for r in results:
        # status가 없는 경우 스킵
        if 'status' not in r: continue

        is_rec = True if r['status'] == 'RECOMMENDED' else False

        data.append((r['id'], r['category'], is_rec, r['ai_reason']))

    cursor.executemany(query, data)
    conn.commit()
    cursor.close()


def calculate_quotas(conn, config):
    cursor = conn.cursor()
    categories = config['categories']
    query = """
    SELECT primary_category as category, COUNT(*) as count
    FROM paper_pool p
    WHERE p.citation_score IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM paper_evaluation_log log WHERE log.paper_id = p.id)
      AND p.primary_category IN %s
    GROUP BY p.primary_category
    """
    cursor.execute(query, (tuple(categories.keys()),))
    stats = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.close()

    total_count = sum(stats.values())
    target_count = config['recommendation_settings']['daily_target_count']
    quotas = {}
    if total_count == 0: return quotas

    for cat, count in stats.items():
        raw_quota = (count / total_count) * target_count
        final_quota = min(math.ceil(raw_quota), count)
        if final_quota > 0:
            quotas[cat] = final_quota
    return quotas


def fetch_candidates(conn, category, quota):
    cursor = conn.cursor()
    query = """
    SELECT id, title, summary as abstract, extract(year from published_at) as year
    FROM paper_pool p
    WHERE p.primary_category = %s
      AND NOT EXISTS (SELECT 1 FROM paper_evaluation_log log WHERE log.paper_id = p.id)
      AND p.citation_score IS NOT NULL
    ORDER BY p.citation_score DESC
    LIMIT %s
    """
    cursor.execute(query, (category, quota))
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    return rows


# ==========================================
# 3. Async Logic
# ==========================================
async def evaluate_paper_async(client, config, paper, semaphore):
    exec_settings = config['execution_settings']
    async with semaphore:
        system_prompt = config['prompts']['system_prompt']
        user_template = config['prompts']['user_prompt_template']
        model_name = config['gemini_config']['model_name']

        prompt = user_template.format(
            title=paper['title'],
            abstract=paper['abstract'][:1200],
            year=paper['year']
        )
        full_prompt = f"{system_prompt}\n\n{prompt}"

        attempt = 0
        while attempt <= exec_settings['max_retries']:
            try:
                # API 호출
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )

                result = json.loads(response.text)

                paper['ai_reason'] = result.get('reason', '')
                paper['status'] = 'RECOMMENDED' if result.get('recommendation') else 'REJECTED'
                return paper

            except Exception as e:
                attempt += 1
                if attempt > exec_settings['max_retries']:
                    logging.error(f"❌ [Paper {paper['id']}] Failed. Error: {e}")
                    paper['status'] = 'REJECTED'
                    paper['ai_reason'] = f"API Error: {str(e)}"
                    # paper['ai_tags'] = []  <-- 삭제
                    return paper

                sleep_time = (exec_settings['initial_delay'] * (
                        exec_settings['backoff_factor'] ** (attempt - 1))) + random.uniform(0, 1)
                await asyncio.sleep(sleep_time)

async def process_category_async(conn, client, config, cat, quota, semaphore):
    candidates = fetch_candidates(conn, cat, quota)
    if not candidates: return []
    for p in candidates: p['category'] = cat
    tasks = [evaluate_paper_async(client, config, p, semaphore) for p in candidates]
    return await asyncio.gather(*tasks)


async def main_async_logic():
    config = load_config()
    client = genai.Client(api_key=config['gemini_config']['api_key'])
    conn = get_db_connection()
    try:
        logging.info("1. Calculating quotas...")
        quotas = calculate_quotas(conn, config)
        total_target = sum(quotas.values())
        logging.info(f"-> Target fetch count: {total_target}")

        if total_target == 0:
            logging.info("No papers to process.")
            return

        semaphore = asyncio.Semaphore(config['execution_settings']['concurrency_limit'])
        all_evaluations = []

        for cat, quota in quotas.items():
            logging.info(f"Processing {cat} (Quota: {quota})...")
            results = await process_category_async(conn, client, config, cat, quota, semaphore)
            if results:
                all_evaluations.extend(results)
                rec_cnt = sum(1 for p in results if p.get('status') == 'RECOMMENDED')
                logging.info(f"-> Evaluated {len(results)}, Recommended {rec_cnt}")

        if all_evaluations:
            save_evaluation_results(conn, all_evaluations)
            logging.info(f"✅ Saved total {len(all_evaluations)} evaluation logs.")
        else:
            logging.info("No evaluations to save.")
    finally:
        if conn: conn.close()


# ==========================================
# 4. Entry Point for Airflow
# ==========================================
def run_filtering_process(**context):
    asyncio.run(main_async_logic())