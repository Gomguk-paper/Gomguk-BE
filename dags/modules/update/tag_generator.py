import os
import json
import re
import logging
from airflow.models import Variable
from google import genai
from google.genai import types

# 설정 파일 경로
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'tag_config.json')


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def clean_json_text(text):
    """ 마크다운 코드 블록 제거 및 공백 정리 """
    cleaned = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def generate_tags(paper_list):
    """
    논문 리스트를 받아 Gemini를 통해 태그를 추출합니다.
    Returns: [{'id': 123, 'tags': ['Tag1', 'Tag2']}]
    """
    config = load_config()

    # 1. Client Init
    try:
        api_key = Variable.get("gemini_api_key")
        client = genai.Client(api_key=api_key)
    except Exception as e:
        logging.error(f"Failed to load API Key or Init Client: {e}")
        raise

    tag_results = []
    print(f"INFO: Start generating tags for {len(paper_list)} papers...")

    # 2. Config Setup
    gen_config = types.GenerateContentConfig(
        temperature=config['generation_config']['temperature'],
        top_p=config['generation_config']['top_p'],
        top_k=config['generation_config']['top_k'],
        response_mime_type="application/json"
    )

    # 3. Prompt Construction
    # 리스트로 된 프롬프트를 줄바꿈으로 합침
    system_instruction_text = "\n".join(config['prompts']['system_prompt'])
    user_prompt_template_text = "\n".join(config['prompts']['user_prompt_template'])

    for paper in paper_list:
        paper_id = paper.get('pool_id')
        try:
            # 프롬프트 완성
            prompt = user_prompt_template_text.format(
                title=paper['title'],
                abstract=paper['abstract']
            )

            response = client.models.generate_content(
                model=config['model_name'],
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=config['generation_config']['temperature'],
                    top_p=config['generation_config']['top_p'],
                    top_k=config['generation_config']['top_k'],
                    response_mime_type="application/json",
                    system_instruction=system_instruction_text  # 시스템 프롬프트 주입
                )
            )

            # 결과 파싱
            cleaned_text = clean_json_text(response.text)
            parsed_json = json.loads(cleaned_text)

            # "tags" 키가 있는지 확인, 없으면 빈 리스트
            tags = parsed_json.get("tags", [])

            # PascalCase, 공백 제거 등 안전장치 (LLM이 잘하지만 혹시 모를 에러 방지)
            sanitized_tags = [t.strip().replace(" ", "") for t in tags if isinstance(t, str)]

            result_item = {
                "id": paper_id,
                "tags": sanitized_tags
            }
            tag_results.append(result_item)
            print(f"SUCCESS: Generated tags for {paper_id}: {sanitized_tags}")

        except Exception as e:
            logging.error(f"FAIL: Failed to generate tags for {paper_id}: {e}")
            # 실패 시 빈 태그 리스트 반환 (파이프라인 중단 방지)
            tag_results.append({"id": paper_id, "tags": []})
            continue

    return tag_results