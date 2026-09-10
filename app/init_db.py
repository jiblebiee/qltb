"""
Tạo bảng và vá schema lúc khởi động.

Dự án chưa dùng Alembic. Hàm này tạo mọi bảng còn thiếu và thêm những cột mới
theo kiểu thêm-nếu-chưa-có, an toàn khi chạy lại nhiều lần. Bảng cũ được giữ
nguyên, không xoá, để còn tra cứu lịch sử.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from . import models, models_v2  # noqa: F401  — nạp để create_all thấy mọi bảng
from .db import Base, engine

logger = logging.getLogger(__name__)

# Các cột bổ sung cho bảng đã tồn tại: (bảng, cột, kiểu MySQL)
_COLUMN_PATCHES: list[tuple[str, str, str]] = [
    ("departments", "head_staff_id", "INTEGER NULL"),
    ("devices", "info", "TEXT NULL"),
    ("users", "permissions", "TEXT NULL"),
    ("loans", "note", "TEXT NULL"),
]

# Index nên có, chủ yếu cho các cột hay lọc
_INDEX_PATCHES: list[tuple[str, str, str]] = [
    ("loans", "ix_loans_borrower", "borrower_staff_id"),
    ("loans", "ix_loans_device", "device_id"),
    ("loans", "ix_loans_status", "status"),
]


def _add_missing_columns(insp) -> None:
    for table, column, ddl in _COLUMN_PATCHES:
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        logger.info("Đã thêm cột %s.%s", table, column)


def _add_missing_indexes(insp) -> None:
    for table, name, column in _INDEX_PATCHES:
        if not insp.has_table(table):
            continue
        existing = {i["name"] for i in insp.get_indexes(table)}
        if name in existing:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(f"CREATE INDEX {name} ON {table} ({column})"))
            logger.info("Đã tạo index %s", name)
        except Exception:
            logger.warning("Không tạo được index %s", name, exc_info=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    _add_missing_columns(insp)
    _add_missing_indexes(inspect(engine))
