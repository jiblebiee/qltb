"""API cho màn hình Tổng quan và lịch sử gửi mail."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..db import get_db
from ..models import EmailLog, Staff
from ..models_v2 import (
    DeviceUnit, LoanTicket, LoanTicketItem, MaintStatus, UnitMaintenance, UnitStatus,
)
from ..security import require_perm
from ..services import loan_service

router = APIRouter(prefix="/api/v2", tags=["reports"])


@router.get("/dashboard", dependencies=[Depends(require_perm("loan.devices.view",
                                                             "loan.loans.view"))])
def dashboard(db: Session = Depends(get_db)):
    """Số liệu và danh sách việc cần xử lý cho màn hình Tổng quan."""
    now = datetime.utcnow()

    counts = dict(db.execute(
        select(DeviceUnit.status, func.count(DeviceUnit.id)).group_by(DeviceUnit.status)
    ).all())
    avail = int(counts.get(UnitStatus.AVAIL, 0))
    out = int(counts.get(UnitStatus.OUT, 0))
    maint = int(counts.get(UnitStatus.MAINT, 0))
    broken = int(counts.get(UnitStatus.BROKEN, 0))

    open_tickets = list(db.execute(
        select(LoanTicket).options(selectinload(LoanTicket.items))
        .where(LoanTicket.returned_at.is_(None))
        .order_by(LoanTicket.borrowed_at)
    ).scalars().all())

    over, soon = [], []
    for t in open_tickets:
        state = loan_service.ticket_state(t, now)
        if state == "over":
            over.append(t)
        elif state == "soon":
            soon.append(t)

    people = {s.id: s for s in db.execute(
        select(Staff).where(Staff.id.in_({t.borrower_staff_id for t in over + soon} or {0}))
    ).scalars().all()}

    def ticket_brief(t: LoanTicket) -> dict:
        s = people.get(t.borrower_staff_id)
        return {
            "code": t.code,
            "borrower_name": s.full_name if s else None,
            "department": s.department.name if s and s.department else None,
            "borrowed_at": t.borrowed_at,
            "days_elapsed": loan_service.days_since(t.borrowed_at, now),
            "open_units": len([i for i in t.items if not i.returned]),
        }

    # Máy mang ghi chú tình trạng — vẫn có thể đang Sẵn sàng nên dễ bị cho mượn tiếp
    flagged = list(db.execute(
        select(DeviceUnit).options(selectinload(DeviceUnit.model))
        .where(DeviceUnit.issue_text.is_not(None))
        .order_by(DeviceUnit.issue_at.desc())
    ).scalars().all())

    open_maint = list(db.execute(
        select(UnitMaintenance, DeviceUnit)
        .join(DeviceUnit, DeviceUnit.id == UnitMaintenance.unit_id)
        .options(selectinload(DeviceUnit.model))
        .where(UnitMaintenance.status == MaintStatus.SCHEDULED)
        .order_by(UnitMaintenance.scheduled_at)
    ).all())

    # Lượt mượn / trả 7 ngày gần nhất
    start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    borrowed = dict(db.execute(
        select(func.date(LoanTicket.borrowed_at), func.count(LoanTicketItem.id))
        .join(LoanTicketItem, LoanTicketItem.ticket_id == LoanTicket.id)
        .where(LoanTicket.borrowed_at >= start)
        .group_by(func.date(LoanTicket.borrowed_at))
    ).all())
    returned = dict(db.execute(
        select(func.date(LoanTicketItem.returned_at), func.count(LoanTicketItem.id))
        .where(LoanTicketItem.returned_at.is_not(None),
               LoanTicketItem.returned_at >= start)
        .group_by(func.date(LoanTicketItem.returned_at))
    ).all())

    series = []
    for i in range(7):
        day = (start + timedelta(days=i)).date()
        series.append({
            "date": day.strftime("%d/%m"),
            "borrowed": int(borrowed.get(day, borrowed.get(str(day), 0)) or 0),
            "returned": int(returned.get(day, returned.get(str(day), 0)) or 0),
        })

    return {
        "units": {"total": avail + out + maint + broken, "avail": avail,
                  "out": out, "maint": maint, "broken": broken},
        "tickets": {"open": len(open_tickets), "overdue": len(over), "soon": len(soon)},
        "overdue_days": settings.loan_overdue_days,
        "todo": {
            "overdue": [ticket_brief(t) for t in over],
            "soon": [ticket_brief(t) for t in soon],
            "issues": [{
                "unit_id": u.id, "code": u.code, "model_name": u.model.name,
                "issue_text": u.issue_text, "issue_at": u.issue_at,
                "status": u.status.value,
            } for u in flagged],
            "maintenance": [{
                "id": m.id, "unit_id": u.id, "code": u.code, "model_name": u.model.name,
                "note": m.note, "scheduled_at": m.scheduled_at,
                "days": loan_service.days_since(m.scheduled_at, now),
            } for m, u in open_maint],
        },
        "series7": series,
    }


@router.get("/email-logs", dependencies=[Depends(require_perm("loan.loans.view"))])
def email_logs(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.execute(
        select(EmailLog).order_by(EmailLog.created_at.desc(), EmailLog.id.desc()).limit(limit)
    ).scalars().all()
    return [{
        "id": r.id, "subject": r.subject, "recipients": r.recipients,
        "status": r.status, "error_message": r.error_message, "created_at": r.created_at,
    } for r in rows]
