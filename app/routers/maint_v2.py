"""API bảo trì — gắn với TỪNG MÁY, không còn theo số lượng."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import schemas_v2 as sc
from ..db import get_db
from ..models_v2 import DeviceUnit, MaintStatus, UnitMaintenance, UnitStatus
from ..security import require_perm
from ..services import issue_service

router = APIRouter(prefix="/api/v2/maintenance", tags=["maintenance"])


def _out(m: UnitMaintenance, unit: DeviceUnit) -> sc.MaintOut:
    return sc.MaintOut(
        id=m.id, unit_id=m.unit_id, unit_code=unit.code, model_name=unit.model.name,
        status=m.status, note=m.note,
        scheduled_at=m.scheduled_at, completed_at=m.completed_at,
    )


@router.get("", response_model=list[sc.MaintOut],
            dependencies=[Depends(require_perm("loan.maintenance.view"))])
def list_maintenance(
    status: MaintStatus | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    stmt = (
        select(UnitMaintenance, DeviceUnit)
        .join(DeviceUnit, DeviceUnit.id == UnitMaintenance.unit_id)
        .options(selectinload(DeviceUnit.model))
        .order_by(UnitMaintenance.scheduled_at.desc(), UnitMaintenance.id.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(UnitMaintenance.status == status)
    return [_out(m, u) for m, u in db.execute(stmt).all()]


@router.get("/broken",
            dependencies=[Depends(require_perm("loan.maintenance.view"))])
def list_broken(db: Session = Depends(get_db)):
    """Máy đang hỏng — chưa có lịch bảo trì nhưng cũng không cho mượn được."""
    units = db.execute(
        select(DeviceUnit).options(selectinload(DeviceUnit.model))
        .where(DeviceUnit.status == UnitStatus.BROKEN).order_by(DeviceUnit.code)
    ).scalars().all()
    return [{
        "unit_id": u.id, "code": u.code, "model_name": u.model.name,
        "issue_text": u.issue_text, "issue_at": u.issue_at,
    } for u in units]


@router.post("", response_model=sc.MaintOut, status_code=201,
             dependencies=[Depends(require_perm("loan.maintenance.create"))])
def create_maintenance(payload: sc.MaintCreate, request: Request, db: Session = Depends(get_db)):
    """Đưa một máy vào bảo trì. Máy đang cho mượn thì phải nhận trả trước."""
    unit = db.get(DeviceUnit, payload.unit_id)
    if not unit:
        raise HTTPException(404, "Không tìm thấy máy")
    if unit.status == UnitStatus.OUT:
        raise HTTPException(400, f"{unit.code} đang được cho mượn, cần nhận trả trước")
    if unit.status == UnitStatus.MAINT:
        raise HTTPException(400, f"{unit.code} đã đang trong lịch bảo trì")

    m = UnitMaintenance(
        unit_id=unit.id,
        status=MaintStatus.SCHEDULED,
        note=(payload.note or "").strip() or None,
        scheduled_at=payload.scheduled_at or datetime.utcnow(),
        created_by_user_id=getattr(request.state, "user_id", None),
    )
    unit.status = UnitStatus.MAINT
    db.add_all([m, unit])
    db.commit()
    db.refresh(m)
    return _out(m, unit)


@router.post("/{maint_id}/complete", response_model=sc.MaintOut,
             dependencies=[Depends(require_perm("loan.maintenance.update"))])
def complete_maintenance(maint_id: int, payload: sc.MaintComplete | None = None,
                         db: Session = Depends(get_db)):
    """Hoàn tất bảo trì: máy trở lại Sẵn sàng, tuỳ chọn gỡ ghi chú tình trạng."""
    m = db.get(UnitMaintenance, maint_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy lịch bảo trì")
    unit = db.get(DeviceUnit, m.unit_id)
    if not unit:
        raise HTTPException(404, "Không tìm thấy máy")

    if m.status == MaintStatus.DONE:
        return _out(m, unit)

    payload = payload or sc.MaintComplete()
    if payload.note:
        m.note = payload.note.strip() or m.note
    m.status = MaintStatus.DONE
    m.completed_at = datetime.utcnow()

    if unit.status == UnitStatus.MAINT:
        unit.status = UnitStatus.AVAIL
    if payload.clear_issue:
        issue_service.clear_issue(unit)

    db.add_all([m, unit])
    db.commit()
    db.refresh(m)
    return _out(m, unit)


@router.post("/{maint_id}/cancel", response_model=sc.MaintOut,
             dependencies=[Depends(require_perm("loan.maintenance.update"))])
def cancel_maintenance(maint_id: int, db: Session = Depends(get_db)):
    m = db.get(UnitMaintenance, maint_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy lịch bảo trì")
    unit = db.get(DeviceUnit, m.unit_id)
    if m.status == MaintStatus.SCHEDULED:
        m.status = MaintStatus.CANCELED
        if unit and unit.status == UnitStatus.MAINT:
            unit.status = UnitStatus.AVAIL
        db.commit()
        db.refresh(m)
    return _out(m, unit)


@router.post("/units/{unit_id}/mark-broken",
             dependencies=[Depends(require_perm("loan.maintenance.update"))])
def mark_broken(unit_id: int, payload: sc.MaintComplete | None = None,
                db: Session = Depends(get_db)):
    """Đánh dấu một máy đang hỏng mà không qua luồng nhận trả."""
    unit = db.get(DeviceUnit, unit_id)
    if not unit:
        raise HTTPException(404, "Không tìm thấy máy")
    if unit.status == UnitStatus.OUT:
        raise HTTPException(400, f"{unit.code} đang được cho mượn, cần nhận trả trước")
    unit.status = UnitStatus.BROKEN
    note = (payload.note if payload else None) or ""
    if note.strip():
        issue_service.apply_issue(unit, note, "BROKEN", datetime.utcnow(), "thủ công")
    db.commit()
    return {"ok": True, "code": unit.code, "status": unit.status.value}
