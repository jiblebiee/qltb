"""
Email nghiệp vụ: gửi tới TRƯỞNG BỘ PHẬN của người mượn.

Hai loại email:
  1. Phiếu mượn mới tạo thành công
  2. Cảnh báo phiếu quá ngưỡng ngày chưa hoàn trả

Việc gửi thật vẫn dùng lại email_service.send_email (SMTP + ghi email_logs).
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Department, Staff
from ..models_v2 import DeviceUnit, LoanTicket
from .email_service import send_email

logger = logging.getLogger(__name__)
BANGKOK = ZoneInfo("Asia/Bangkok")


def _fmt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M")


def department_head(db: Session, staff: Staff | None) -> Staff | None:
    """Trưởng bộ phận của phòng mà nhân sự này thuộc về."""
    if not staff or not staff.department_id:
        return None
    dep = db.get(Department, staff.department_id)
    head_id = getattr(dep, "head_staff_id", None) if dep else None
    return db.get(Staff, head_id) if head_id else None


def _fallback_recipients() -> list[str]:
    raw = settings.email_manage or settings.mail_alert_recipients or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def _recipients(db: Session, borrower: Staff | None) -> tuple[list[str], str]:
    """Ưu tiên trưởng bộ phận; không có thì rơi về EMAIL_MANAGE."""
    head = department_head(db, borrower)
    if head and head.email:
        dep_name = head.department.name if head.department else ""
        return [head.email], f"{head.full_name} (trưởng BP {dep_name})"
    return _fallback_recipients(), "EMAIL_MANAGE"


def _unit_lines(db: Session, unit_ids: list[int]) -> list[str]:
    if not unit_ids:
        return []
    units = db.query(DeviceUnit).filter(DeviceUnit.id.in_(unit_ids)).all()
    return [f"{u.code} — {u.model.name}" for u in units]


def _table(rows: list[str]) -> str:
    body = "".join(
        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #e5e7eb">{escape(r)}</td></tr>'
        for r in rows
    )
    return f'<table style="border-collapse:collapse;font-size:14px">{body}</table>'


def notify_ticket_created(db: Session, ticket: LoanTicket) -> bool:
    """Email xác nhận sau khi tạo phiếu mượn thành công."""
    borrower = db.get(Staff, ticket.borrower_staff_id)
    lender = db.get(Staff, ticket.lender_staff_id)
    to, who = _recipients(db, borrower)
    if not to:
        logger.info("Bỏ qua email phiếu %s: không có người nhận", ticket.code)
        return False

    rows = _unit_lines(db, [i.unit_id for i in ticket.items])
    borrower_name = borrower.full_name if borrower else "—"
    subject = f"[IT-QLTB] Phiếu mượn mới #{ticket.code} — {borrower_name}, {len(rows)} máy"

    text = "\n".join([
        "Hệ thống vừa tạo một phiếu mượn thiết bị.",
        f"Mã phiếu: {ticket.code}",
        f"Nhân sự mượn: {borrower_name}",
        f"Nhân sự cho mượn: {lender.full_name if lender else '—'}",
        f"Thời gian mượn: {_fmt(ticket.borrowed_at)}",
        f"Ghi chú: {ticket.note or '(không có)'}",
        "",
        f"Danh sách {len(rows)} máy:",
        *[f"  - {r}" for r in rows],
        "",
        f"Phiếu không đặt hạn trả. Quá {settings.loan_overdue_days} ngày chưa hoàn trả,"
        " hệ thống sẽ gửi email cảnh báo.",
    ])
    html = f"""
      <div style="font-family:system-ui,Segoe UI,sans-serif;color:#14181b">
        <p>Hệ thống vừa tạo một phiếu mượn thiết bị.</p>
        <p><b>Mã phiếu:</b> {escape(ticket.code)}<br>
           <b>Nhân sự mượn:</b> {escape(borrower_name)}<br>
           <b>Nhân sự cho mượn:</b> {escape(lender.full_name if lender else '—')}<br>
           <b>Thời gian mượn:</b> {_fmt(ticket.borrowed_at)}<br>
           <b>Ghi chú:</b> {escape(ticket.note or '(không có)')}</p>
        <p><b>Danh sách {len(rows)} máy</b></p>
        {_table(rows)}
        <p style="color:#6e787c;font-size:13px">Phiếu không đặt hạn trả.
           Quá {settings.loan_overdue_days} ngày chưa hoàn trả sẽ có email cảnh báo.</p>
      </div>"""

    logger.info("Gửi email phiếu %s tới %s", ticket.code, who)
    return send_email(subject=subject, body=text, recipients=to, html_body=html)


ONE_TIME_NOTICE = ("Đây là thư cảnh báo duy nhất cho phiếu này — hệ thống sẽ "
                   "không gửi lại. Phiếu vẫn hiển thị trạng thái quá hạn trên "
                   "phần mềm cho tới khi thiết bị được hoàn trả.")


def notify_ticket_overdue(db: Session, ticket: LoanTicket, elapsed_days: int) -> bool:
    """
    Cảnh báo phiếu đã quá ngưỡng ngày mà chưa hoàn trả.

    Chỉ gửi MỘT LẦN cho mỗi phiếu — xem `overdue_service.sweep_overdue`.
    """
    borrower = db.get(Staff, ticket.borrower_staff_id)
    to, who = _recipients(db, borrower)
    if not to:
        return False

    open_ids = [i.unit_id for i in ticket.items if not i.returned]
    rows = _unit_lines(db, open_ids)
    borrower_name = borrower.full_name if borrower else "—"
    subject = (f"[IT-QLTB] CẢNH BÁO: phiếu #{ticket.code} đã {elapsed_days} ngày "
               f"chưa hoàn trả")

    text = "\n".join([
        f"Phiếu mượn #{ticket.code} đã quá {settings.loan_overdue_days} ngày chưa hoàn trả.",
        f"Nhân sự mượn: {borrower_name}",
        f"Ngày mượn: {_fmt(ticket.borrowed_at)} ({elapsed_days} ngày trước)",
        "",
        f"Còn {len(rows)} máy chưa trả:",
        *[f"  - {r}" for r in rows],
        "",
        ONE_TIME_NOTICE,
    ])
    html = f"""
      <div style="font-family:system-ui,Segoe UI,sans-serif;color:#14181b">
        <p style="color:#b3261e;font-weight:600">
          Phiếu mượn #{escape(ticket.code)} đã {elapsed_days} ngày chưa hoàn trả.</p>
        <p><b>Nhân sự mượn:</b> {escape(borrower_name)}<br>
           <b>Ngày mượn:</b> {_fmt(ticket.borrowed_at)} ({elapsed_days} ngày trước)</p>
        <p><b>Còn {len(rows)} máy chưa trả</b></p>
        {_table(rows)}
        <p style="color:#6e787c;font-size:13px;margin-top:16px">{escape(ONE_TIME_NOTICE)}</p>
      </div>"""

    logger.info("Gửi cảnh báo quá hạn phiếu %s tới %s", ticket.code, who)
    return send_email(subject=subject, body=text, recipients=to, html_body=html)
