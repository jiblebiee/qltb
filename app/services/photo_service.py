"""
Ảnh sản phẩm dùng chung một bảng `photos`, phân biệt bằng (owner_type, owner_id).

Trình duyệt xin presigned PUT rồi tải thẳng lên S3; máy chủ chỉ lưu object key.
Lúc đọc, key được ký thành URL có hạn.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models_v2 import Photo, PhotoOwner
from ..s3 import presigned_get_url, public_s3_url

logger = logging.getLogger(__name__)
MAX_PHOTOS_PER_OWNER = 20


def attach_photos(
    db: Session,
    owner_type: PhotoOwner,
    owner_id: int,
    keys: list[str] | None,
    user_id: int | None = None,
) -> int:
    """Gắn danh sách object key vào một chủ sở hữu. Chưa commit."""
    keys = [k.strip() for k in (keys or []) if k and k.strip()]
    if not keys:
        return 0

    existing = db.execute(
        select(Photo.image_key).where(
            Photo.owner_type == owner_type, Photo.owner_id == owner_id
        )
    ).scalars().all()
    room = MAX_PHOTOS_PER_OWNER - len(existing)
    if room <= 0:
        return 0

    added = 0
    for key in keys[:room]:
        if key in existing:
            continue
        db.add(Photo(owner_type=owner_type, owner_id=owner_id,
                     image_key=key, created_by_user_id=user_id))
        added += 1
    return added


def photo_payload(db: Session, owner_type: PhotoOwner, owner_id: int) -> list[dict]:
    """Danh sách ảnh kèm URL đã ký, sẵn sàng trả về cho frontend."""
    rows = db.execute(
        select(Photo).where(Photo.owner_type == owner_type, Photo.owner_id == owner_id)
        .order_by(Photo.id)
    ).scalars().all()
    return [{"id": p.id, "key": p.image_key, "url": signed_url(p.image_key)} for p in rows]


def photo_payload_many(
    db: Session, owner_type: PhotoOwner, owner_ids: list[int]
) -> dict[int, list[dict]]:
    """Lấy ảnh cho nhiều chủ sở hữu bằng một truy vấn, tránh N+1."""
    if not owner_ids:
        return {}
    rows = db.execute(
        select(Photo).where(Photo.owner_type == owner_type, Photo.owner_id.in_(owner_ids))
        .order_by(Photo.id)
    ).scalars().all()
    out: dict[int, list[dict]] = {oid: [] for oid in owner_ids}
    for p in rows:
        out.setdefault(p.owner_id, []).append(
            {"id": p.id, "key": p.image_key, "url": signed_url(p.image_key)}
        )
    return out


def signed_url(key: str) -> str:
    if not key:
        return ""
    if key.startswith("http://") or key.startswith("https://"):
        return key
    try:
        return presigned_get_url(key)
    except Exception:
        logger.warning("Không ký được URL cho key %s", key, exc_info=True)
        return public_s3_url(key)


def delete_photo(db: Session, photo_id: int) -> bool:
    p = db.get(Photo, photo_id)
    if not p:
        return False
    db.delete(p)
    return True
