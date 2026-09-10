"""
API thiết bị cho mượn: loại thiết bị và từng máy đơn chiếc.

Mọi endpoint tự khai báo quyền qua Depends(require_perm(...)).
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas_v2 as sc
from ..db import get_db
from ..models import Staff
from ..models_v2 import DeviceModel, DeviceUnit, LoanTicket, LoanTicketItem, Photo, PhotoOwner, UnitReturn, UnitStatus
from ..security import require_perm
from ..services import issue_service, unit_service
from ..services import label_service
from ..services.photo_service import attach_photos, photo_payload

router = APIRouter(prefix="/api/v2/devices", tags=["devices"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _unit_out(u: DeviceUnit, holder_names: dict[int, str] | None = None) -> sc.UnitOut:
    holder_names = holder_names or {}
    return sc.UnitOut(
        id=u.id, code=u.code, no=u.no, model_id=u.model_id, status=u.status,
        holder_staff_id=u.holder_staff_id,
        holder_name=holder_names.get(u.holder_staff_id) if u.holder_staff_id else None,
        serial=u.serial, note=u.note,
        issue_text=u.issue_text, issue_at=u.issue_at, issue_source=u.issue_source,
    )


def _holder_names(db: Session, units: list[DeviceUnit]) -> dict[int, str]:
    """Lấy tên người giữ bằng một truy vấn, thay vì hỏi từng máy một."""
    ids = {u.holder_staff_id for u in units if u.holder_staff_id}
    if not ids:
        return {}
    rows = db.execute(select(Staff.id, Staff.full_name).where(Staff.id.in_(ids))).all()
    return {sid: name for sid, name in rows}


# ----------------------------------------------------------------- loại thiết bị

@router.get("/models", response_model=list[sc.ModelOut],
            dependencies=[Depends(require_perm("loan.devices.view"))])
def list_models(
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    stmt = select(DeviceModel).order_by(DeviceModel.name)
    if q:
        kw = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            DeviceModel.name.ilike(kw), DeviceModel.code.ilike(kw),
            DeviceModel.brand.ilike(kw), DeviceModel.info.ilike(kw),
        ))
    models = list(db.execute(stmt).scalars().all())
    ids = [m.id for m in models]

    counters = unit_service.model_counters(db, ids)
    issues = unit_service.issue_counts(db, ids)
    photos = dict(db.execute(
        select(Photo.owner_id, func.count(Photo.id))
        .where(Photo.owner_type == PhotoOwner.MODEL, Photo.owner_id.in_(ids or [0]))
        .group_by(Photo.owner_id)
    ).all())

    out = []
    for m in models:
        c = counters.get(m.id, {})
        out.append(sc.ModelOut(
            id=m.id, code=m.code, name=m.name, brand=m.brand, info=m.info, note=m.note,
            counters=sc.ModelCounters(**{**c, "issues": issues.get(m.id, 0)}),
            photo_count=int(photos.get(m.id, 0)),
        ))
    return out


@router.get("/models/{model_id}", response_model=sc.ModelDetailOut,
            dependencies=[Depends(require_perm("loan.devices.view"))])
def get_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(DeviceModel, model_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy loại thiết bị")

    units = list(db.execute(
        select(DeviceUnit).where(DeviceUnit.model_id == m.id).order_by(DeviceUnit.no)
    ).scalars().all())
    names = _holder_names(db, units)
    c = unit_service.model_counters(db, [m.id]).get(m.id, {})
    issues = unit_service.issue_counts(db, [m.id]).get(m.id, 0)

    return sc.ModelDetailOut(
        id=m.id, code=m.code, name=m.name, brand=m.brand, info=m.info, note=m.note,
        counters=sc.ModelCounters(**{**c, "issues": issues}),
        units=[_unit_out(u, names) for u in units],
        photos=photo_payload(db, PhotoOwner.MODEL, m.id),
    )


@router.get("/models/{model_id}/qr.svg",
            dependencies=[Depends(require_perm("loan.devices.view"))])
def model_qr(model_id: int, db: Session = Depends(get_db)):
    """Ảnh QR của mã loại, dùng làm ô xem trước trong bảng thiết bị."""
    m = db.get(DeviceModel, model_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy loại thiết bị")
    svg = label_service.qr_svg(m.code, size_mm=None)
    # Mã loại không đổi nên cho trình duyệt giữ lại một ngày, khỏi vẽ đi vẽ lại
    return Response(svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=86400"})


@router.get("/models/{model_id}/labels", response_class=HTMLResponse,
            dependencies=[Depends(require_perm("loan.devices.view"))])
def model_labels(model_id: int, kind: str = Query(default="units", pattern="^(units|model)$"),
                 db: Session = Depends(get_db)):
    """
    Tờ tem QR in được, mở thẳng trong trình duyệt rồi Ctrl+P.

    `kind=units` — mỗi máy một tem mang mã riêng (LAP-01, LAP-02…). Đây là loại
    tem dán lên máy, quét vào là thêm đúng máy đó vào phiếu.
    `kind=model` — một tem mang mã loại, dán lên thùng hoặc kệ chứa cả lô.
    """
    m = db.get(DeviceModel, model_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy loại thiết bị")

    if kind == "model":
        rows = [(m.code, m.name)]
        heading = f"{m.name} · mã loại"
    else:
        units = db.execute(
            select(DeviceUnit).where(DeviceUnit.model_id == m.id).order_by(DeviceUnit.no)
        ).scalars().all()
        if not units:
            raise HTTPException(400, "Loại này chưa có máy nào để in tem")
        rows = [(u.code, m.name) for u in units]
        heading = m.name

    return HTMLResponse(label_service.labels_html(rows, heading=heading))


@router.post("/models", response_model=sc.ModelDetailOut, status_code=201,
             dependencies=[Depends(require_perm("loan.devices.create"))])
def create_model(payload: sc.ModelCreate, request: Request, db: Session = Depends(get_db)):
    """Tạo loại mới và sinh sẵn số máy ban đầu."""
    code = unit_service.validate_code(payload.code) if payload.code \
        else unit_service.suggest_code(db, payload.name)
    if not code:
        raise HTTPException(400, "Không suy ra được mã loại, hãy nhập thủ công")
    if db.execute(select(DeviceModel.id).where(DeviceModel.code == code)).first():
        raise HTTPException(400, f"Mã loại {code} đã được dùng")

    m = DeviceModel(
        code=code, name=payload.name.strip(),
        brand=(payload.brand or "").strip() or None,
        info=(payload.info or "").strip() or None,
        note=(payload.note or "").strip() or None,
    )
    db.add(m)
    db.flush()

    unit_service.create_units(db, m, payload.quantity)
    attach_photos(db, PhotoOwner.MODEL, m.id, payload.photo_keys,
                  getattr(request.state, "user_id", None))
    db.commit()
    return get_model(m.id, db)


@router.put("/models/{model_id}", response_model=sc.ModelDetailOut,
            dependencies=[Depends(require_perm("loan.devices.update"))])
def update_model(model_id: int, payload: sc.ModelUpdate, db: Session = Depends(get_db)):
    m = db.get(DeviceModel, model_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy loại thiết bị")
    data = payload.model_dump(exclude_unset=True)
    for field in ("name", "brand", "info", "note"):
        if field in data:
            value = (data[field] or "").strip() if isinstance(data[field], str) else data[field]
            setattr(m, field, value or None)
    if not m.name:
        raise HTTPException(400, "Tên loại không được để trống")
    db.commit()
    return get_model(model_id, db)


@router.delete("/models/{model_id}",
               dependencies=[Depends(require_perm("loan.devices.delete"))])
def delete_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(DeviceModel, model_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy loại thiết bị")

    used = db.execute(
        select(func.count(LoanTicketItem.id))
        .join(DeviceUnit, DeviceUnit.id == LoanTicketItem.unit_id)
        .where(DeviceUnit.model_id == model_id)
    ).scalar_one()
    if used:
        raise HTTPException(400, "Loại này đã có lịch sử cho mượn, không được xoá")

    db.delete(m)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- máy đơn chiếc

@router.post("/models/{model_id}/units", response_model=sc.ModelDetailOut, status_code=201,
             dependencies=[Depends(require_perm("loan.devices.create"))])
def add_units(model_id: int, payload: sc.UnitsAdd, request: Request, db: Session = Depends(get_db)):
    """Nhập bổ sung máy cho loại đã có; đánh số tiếp từ số lớn nhất."""
    m = db.get(DeviceModel, model_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy loại thiết bị")
    unit_service.create_units(db, m, payload.quantity)
    attach_photos(db, PhotoOwner.MODEL, m.id, payload.photo_keys,
                  getattr(request.state, "user_id", None))
    db.commit()
    return get_model(model_id, db)


@router.post("/models/{model_id}/photos", response_model=sc.ModelDetailOut,
             dependencies=[Depends(require_perm("loan.devices.update"))])
def add_model_photos(model_id: int, payload: sc.PhotoKeys, request: Request,
                     db: Session = Depends(get_db)):
    """Gắn thêm ảnh cho loại thiết bị mà không sinh máy mới."""
    m = db.get(DeviceModel, model_id)
    if not m:
        raise HTTPException(404, "Không tìm thấy loại thiết bị")
    added = attach_photos(db, PhotoOwner.MODEL, m.id, payload.photo_keys,
                          getattr(request.state, "user_id", None))
    if not added:
        raise HTTPException(400, "Không thêm được ảnh — có thể đã đạt giới hạn số ảnh")
    db.commit()
    return get_model(model_id, db)


@router.delete("/models/{model_id}/photos/{photo_id}",
               dependencies=[Depends(require_perm("loan.devices.update"))])
def delete_model_photo(model_id: int, photo_id: int, db: Session = Depends(get_db)):
    p = db.get(Photo, photo_id)
    if not p or p.owner_type != PhotoOwner.MODEL or p.owner_id != model_id:
        raise HTTPException(404, "Không tìm thấy ảnh")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/units", response_model=list[sc.UnitOut],
            dependencies=[Depends(require_perm("loan.devices.view"))])
def list_units(
    q: str | None = Query(default=None, max_length=200),
    status: UnitStatus | None = None,
    model_id: int | None = None,
    has_issue: bool | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(DeviceUnit).join(DeviceModel).order_by(DeviceUnit.code)
    if status:
        stmt = stmt.where(DeviceUnit.status == status)
    if model_id:
        stmt = stmt.where(DeviceUnit.model_id == model_id)
    if has_issue is True:
        stmt = stmt.where(DeviceUnit.issue_text.is_not(None))
    elif has_issue is False:
        stmt = stmt.where(DeviceUnit.issue_text.is_(None))
    if q:
        kw = f"%{q.strip()}%"
        # tìm được cả theo nội dung ghi chú tình trạng
        stmt = stmt.where(or_(
            DeviceUnit.code.ilike(kw), DeviceUnit.issue_text.ilike(kw),
            DeviceUnit.serial.ilike(kw), DeviceModel.name.ilike(kw),
        ))
    units = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
    names = _holder_names(db, units)
    return [_unit_out(u, names) for u in units]


@router.get("/units/{unit_id}",
            dependencies=[Depends(require_perm("loan.devices.view"))])
def get_unit(unit_id: int, db: Session = Depends(get_db)):
    """Chi tiết một máy: thông số, tình trạng ghi nhận và toàn bộ lịch sử của nó."""
    u = db.get(DeviceUnit, unit_id)
    if not u:
        raise HTTPException(404, "Không tìm thấy máy")
    names = _holder_names(db, [u])

    borrows = db.execute(
        select(LoanTicket, LoanTicketItem)
        .join(LoanTicketItem, LoanTicketItem.ticket_id == LoanTicket.id)
        .where(LoanTicketItem.unit_id == unit_id)
        .order_by(LoanTicket.borrowed_at.desc())
    ).all()
    staff_ids = {t.borrower_staff_id for t, _ in borrows} | {t.lender_staff_id for t, _ in borrows}
    staff_names = dict(db.execute(
        select(Staff.id, Staff.full_name).where(Staff.id.in_(staff_ids or {0}))
    ).all())

    returns = db.execute(
        select(UnitReturn).where(UnitReturn.unit_id == unit_id)
        .order_by(UnitReturn.returned_at.desc())
    ).scalars().all()
    ticket_codes = dict(db.execute(
        select(LoanTicket.id, LoanTicket.code)
        .where(LoanTicket.id.in_([r.ticket_id for r in returns] or [0]))
    ).all())

    return {
        "unit": _unit_out(u, names).model_dump(),
        "model": {"id": u.model.id, "code": u.model.code, "name": u.model.name,
                  "brand": u.model.brand, "info": u.model.info, "note": u.model.note},
        "borrows": [
            {"ticket_code": t.code, "borrowed_at": t.borrowed_at,
             "returned": item.returned, "returned_at": item.returned_at,
             "borrower_name": staff_names.get(t.borrower_staff_id),
             "lender_name": staff_names.get(t.lender_staff_id)}
            for t, item in borrows
        ],
        "returns": [
            {"condition": r.condition.value, "note": r.note, "returned_at": r.returned_at,
             "ticket_code": ticket_codes.get(r.ticket_id)}
            for r in returns
        ],
    }


@router.put("/units/{unit_id}", response_model=sc.UnitOut,
            dependencies=[Depends(require_perm("loan.devices.update"))])
def update_unit(unit_id: int, payload: sc.UnitUpdate, db: Session = Depends(get_db)):
    u = db.get(DeviceUnit, unit_id)
    if not u:
        raise HTTPException(404, "Không tìm thấy máy")
    data = payload.model_dump(exclude_unset=True)
    if "serial" in data:
        u.serial = (data["serial"] or "").strip() or None
    if "note" in data:
        u.note = (data["note"] or "").strip() or None
    db.commit()
    db.refresh(u)
    return _unit_out(u, _holder_names(db, [u]))


@router.post("/units/{unit_id}/clear-issue", response_model=sc.UnitOut,
             dependencies=[Depends(require_perm("loan.devices.update"))])
def clear_unit_issue(unit_id: int, db: Session = Depends(get_db)):
    """Gỡ ghi chú tình trạng sau khi đã xử lý xong."""
    u = db.get(DeviceUnit, unit_id)
    if not u:
        raise HTTPException(404, "Không tìm thấy máy")
    issue_service.clear_issue(u)
    db.commit()
    db.refresh(u)
    return _unit_out(u, _holder_names(db, [u]))


@router.delete("/units/{unit_id}",
               dependencies=[Depends(require_perm("loan.devices.delete"))])
def delete_unit(unit_id: int, db: Session = Depends(get_db)):
    u = db.get(DeviceUnit, unit_id)
    if not u:
        raise HTTPException(404, "Không tìm thấy máy")
    if u.status == UnitStatus.OUT:
        raise HTTPException(400, "Máy đang được cho mượn, không thể xoá")
    used = db.execute(
        select(func.count(LoanTicketItem.id)).where(LoanTicketItem.unit_id == unit_id)
    ).scalar_one()
    if used:
        raise HTTPException(400, "Máy này đã có lịch sử cho mượn, không được xoá")
    db.delete(u)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- Excel

TEMPLATE_COLUMNS = ["model_code", "model_name", "brand", "quantity", "info", "note"]

# Chặn lỗi gõ nhầm kiểu 2000 thành 20000: một dòng sinh tối đa từng này máy.
# Kho thật có những mặt hàng đếm theo sợi (dây tín hiệu 1000 sợi) nên trần phải
# đủ rộng cho chúng, vẫn chặn được số lượng vô lý.
MAX_UNITS_PER_ROW = 2000


@router.get("/import-template",
            dependencies=[Depends(require_perm("loan.devices.create"))])
def import_template():
    df = pd.DataFrame([{
        "model_code": "LAP",
        "model_name": "Laptop Dell Latitude 7420",
        "brand": "Dell",
        "quantity": 20,
        "info": "OS: Windows 11 Pro\nCPU: i7-1185G7\nRAM: 16GB\nSSD: 512GB",
        "note": "Cấp cho nhân sự đi công tác",
    }])
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="device_models")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=device_models_template.xlsx"},
    )


@router.post("/import-excel",
             dependencies=[Depends(require_perm("loan.devices.create"))])
async def import_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Nhập danh mục từ Excel: mỗi dòng là một LOẠI, hệ thống tự sinh đủ số máy.
    Loại đã tồn tại (trùng model_code) thì chỉ cập nhật thông tin, không sinh thêm máy.
    """
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Chỉ hỗ trợ file .xlsx")
    try:
        df = pd.read_excel(BytesIO(await file.read()))
    except Exception as exc:
        raise HTTPException(400, f"Không đọc được file: {exc}")

    missing = [c for c in TEMPLATE_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Thiếu cột: {', '.join(missing)}")

    created_models = updated_models = created_units = 0
    errors: list[dict] = []

    for idx, row in df.iterrows():
        excel_row = int(idx) + 2

        def cell(key):
            """Ô rỗng trong Excel về đây là NaN. str(NaN) ra chuỗi 'nan' —
            phải chặn trước, nếu không một ô mã loại bỏ trống sẽ lặng lẽ
            tạo ra loại thiết bị tên 'NAN'."""
            value = row.get(key)
            if value is None or (not isinstance(value, str) and pd.isna(value)):
                return None
            return str(value).strip() or None

        # Excel hay đính kèm vài dòng trống ở cuối — bỏ qua, không tính là lỗi
        if all(cell(c) is None for c in TEMPLATE_COLUMNS):
            continue

        try:
            raw_code = cell("model_code")
            if not raw_code:
                raise ValueError("Thiếu mã loại ở cột model_code")
            code = unit_service.validate_code(raw_code)

            name = cell("model_name")
            if not name:
                raise ValueError("Thiếu tên loại ở cột model_name")

            qty_cell = row.get("quantity")
            if qty_cell is None or (not isinstance(qty_cell, str) and pd.isna(qty_cell)):
                qty = 0
            else:
                try:
                    qty = int(str(qty_cell).strip())
                except ValueError:
                    raise ValueError(
                        f"Số lượng '{qty_cell}' không phải số nguyên") from None
            if qty < 0:
                raise ValueError("Số lượng không được âm")
            if qty > MAX_UNITS_PER_ROW:
                raise ValueError(
                    f"Số lượng {qty} vượt mức cho phép {MAX_UNITS_PER_ROW} máy mỗi dòng")

            # Mỗi dòng nằm trong một điểm lưu riêng: dòng hỏng ở giữa chừng
            # (ví dụ trùng mã máy) chỉ tự huỷ phần của nó, các dòng trước vẫn giữ.
            made = added = 0
            with db.begin_nested():
                m = db.execute(
                    select(DeviceModel).where(DeviceModel.code == code)
                ).scalar_one_or_none()
                if m:
                    m.name, m.brand = name, cell("brand")
                    m.info, m.note = cell("info"), cell("note")
                    made = -1                      # đánh dấu: cập nhật
                else:
                    m = DeviceModel(code=code, name=name, brand=cell("brand"),
                                    info=cell("info"), note=cell("note"))
                    db.add(m)
                    db.flush()
                    made = 1                       # đánh dấu: tạo mới
                    if qty:
                        unit_service.create_units(db, m, qty)
                        added = qty

            if made == 1:
                created_models += 1
                created_units += added
            elif made == -1:
                updated_models += 1
        except Exception as exc:
            errors.append({"row": excel_row, "error": str(exc)})

    if created_models or updated_models:
        db.commit()
    else:
        db.rollback()

    return {"created_models": created_models, "updated_models": updated_models,
            "created_units": created_units, "failed": len(errors), "errors": errors}


@router.get("/export",
            dependencies=[Depends(require_perm("loan.devices.view"))])
def export_units(db: Session = Depends(get_db)):
    """Xuất toàn bộ máy ra Excel, kèm người đang giữ và ghi chú tình trạng."""
    units = list(db.execute(
        select(DeviceUnit).options(selectinload(DeviceUnit.model)).order_by(DeviceUnit.code)
    ).scalars().all())
    names = _holder_names(db, units)
    label = {UnitStatus.AVAIL: "Sẵn sàng", UnitStatus.OUT: "Đang mượn",
             UnitStatus.MAINT: "Bảo trì", UnitStatus.BROKEN: "Hỏng"}

    df = pd.DataFrame([{
        "Mã máy": u.code,
        "Loại thiết bị": u.model.name,
        "Mã loại": u.model.code,
        "Hãng": u.model.brand,
        "Trạng thái": label[u.status],
        "Người đang giữ": names.get(u.holder_staff_id) if u.holder_staff_id else "",
        "Tình trạng ghi nhận": u.issue_text or "",
        "Cập nhật tình trạng": u.issue_at.strftime("%d/%m/%Y %H:%M") if u.issue_at else "",
        "Serial": u.serial or "",
        "Ghi chú": u.note or "",
    } for u in units])

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="device_units")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=device_units.xlsx"},
    )
