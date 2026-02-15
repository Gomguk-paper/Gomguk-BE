from __future__ import annotations

import json
import uuid
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import UploadFile

from app.core.config import settings

MINIO_ENDPOINT_URL = "http://minio:9000"
MINIO_PROFILE_BUCKET = "profiles"
MINIO_PROFILE_PUBLIC_READ = True
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024
S3_PROFILES_PREFIX = f"s3://{MINIO_PROFILE_BUCKET}/"
PROFILES_PUBLIC_BASE = "http://gomguk.cloud/profiles/"


def _s3_client():
    minio_user = (settings.MINIO_ROOT_USER or "").strip()
    minio_password = (settings.MINIO_ROOT_PASSWORD or "").strip()
    if not minio_user or not minio_password:
        raise ValueError("MINIO credentials are not configured")

    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT_URL,
        aws_access_key_id=minio_user,
        aws_secret_access_key=minio_password,
        config=Config(s3={"addressing_style": "path"}),
    )


def _ensure_bucket(client) -> None:
    try:
        client.head_bucket(Bucket=MINIO_PROFILE_BUCKET)
    except ClientError:
        client.create_bucket(Bucket=MINIO_PROFILE_BUCKET)

    if MINIO_PROFILE_PUBLIC_READ:
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadObjects",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{MINIO_PROFILE_BUCKET}/*"],
                }
            ],
        }
        client.put_bucket_policy(
            Bucket=MINIO_PROFILE_BUCKET,
            Policy=json.dumps(policy),
        )


def profile_image_to_public_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return path
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith(S3_PROFILES_PREFIX):
        key = path[len(S3_PROFILES_PREFIX):]
        return f"{PROFILES_PUBLIC_BASE}{key}"
    return path


def upload_user_profile_png(*, user_id: int, image: UploadFile) -> tuple[str, str]:
    content_type = (image.content_type or "").lower().strip()
    filename = (image.filename or "").lower()
    if content_type != "image/png" and not filename.endswith(".png"):
        raise ValueError("Only PNG is allowed")

    data = image.file.read(MAX_PROFILE_IMAGE_BYTES + 1)
    if not data:
        raise ValueError("Empty file is not allowed")
    if len(data) > MAX_PROFILE_IMAGE_BYTES:
        raise ValueError(f"Image too large. Max {MAX_PROFILE_IMAGE_BYTES} bytes")

    key = f"user-profiles/user_{user_id}_{uuid.uuid4().hex}.png"
    s3_uri = f"{S3_PROFILES_PREFIX}{key}"

    client = _s3_client()
    _ensure_bucket(client)
    client.put_object(
        Bucket=MINIO_PROFILE_BUCKET,
        Key=key,
        Body=data,
        ContentType="image/png",
    )

    return s3_uri, f"{PROFILES_PUBLIC_BASE}{key}"
