"""
Tải ảnh lên và đọc ảnh về.

Trình duyệt xin một URL đã ký rồi PUT thẳng file lên S3, máy chủ không phải
trung chuyển byte nào. Đọc ảnh thì đi qua /api/v2/media để URL trong HTML
không lộ chữ ký S3 và vẫn chịu sự kiểm soát đăng nhập.
"""
from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..s3 import s3_client, s3_presign_client
from ..security import require_perm

router = APIRouter(prefix="/api/v2", tags=["uploads"])

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "image/heic": "heic", "image/heif": "heif",
}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # 12MB, ảnh chụp điện thoại đã nén vẫn thừa


class PresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=100)
    # images/ cho ảnh thiết bị, im_export/ cho ảnh kho hàng bán
    folder: str = Field(default="images", pattern="^(images|im_export)$")


@router.post("/uploads/presign", dependencies=[Depends(require_perm(
    "loan.devices.create", "loan.devices.update",
    "loan.loans.create", "loan.loans.update",
    "import_export.create", "import_export.update",
))])
def presign_put(payload: PresignRequest):
    """Xin URL để tải một ảnh lên. Chỉ nhận đúng các định dạng ảnh."""
    ctype = payload.content_type.split(";")[0].strip().lower()
    if ctype not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            400, "Chỉ nhận ảnh JPG, PNG, WEBP hoặc HEIC")

    ext = ALLOWED_IMAGE_TYPES[ctype]
    prefix = settings.s3_prefix if payload.folder == "images" else settings.s3_im_export
    key = f"{prefix.rstrip('/')}/{uuid.uuid4().hex}.{ext}"

    # Ký bằng địa chỉ mà TRÌNH DUYỆT nhìn thấy, không phải địa chỉ nội bộ
    url = s3_presign_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": ctype},
        ExpiresIn=settings.presign_expires,
    )
    return {"key": key, "upload_url": url, "content_type": ctype,
            "max_bytes": MAX_UPLOAD_BYTES}


@router.get("/media/{key:path}", dependencies=[Depends(require_perm(
    "loan.devices.view", "loan.loans.view",
    "loan.maintenance.view", "import_export.view",
))])
def get_media(key: str):
    """
    Đọc một ảnh từ S3.

    Bản cũ (main.py:950) gọi `s3.get_object` trên chính module app.s3 và dùng
    biến BUCKET chưa định nghĩa, nên route này trả 500 ở mọi lần gọi.
    """
    if ".." in key or key.startswith("/"):
        raise HTTPException(400, "Đường dẫn ảnh không hợp lệ")

    allowed = (settings.s3_prefix.rstrip("/"), settings.s3_im_export.rstrip("/"))
    if not key.startswith(allowed):
        raise HTTPException(403, "Không được phép đọc đường dẫn này")

    try:
        obj = s3_client().get_object(Bucket=settings.s3_bucket, Key=key)
    except Exception:
        raise HTTPException(404, "Không tìm thấy ảnh")

    ctype = obj.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream"
    return StreamingResponse(
        obj["Body"], media_type=ctype,
        headers={"Cache-Control": "private, max-age=3600"},
    )
