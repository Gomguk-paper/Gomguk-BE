import os
import json
import re
import logging
import traceback
from airflow.models import Variable
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'summary_config.json')


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def clean_json_text(text):
    """마크다운 코드 블록 제거"""
    cleaned = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


# --- [재시도 로직] ---
# 1. JSON 파싱 실패 (JSONDecodeError)
# 2. 리스트 반환 (ValueError)
# 위 두 경우에 대해 최대 3회 재시도 (대기시간: 2초 -> 4초 -> 8초)
@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def _generate_content_with_retry(client, model_name, prompt, gen_config):
    """
    Gemini 호출 및 포맷 검증.
    Dictionary 형태가 아니면 에러를 발생시켜 재시도 유도.
    """
    # 1. 호출
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=gen_config
    )

    if not response or not response.text:
        raise ValueError("API Response is empty")

    # 2. 파싱
    cleaned_text = clean_json_text(response.text)
    try:
        data = json.loads(cleaned_text)
    except json.JSONDecodeError:
        print(f"WARN: JSON Decode Error. Retrying...")
        raise  # 재시도 트리거

    # 3. 타입 검증 (여기가 핵심)
    if isinstance(data, list):
        print(f"WARN: Output is a LIST. Retrying to get a DICT...")
        raise ValueError("Output format mismatch: Expected Dict, got List.")

    return data


def generate_summaries(paper_list):
    print("DEBUG: Loading config...")
    config = load_config()

    try:
        api_key = Variable.get("gemini_api_key")
        client = genai.Client(api_key=api_key)
    except Exception as e:
        logging.error(f"FATAL: Client Init Failed: {e}")
        raise

    summary_results = []

    # 모델 설정
    gen_config = types.GenerateContentConfig(
        temperature=config['generation_config']['temperature'],
        top_p=config['generation_config']['top_p'],
        top_k=config['generation_config']['top_k'],
        response_mime_type="application/json"
    )

    print(f"INFO: Start generating summaries for {len(paper_list)} papers...")

    for paper in paper_list:
        paper_id = paper.get('pool_id', 'Unknown')

        try:
            # 프롬프트 포맷팅
            prompt = config['prompt_template'].format(
                title=paper['title'],
                abstract=paper['abstract']
            )

            # --- 재시도 함수 호출 ---
            # 여기서 리스트가 반환되면 알아서 재시도함
            summary_json = _generate_content_with_retry(
                client,
                config['model_name'],
                prompt,
                gen_config
            )

            # 성공 시 결과 구성
            result_item = {
                "id": paper_id,
                "title": paper['title'],
                "summary": {
                    "hook": summary_json.get("hook", "요약 실패"),
                    "points": summary_json.get("points", []),
                    "detail": summary_json.get("detail", "")
                }
            }
            summary_results.append(result_item)
            print(f"SUCCESS: Generated summary for {paper_id}")

        except Exception as e:
            # 3번 재시도 후에도 실패하면 에러 로그 찍고 다음 논문으로 넘어감
            logging.error(f"❌ FINAL FAIL for {paper_id}: {e}")
            logging.error(traceback.format_exc())
            continue

    return summary_results