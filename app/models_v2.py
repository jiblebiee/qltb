"""
Mô hình dữ liệu phiên bản 2 — quản lý theo TỪNG MÁY.

Khác biệt cốt lõi so với bản cũ (app/models.py):
  - Bản cũ: mỗi dòng `devices` là một LOẠI thiết bị kèm số lượng (normal_qty, broken_qty…).
  - Bản mới: `device_models` là LOẠI, `device_units` là TỪNG MÁY có mã riêng
    (LAP-01 … LAP-20). Phiếu mượn trỏ tới từng máy, nên luôn biết máy nào ở chỗ ai.

Các bảng cũ được giữ nguyên, không xoá, để còn tra cứu lịch sử.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ====================== Enum ======================

class UnitStatus(str, enum.Enum):
    """Trạng thái của một máy cụ thể."""
    AVAIL = "AVAIL"      # Sẵn sàng cho mượn
    OUT = "OUT"          # Đang cho mượn
    MAINT = "MAINT"      # Đang bảo trì
    BROKEN = "BROKEN"    # Đang hỏng


class ReturnCondition(str, enum.Enum):
    """Tình trạng máy tại thời điểm nhận trả."""
    NORMAL = "NORMAL"
    BROKEN = "BROKEN"
    MAINT = "MAINT"


class MaintStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    DONE = "DONE"
    CANCELED = "CANCELED"


class PhotoOwner(str, enum.Enum):
    """Ảnh dùng chung một bảng, phân biệt bằng chủ sở hữu."""
    MODEL = "MODEL"              # ảnh của loại thiết bị
    STOCK_IMPORT = "STOCK_IMPORT"
    STOCK_EXPORT = "STOCK_EXPORT"
    TICKET = "TICKET"            # ảnh lúc bàn giao
    RETURN = "RETURN"            # ảnh lúc nhận trả


# ====================== Loại thiết bị ======================

class DeviceModel(Base):
    """Một LOẠI thiết bị, ví dụ 'Laptop Dell Latitude 7420'."""
    __tablename__ = "device_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Mã ngắn dùng làm tiền tố cho từng máy: LAP -> LAP-01, LAP-02…
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Thông số chung, áp dụng cho mọi máy thuộc loại này
    info: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    units: Mapped[list["DeviceUnit"]] = relationship(
        back_populates="model", cascade="all, delete-orphan", order_by="DeviceUnit.no"
    )


class DeviceUnit(Base):
    """Một MÁY cụ thể. Đây là thứ được cho mượn, bảo trì, ghi nhận hỏng."""
    __tablename__ = "device_units"
    __table_args__ = (
        UniqueConstraint("model_id", "no", name="uq_unit_model_no"),
        Index("ix_unit_status", "status"),
        Index("ix_unit_holder", "holder_staff_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("device_models.id"), nullable=False, index=True)

    # Số thứ tự trong loại (1..n) và mã đầy đủ đã sinh sẵn để tra cứu nhanh
    no: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)

    status: Mapped[UnitStatus] = mapped_column(
        SAEnum(UnitStatus), nullable=False, default=UnitStatus.AVAIL
    )
    # Ai đang giữ máy — chỉ có giá trị khi status = OUT
    holder_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)

    serial: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Trường "tình trạng ghi nhận" ---
    # Tự động gắn từ ghi chú lúc nhận trả nếu ghi chú chứa từ khoá hư hại.
    # Máy vẫn có thể AVAIL nhưng mang cảnh báo này, ví dụ "hư sợi 1,3".
    issue_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    issue_source: Mapped[str | None] = mapped_column(String(64), nullable=True)  # mã phiếu

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    model: Mapped["DeviceModel"] = relationship(back_populates="units")


# ====================== Phiếu mượn ======================

class LoanTicket(Base):
    """
    Một phiếu mượn gom nhiều máy. KHÔNG có hạn trả.
    Quá `LOAN_OVERDUE_DAYS` (mặc định 10) ngày mà còn máy chưa trả thì coi là quá hạn.
    """
    __tablename__ = "loan_tickets"
    __table_args__ = (Index("ix_ticket_borrower", "borrower_staff_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)

    borrower_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False)
    lender_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    borrowed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # Chỉ được set khi TẤT CẢ máy trong phiếu đã trả
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Mốc đã gửi email cảnh báo quá hạn. Có giá trị nghĩa là phiếu này ĐÃ ĐƯỢC
    # cảnh báo và sẽ KHÔNG BAO GIỜ gửi lại, dù còn treo bao lâu — tránh làm phiền
    # trưởng bộ phận mỗi ngày. Phiếu vẫn hiện "Quá hạn" trên giao diện.
    overdue_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["LoanTicketItem"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )


class LoanTicketItem(Base):
    """Một máy trong một phiếu mượn."""
    __tablename__ = "loan_ticket_items"
    __table_args__ = (
        UniqueConstraint("ticket_id", "unit_id", name="uq_item_ticket_unit"),
        Index("ix_item_unit", "unit_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("loan_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[int] = mapped_column(ForeignKey("device_units.id"), nullable=False)

    returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ticket: Mapped["LoanTicket"] = relationship(back_populates="items")


class UnitReturn(Base):
    """
    Nhật ký nhận trả — MỘT DÒNG CHO MỘT MÁY.
    `note` là ghi chú riêng của đúng máy đó, ví dụ "hư sợi 1,3".
    """
    __tablename__ = "unit_returns"
    __table_args__ = (Index("ix_return_unit", "unit_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("loan_tickets.id"), nullable=False, index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("device_units.id"), nullable=False)

    condition: Mapped[ReturnCondition] = mapped_column(SAEnum(ReturnCondition), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    returned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    receiver_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


# ====================== Bảo trì ======================

class UnitMaintenance(Base):
    """Lịch bảo trì gắn với một máy cụ thể."""
    __tablename__ = "unit_maintenances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("device_units.id"), nullable=False, index=True)

    status: Mapped[MaintStatus] = mapped_column(
        SAEnum(MaintStatus), nullable=False, default=MaintStatus.SCHEDULED, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


# ====================== Kho hàng bán (tách khỏi kho cho mượn) ======================

class StockImport(Base):
    """Phiếu nhập hàng hoá về để BÁN. Không liên quan tới thiết bị cho mượn."""
    __tablename__ = "stock_imports"
    __table_args__ = (Index("ix_import_product", "product_name", "model_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_code: Mapped[str] = mapped_column(String(120), nullable=False)

    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[str | None] = mapped_column(String(60), nullable=True)  # Hàng mới / tân trang…

    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Nhân viên nào lập phiếu — lấy từ tài khoản đang đăng nhập
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class StockExport(Base):
    """Phiếu xuất hàng khỏi kho bán: bán, bảo hành, cấp nội bộ, trả nhà cung cấp."""
    __tablename__ = "stock_exports"
    __table_args__ = (Index("ix_export_product", "product_name", "model_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_code: Mapped[str] = mapped_column(String(120), nullable=False)

    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(60), nullable=False)          # Bán / Bảo hành / …
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)  # khách hàng, nơi nhận

    exported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


# ====================== Ảnh dùng chung ======================

class Photo(Base):
    """
    Một bảng ảnh cho mọi thứ, phân biệt bằng (owner_type, owner_id).
    Chỉ lưu object key của S3, URL được ký lúc đọc.
    """
    __tablename__ = "photos"
    __table_args__ = (Index("ix_photo_owner", "owner_type", "owner_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_type: Mapped[PhotoOwner] = mapped_column(SAEnum(PhotoOwner), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)

    image_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
