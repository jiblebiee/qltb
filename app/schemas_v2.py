"""Pydantic schema cho các API phiên bản 2."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models_v2 import MaintStatus, ReturnCondition, UnitStatus


# ------------------------------------------------------------------ thiết bị

class UnitOut(BaseModel):
    id: int
    code: str
    no: int
    model_id: int
    status: UnitStatus
    holder_staff_id: int | None = None
    holder_name: str | None = None
    serial: str | None = None
    note: str | None = None

    # Trường tình trạng: ghi chú hư hại bám theo máy, kèm thời điểm cập nhật
    issue_text: str | None = None
    issue_at: datetime | None = None
    issue_source: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ModelCounters(BaseModel):
    total: int = 0
    avail: int = 0
    out: int = 0
    maint: int = 0
    broken: int = 0
    issues: int = 0


class ModelOut(BaseModel):
    id: int
    code: str
    name: str
    brand: str | None = None
    info: str | None = None
    note: str | None = None
    counters: ModelCounters = Field(default_factory=ModelCounters)
    photo_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ModelDetailOut(ModelOut):
    units: list[UnitOut] = Field(default_factory=list)
    photos: list[dict] = Field(default_factory=list)


class ModelCreate(BaseModel):
    """Tạo loại mới kèm sinh sẵn `quantity` máy."""
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=12)
    brand: str | None = Field(default=None, max_length=120)
    info: str | None = None
    note: str | None = None
    quantity: int = Field(default=1, ge=1, le=2000)
    photo_keys: list[str] = Field(default_factory=list)


class ModelUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    brand: str | None = Field(default=None, max_length=120)
    info: str | None = None
    note: str | None = None


class UnitsAdd(BaseModel):
    """Thêm máy vào một loại đã có; hệ thống tự đánh số tiếp."""
    quantity: int = Field(ge=1, le=2000)
    photo_keys: list[str] = Field(default_factory=list)


class PhotoKeys(BaseModel):
    photo_keys: list[str] = Field(default_factory=list, min_length=1)


class UnitUpdate(BaseModel):
    serial: str | None = Field(default=None, max_length=120)
    note: str | None = None


# ------------------------------------------------------------------ mượn - trả

class BorrowRequest(BaseModel):
    borrower_staff_id: int
    lender_staff_id: int
    unit_ids: list[int] = Field(min_length=1)
    note: str | None = None
    image_keys: list[str] = Field(default_factory=list)

    # Ngày mượn. Bỏ trống thì lấy đúng lúc lập phiếu. Cho sửa để nhập bù những
    # phiếu đã giao máy từ hôm trước mà chưa kịp ghi vào hệ thống.
    borrowed_at: datetime | None = None

    @field_validator("borrowed_at")
    @classmethod
    def _check_borrowed_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is not None:
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        now = datetime.utcnow()
        # Nới một ngày vì máy trạm có thể lệch múi giờ so với máy chủ.
        if v > now + timedelta(days=1):
            raise ValueError("Ngày mượn không được nằm ở tương lai")
        if v < now - timedelta(days=3650):
            raise ValueError("Ngày mượn quá xa trong quá khứ")
        return v


class ReturnLineIn(BaseModel):
    unit_id: int
    condition: ReturnCondition = ReturnCondition.NORMAL
    # Ghi chú riêng cho ĐÚNG máy này, ví dụ "hư sợi 1,3" trên cuộn quang 6 đầu
    note: str | None = None
    image_keys: list[str] = Field(default_factory=list)


class ReturnRequest(BaseModel):
    items: list[ReturnLineIn] = Field(min_length=1)
    receiver_staff_id: int | None = None


class TicketItemOut(BaseModel):
    unit_id: int
    code: str
    model_name: str
    returned: bool
    returned_at: datetime | None = None


class TicketOut(BaseModel):
    id: int
    code: str
    state: str
    state_label: str
    days_elapsed: int
    borrower_staff_id: int
    borrower_name: str | None = None
    borrower_department: str | None = None
    lender_staff_id: int
    lender_name: str | None = None
    borrowed_at: datetime
    returned_at: datetime | None = None
    note: str | None = None
    total_units: int
    open_units: int
    summary: str = ""


class TicketDetailOut(TicketOut):
    items: list[TicketItemOut] = Field(default_factory=list)
    returns: list["ReturnOut"] = Field(default_factory=list)
    images: list[dict] = Field(default_factory=list)


class ReturnOut(BaseModel):
    id: int
    unit_id: int
    unit_code: str
    condition: ReturnCondition
    note: str | None = None
    returned_at: datetime
    receiver_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ bảo trì

class MaintOut(BaseModel):
    id: int
    unit_id: int
    unit_code: str
    model_name: str
    status: MaintStatus
    note: str | None = None
    scheduled_at: datetime
    completed_at: datetime | None = None


class MaintCreate(BaseModel):
    unit_id: int
    note: str | None = None
    scheduled_at: datetime | None = None


class MaintComplete(BaseModel):
    note: str | None = None
    # Sau khi bảo trì xong, máy trở lại Sẵn sàng và ghi chú tình trạng được gỡ
    clear_issue: bool = True


# ------------------------------------------------------------------ kho nhập/xuất

class ImportCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=120)
    model_code: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=1)
    condition: str | None = Field(default="Hàng mới", max_length=60)
    imported_at: datetime | None = None
    note: str | None = None
    photo_keys: list[str] = Field(default_factory=list)


class ExportCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    model_code: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=1)
    purpose: str = Field(default="Bán", max_length=60)
    destination: str | None = Field(default=None, max_length=255)
    exported_at: datetime | None = None
    note: str | None = None
    photo_keys: list[str] = Field(default_factory=list)


class StockRecordOut(BaseModel):
    id: int
    product_name: str
    model_code: str
    qty: int
    brand: str | None = None
    condition: str | None = None
    purpose: str | None = None
    destination: str | None = None
    note: str | None = None
    at: datetime
    created_by_user_id: int
    created_by_username: str | None = None
    created_by_name: str | None = None
    photos: list[dict] = Field(default_factory=list)


class StockLevelOut(BaseModel):
    product_name: str
    model_code: str
    imported: int
    exported: int
    on_hand: int


# ------------------------------------------------------------------ tổ chức

class DepartmentOut(BaseModel):
    id: int
    name: str
    head_staff_id: int | None = None
    head_name: str | None = None
    head_email: str | None = None
    staff_count: int = 0
    units_held: int = 0


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    head_staff_id: int | None = None


class StaffOut(BaseModel):
    id: int
    full_name: str
    email: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    status: str
    is_head: bool = False
    units_held: list[str] = Field(default_factory=list)


class StaffIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    department_id: int | None = None
    status: str = "ACTIVE"


TicketDetailOut.model_rebuild()
