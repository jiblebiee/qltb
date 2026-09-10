"""
Việc chạy nền: rà phiếu quá hạn và gửi cảnh báo.

Chạy trong vòng lặp asyncio của tiến trình web, mỗi giờ một lần. Cột
`overdue_notified_at` trên phiếu đảm bảo mỗi phiếu chỉ cảnh báo một lần mỗi
ngày, kể cả khi chạy nhiều uvicorn worker.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from . import loan_service, mail_service

logger = logging.getLogger(__name__)
CHECK_INTERVAL_SECONDS = 3600


def sweep_overdue(db: Session, now: datetime | None = None) -> int:
    """
    Gửi cảnh báo quá hạn. Trả về số email đã gửi.

    MỖI PHIẾU CHỈ CẢNH BÁO ĐÚNG MỘT LẦN, không nhắc lại dù phiếu còn treo bao
    lâu. Cột `overdue_notified_at` một khi đã có giá trị là phiếu vĩnh viễn
    không gửi thêm email nào nữa.

    Phiếu vẫn hiển thị "Quá 10n" trên màn hình Tổng quan và tab Mượn - Trả cho
    tới khi hoàn trả, nên việc không nhắc lại qua email không làm mất dấu phiếu.
    """
    now = now or datetime.utcnow()
    sent = 0
    for ticket in loan_service.overdue_tickets(db, now):
        if ticket.overdue_notified_at is not None:
            continue  # đã cảnh báo rồi — không gửi lại
        elapsed = loan_service.days_since(ticket.borrowed_at, now)
        if mail_service.notify_ticket_overdue(db, ticket, elapsed):
            ticket.overdue_notified_at = now
            db.add(ticket)
            sent += 1
    if sent:
        db.commit()
    return sent


async def _loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                count = sweep_overdue(db)
                if count:
                    logger.info("Đã gửi %s cảnh báo quá hạn", count)
        except Exception:
            logger.exception("Rà phiếu quá hạn thất bại")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def start(app) -> None:
    task = getattr(app.state, "overdue_task", None)
    if task and not task.done():
        return
    app.state.overdue_task = asyncio.create_task(_loop())


async def stop(app) -> None:
    task = getattr(app.state, "overdue_task", None)
    if not task:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
