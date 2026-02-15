import json
import logging
import os
import re
from airflow.models import Variable
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "multi_summary_config.json")


def load_multi_summary_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_json_text(text):
    cleaned = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def parse_delimited_summary(text):
    pattern = re.compile(
        r"###TITLE###\s*(.*?)\s*###HOOK###\s*(.*?)\s*###SUMMARY###\s*(.*)",
        flags=re.DOTALL,
    )
    match = pattern.search(text or "")
    if not match:
        return None

    title = match.group(1).strip()
    hook = match.group(2).strip()
    summary = match.group(3).strip()

    return {
        "title": title,
        "hook": hook,
        "summary": summary,
    }


def _pick_first(d, keys, default=""):
    for k in keys:
        if k in d and d.get(k) is not None:
            v = d.get(k)
            if isinstance(v, str):
                return v.strip()
            return v
    return default


def sanitize_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    text = value.strip()
    # 응답이 문자열로 한번 더 감싸져 들어오는 경우 처리
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    text = text.replace('\\"', '"').replace("\\n", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # 앞뒤의 무의미한 기호 정리
    text = re.sub(r'^[\s"\'`:,{}\[\]]+', "", text)
    text = re.sub(r'[\s"\'`:,{}\[\]]+$', "", text)
    return text.strip()


def normalize_points(value):
    if isinstance(value, list):
        out = [sanitize_text(v) for v in value if sanitize_text(v)]
        return out[:5]
    if isinstance(value, str):
        cleaned = sanitize_text(value)
        return [cleaned] if cleaned else []
    return []


def normalize_summary_payload(raw):
    if not isinstance(raw, dict):
        return None

    hook = sanitize_text(_pick_first(raw, ["hook", "HOOK"]))
    detail = sanitize_text(_pick_first(raw, ["detail", "DETAIL", "summary", "SUMMARY", "소개"]))
    title = sanitize_text(_pick_first(raw, ["title", "TITLE"]))

    points = normalize_points(raw.get("points", []))

    # TITLE/HOOK/SUMMARY 구조 대응
    if title and not points:
        points = [title]

    # 본문이 dict 내부 문자열로 한번 더 감싸져 있을 때 보정
    if (not hook or not detail) and isinstance(_pick_first(raw, ["content", "text"]), str):
        parsed = parse_delimited_summary(_pick_first(raw, ["content", "text"]))
        if parsed:
            hook = hook or sanitize_text(parsed["hook"])
            detail = detail or sanitize_text(parsed["summary"])
            if parsed["title"] and not points:
                points = [sanitize_text(parsed["title"])]

    if not hook and not detail and not points:
        return None

    return {
        "hook": sanitize_text(hook) or "",
        "points": points,
        "detail": sanitize_text(detail) or "",
    }


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def _generate_profile_summary(client, model_name, prompt, system_instruction, gen_config, output_format="json"):
    response_config = types.GenerateContentConfig(
        temperature=gen_config["temperature"],
        top_p=gen_config["top_p"],
        top_k=gen_config["top_k"],
        system_instruction=system_instruction,
    )
    if output_format != "delimited":
        response_config.response_mime_type = "application/json"

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=response_config,
    )

    if not response or not response.text:
        raise ValueError("empty response")

    # 1) JSON 응답 우선 파싱 + 키 정규화
    try:
        data = json.loads(clean_json_text(response.text))
        normalized = normalize_summary_payload(data)
        if normalized:
            return normalized
    except Exception:
        pass

    # 2) 구분자 응답 파싱
    parsed = parse_delimited_summary(response.text)
    if parsed:
        return {
            "hook": parsed["hook"],
            "points": [parsed["title"]] if parsed["title"] else [],
            "detail": parsed["summary"],
        }

    raise ValueError("response format is invalid")


def generate_multi_prompt_summaries(paper_list):
    config = load_multi_summary_config()
    profiles = config.get("prompt_profiles", [])
    if not profiles:
        logging.warning("No prompt profiles configured.")
        return []

    try:
        api_key = Variable.get("gemini_api_key")
        client = genai.Client(api_key=api_key)
    except Exception as e:
        logging.error(f"client init failed: {e}")
        raise

    model_name = config.get("model_name", "gemini-2.0-flash")
    gen_config = config.get("generation_config", {"temperature": 0.6, "top_p": 0.9, "top_k": 40})

    results = []
    logging.info("Generating multi-prompt summaries for %d papers with %d profiles.", len(paper_list), len(profiles))

    for paper in paper_list:
        paper_id = paper.get("paper_id")
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")

        for profile in profiles:
            style = profile.get("style")
            if not style:
                continue

            output_format = profile.get("output_format", "json")
            system_instruction = "\n".join(profile.get("system_prompt", []))
            user_template = "\n".join(profile.get("user_prompt_template", []))

            try:
                prompt = user_template.format(title=title, abstract=abstract)
                summary_json = _generate_profile_summary(
                    client=client,
                    model_name=model_name,
                    prompt=prompt,
                    system_instruction=system_instruction,
                    gen_config=gen_config,
                    output_format=output_format,
                )
                # 빈 payload 저장 방지
                if (
                    not summary_json.get("hook")
                    and not summary_json.get("detail")
                    and not summary_json.get("points")
                ):
                    logging.warning(
                        "Empty summary payload skipped. paper_id=%s style=%s",
                        paper_id,
                        style,
                    )
                    continue

                results.append(
                    {
                        "paper_id": paper_id,
                        "style": style,
                        "summary": {
                            "hook": summary_json.get("hook", ""),
                            "points": summary_json.get("points", []),
                            "detail": summary_json.get("detail", ""),
                        },
                    }
                )
            except Exception as e:
                logging.error("Failed summary generation. paper_id=%s style=%s error=%s", paper_id, style, e)
                continue

    return results
