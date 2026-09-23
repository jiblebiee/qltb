import logging
import os
import uuid
from functools import lru_cache

import boto3
from botocore.config import Config

from .config import settings

logger = logging.getLogger(__name__)


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


def ensure_bucket() -> bool:
    """
    Tạo bucket nếu chưa có.

    Trước đây việc này do một container `minio/mc` chạy một lần rồi thoát lo.
    Bỏ đi vì nó bắt phải tải thêm một ảnh Docker nữa — mà đúng cái ảnh đó hay
    bị Docker Hub chặn khi máy vượt hạn mức tải ẩn danh, làm cả hệ thống không
    dựng lên được chỉ vì một lệnh tạo thư mục.

    Chạy lại bao nhiêu lần cũng được: đã có bucket thì không làm gì.
    Kho ảnh chưa kịp lên thì trả False, gọi lại sau là xong — không được ném
    lỗi ra ngoài, vì phần còn lại của hệ thống không phụ thuộc kho ảnh.
    """
    bucket = (settings.s3_bucket or "").strip()
    if not bucket:
        return False
    try:
        client = s3_client()
        client.head_bucket(Bucket=bucket)
        return True
    except Exception:
        pass

    try:
        client = s3_client()
        region = (settings.s3_region or "").strip()
        # MinIO và us-east-1 không nhận LocationConstraint, các vùng khác thì bắt buộc
        if region and region != "us-east-1":
            client.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        else:
            client.create_bucket(Bucket=bucket)
        logger.info("Đã tạo bucket %s", bucket)
        return True
    except Exception as exc:
        name = type(exc).__name__
        # Người khác vừa tạo trước, hoặc bucket đã có sẵn — coi như xong
        if "BucketAlreadyOwnedByYou" in name or "BucketAlreadyExists" in name:
            return True
        logger.warning("Chưa tạo được bucket %s: %s", bucket, exc)
        return False
