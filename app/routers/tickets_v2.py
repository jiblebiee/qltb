"""
API phiếu mượn — trả.

Phiếu không có hạn trả. Trạng thái suy ra từ số ngày đã mượn; quá ngưỡng thì
chuyển "Quá <n>n" và có email cảnh báo gửi tới trưởng bộ phận của người mượn.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas_v2 as sc
from ..config import settings
from ..db import get_db
from ..models import Department, Staff
from ..models_v2 import (
    DeviceModel, DeviceUnit, LoanTicket, LoanTicketItem, Photo, PhotoOwner, UnitReturn,
)
from ..security import require_perm
from ..services import loan_service, mail_service
from ..services.photo_service import attach_photos, photo_payload

router = APIRouter(prefix="/api/v2/tickets", tags=["tickets"])


def _people(db: Session, ids: set[int]) -> dict[int, Staff]:
    if not ids:
        return {}
    rows = db.execute(select(Staff).where(Staff.id.in_(ids))).scalars().all()
    return {s.id: s for s in rows}


def _units(db: Session, ids: set[int]) -> dict[int, DeviceUnit]:
    if not ids:
        return {}
    rows = db.execute(
        select(DeviceUnit).options(selectinload(DeviceUnit.model))
        .where(DeviceUnit.id.in_(ids))
    ).scalars().all()
    return {u.id: u for u in rows}


def _summary(units: dict[int, DeviceUnit], unit_ids: list[int]) -> str:
    """Gom mã máy cho gọn: 'LAP ×8 · HDMI ×4 · MC-01'."""
    groups: dict[str, list[str]] = {}
    for uid in unit_ids:
        u = units.get(uid)
        if not u:
            continue
        groups.setdefault(u.model.code, []).append(u.code)
    return " · ".join(
        codes[0] if len(codes) == 1 else f"{code} ×{len(codes)}"
        for code, codes in groups.items()
    )


def _ticket_out(db: Session, t: LoanTicket, people: dict[int, Staff],
                units: dict[int, DeviceUnit], now: datetime) -> sc.TicketOut:
    state = loan_service.ticket_state(t, now)
    borrower = people.get(t.borrower_staff_id)
    dep = borrower.department.name if borrower and borrower.department else None
    open_ids = [i.unit_id for i in t.items if not i.returned]
    return sc.TicketOut(
        id=t.id, code=t.code, state=state,
        state_label=loan_service.STATE_LABEL[state],
        days_elapsed=loan_service.days_since(t.borrowed_at, now),
        borrower_staff_id=t.borrower_staff_id,
        borrower_name=borrower.full_name if borrower else None,
        borrower_department=dep,
        lender_staff_id=t.lender_staff_id,
        lender_name=(people.get(t.lender_staff_id).full_name
                     if people.get(t.lender_staff_id) else None),
        borrowed_at=t.borrowed_at, returned_at=t.returned_at, note=t.note,
        total_units=len(t.items), open_units=len(open_ids),
        summary=_summary(units, open_ids or [i.unit_id for i in t.items]),
    )


# ----------------------------------------------------------------- danh sách

@router.get("", response_model=list[sc.TicketOut],
            dependencies=[Depends(require_perm("loan.loans.view"))])
def list_tickets(
    state: str | None = Query(default=None, pattern="^(open|over|soon|done|all)$"),
    borrower_staff_id: int | None = None,
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    stmt = (
        select(LoanTicket)
        .options(selectinload(LoanTicket.items))
        .order_by(LoanTicket.borrowed_at.desc(), LoanTicket.id.desc())
    )
    if borrower_staff_id:
        stmt = stmt.where(LoanTicket.borrower_staff_id == borrower_staff_id)
    if state == "done":
        stmt = stmt.where(LoanTicket.returned_at.is_not(None))
    elif state in {"open", "over", "soon"}:
        stmt = stmt.where(LoanTicket.returned_at.is_(None))

    if q:
        kw = f"%{q.strip()}%"
        unit_ticket_ids = select(LoanTicketItem.ticket_id).join(
            DeviceUnit, DeviceUnit.id == LoanTicketItem.unit_id
        ).where(DeviceUnit.code.ilike(kw))
        staff_ids = select(Staff.id).where(Staff.full_name.ilike(kw))
        stmt = stmt.where(or_(
            LoanTicket.code.ilike(kw),
            LoanTicket.borrower_staff_id.in_(staff_ids),
            LoanTicket.id.in_(unit_ticket_ids),
        ))

    tickets = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
    if state in {"over", "soon"}:
        tickets = [t for t in tickets if loan_service.ticket_state(t, now) == state]

    people = _people(db, {t.borrower_staff_id for t in tickets} |
                         {t.lender_staff_id for t in tickets})
    units = _units(db, {i.unit_id for t in tickets for i in t.items})
    return [_ticket_out(db, t, people, units, now) for t in tickets]


@router.get("/{code}", response_model=sc.TicketDetailOut,
            dependencies=[Depends(require_perm("loan.loans.view"))])
def get_ticket(code: str, db: Session = Depends(get_db)):
    t = db.execute(
        select(LoanTicket).options(selectinload(LoanTicket.items))
        .where(LoanTicket.code == code)
    ).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Không tìm thấy phiếu")

    now = datetime.utcnow()
    units = _units(db, {i.unit_id for i in t.items})
    people = _people(db, {t.borrower_staff_id, t.lender_staff_id})
    base = _ticket_out(db, t, people, units, now)

    returns = db.execute(
        select(UnitReturn).where(UnitReturn.ticket_id == t.id)
        .order_by(UnitReturn.returned_at.desc(), UnitReturn.id.desc())
    ).scalars().all()
    receivers = _people(db, {r.receiver_staff_id for r in returns if r.receiver_staff_id})

    return sc.TicketDetailOut(
        **base.model_dump(),
        items=[
            sc.TicketItemOut(
                unit_id=i.unit_id,
                code=units[i.unit_id].code if i.unit_id in units else str(i.unit_id),
                model_name=units[i.unit_id].model.name if i.unit_id in units else "",
                returned=i.returned, returned_at=i.returned_at,
            ) for i in sorted(t.items, key=lambda x: x.id)
        ],
        returns=[
            sc.ReturnOut(
                id=r.id, unit_id=r.unit_id,
                unit_code=units[r.unit_id].code if r.unit_id in units else str(r.unit_id),
                condition=r.condition, note=r.note, returned_at=r.returned_at,
                receiver_name=(receivers.get(r.receiver_staff_id).full_name
                               if r.receiver_staff_id in receivers else None),
            ) for r in returns
        ],
        images=photo_payload(db, PhotoOwner.TICKET, t.id),
    )


# ----------------------------------------------------------------- mượn

@router.post("", response_model=sc.TicketDetailOut, status_code=201,
             dependencies=[Depends(require_perm("loan.loans.create"))])
def create_ticket(payload: sc.BorrowRequest, request: Request, db: Session = Depends(get_db)):
    """
    Tạo phiếu mượn. Các máy được khoá dòng trước khi kiểm tra nên hai người
    mượn cùng lúc cùng một máy thì chỉ một người thành công.
    """
    uid = getattr(request.state, "user_id", None)
    ticket = loan_service.borrow(
        db,
        borrower_staff_id=payload.borrower_staff_id,
        lender_staff_id=payload.lender_staff_id,
        unit_ids=payload.unit_ids,
        note=payload.note,
        created_by_user_id=uid,
        borrowed_at=payload.borrowed_at,
    )
    attach_photos(db, PhotoOwner.TICKET, ticket.id, payload.image_keys, uid)
    db.commit()
    db.refresh(ticket)

    # Email xác nhận gửi tới trưởng bộ phận của người mượn.
    # Lỗi gửi mail không được làm hỏng phiếu đã tạo.
    try:
        mail_service.notify_ticket_created(db, ticket)
    except Exception:
        pass

    return get_ticket(ticket.code, db)


# ----------------------------------------------------------------- trả

@router.post("/{code}/return",
             dependencies=[Depends(require_perm("loan.loans.update"))])
def return_ticket(code: str, payload: sc.ReturnRequest, request: Request,
                  db: Session = Depends(get_db)):
    """
    Nhận trả. Dùng chung cho cả trả một máy lẫn trả cả phiếu — chỉ khác số phần
    tử trong `items`. Mỗi phần tử có ghi chú riêng cho đúng máy đó.
    """
    t = db.execute(
        select(LoanTicket).options(selectinload(LoanTicket.items))
        .where(LoanTicket.code == code)
    ).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Không tìm thấy phiếu")

    uid = getattr(request.state, "user_id", None)
    lines = [
        loan_service.ReturnLine(i.unit_id, i.condition.value, i.note)
        for i in payload.items
    ]
    summary = loan_service.return_units(
        db, ticket=t, lines=lines,
        receiver_staff_id=payload.receiver_staff_id,
        created_by_user_id=uid,
    )

    for item in payload.items:
        if item.image_keys:
            ret = db.execute(
                select(UnitReturn).where(
                    UnitReturn.ticket_id == t.id, UnitReturn.unit_id == item.unit_id
                ).order_by(UnitReturn.id.desc()).limit(1)
            ).scalar_one_or_none()
            if ret:
                attach_photos(db, PhotoOwner.RETURN, ret.id, item.image_keys, uid)

    db.commit()
    return {"ok": True, "ticket": get_ticket(code, db).model_dump(), "summary": summary}


# ----------------------------------------------------------------- tiện ích

@router.get("/staff/{staff_id}/holding",
            dependencies=[Depends(require_perm("loan.loans.view"))])
def staff_holding(staff_id: int, db: Session = Depends(get_db)):
    """Các máy một nhân sự đang giữ — dùng khi chặn cho nghỉ việc."""
    units = db.execute(
        select(DeviceUnit).options(selectinload(DeviceUnit.model))
        .where(DeviceUnit.holder_staff_id == staff_id).order_by(DeviceUnit.code)
    ).scalars().all()
    return [{"unit_id": u.id, "code": u.code, "model_name": u.model.name} for u in units]


@router.post("/run-overdue-sweep",
             dependencies=[Depends(require_perm("loan.loans.update"))])
def run_overdue_sweep(db: Session = Depends(get_db)):
    """Chạy tay việc rà phiếu quá hạn, không cần đợi lịch hàng giờ."""
    from ..services.overdue_service import sweep_overdue
    sent = sweep_overdue(db)
    return {"ok": True, "sent": sent, "overdue_days": settings.loan_overdue_days}
