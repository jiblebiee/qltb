# app/schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict

from .models import (
    StaffStatus,
    LoanStatus,
    LoanCondition,
    MaintenanceStatus,
)


# ===================== Departments =====================

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DepartmentOut(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# ===================== Staff =====================

class StaffCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    department_id: int | None = None
    status: StaffStatus = StaffStatus.ACTIVE


class StaffUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    department_id: int | None = None
    status: StaffStatus | None = None


class StaffOut(BaseModel):
    id: int
    full_name: str
    email: str | None
    department_id: int | None
    status: StaffStatus

    model_config = ConfigDict(from_attributes=True)


# ===================== Devices =====================

class DeviceLoanHistoryItem(BaseModel):
    loan_id: int
    qty: int
    borrowed_at: datetime

    returned_at: datetime | None = None
    condition: LoanCondition | None = None
    note: str | None = None

    borrower_name: str | None = None
    lender_name: str | None = None
    returner_name: str | None = None
    receiver_name: str | None = None

    images: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)




class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    normal_qty: int = Field(default=0, ge=0)
    broken_qty: int = Field(default=0, ge=0)
    maint_qty: int = Field(default=0, ge=0)
    image_key: str | None = None
    info: str | None = None
    note: str | None = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    normal_qty: Optional[int] = Field(default=None, ge=0)
    broken_qty: Optional[int] = Field(default=None, ge=0)
    maint_qty: Optional[int] = Field(default=None, ge=0)
    #image_key: Optional[str] = None
    image_key: str | None = None
    info: Optional[str] = None
    note: Optional[str] = None



class DeviceOut(BaseModel):
    id: int
    name: str
    normal_qty: int
    broken_qty: int
    maint_qty: int
    total_qty: int
    available_qty: int
    image_key: str | None
    info: str | None
    note: str | None

    model_config = ConfigDict(from_attributes=True)

from pydantic import BaseModel
from typing import Optional, List

class ImportRowError(BaseModel):
    row: int
    name: Optional[str] = None
    error: str

class ImportExcelResult(BaseModel):
    created: int
    updated: int
    failed: int
    errors: List[ImportRowError] = Field(default_factory=list)


# ===================== Loans =====================

class BorrowItem(BaseModel):
    device_id: int
    qty: int = Field(ge=1)
    note: str | None = None


class BorrowMultiRequest(BaseModel):
    borrower_staff_id: int
    lender_staff_id: int
    items: list[BorrowItem]
    borrowed_at: datetime | None = None
    due_at: datetime | None = None

    image_keys: list[str] | None = None   # âœ… THÃŠM DÃ’NG NÃ€Y



class LoanTicketListOut(BaseModel):
    ticket_code: str
    borrowed_at: datetime
    borrower_staff_id: int
    lender_staff_id: int
    returned_at: datetime | None = None
    receiver_staff_id: int | None = None
    status: str

    image_keys: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class BorrowRequest(BaseModel):
    device_id: int
    borrower_staff_id: int
    lender_staff_id: int
    qty: int = Field(ge=1)
    borrowed_at: datetime | None = None
    due_at: datetime | None = None


# (Náº¿u báº¡n váº«n dÃ¹ng endpoint borrow-ticket)
class BorrowTicketRequest(BorrowRequest):
    pass


class ReturnRequest(BaseModel):
    loan_id: int
    qty_return: int | None = Field(default=None, ge=1)
    returner_staff_id: int
    receiver_staff_id: int
    returned_at: datetime | None = None
    note: str | None = None
    condition: Literal["NORMAL", "BROKEN", "MAINT"] | None = None
    # âœ… condition/note dÃ¹ng cho popup náº¿u báº¡n gá»i /api/loans/return


    image_keys: list[str] = Field(default_factory=list)

class ReturnBatchItem(BaseModel):
    loan_id: int
    qty_return: int
    condition: Literal["NORMAL", "BROKEN", "MAINT"]
    note: str | None = None

    image_keys: list[str] = Field(default_factory=list)

class ReturnBatchRequest(BaseModel):
    receiver_staff_id: int
    returned_at: datetime | None = None
    note: str | None = None
    items: list[ReturnBatchItem]


class LoanOut(BaseModel):
    id: int
    device_id: int
    borrower_staff_id: int
    lender_staff_id: int
    qty: int
    returned_qty: int
    borrowed_at: datetime
    due_at: datetime | None
    returned_at: datetime | None
    returner_staff_id: int | None
    receiver_staff_id: int | None
    status: LoanStatus
    ticket_code: str

    model_config = ConfigDict(from_attributes=True)


class LoanTicketOut(BaseModel):
    ticket_code: str
    borrower_staff_id: int
    lender_staff_id: int
    borrowed_at: datetime
    due_at: datetime | None
    status: LoanStatus
    items: list[LoanOut]

    model_config = ConfigDict(from_attributes=True)


# ===================== Return (Request) =====================

class LoanReturnRequest(BaseModel):
    loan_id: int
    qty_return: int
    condition: Optional[LoanCondition] = LoanCondition.NORMAL
    note: Optional[str] = None
    returned_at: Optional[datetime] = None
    receiver_staff_id: Optional[int] = None



# ===================== Return log / History =====================

class LoanReturnLogOut(BaseModel):
    id: int
    loan_id: int
    qty_return: int
    condition: LoanCondition
    note: str | None = None
    returned_at: datetime
    receiver_staff_id: int | None

    model_config = ConfigDict(from_attributes=True)


class LoanHistoryRow(BaseModel):
    loan_id: int
    device_id: int
    device_name: str

    qty: int
    borrowed_at: datetime

    returned_qty: int
    returned_at: Optional[datetime]
    remaining: int

    status: LoanStatus

    last_condition: Optional[LoanCondition] = None
    last_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ===================== Maintenance =====================

class MaintenanceCreate(BaseModel):
    device_id: int
    scheduled_at: Optional[datetime] = None
    note: Optional[str] = None
    qty: int = Field(default=1, ge=1)

    model_config = ConfigDict(from_attributes=True)


class MaintenanceOut(BaseModel):
    id: int
    device_id: int
    device_name: str | None = None
    qty: int = 1
    scheduled_at: datetime
    completed_at: datetime | None
    status: MaintenanceStatus
    note: str | None

    model_config = ConfigDict(from_attributes=True)


class MaintenanceComplete(BaseModel):
    note: str | None = None


# ===================== Uploads =====================

class PresignPutRequest(BaseModel):
    filename: str
    content_type: str


class PresignPutResponse(BaseModel):
    object_key: str
    upload_url: str


class PresignGetResponse(BaseModel):
    view_url: str


# ===================== Users / RBAC =====================

class MeOut(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    role: str
    is_active: bool
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    role: str
    is_active: bool
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    is_active: bool = True
    permissions: list[str] | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    password: str | None = None
    permissions: list[str] | None = None


# ====== Loan Return Images ======
class LoanReturnLogImageOut(BaseModel):
    id: int
    return_log_id: int
    image_key: str
    created_at: datetime
    note: str | None = None
    model_config = ConfigDict(from_attributes=True)
















class ImportCreate(BaseModel):
    device_name: str
    brand: str
    import_model: str
    qty_import: int
    import_date: datetime
    staff_import: str
    import_status: str
    import_image: List[str] = []   # âœ… danh sÃ¡ch key S3












