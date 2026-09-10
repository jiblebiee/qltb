from fastapi import UploadFile
import os
import uuid
from functools import lru_cache

import boto3
from botocore.config import Config

from .config import settings


@lru_cache(maxsize=1)
def s3_client():
    # If running on AWS with IAM role, credentials can be omitted.
    return boto3.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        config=Config(signature_version="s3v4"),
    )

@lru_cache(maxsize=1)
def s3_presign_client():
    """
    Client chỉ dùng để KÝ url cho trình duyệt.

    Chữ ký S3 gắn liền với tên miền trong url, nên không thể ký bằng địa chỉ
    nội bộ rồi đổi host ở phía trình duyệt — đổi xong chữ ký sẽ sai. Vì vậy khi
    trình duyệt nhìn kho ảnh bằng một địa chỉ khác máy chủ, ta ký bằng đúng địa
    chỉ đó. Không cấu hình S3_PUBLIC_ENDPOINT_URL thì dùng lại client thường.
    """
    public = (settings.s3_public_endpoint_url or "").strip()
    if not public or public.rstrip("/") == (settings.s3_endpoint_url or "").rstrip("/"):
        return s3_client()
    return boto3.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=public.rstrip("/"),
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        config=Config(signature_version="s3v4"),
    )


def make_object_key(filename: str) -> str:
    safe = os.path.basename(filename).replace(" ", "_")
    return f"{settings.s3_prefix}{uuid.uuid4().hex}_{safe}"

def presign_put(filename: str, content_type: str) -> tuple[str, str]:
    key = make_object_key(filename)
    cli = s3_client()
    url = cli.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.presign_expires,
    )
    return key, url

def presign_get(key: str) -> str:
    cli = s3_client()
    url = cli.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.presign_expires,
    )
    return url



def upload_file_to_s3(file: UploadFile) -> str:
    """Upload a FastAPI UploadFile to S3 and return the stored object key."""
    key = make_object_key(file.filename or "upload")
    cli = s3_client()
    cli.upload_fileobj(
        file.file,
        settings.s3_bucket,
        key,
        ExtraArgs={"ContentType": file.content_type or "application/octet-stream"},
    )
    return key


def public_s3_url(key: str) -> str:
    """Build a public URL for object if endpoint supports public access."""
    if not key:
        return ""
    if key.startswith("http://") or key.startswith("https://"):
        return key
    # For MinIO/S3 compatible: endpoint_url/bucket/key
    if settings.s3_endpoint_url:
        base = settings.s3_endpoint_url.rstrip("/")
        return f"{base}/{settings.s3_bucket}/{key.lstrip('/')}"
    return key

def presigned_get_url(key: str) -> str:
    cli = s3_client()
    return cli.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.presign_expires,
    )
