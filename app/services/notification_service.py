from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .. import models
from ..config import settings
from .email_service import default_alert_recipients, send_email

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


def send_test_email(recipients: list[str] | None = None) -> bool:
    targets = recipients or default_alert_recipients()
    body = "\n".join(
        [
            "Đây là email kiểm tra chức năng cảnh báo của hệ thống QLTB.",
            f"Thời gian gửi: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ]
    )
    return send_email(
        subject="[IT-QLTB] Kiểm tra cấu hình email",
        body=body,
        recipients=targets,
    )


def notify_borrow_created(
    borrower: models.Staff | None,
    lender: models.Staff | None,
    ticket_code: str,
    borrowed_at: datetime,
    due_at: datetime | None,
    items: list[tuple[str, int]],
) -> bool:
    recipients = _unique_recipients(manage_recipients(), borrower.email if borrower else None)
    if not recipients:
        return False

    borrower_name = borrower.full_name if borrower else "N/A"
    lines = [
        "Hệ thống vừa tạo phiếu mượn thiết bị mới.",
        f"Nhân sự mượn: {borrower_name}",
        f"Nhân sự cho mượn: {lender.full_name if lender else 'N/A'}",
        f"Thời gian mượn: {_fmt_dt(borrowed_at)}",
        "",
        "Danh sách thiết bị:",
    ]
    lines.extend([f"- {name}: {qty}" for name, qty in items])

    return send_email(
        subject=f"[IT-QLTB] Đã tạo phiếu mượn cho {borrower_name}",
        body="\n".join(lines),
        recipients=recipients,
    )


def notify_maintenance_created(
    device: models.Device,
    qty: int,
    scheduled_at: datetime,
    note: str | None,
) -> bool:
    lines = [
        "Thiết bị đã được chuyển sang bảo trì.",
        f"Thiết bị: {device.name}",
        f"Số lượng: {qty}",
        f"Thời gian: {_fmt_dt(scheduled_at)}",
        f"Ghi chú: {note or '(không có)'}",
    ]
    return send_email(
        subject=f"[IT-QLTB] Cảnh báo bảo trì - {device.name}",
        body="\n".join(lines),
        recipients=default_alert_recipients(),
    )


def notify_return_issue(
    loan: models.Loan,
    device: models.Device,
    borrower: models.Staff | None,
    receiver: models.Staff | None,
    qty_return: int,
    condition: str,
    note: str | None,
    returned_at: datetime,
) -> bool:
    if condition not in {"BROKEN", "MAINT"}:
        return False

    issue_label = "Hỏng" if condition == "BROKEN" else "Cần bảo trì"
    lines = [
        "Hệ thống ghi nhận thiết bị trả về có cảnh báo.",
        f"Thiết bị: {device.name}",
        f"Số lượng: {qty_return}",
        f"Tình trạng: {issue_label}",
        f"Nhân sự mượn: {borrower.full_name if borrower else 'N/A'}",
        f"Nhân sự nhận: {receiver.full_name if receiver else 'N/A'}",
        f"Thời gian trả: {_fmt_dt(returned_at)}",
        f"Mã phiếu: {loan.ticket_code}",
        f"Ghi chú: {note or '(không có)'}",
    ]
    return send_email(
        subject=f"[IT-QLTB] Cảnh báo thiết bị {issue_label} - {device.name}",
        body="\n".join(lines),
        recipients=default_alert_recipients(),
    )


def _unique_recipients(*groups: str | list[str] | None) -> list[str]:
    seen: set[str] = set()
    recipients: list[str] = []
    for group in groups:
        if not group:
            continue
        values = group if isinstance(group, list) else [group]
        for item in values:
            value = (item or "").strip()
            if value and value not in seen:
                seen.add(value)
                recipients.append(value)
    return recipients


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(BANGKOK_TZ).strftime("%Y-%m-%d")


def _now_local() -> datetime:
    return datetime.now(BANGKOK_TZ)

def manage_recipients() -> list[str]:
    raw = settings.email_manage or ""
    return [item.strip() for item in raw.split(",") if item.strip()]
