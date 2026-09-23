"""
API kho hàng hoá kinh doanh — nhập về để BÁN.

Tách hoàn toàn khỏi thiết bị cho mượn: không dùng chung bảng, không dùng chung
mã, không ảnh hưởng tới số máy sẵn sàng. Mọi phiếu ghi lại tài khoản người lập.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import schemas_v2 as sc
from ..db import get_db
from ..models import User
from ..models_v2 import Photo, PhotoOwner, StockExport, StockImport, StockLocation
from ..security import require_perm
from ..services.photo_service import attach_photos, photo_payload_many, signed_url

router = APIRouter(prefix="/api/v2/stock", tags=["stock"])
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PURPOSES = ["Bán", "Bảo hành", "Cấp nội bộ", "Trả nhà cung cấp"]


def _users(db: Session, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    return {u.id: u for u in db.execute(select(User).where(User.id.in_(ids))).scalars().all()}


def _stock_levels(db: Session) -> list[sc.StockLevelOut]:
    """
    Một dòng cho mỗi mặt hàng đang lưu kho, gom theo cặp (tên sản phẩm, model).

    Tồn kho = tổng nhập − tổng xuất. Ngày nhập lấy lần nhập gần nhất. Chỗ để
    và ảnh chỗ để lấy từ bảng `stock_locations`, mặt hàng chưa khai thì để trống.
    Ba truy vấn gom nhóm chứ không phải một truy vấn cho mỗi mặt hàng.
    """
    imports = db.execute(
        select(StockImport.product_name, StockImport.model_code,
               func.sum(StockImport.qty), func.max(StockImport.imported_at))
        .group_by(StockImport.product_name, StockImport.model_code)
    ).all()
    exports = dict(
        ((name, code), int(total or 0))
        for name, code, total in db.execute(
            select(StockExport.product_name, StockExport.model_code, func.sum(StockExport.qty))
            .group_by(StockExport.product_name, StockExport.model_code)
        ).all()
    )
    places = {
        (r.product_name, r.model_code): r
        for r in db.execute(select(StockLocation)).scalars().all()
    }
    out = []
    for name, code, total, last_in in imports:
        imported = int(total or 0)
        exported = exports.get((name, code), 0)
        place = places.get((name, code))
        out.append(sc.StockLevelOut(
            product_name=name, model_code=code,
            imported=imported, exported=exported, on_hand=imported - exported,
            last_in=last_in,
            location=place.location if place else None,
            image_url=signed_url(place.image_key) if place and place.image_key else None,
        ))
    return sorted(out, key=lambda r: r.product_name.lower())


def _on_hand(db: Session, product_name: str, model_code: str) -> int:
    imported = db.execute(
        select(func.coalesce(func.sum(StockImport.qty), 0))
        .where(StockImport.product_name == product_name, StockImport.model_code == model_code)
    ).scalar_one()
    exported = db.execute(
        select(func.coalesce(func.sum(StockExport.qty), 0))
        .where(StockExport.product_name == product_name, StockExport.model_code == model_code)
    ).scalar_one()
    return int(imported or 0) - int(exported or 0)


# ----------------------------------------------------------------- tồn kho

@router.get("/levels", response_model=list[sc.StockLevelOut],
            dependencies=[Depends(require_perm("import_export.view"))])
def stock_levels(db: Session = Depends(get_db)):
    return _stock_levels(db)


# Dưới ngưỡng này thì coi là sắp hết, cần nhập thêm
LOW_STOCK = 3


@router.get("/summary", dependencies=[Depends(require_perm("import_export.view"))])
def stock_summary(db: Session = Depends(get_db)):
    imported = db.execute(select(func.coalesce(func.sum(StockImport.qty), 0))).scalar_one()
    exported = db.execute(select(func.coalesce(func.sum(StockExport.qty), 0))).scalar_one()
    levels = _stock_levels(db)
    return {
        "imported": int(imported or 0),
        "exported": int(exported or 0),
        "on_hand": int(imported or 0) - int(exported or 0),
        "products": len(levels),
        "out_of_stock": sum(1 for r in levels if r.on_hand <= 0),
        "low_stock": sum(1 for r in levels if 0 < r.on_hand <= LOW_STOCK),
        "low_threshold": LOW_STOCK,
        "purposes": PURPOSES,
    }


@router.put("/location", dependencies=[Depends(require_perm("import_export.update"))])
def set_location(payload: sc.LocationUpdate, request: Request, db: Session = Depends(get_db)):
    """
    Khai chỗ để của một mặt hàng trong kho, kèm một tấm ảnh chụp chỗ đó.

    Mỗi mặt hàng một dòng: gọi lại lần nữa là sửa chứ không thêm dòng mới. Để
    trống ô chỗ để và không gửi ảnh mới thì coi như xoá khai báo cũ.
    """
    name = payload.product_name.strip()
    code = payload.model_code.strip().upper()
    if not _known_product(db, name, code):
        raise HTTPException(404, "Không có mặt hàng này trong kho")

    row = db.execute(
        select(StockLocation).where(StockLocation.product_name == name,
                                    StockLocation.model_code == code)
    ).scalar_one_or_none()
    if row is None:
        row = StockLocation(product_name=name, model_code=code)
        db.add(row)

    row.location = (payload.location or "").strip() or None
    row.note = (payload.note or "").strip() or None
    # Không gửi ảnh mới thì giữ nguyên ảnh cũ; gửi chuỗi rỗng mới là xoá ảnh.
    if payload.image_key is not None:
        row.image_key = payload.image_key.strip() or None
    row.updated_by_user_id = getattr(request.state, "user_id", None)
    row.updated_at = datetime.utcnow()
    db.commit()

    return {"product_name": name, "model_code": code, "location": row.location,
            "note": row.note,
            "image_url": signed_url(row.image_key) if row.image_key else None}


def _known_product(db: Session, name: str, code: str) -> bool:
    return db.execute(
        select(StockImport.id)
        .where(StockImport.product_name == name, StockImport.model_code == code)
        .limit(1)
    ).first() is not None


@router.get("/product", dependencies=[Depends(require_perm("import_export.view"))])
def product_history(name: str = Query(..., max_length=255),
                    code: str = Query(..., max_length=120),
                    db: Session = Depends(get_db)):
    """
    Lịch sử ra vào của MỘT mặt hàng: mọi phiếu nhập, mọi phiếu xuất, và số tồn.

    Đây là phần tab Nhập / Xuất còn thiếu — trước chỉ lập được phiếu, không tra
    được một mặt hàng đã vào ra những lần nào, ai lập, đi đâu.
    """
    imports = db.execute(
        select(StockImport)
        .where(StockImport.product_name == name, StockImport.model_code == code)
        .order_by(StockImport.imported_at.desc(), StockImport.id.desc())
    ).scalars().all()
    exports = db.execute(
        select(StockExport)
        .where(StockExport.product_name == name, StockExport.model_code == code)
        .order_by(StockExport.exported_at.desc(), StockExport.id.desc())
    ).scalars().all()
    if not imports and not exports:
        raise HTTPException(404, "Không có mặt hàng này trong kho")

    users = _users(db, {r.created_by_user_id for r in imports} |
                       {r.created_by_user_id for r in exports})

    def who(uid):
        u = users.get(uid)
        return u.full_name or u.username if u else None

    total_in = sum(int(r.qty or 0) for r in imports)
    total_out = sum(int(r.qty or 0) for r in exports)

    # Một dòng thời gian duy nhất, mới nhất lên đầu
    moves = [
        {"kind": "IN", "id": r.id, "qty": int(r.qty or 0), "at": r.imported_at,
         "who": who(r.created_by_user_id), "note": r.note,
         "detail": r.condition, "brand": r.brand}
        for r in imports
    ] + [
        {"kind": "OUT", "id": r.id, "qty": int(r.qty or 0), "at": r.exported_at,
         "who": who(r.created_by_user_id), "note": r.note,
         "detail": r.purpose, "to": r.destination}
        for r in exports
    ]
    moves.sort(key=lambda m: (m["at"], m["id"]), reverse=True)

    place = db.execute(
        select(StockLocation).where(StockLocation.product_name == name,
                                    StockLocation.model_code == code)
    ).scalar_one_or_none()

    return {
        "location": place.location if place else None,
        "location_note": place.note if place else None,
        "image_url": signed_url(place.image_key) if place and place.image_key else None,
        "product_name": name, "model_code": code,
        "brand": next((r.brand for r in imports if r.brand), None),
        "imported": total_in, "exported": total_out, "on_hand": total_in - total_out,
        "first_in": imports[-1].imported_at if imports else None,
        "last_move": moves[0]["at"] if moves else None,
        "moves": moves,
    }


# ----------------------------------------------------------------- phiếu nhập

@router.get("/imports", response_model=list[sc.StockRecordOut],
            dependencies=[Depends(require_perm("import_export.view"))])
def list_imports(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(StockImport).order_by(StockImport.imported_at.desc(), StockImport.id.desc())
    if q:
        kw = f"%{q.strip()}%"
        stmt = stmt.where(or_(StockImport.product_name.ilike(kw),
                              StockImport.model_code.ilike(kw),
                              StockImport.brand.ilike(kw)))
    rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
    users = _users(db, {r.created_by_user_id for r in rows})
    photos = photo_payload_many(db, PhotoOwner.STOCK_IMPORT, [r.id for r in rows])
    return [
        sc.StockRecordOut(
            id=r.id, product_name=r.product_name, model_code=r.model_code, qty=r.qty,
            brand=r.brand, condition=r.condition, note=r.note, at=r.imported_at,
            created_by_user_id=r.created_by_user_id,
            created_by_username=users[r.created_by_user_id].username if r.created_by_user_id in users else None,
            created_by_name=users[r.created_by_user_id].full_name if r.created_by_user_id in users else None,
            photos=photos.get(r.id, []),
        ) for r in rows
    ]


@router.post("/imports", response_model=sc.StockRecordOut, status_code=201,
             dependencies=[Depends(require_perm("import_export.create"))])
def create_import(payload: sc.ImportCreate, request: Request, db: Session = Depends(get_db)):
    """Lập phiếu nhập thủ công. Người lập lấy từ tài khoản đang đăng nhập."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(401, "Chưa đăng nhập")

    row = StockImport(
        product_name=payload.product_name.strip(),
        brand=(payload.brand or "").strip() or None,
        model_code=payload.model_code.strip().upper(),
        qty=payload.qty,
        condition=(payload.condition or "").strip() or None,
        imported_at=payload.imported_at or datetime.utcnow(),
        note=(payload.note or "").strip() or None,
        created_by_user_id=uid,
    )
    db.add(row)
    db.flush()
    attach_photos(db, PhotoOwner.STOCK_IMPORT, row.id, payload.photo_keys, uid)
    db.commit()
    db.refresh(row)

    u = db.get(User, uid)
    return sc.StockRecordOut(
        id=row.id, product_name=row.product_name, model_code=row.model_code, qty=row.qty,
        brand=row.brand, condition=row.condition, note=row.note, at=row.imported_at,
        created_by_user_id=uid, created_by_username=u.username if u else None,
        created_by_name=u.full_name if u else None,
        photos=photo_payload_many(db, PhotoOwner.STOCK_IMPORT, [row.id]).get(row.id, []),
    )


