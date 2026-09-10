"""
Tạo loại thiết bị và sinh máy đơn chiếc.

Quy ước mã: <MÃ LOẠI>-<số thứ tự 2 chữ số>, ví dụ LAP-01 … LAP-20.
Thêm máy vào loại đã có thì đánh số tiếp từ số lớn nhất hiện tại.
"""
from __future__ import annotations

import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models_v2 import DeviceModel, DeviceUnit, UnitStatus

# Kho thật có mặt hàng đếm theo sợi (dây tín hiệu 1000 sợi), nên trần một lần
# tạo phải đủ rộng cho chúng. Vẫn chặn được số lượng vô lý do gõ nhầm.
MAX_UNITS_PER_BATCH = 2000
CODE_RE = re.compile(r"^[A-Z0-9]{2,12}$")


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def suggest_code(db: Session, name: str) -> str:
    """Gợi ý mã loại từ tên: 'Laptop HP ProBook 450 G9' -> 'LHP'."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", strip_accents(name).upper()) if w]
    if not words:
        return ""
    base = words[0][:4] if len(words) == 1 else "".join(w[0] for w in words[:3])
    code, i = base, 2
    while db.execute(select(DeviceModel.id).where(DeviceModel.code == code)).first():
        code, i = f"{base}{i}", i + 1
    return code


def validate_code(code: str) -> str:
    code = strip_accents(code or "").upper()
    code = re.sub(r"[^A-Z0-9]", "", code)
    if not CODE_RE.match(code):
        raise HTTPException(400, "Mã loại chỉ gồm chữ và số, dài 2–12 ký tự")
    return code


def unit_code(model_code: str, no: int) -> str:
    return f"{model_code}-{no:02d}"


def next_unit_no(db: Session, model_id: int) -> int:
    current = db.execute(
        select(func.coalesce(func.max(DeviceUnit.no), 0)).where(DeviceUnit.model_id == model_id)
    ).scalar_one()
    return int(current) + 1


def create_units(db: Session, model: DeviceModel, quantity: int) -> list[DeviceUnit]:
    """
    Sinh `quantity` máy mới cho một loại, đánh số tiếp theo số hiện có.
    Chưa commit — nơi gọi tự quyết định thời điểm commit.
    """
    if quantity < 1:
        raise HTTPException(400, "Số lượng phải từ 1 trở lên")
    if quantity > MAX_UNITS_PER_BATCH:
        raise HTTPException(400, f"Mỗi lần chỉ tạo tối đa {MAX_UNITS_PER_BATCH} máy")

    start = next_unit_no(db, model.id)
    made: list[DeviceUnit] = []
    for offset in range(quantity):
        no = start + offset
        unit = DeviceUnit(
            model_id=model.id,
            no=no,
            code=unit_code(model.code, no),
            status=UnitStatus.AVAIL,
        )
        db.add(unit)
        made.append(unit)
    return made


def model_counters(db: Session, model_ids: list[int]) -> dict[int, dict[str, int]]:
    """Đếm số máy theo trạng thái cho nhiều loại bằng MỘT truy vấn (tránh N+1)."""
    if not model_ids:
        return {}
    rows = db.execute(
        select(DeviceUnit.model_id, DeviceUnit.status, func.count(DeviceUnit.id))
        .where(DeviceUnit.model_id.in_(model_ids))
        .group_by(DeviceUnit.model_id, DeviceUnit.status)
    ).all()

    out: dict[int, dict[str, int]] = {
        mid: {"total": 0, "avail": 0, "out": 0, "maint": 0, "broken": 0} for mid in model_ids
    }
    key = {
        UnitStatus.AVAIL: "avail", UnitStatus.OUT: "out",
        UnitStatus.MAINT: "maint", UnitStatus.BROKEN: "broken",
    }
    for model_id, status, count in rows:
        bucket = out.setdefault(
            model_id, {"total": 0, "avail": 0, "out": 0, "maint": 0, "broken": 0}
        )
        bucket[key[status]] = int(count)
        bucket["total"] += int(count)
    return out


def issue_counts(db: Session, model_ids: list[int]) -> dict[int, int]:
    """Số máy đang mang ghi chú tình trạng, theo từng loại."""
    if not model_ids:
        return {}
    rows = db.execute(
        select(DeviceUnit.model_id, func.count(DeviceUnit.id))
        .where(DeviceUnit.model_id.in_(model_ids), DeviceUnit.issue_text.is_not(None))
        .group_by(DeviceUnit.model_id)
    ).all()
    return {mid: int(n) for mid, n in rows}
