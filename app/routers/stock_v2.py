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
from ..models_v2 import Photo, PhotoOwner, StockExport, StockImport
from ..security import require_perm
from ..services.photo_service import attach_photos, photo_payload_many

router = APIRouter(prefix="/api/v2/stock", tags=["stock"])
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PURPOSES = ["Bán", "Bảo hành", "Cấp nội bộ", "Trả nhà cung cấp"]


def _users(db: Session, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    return {u.id: u for u in db.execute(select(User).where(User.id.in_(ids))).scalars().all()}


def _stock_levels(db: Session) -> list[sc.StockLevelOut]:
    """Tồn kho = tổng nhập − tổng xuất, tính theo cặp (tên sản phẩm, model)."""
    imports = db.execute(
        select(StockImport.product_name, StockImport.model_code, func.sum(StockImport.qty))
        .group_by(StockImport.product_name, StockImport.model_code)
    ).all()
    exports = dict(
        ((name, code), int(total or 0))
        for name, code, total in db.execute(
            select(StockExport.product_name, StockExport.model_code, func.sum(StockExport.qty))
            .group_by(StockExport.product_name, StockExport.model_code)
        ).all()
    )
    out = []
    for name, code, total in imports:
        imported = int(total or 0)
        exported = exports.get((name, code), 0)
        out.append(sc.StockLevelOut(
            product_name=name, model_code=code,
            imported=imported, exported=exported, on_hand=imported - exported,
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
        "purposes": PURPOSES,
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
