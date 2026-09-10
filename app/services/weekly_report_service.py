"""
Báo cáo định kỳ gửi cho quản lý.

Chỉ còn HAI thư định kỳ, và cả hai chỉ gửi tới địa chỉ quản lý trong
`EMAIL_MANAGE` — không gửi cho nhân sự:

  1. Thứ Bảy hàng tuần — thiết bị còn đang mượn
  2. Ngày 1 hàng tháng  — lịch sử cho mượn tháng trước, kèm file Excel

Việc nhắc quá hạn KHÔNG nằm ở đây. Nó do `overdue_service` lo, gửi thẳng cho
trưởng bộ phận và chỉ một lần cho mỗi phiếu.

Bản cũ còn một việc thứ ba: gửi nhắc quá hạn tới TỪNG NGƯỜI MƯỢN, lặp lại mỗi
ngày, chạy trên bảng `loans` cũ. Việc đó đã bị bỏ hẳn — vừa trùng chức năng vừa
làm phiền nhân sự.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import SessionLocal
from ..models import JobRun, Staff
from ..models_v2 import DeviceUnit, LoanTicket, LoanTicketItem, UnitReturn
from .email_service import send_email
from .notification_service import manage_recipients

logger = logging.getLogger(__name__)

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
WEEKLY_JOB = "weekly_outstanding_loans_report"
MONTHLY_JOB = "monthly_loan_history_report"
REPORT_HOUR = 8
CHECK_INTERVAL_SECONDS = 3600
SATURDAY = 5

TABLE_CSS = "border-collapse:collapse;font-size:13px;width:100%"
TH = 'style="padding:7px 10px;border-bottom:2px solid #14181b;text-align:left"'
TD = 'style="padding:6px 10px;border-bottom:1px solid #e5e7eb"'


# ---------------------------------------------------------------- vòng lặp

def start_weekly_report_scheduler(app) -> None:
    task = getattr(app.state, "weekly_report_task", None)
    if task and not task.done():
        return
    app.state.weekly_report_task = asyncio.create_task(_loop())


async def stop_weekly_report_scheduler(app) -> None:
    task = getattr(app.state, "weekly_report_task", None)
    if not task:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                send_weekly_outstanding_report_if_due(db)
                send_monthly_loan_history_report_if_due(db)
        except Exception:
            logger.exception("Chạy báo cáo định kỳ thất bại")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


# ---------------------------------------------------------------- tiện ích

def _local(value: datetime | None = None) -> datetime:
    value = value or datetime.utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(BANGKOK_TZ)


def _fmt(value: datetime | None) -> str:
    return _local(value).strftime("%d/%m/%Y") if value else "—"


def _days(value: datetime, now: datetime | None = None) -> int:
    return max(0, (_local(now).date() - _local(value).date()).days)


def _already_ran_today(db: Session, job_name: str, now_local: datetime) -> bool:
    job = db.execute(select(JobRun).where(JobRun.job_name == job_name)).scalar_one_or_none()
    return bool(job and job.last_run_at and _local(job.last_run_at).date() == now_local.date())


def _mark_ran(db: Session, job_name: str) -> None:
    job = db.execute(select(JobRun).where(JobRun.job_name == job_name)).scalar_one_or_none()
    if job:
        job.last_run_at = datetime.utcnow()
    else:
        db.add(JobRun(job_name=job_name, last_run_at=datetime.utcnow()))
    db.commit()


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th {TH}>{escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td {TD}>{escape(str(c))}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f'<table style="{TABLE_CSS}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


# ---------------------------------------------------------------- lấy dữ liệu

def _outstanding_rows(db: Session, now: datetime | None = None) -> list[dict]:
    """Từng máy còn đang ở ngoài, kèm số ngày đã mượn."""
    from ..config import settings

    tickets = db.execute(
        select(LoanTicket).options(selectinload(LoanTicket.items))
        .where(LoanTicket.returned_at.is_(None))
        .order_by(LoanTicket.borrowed_at)
    ).scalars().all()
    if not tickets:
        return []

    unit_ids = {i.unit_id for t in tickets for i in t.items if not i.returned}
    units = {
        u.id: u for u in db.execute(
            select(DeviceUnit).options(selectinload(DeviceUnit.model))
            .where(DeviceUnit.id.in_(unit_ids or {0}))
        ).scalars().all()
    }
    people = {
        s.id: s for s in db.execute(
            select(Staff).options(selectinload(Staff.department))
            .where(Staff.id.in_({t.borrower_staff_id for t in tickets} or {0}))
        ).scalars().all()
    }

    rows: list[dict] = []
    for t in tickets:
        borrower = people.get(t.borrower_staff_id)
        elapsed = _days(t.borrowed_at, now)
        for item in t.items:
            if item.returned:
                continue
            unit = units.get(item.unit_id)
            rows.append({
                "ticket_code": t.code,
                "unit_code": unit.code if unit else str(item.unit_id),
                "model_name": unit.model.name if unit else "",
                "borrower": borrower.full_name if borrower else "—",
                "department": borrower.department.name if borrower and borrower.department else "—",
                "borrowed_at": t.borrowed_at,
                "days": elapsed,
                "overdue": elapsed >= settings.loan_overdue_days,
            })
    rows.sort(key=lambda r: (-r["days"], r["borrower"]))
    return rows


def _month_rows(db: Session, start: datetime, end: datetime) -> list[dict]:
    """Lượt mượn phát sinh trong khoảng, kèm tình trạng lúc trả nếu đã trả."""
    tickets = db.execute(
        select(LoanTicket).options(selectinload(LoanTicket.items))
        .where(LoanTicket.borrowed_at >= start, LoanTicket.borrowed_at < end)
        .order_by(LoanTicket.borrowed_at)
    ).scalars().all()
    if not tickets:
        return []

    ticket_ids = [t.id for t in tickets]
    unit_ids = {i.unit_id for t in tickets for i in t.items}
    units = {
        u.id: u for u in db.execute(
            select(DeviceUnit).options(selectinload(DeviceUnit.model))
            .where(DeviceUnit.id.in_(unit_ids or {0}))
        ).scalars().all()
    }
    people = {
        s.id: s for s in db.execute(
            select(Staff).options(selectinload(Staff.department))
            .where(Staff.id.in_(
                {t.borrower_staff_id for t in tickets} |
                {t.lender_staff_id for t in tickets} or {0}))
        ).scalars().all()
    }
    returns = {
        (r.ticket_id, r.unit_id): r for r in db.execute(
            select(UnitReturn).where(UnitReturn.ticket_id.in_(ticket_ids or [0]))
            .order_by(UnitReturn.id)
        ).scalars().all()
    }
    cond_label = {"NORMAL": "Bình thường", "BROKEN": "Hỏng", "MAINT": "Cần bảo trì"}

    rows: list[dict] = []
    for t in tickets:
        borrower = people.get(t.borrower_staff_id)
        lender = people.get(t.lender_staff_id)
        for item in t.items:
            unit = units.get(item.unit_id)
            ret = returns.get((t.id, item.unit_id))
            rows.append({
                "ticket_code": t.code,
                "unit_code": unit.code if unit else str(item.unit_id),
                "model_name": unit.model.name if unit else "",
                "borrower": borrower.full_name if borrower else "—",
                "department": borrower.department.name if borrower and borrower.department else "—",
                "lender": lender.full_name if lender else "—",
                "borrowed_at": t.borrowed_at,
                "returned_at": item.returned_at,
                "status": "Đã trả" if item.returned else "Chưa trả",
                "condition": cond_label.get(ret.condition.value, "") if ret else "",
                # Ghi chú riêng của đúng máy đó lúc nhận trả
                "note": (ret.note if ret else None) or "",
            })
    return rows


# ---------------------------------------------------------------- báo cáo tuần

def send_weekly_outstanding_report_if_due(db: Session, now: datetime | None = None) -> bool:
    now_local = _local(now)
    if now_local.weekday() != SATURDAY or now_local.hour < REPORT_HOUR:
        return False
    if _already_ran_today(db, WEEKLY_JOB, now_local):
        return False
    if not send_weekly_outstanding_report_now(db, now):
        return False
    _mark_ran(db, WEEKLY_JOB)
    return True


def send_weekly_outstanding_report_now(db: Session, now: datetime | None = None) -> bool:
    recipients = manage_recipients()
    if not recipients:
        logger.info("Bỏ qua báo cáo tuần: EMAIL_MANAGE chưa cấu hình")
        return False

    now_local = _local(now)
    rows = _outstanding_rows(db, now)
    overdue = [r for r in rows if r["overdue"]]
    stamp = now_local.strftime("%d/%m/%Y")

    if not rows:
        text = f"Tính đến {stamp}, không còn thiết bị nào đang được mượn."
        html = f'<p style="font-family:system-ui">Tính đến {stamp}, không còn thiết bị nào đang được mượn.</p>'
    else:
        lines = [
            f"Tính đến {stamp}, còn {len(rows)} máy đang được mượn"
            + (f", trong đó {len(overdue)} máy quá hạn." if overdue else "."),
            "",
        ]
        lines += [
            f"  {r['unit_code']:<14} {r['borrower']:<22} {r['days']:>3} ngày"
            f"{'  ⚠ quá hạn' if r['overdue'] else ''}"
            for r in rows
        ]
        text = "\n".join(lines)
        html = (
            f'<div style="font-family:system-ui,Segoe UI,sans-serif;color:#14181b">'
            f"<p>Tính đến <b>{stamp}</b>, còn <b>{len(rows)} máy</b> đang được mượn"
            + (f", trong đó <b style=\"color:#b3261e\">{len(overdue)} máy quá hạn</b>." if overdue else ".")
            + "</p>"
            + _html_table(
                ["Mã máy", "Thiết bị", "Người mượn", "Phòng ban", "Ngày mượn", "Số ngày", "Phiếu"],
                [[r["unit_code"], r["model_name"], r["borrower"], r["department"],
                  _fmt(r["borrowed_at"]),
                  f"{r['days']} ngày" + (" — quá hạn" if r["overdue"] else ""),
                  r["ticket_code"]] for r in rows])
            + "</div>"
        )

    return send_email(
        subject="[IT-QLTB] Báo cáo thiết bị còn đang mượn — tuần " + stamp,
        body=text, recipients=recipients, html_body=html,
    )


# ---------------------------------------------------------------- báo cáo tháng

def _previous_month(now_local: datetime) -> tuple[datetime, datetime]:
    first_this = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), first_this


def send_monthly_loan_history_report_if_due(db: Session, now: datetime | None = None) -> bool:
    now_local = _local(now)
    if now_local.day != 1 or now_local.hour < REPORT_HOUR:
        return False
    if _already_ran_today(db, MONTHLY_JOB, now_local):
        return False
    if not send_monthly_loan_history_report_now(db, now):
        return False
    _mark_ran(db, MONTHLY_JOB)
    return True


def send_monthly_loan_history_report_now(db: Session, now: datetime | None = None) -> bool:
    recipients = manage_recipients()
    if not recipients:
        logger.info("Bỏ qua báo cáo tháng: EMAIL_MANAGE chưa cấu hình")
        return False

    now_local = _local(now)
    start, end = _previous_month(now_local)
    rows = _month_rows(db, start.replace(tzinfo=None), end.replace(tzinfo=None))
    label = start.strftime("%m/%Y")
    returned = sum(1 for r in rows if r["status"] == "Đã trả")

    text = "\n".join([
        f"Lịch sử cho mượn thiết bị tháng {label}.",
        f"Tổng lượt mượn: {len(rows)} máy — đã trả {returned}, chưa trả {len(rows) - returned}.",
        "",
        "Chi tiết xem file Excel đính kèm.",
    ])
    html = (
        f'<div style="font-family:system-ui,Segoe UI,sans-serif;color:#14181b">'
        f"<p>Lịch sử cho mượn thiết bị tháng <b>{label}</b>.</p>"
        f"<p>Tổng lượt mượn: <b>{len(rows)} máy</b> — đã trả {returned}, "
        f"chưa trả {len(rows) - returned}.</p>"
        + (_html_table(
            ["Mã máy", "Thiết bị", "Người mượn", "Ngày mượn", "Ngày trả", "Tình trạng", "Ghi chú"],
            [[r["unit_code"], r["model_name"], r["borrower"], _fmt(r["borrowed_at"]),
              _fmt(r["returned_at"]), r["condition"] or r["status"], r["note"]]
             for r in rows[:60]]) if rows else "<p>Tháng này không phát sinh lượt mượn nào.</p>")
        + ("<p style='color:#6e787c;font-size:13px'>Bảng trên hiển thị 60 dòng đầu, "
           "đầy đủ trong file Excel đính kèm.</p>" if len(rows) > 60 else "")
        + "</div>"
    )

    attachments = []
    if rows:
        attachments.append({
            "filename": f"Lich_su_cho_muon_{start.strftime('%m-%Y')}.xlsx",
            "content": _monthly_excel(rows),
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

    return send_email(
        subject=f"[IT-QLTB] Báo cáo lịch sử cho mượn thiết bị tháng {label}",
        body=text, recipients=recipients, html_body=html, attachments=attachments,
    )


def _monthly_excel(rows: list[dict]) -> bytes:
    df = pd.DataFrame([{
        "Mã phiếu": r["ticket_code"],
        "Mã máy": r["unit_code"],
        "Thiết bị": r["model_name"],
        "Người mượn": r["borrower"],
        "Phòng ban": r["department"],
        "Người cho mượn": r["lender"],
        "Ngày mượn": _fmt(r["borrowed_at"]),
        "Ngày trả": _fmt(r["returned_at"]),
        "Trạng thái": r["status"],
        "Tình trạng khi trả": r["condition"],
        "Ghi chú riêng": r["note"],
    } for r in rows])

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Lich su cho muon")
        sheet = writer.sheets["Lich su cho muon"]
        for idx, column in enumerate(df.columns, start=1):
            width = max(len(str(column)), *(len(str(v)) for v in df[column])) + 2
            sheet.column_dimensions[sheet.cell(row=1, column=idx).column_letter].width = min(width, 45)
    buf.seek(0)
    return buf.read()
