import os
import json
import logging
from airflow.models import Variable
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'image_config.json')


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# --- [재시도 로직] ---
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    reraise=True
)
def _generate_image_with_retry(client, model_name, prompt, config_params):
    """
    Gemini 2.5 Flash Image 모델 호출
    """
    # Gemini 2.5 Flash Image 호출 규격
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=config_params.get('aspect_ratio', '1:1')
            )
        )
    )
    return response


def generate_and_upload_images(summary_list):
    """
    요약 정보를 받아 이미지를 생성하고 MinIO에 저장합니다.
    (이미 존재하는 파일은 건너뜁니다 - 멱등성 보장)
    """
    config = load_config()
    bucket_name = config['bucket_name']
    model_name = config.get('model_name', 'gemini-2.5-flash-image')

    # 1. Init
    try:
        api_key = Variable.get("gemini_api_key")
        client = genai.Client(api_key=api_key)
        s3_hook = S3Hook(aws_conn_id='minio_s3')
        if not s3_hook.check_for_bucket(bucket_name):
            s3_hook.create_bucket(bucket_name)
    except Exception as e:
        logging.error(f"Init Failed: {e}")
        raise

    results = []
    print(f"INFO: Start processing images for {len(summary_list)} papers...")

    for item in summary_list:
        paper_id = item['id']
        file_name = f"summary_{paper_id}.png"
        s3_uri = f"s3://{bucket_name}/{file_name}"

        # --- [핵심] 멱등성 체크: 이미 파일이 있으면 생성 스킵 ---
        if s3_hook.check_for_key(file_name, bucket_name):
            print(f"SKIP: Image for {paper_id} already exists. ({file_name})")
            results.append({
                "id": paper_id,
                "minio_img_path": s3_uri
            })
            continue  # 다음 논문으로 넘어감
        # -------------------------------------------------------

        summary_data = item['summary']
        hook_text = summary_data.get('hook', '')
        detail_text = summary_data.get('detail', '')
        summary_text = f"{hook_text} {detail_text}"[:350]

        base_prompt = config['prompt_template'].format(summary=summary_text)
        negative_text = config.get('negative_prompt', '')
        full_prompt = f"{base_prompt} (Exclude elements: {negative_text})" if negative_text else base_prompt

        try:
            print(f"DEBUG: Generating image for {paper_id}...")

            # 이미지 생성 호출
            response = _generate_image_with_retry(client, model_name, full_prompt, config)

            image_bytes = None

            # [수정된 파싱 로직] 안전하게 데이터 추출
            if response.candidates:
                candidate = response.candidates[0]
                # 안전 필터 등으로 인해 content가 없을 수 있음
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.inline_data:
                            image_bytes = part.inline_data.data
                            break
                else:
                    logging.warning(f"WARN: Blocked/Empty. Reason: {candidate.finish_reason}")

            if image_bytes:
                # 업로드
                s3_hook.load_bytes(
                    bytes_data=image_bytes,
                    key=file_name,
                    bucket_name=bucket_name,
                    replace=True
                )
                results.append({"id": paper_id, "minio_img_path": s3_uri})
                print(f"SUCCESS: Uploaded {file_name}")
            else:
                logging.warning(f"WARN: No image data for {paper_id}")
                results.append({"id": paper_id, "minio_img_path": None})

        except Exception as e:
            # 개별 실패는 로그만 남기고 전체 파이프라인은 진행 (Partial Failure 허용)
            # 만약 정말 중요한 에러라면 raise e를 하세요.
            logging.error(f"FAIL: Error processing {paper_id}: {e}")
            results.append({"id": paper_id, "minio_img_path": None})
            continue

    return results