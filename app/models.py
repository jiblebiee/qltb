import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, Enum as SAEnum, ForeignKey, Text,
    UniqueConstraint, Boolean, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ====== enums ======
class StaffStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class LoanStatus(str, enum.Enum):
    BORROWED = "Äang MÆ°á»£n"
    RETURNED = "ÄÃ£ Tráº£"
    PARTIAL  = "Tráº£ CÃ²n Thiáº¿u"   # âœ… thÃªm náº¿u báº¡n muá»‘n dÃ¹ng
    OVERDUE  = "QuÃ¡ Háº¡n"

class LoanCondition(str, enum.Enum):
    NORMAL = "NORMAL"
    BROKEN = "BROKEN"
    MAINT  = "MAINT"

class MaintenanceStatus(str, enum.Enum):
    SCHEDULED = "Äang Báº£o TrÃ¬"
    DONE = "ÄÃ£ Báº£o TrÃ¬"
    CANCELED = "ÄÃ£ Há»§y"


# ====== Departments ======
class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Trưởng bộ phận: nhận email khi nhân sự trong phòng mượn thiết bị,
    # và nhận cảnh báo khi phiếu quá hạn chưa hoàn trả.
    head_staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", use_alter=True, name="fk_dept_head"), nullable=True
    )

    staff: Mapped[list["Staff"]] = relationship(
        back_populates="department", foreign_keys="Staff.department_id"
    )


# ====== Staff ======
class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (UniqueConstraint("email", name="uq_staff_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[StaffStatus] = mapped_column(
        SAEnum(StaffStatus),
        default=StaffStatus.ACTIVE,
        nullable=False
    )

    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    department: Mapped["Department | None"] = relationship(
        back_populates="staff", foreign_keys=[department_id]
    )


# ====== Device ======
class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    normal_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    broken_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maint_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    image_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # ThÃ´ng tin thiáº¿t bá»‹ (cáº¥u hÃ¬nh, serial, OS, ...)
    info: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ====== Loans ======
class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)

    borrower_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False)
    lender_staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False)

    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    returned_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    borrowed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    returner_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    receiver_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[LoanStatus] = mapped_column(SAEnum(LoanStatus), default=LoanStatus.BORROWED, nullable=False)

    # ticket_code (náº¿u báº¡n Ä‘ang dÃ¹ng UUID() cá»§a MySQL thÃ¬ giá»¯ nguyÃªn theo code báº¡n)
    ticket_code: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped["Device"] = relationship()
    borrower: Mapped["Staff"] = relationship(foreign_keys=[borrower_staff_id])
    lender: Mapped["Staff"] = relationship(foreign_keys=[lender_staff_id])
    returner: Mapped["Staff | None"] = relationship(foreign_keys=[returner_staff_id])
    receiver: Mapped["Staff | None"] = relationship(foreign_keys=[receiver_staff_id])

    # âœ… quan trá»ng: dÃ¹ng back_populates (trÃ¡nh backref trÃ¹ng)
    return_logs: Mapped[list["LoanReturnLog"]] = relationship(
        "LoanReturnLog",
        back_populates="loan",
        cascade="all, delete-orphan",
    )


class LoanReturnLog(Base):
    __tablename__ = "loan_return_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), nullable=False)

    qty_return: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[LoanCondition] = mapped_column(SAEnum(LoanCondition), nullable=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    receiver_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)

    loan: Mapped["Loan"] = relationship("Loan", back_populates="return_logs")

    return_images: Mapped[list["LoanReturnLogImage"]] = relationship(
        "LoanReturnLogImage",
        back_populates="return_log",
        cascade="all, delete-orphan",
    )
class LoanTicketImage(Base):
    __tablename__ = "loan_ticket_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_code: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    image_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class LoanReturnLogImage(Base):
    __tablename__ = "loan_return_log_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    return_log_id: Mapped[int] = mapped_column(
        ForeignKey("loan_return_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    return_log: Mapped["LoanReturnLog"] = relationship("LoanReturnLog", back_populates="return_images")




# ====== Maintenance ======
class MaintenanceSchedule(Base):
    __tablename__ = "maintenance_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[MaintenanceStatus] = mapped_column(
        SAEnum(MaintenanceStatus),
        default=MaintenanceStatus.SCHEDULED,
        nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped["Device"] = relationship()


# ====== Users ======
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="ADMIN")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    permissions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())



class Imports(Base):
    __tablename__ = "imports"
    id = Column(Integer, primary_key=True, index=True)

    device_name = Column(String(255))
    brand = Column(String(120))
    import_model = Column(String(120))
    qty_import = Column(Integer)
    import_date = Column(DateTime, default=datetime.utcnow)
    staff_import = Column(String(120))
    import_status = Column(String(120))
    import_image = Column(Text, nullable=True)


class Exports(Base):
    __tablename__ = "exports"
    id = Column(Integer, primary_key=True, index=True)

    device_name = Column(String(255))
    export_date = Column(DateTime, default=datetime.utcnow)
    model_export = Column(String(120))
    import_model_ref = Column(String(120), nullable=True)
    qty_export = Column(Integer)
    staff_export = Column(String(120))
    project_export = Column(String(120))
    img_export = Column(Text, nullable=True)


class ImportHistory(Base):
    __tablename__ = "import_history"
    id = Column(Integer, primary_key=True, index=True)

    device_name = Column(String(255))
    brand = Column(String(120))
    model_import = Column(String(120))
    qty_import = Column(Integer)
    import_date = Column(DateTime)
    staff_import = Column(String(120))
    status_import = Column(String(120))
    img_import = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class ExportHistory(Base):
    __tablename__ = "export_history"
    id = Column(Integer, primary_key=True, index=True)

    device_name = Column(String(255))
    export_date = Column(DateTime)
    model_export = Column(String(120))
    qty_export = Column(Integer)
    staff_export = Column(String(120))
    project_export = Column(String(120))
    img_export = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String(100), unique=True, nullable=False, index=True)
    last_run_at = Column(DateTime, nullable=True)

class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(255), nullable=False)
    recipients = Column(Text, nullable=False)
    body_preview = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="SENT")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