# ----------------------------------------------------------------- phiếu xuất

@router.get("/exports", response_model=list[sc.StockRecordOut],
            dependencies=[Depends(require_perm("import_export.view"))])
def list_exports(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(StockExport).order_by(StockExport.exported_at.desc(), StockExport.id.desc())
    if q:
        kw = f"%{q.strip()}%"
        stmt = stmt.where(or_(StockExport.product_name.ilike(kw),
                              StockExport.model_code.ilike(kw),
                              StockExport.destination.ilike(kw)))
    rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
    users = _users(db, {r.created_by_user_id for r in rows})
    photos = photo_payload_many(db, PhotoOwner.STOCK_EXPORT, [r.id for r in rows])
    return [
        sc.StockRecordOut(
            id=r.id, product_name=r.product_name, model_code=r.model_code, qty=r.qty,
            purpose=r.purpose, destination=r.destination, note=r.note, at=r.exported_at,
            created_by_user_id=r.created_by_user_id,
            created_by_username=users[r.created_by_user_id].username if r.created_by_user_id in users else None,
            created_by_name=users[r.created_by_user_id].full_name if r.created_by_user_id in users else None,
            photos=photos.get(r.id, []),
        ) for r in rows
    ]


@router.post("/exports", response_model=sc.StockRecordOut, status_code=201,
             dependencies=[Depends(require_perm("import_export.create"))])
def create_export(payload: sc.ExportCreate, request: Request, db: Session = Depends(get_db)):
    """Xuất hàng khỏi kho, trừ thẳng vào tồn. Không cho xuất quá số đang có."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(401, "Chưa đăng nhập")

    name = payload.product_name.strip()
    code = payload.model_code.strip().upper()
    available = _on_hand(db, name, code)
    if available <= 0:
        raise HTTPException(400, f"{name} ({code}) đã hết hàng trong kho")
    if payload.qty > available:
        raise HTTPException(400, f"Không đủ hàng. Tồn kho hiện tại: {available}")

    row = StockExport(
        product_name=name, model_code=code, qty=payload.qty,
        purpose=(payload.purpose or "Bán").strip(),
        destination=(payload.destination or "").strip() or None,
        exported_at=payload.exported_at or datetime.utcnow(),
        note=(payload.note or "").strip() or None,
        created_by_user_id=uid,
    )
    db.add(row)
    db.flush()
    attach_photos(db, PhotoOwner.STOCK_EXPORT, row.id, payload.photo_keys, uid)
    db.commit()
    db.refresh(row)

    u = db.get(User, uid)
    return sc.StockRecordOut(
        id=row.id, product_name=row.product_name, model_code=row.model_code, qty=row.qty,
        purpose=row.purpose, destination=row.destination, note=row.note, at=row.exported_at,
        created_by_user_id=uid, created_by_username=u.username if u else None,
        created_by_name=u.full_name if u else None,
        photos=photo_payload_many(db, PhotoOwner.STOCK_EXPORT, [row.id]).get(row.id, []),
    )


# ----------------------------------------------------------------- Excel

@router.get("/export-excel",
            dependencies=[Depends(require_perm("import_export.view"))])
def export_excel(db: Session = Depends(get_db)):
    """Ba sheet: tồn kho, phiếu nhập, phiếu xuất — kèm tài khoản người lập."""
    users = {u.id: u for u in db.execute(select(User)).scalars().all()}

    def who(uid):
        u = users.get(uid)
        return f"{u.full_name or u.username} ({u.username})" if u else ""

    levels = pd.DataFrame([{
        "Sản phẩm": r.product_name, "Model": r.model_code,
        "Tổng nhập": r.imported, "Đã xuất": r.exported, "Tồn kho": r.on_hand,
        "Ngày nhập": r.last_in.strftime("%d/%m/%Y") if r.last_in else "",
        "Vị trí kho": r.location or "",
    } for r in _stock_levels(db)])

    imports = pd.DataFrame([{
        "Sản phẩm": r.product_name, "Hãng": r.brand or "", "Model": r.model_code,
        "Số lượng": r.qty, "Tình trạng": r.condition or "",
        "Ngày nhập": r.imported_at.strftime("%d/%m/%Y"),
        "Người nhập": who(r.created_by_user_id), "Ghi chú": r.note or "",
    } for r in db.execute(select(StockImport).order_by(StockImport.imported_at)).scalars().all()])

    exports = pd.DataFrame([{
        "Sản phẩm": r.product_name, "Model": r.model_code, "Số lượng": r.qty,
        "Mục đích": r.purpose, "Nơi nhận": r.destination or "",
        "Ngày xuất": r.exported_at.strftime("%d/%m/%Y"),
        "Người xuất": who(r.created_by_user_id), "Ghi chú": r.note or "",
    } for r in db.execute(select(StockExport).order_by(StockExport.exported_at)).scalars().all()])

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        (levels if not levels.empty else pd.DataFrame([{"Sản phẩm": ""}])).to_excel(
            w, index=False, sheet_name="Ton kho")
        (imports if not imports.empty else pd.DataFrame([{"Sản phẩm": ""}])).to_excel(
            w, index=False, sheet_name="Phieu nhap")
        (exports if not exports.empty else pd.DataFrame([{"Sản phẩm": ""}])).to_excel(
            w, index=False, sheet_name="Phieu xuat")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=kho_nhap_xuat.xlsx"},
    )


@router.delete("/photos/{photo_id}",
               dependencies=[Depends(require_perm("import_export.update"))])
def delete_stock_photo(photo_id: int, db: Session = Depends(get_db)):
    p = db.get(Photo, photo_id)
    if not p or p.owner_type not in {PhotoOwner.STOCK_IMPORT, PhotoOwner.STOCK_EXPORT}:
        raise HTTPException(404, "Không tìm thấy ảnh")
    db.delete(p)
    db.commit()
    return {"ok": True}
