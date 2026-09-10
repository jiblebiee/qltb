"""
API nhân sự và phòng ban.

Phòng ban có thêm trưởng bộ phận — người nhận email khi nhân sự trong phòng
mượn thiết bị, và nhận cảnh báo khi phiếu quá hạn.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas_v2 as sc
from ..db import get_db
from ..models import Department, Staff, StaffStatus
from ..models_v2 import DeviceUnit
from ..security import require_perm

router = APIRouter(prefix="/api/v2", tags=["org"])

EMAIL_RE = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


def _held_by_dept(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Staff.department_id, func.count(DeviceUnit.id))
        .join(DeviceUnit, DeviceUnit.holder_staff_id == Staff.id)
        .group_by(Staff.department_id)
    ).all()
    return {dep_id: int(n) for dep_id, n in rows if dep_id}


def _held_codes(db: Session, staff_ids: list[int]) -> dict[int, list[str]]:
    if not staff_ids:
        return {}
    rows = db.execute(
        select(DeviceUnit.holder_staff_id, DeviceUnit.code)
        .where(DeviceUnit.holder_staff_id.in_(staff_ids))
        .order_by(DeviceUnit.code)
    ).all()
    out: dict[int, list[str]] = {}
    for sid, code in rows:
        out.setdefault(sid, []).append(code)
    return out


# ----------------------------------------------------------------- phòng ban

def _departments(db: Session, only_id: int | None = None) -> list[sc.DepartmentOut]:
    """Dựng dữ liệu phòng ban. Tách khỏi route để nơi khác gọi lại được."""
    stmt = select(Department).order_by(Department.name)
    if only_id is not None:
        stmt = stmt.where(Department.id == only_id)
    deps = list(db.execute(stmt).scalars().all())
    counts = dict(db.execute(
        select(Staff.department_id, func.count(Staff.id)).group_by(Staff.department_id)
    ).all())
    held = _held_by_dept(db)
    head_ids = {getattr(d, "head_staff_id", None) for d in deps} - {None}
    heads = {s.id: s for s in db.execute(
        select(Staff).where(Staff.id.in_(head_ids or {0}))
    ).scalars().all()}

    out = []
    for d in deps:
        head = heads.get(getattr(d, "head_staff_id", None))
        out.append(sc.DepartmentOut(
            id=d.id, name=d.name,
            head_staff_id=getattr(d, "head_staff_id", None),
            head_name=head.full_name if head else None,
            head_email=head.email if head else None,
            staff_count=int(counts.get(d.id, 0)),
            units_held=held.get(d.id, 0),
        ))
    return out


@router.get("/departments", response_model=list[sc.DepartmentOut],
            dependencies=[Depends(require_perm("loan.departments.view"))])
def list_departments(db: Session = Depends(get_db)):
    return _departments(db)


@router.post("/departments", response_model=sc.DepartmentOut, status_code=201,
             dependencies=[Depends(require_perm("loan.departments.create"))])
def create_department(payload: sc.DepartmentIn, db: Session = Depends(get_db)):
    name = payload.name.strip()
    exists = db.execute(
        select(Department.id).where(func.lower(Department.name) == name.lower())
    ).first()
    if exists:
        raise HTTPException(400, "Tên phòng ban này đã tồn tại")

    dep = Department(name=name)
    if payload.head_staff_id:
        _validate_head(db, payload.head_staff_id, None)
        dep.head_staff_id = payload.head_staff_id
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return _one_department(db, dep.id)


@router.put("/departments/{dep_id}", response_model=sc.DepartmentOut,
            dependencies=[Depends(require_perm("loan.departments.update"))])
def update_department(dep_id: int, payload: sc.DepartmentIn, db: Session = Depends(get_db)):
    dep = db.get(Department, dep_id)
    if not dep:
        raise HTTPException(404, "Không tìm thấy phòng ban")

    name = payload.name.strip()
    dup = db.execute(
        select(Department.id).where(func.lower(Department.name) == name.lower(),
                                    Department.id != dep_id)
    ).first()
    if dup:
        raise HTTPException(400, "Tên phòng ban này đã tồn tại")
    dep.name = name

    if payload.head_staff_id is None:
        dep.head_staff_id = None
    else:
        _validate_head(db, payload.head_staff_id, dep_id)
        dep.head_staff_id = payload.head_staff_id

    db.commit()
    return _one_department(db, dep_id)


def _validate_head(db: Session, staff_id: int, dep_id: int | None) -> None:
    head = db.get(Staff, staff_id)
    if not head:
        raise HTTPException(404, "Không tìm thấy nhân sự được chọn làm trưởng bộ phận")
    if head.status == StaffStatus.INACTIVE:
        raise HTTPException(400, "Nhân sự đã nghỉ không thể làm trưởng bộ phận")
    if dep_id is not None and head.department_id != dep_id:
        raise HTTPException(400, "Trưởng bộ phận phải là nhân sự thuộc chính phòng đó")
    if not head.email:
        raise HTTPException(400, "Trưởng bộ phận phải có email để nhận thông báo")


def _one_department(db: Session, dep_id: int) -> sc.DepartmentOut:
    rows = _departments(db, only_id=dep_id)
    if not rows:
        raise HTTPException(404, "Không tìm thấy phòng ban")
    return rows[0]


@router.delete("/departments/{dep_id}",
               dependencies=[Depends(require_perm("loan.departments.delete"))])
def delete_department(dep_id: int, db: Session = Depends(get_db)):
    dep = db.get(Department, dep_id)
    if not dep:
        raise HTTPException(404, "Không tìm thấy phòng ban")
    count = db.execute(
        select(func.count(Staff.id)).where(Staff.department_id == dep_id)
    ).scalar_one()
    if count:
        raise HTTPException(
            400, f"Phòng còn {count} nhân sự. Chuyển họ sang phòng khác trước khi xoá.")
    db.delete(dep)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- nhân sự

def _staff_list(
    db: Session,
    *,
    department_id: int | None = None,
    q: str | None = None,
    include_inactive: bool = True,
    only_id: int | None = None,
) -> list[sc.StaffOut]:
    """Dựng dữ liệu nhân sự. Tách khỏi route để nơi khác gọi lại được."""
    stmt = select(Staff).options(selectinload(Staff.department)).order_by(Staff.full_name)
    if only_id is not None:
        stmt = stmt.where(Staff.id == only_id)
    if department_id:
        stmt = stmt.where(Staff.department_id == department_id)
    if not include_inactive:
        stmt = stmt.where(Staff.status == StaffStatus.ACTIVE)
    if q:
        kw = f"%{q.strip()}%"
        stmt = stmt.where(Staff.full_name.ilike(kw) | Staff.email.ilike(kw))

    rows = list(db.execute(stmt).scalars().all())
    held = _held_codes(db, [s.id for s in rows])
    heads = {
        d.head_staff_id for d in db.execute(select(Department)).scalars().all()
        if getattr(d, "head_staff_id", None)
    }
    return [
        sc.StaffOut(
            id=s.id, full_name=s.full_name, email=s.email,
            department_id=s.department_id,
            department_name=s.department.name if s.department else None,
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            is_head=s.id in heads,
            units_held=held.get(s.id, []),
        ) for s in rows
    ]


@router.get("/staff", response_model=list[sc.StaffOut],
            dependencies=[Depends(require_perm("loan.staff.view"))])
def list_staff(
    department_id: int | None = None,
    q: str | None = Query(default=None, max_length=200),
    include_inactive: bool = True,
    db: Session = Depends(get_db),
):
    return _staff_list(db, department_id=department_id, q=q,
                       include_inactive=include_inactive)


@router.post("/staff", response_model=sc.StaffOut, status_code=201,
             dependencies=[Depends(require_perm("loan.staff.create"))])
def create_staff(payload: sc.StaffIn, db: Session = Depends(get_db)):
    email = (payload.email or "").strip() or None
    _check_email(db, email, None)
    if payload.department_id and not db.get(Department, payload.department_id):
        raise HTTPException(404, "Không tìm thấy phòng ban")

    s = Staff(
        full_name=payload.full_name.strip(),
        email=email,
        department_id=payload.department_id,
        status=StaffStatus(payload.status if payload.status in {"ACTIVE", "INACTIVE"} else "ACTIVE"),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _one_staff(db, s.id)


@router.put("/staff/{staff_id}", response_model=sc.StaffOut,
            dependencies=[Depends(require_perm("loan.staff.update"))])
def update_staff(staff_id: int, payload: sc.StaffIn, db: Session = Depends(get_db)):
    s = db.get(Staff, staff_id)
    if not s:
        raise HTTPException(404, "Không tìm thấy nhân sự")

    email = (payload.email or "").strip() or None
    _check_email(db, email, staff_id)

    new_status = payload.status if payload.status in {"ACTIVE", "INACTIVE"} else "ACTIVE"
    if new_status == "INACTIVE":
        holding = db.execute(
            select(func.count(DeviceUnit.id)).where(DeviceUnit.holder_staff_id == staff_id)
        ).scalar_one()
        if holding:
            raise HTTPException(
                400, f"Không thể cho nghỉ khi còn giữ {holding} máy chưa trả")
        # Trưởng bộ phận nghỉ thì gỡ khỏi vị trí, tránh email gửi vào hư không
        for dep in db.execute(
            select(Department).where(Department.head_staff_id == staff_id)
        ).scalars().all():
            dep.head_staff_id = None

    if payload.department_id and not db.get(Department, payload.department_id):
        raise HTTPException(404, "Không tìm thấy phòng ban")

    s.full_name = payload.full_name.strip()
    s.email = email
    s.department_id = payload.department_id
    s.status = StaffStatus(new_status)
    db.commit()
    return _one_staff(db, staff_id)


def _check_email(db: Session, email: str | None, staff_id: int | None) -> None:
    import re
    if not email:
        return
    if not re.match(EMAIL_RE, email):
        raise HTTPException(400, "Email chưa đúng định dạng")
    stmt = select(Staff.id).where(Staff.email == email)
    if staff_id:
        stmt = stmt.where(Staff.id != staff_id)
    if db.execute(stmt).first():
        raise HTTPException(400, "Email này đã dùng cho nhân sự khác")


def _one_staff(db: Session, staff_id: int) -> sc.StaffOut:
    rows = _staff_list(db, only_id=staff_id)
    if not rows:
        raise HTTPException(404, "Không tìm thấy nhân sự")
    return rows[0]


@router.delete("/staff/{staff_id}",
               dependencies=[Depends(require_perm("loan.staff.delete"))])
def deactivate_staff(staff_id: int, db: Session = Depends(get_db)):
    """Không xoá cứng — chuyển sang Đã nghỉ để giữ nguyên lịch sử mượn."""
    s = db.get(Staff, staff_id)
    if not s:
        raise HTTPException(404, "Không tìm thấy nhân sự")
    holding = db.execute(
        select(func.count(DeviceUnit.id)).where(DeviceUnit.holder_staff_id == staff_id)
    ).scalar_one()
    if holding:
        raise HTTPException(400, f"Nhân sự còn giữ {holding} máy chưa trả")

    for dep in db.execute(
        select(Department).where(Department.head_staff_id == staff_id)
    ).scalars().all():
        dep.head_staff_id = None

    s.status = StaffStatus.INACTIVE
    db.commit()
    return {"ok": True, "soft_deleted": True}
