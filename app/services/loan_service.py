"""
Nghiệp vụ mượn — trả.

Hai điểm quan trọng so với bản cũ:

1. KHOÁ DÒNG khi đổi trạng thái máy. Bản cũ đọc rồi ghi available_qty không khoá,
   nên hai người mượn cùng lúc một thiết bị còn 1 cái thì cả hai đều thành công.
   Ở đây mọi máy được SELECT ... FOR UPDATE trước khi kiểm tra và ghi.

2. MỘT ĐƯỜNG TRẢ DUY NHẤT. Bản cũ có /return và /return-batch xử lý tình trạng
   khác nhau, cho ra tồn kho lệch nhau. Giờ chỉ còn `return_units`, dùng chung
   cho cả trả một máy lẫn trả cả phiếu.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Staff
from ..models_v2 import (
    DeviceUnit, LoanTicket, LoanTicketItem, MaintStatus, ReturnCondition,
    UnitMaintenance, UnitReturn, UnitStatus,
)
from . import issue_service


# ---------------------------------------------------------------- trạng thái phiếu

def ticket_open_items(ticket: LoanTicket) -> list[LoanTicketItem]:
    return [i for i in ticket.items if not i.returned]


def days_since(dt: datetime, now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    return max(0, (now.date() - dt.date()).days)


def ticket_state(ticket: LoanTicket, now: datetime | None = None) -> str:
    """
    Không có hạn trả. Trạng thái suy ra từ số ngày đã mượn:
      done  — đã trả hết
      over  — còn máy chưa trả và đã quá LOAN_OVERDUE_DAYS ngày  ("Quá 10n")
      soon  — sắp chạm ngưỡng, dùng để nhắc trước
      open  — đang mượn bình thường
    """
    if not ticket_open_items(ticket):
        return "done"
    elapsed = days_since(ticket.borrowed_at, now)
    if elapsed >= settings.loan_overdue_days:
        return "over"
    if elapsed >= max(1, settings.loan_overdue_days - 2):
        return "soon"
    return "open"


STATE_LABEL = {
    "done": "Đã trả",
    "over": f"Quá {settings.loan_overdue_days}n",
    "soon": f"Sắp quá {settings.loan_overdue_days}n",
    "open": "Đang mượn",
}


def make_ticket_code() -> str:
    raw = uuid.uuid4().hex.upper()
    return f"{raw[:4]}-{raw[4:8]}"


# ---------------------------------------------------------------- mượn

def _lock_units(db: Session, unit_ids: list[int]) -> list[DeviceUnit]:
    """Khoá các dòng máy theo thứ tự id để tránh deadlock giữa hai giao dịch."""
    if not unit_ids:
        raise HTTPException(400, "Chưa chọn máy nào")
    stmt = (
        select(DeviceUnit)
        .where(DeviceUnit.id.in_(sorted(set(unit_ids))))
        .order_by(DeviceUnit.id)
    )
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    return list(db.execute(stmt).scalars().all())


def _require_staff(db: Session, staff_id: int, label: str) -> Staff:
    staff = db.get(Staff, staff_id)
    if not staff:
        raise HTTPException(404, f"Không tìm thấy {label}")
    return staff


def borrow(
    db: Session,
    *,
    borrower_staff_id: int,
    lender_staff_id: int,
    unit_ids: list[int],
    note: str | None = None,
    created_by_user_id: int | None = None,
    borrowed_at: datetime | None = None,
) -> LoanTicket:
    """Tạo một phiếu mượn gồm nhiều máy. Toàn bộ thành công hoặc không gì cả."""
    borrower = _require_staff(db, borrower_staff_id, "nhân sự mượn")
    _require_staff(db, lender_staff_id, "nhân sự cho mượn")

    if getattr(borrower, "status", None) and str(borrower.status).endswith("INACTIVE"):
        raise HTTPException(400, "Nhân sự này đã nghỉ, không thể cho mượn")

    unit_ids = list(dict.fromkeys(unit_ids))  # bỏ trùng, giữ thứ tự người dùng chọn
    if not unit_ids:
        raise HTTPException(400, "Chưa chọn máy nào")

    units = _lock_units(db, unit_ids)
    found = {u.id: u for u in units}

    missing = [uid for uid in unit_ids if uid not in found]
    if missing:
        raise HTTPException(404, f"Không tìm thấy máy có id: {missing}")

    busy = [u.code for u in units if u.status != UnitStatus.AVAIL]
    if busy:
        raise HTTPException(
            409, f"Các máy sau không còn sẵn sàng, có người vừa mượn trước: {', '.join(busy)}"
        )

    ticket = LoanTicket(
        code=make_ticket_code(),
        borrower_staff_id=borrower_staff_id,
        lender_staff_id=lender_staff_id,
        created_by_user_id=created_by_user_id,
        borrowed_at=borrowed_at or datetime.utcnow(),
        note=(note or None),
    )
    db.add(ticket)
    db.flush()

    for uid in unit_ids:
        unit = found[uid]
        unit.status = UnitStatus.OUT
        unit.holder_staff_id = borrower_staff_id
        db.add(LoanTicketItem(ticket_id=ticket.id, unit_id=unit.id, returned=False))

    db.flush()
    return ticket


# ---------------------------------------------------------------- trả

class ReturnLine:
    """Một dòng trong phiếu nhận trả: máy nào, tình trạng gì, ghi chú riêng."""

    __slots__ = ("unit_id", "condition", "note")

    def __init__(self, unit_id: int, condition: str, note: str | None = None):
        cond = (condition or "NORMAL").upper()
        if cond not in {c.value for c in ReturnCondition}:
            raise HTTPException(400, "Tình trạng phải là NORMAL, BROKEN hoặc MAINT")
        self.unit_id = int(unit_id)
        self.condition = ReturnCondition(cond)
        self.note = (note or "").strip() or None


def return_units(
    db: Session,
    *,
    ticket: LoanTicket,
    lines: list[ReturnLine],
    receiver_staff_id: int | None = None,
    created_by_user_id: int | None = None,
    returned_at: datetime | None = None,
) -> dict:
    """
    Nhận trả một phần hoặc toàn bộ phiếu.

    - NORMAL: máy trở lại Sẵn sàng
    - BROKEN: máy chuyển sang Hỏng, không cho mượn tiếp
    - MAINT : máy chuyển sang Bảo trì và tự sinh lịch bảo trì, dùng chính ghi chú
              riêng của máy đó làm nội dung

    Ghi chú riêng được lưu vào `unit_returns.note` và, nếu nhắc tới hư hại, được
    gắn lên trường tình trạng của máy.
    """
    if not lines:
        raise HTTPException(400, "Chưa chọn máy nào để trả")
    now = returned_at or datetime.utcnow()

    open_items = {i.unit_id: i for i in ticket_open_items(ticket)}
    unknown = [l.unit_id for l in lines if l.unit_id not in open_items]
    if unknown:
        raise HTTPException(400, f"Các máy này không nằm trong phiếu hoặc đã trả rồi: {unknown}")

    units = {u.id: u for u in _lock_units(db, [l.unit_id for l in lines])}

    summary = {"normal": 0, "broken": 0, "maint": 0, "flagged": []}

    for line in lines:
        unit = units.get(line.unit_id)
        if not unit:
            raise HTTPException(404, f"Không tìm thấy máy id={line.unit_id}")

        item = open_items[line.unit_id]
        item.returned = True
        item.returned_at = now

        unit.holder_staff_id = None
        if line.condition == ReturnCondition.NORMAL:
            unit.status = UnitStatus.AVAIL
            summary["normal"] += 1
        elif line.condition == ReturnCondition.BROKEN:
            unit.status = UnitStatus.BROKEN
            summary["broken"] += 1
        else:
            unit.status = UnitStatus.MAINT
            summary["maint"] += 1
            db.add(UnitMaintenance(
                unit_id=unit.id,
                status=MaintStatus.SCHEDULED,
                # ghi chú riêng của máy trở thành nội dung lịch bảo trì
                note=line.note or "Trả thiết bị — cần bảo trì",
                scheduled_at=now,
                created_by_user_id=created_by_user_id,
            ))

        db.add(UnitReturn(
            ticket_id=ticket.id,
            unit_id=unit.id,
            condition=line.condition,
            note=line.note,
            returned_at=now,
            receiver_staff_id=receiver_staff_id,
            created_by_user_id=created_by_user_id,
        ))

        if issue_service.apply_issue(unit, line.note, line.condition, now, ticket.code):
            summary["flagged"].append(unit.code)

    db.flush()
    if not ticket_open_items(ticket):
        ticket.returned_at = now

    return summary


# ---------------------------------------------------------------- quá hạn

def overdue_tickets(db: Session, now: datetime | None = None) -> list[LoanTicket]:
    """Phiếu còn máy chưa trả và đã quá ngưỡng ngày."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=settings.loan_overdue_days)
    stmt = (
        select(LoanTicket)
        .where(LoanTicket.returned_at.is_(None), LoanTicket.borrowed_at <= cutoff)
        .order_by(LoanTicket.borrowed_at)
    )
    return [t for t in db.execute(stmt).scalars().all() if ticket_open_items(t)]
