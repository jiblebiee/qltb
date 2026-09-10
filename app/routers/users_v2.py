"""
API tài khoản và phân quyền.

Vá lỗ hổng số 02 trong bản rà soát: bản cũ để `update_user` không kiểm tra vai
trò của tài khoản ĐÍCH, nên bất kỳ ai có quyền `users.update` đều đổi được mật
khẩu của ADMIN rồi đăng nhập bằng đó. Ở đây mọi thao tác chạm tới một tài khoản
ADMIN đều đòi người gọi cũng phải là ADMIN.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..db import get_db
from ..models import User
from ..security import (
    PERMISSION_ACTIONS, PERMISSION_GROUPS, PERMISSIONS_ALL,
    is_admin, normalize_permissions, parse_permissions, require_perm,
)

router = APIRouter(prefix="/api/v2/users", tags=["users"])

MIN_USERNAME = 5
# Ứng dụng nội bộ trong mạng công ty. Mật khẩu ngắn chấp nhận được vì đã có
# khoá tạm sau 5 lần sai (LOGIN_MAX_ATTEMPTS / LOGIN_LOCKOUT_SECONDS).
MIN_PASSWORD = 6


class UserCreate(BaseModel):
    username: str = Field(min_length=MIN_USERNAME, max_length=50)
    password: str = Field(min_length=MIN_PASSWORD, max_length=72)
    full_name: str | None = Field(default=None, max_length=120)
    is_active: bool = True
    permissions: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=72)
    is_active: bool | None = None
    permissions: list[str] | None = None


class PasswordChange(BaseModel):
    """Đổi mật khẩu của chính mình — không cần quyền users.update."""
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD, max_length=72)


def _out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": bool(u.is_active),
        "permissions": sorted(parse_permissions(u.permissions)),
    }


def _guard_target(request: Request, target: User) -> None:
    """
    Chặn leo thang đặc quyền: chỉ ADMIN mới được chạm vào tài khoản ADMIN khác.
    Người không phải ADMIN vẫn quản lý được các tài khoản thường như trước.
    """
    if str(target.role or "").upper() == "ADMIN" and not is_admin(request):
        raise HTTPException(
            403, "Chỉ quản trị viên mới được thao tác trên tài khoản quản trị viên")


def _count_active_admins(db: Session, exclude_id: int | None = None) -> int:
    stmt = select(func.count(User.id)).where(
        func.upper(User.role) == "ADMIN", User.is_active.is_(True))
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return int(db.execute(stmt).scalar_one())


@router.get("/permission-catalog", dependencies=[Depends(require_perm("users.view"))])
def permission_catalog():
    """Danh mục 28 quyền, gom theo nhóm — dùng để dựng ma trận phân quyền."""
    return {
        "groups": [
            {"key": key, "label": label,
             "actions": [{"key": f"{key}.{a}", "action": a, "label": lbl}
                         for a, lbl in PERMISSION_ACTIONS]}
            for key, label in PERMISSION_GROUPS
        ],
        "total": len(PERMISSIONS_ALL),
        "presets": {
            "all": sorted(PERMISSIONS_ALL),
            "loan": sorted(p for p in PERMISSIONS_ALL if p.startswith("loan.")),
            "view": sorted(p for p in PERMISSIONS_ALL if p.endswith(".view")),
            "none": [],
        },
    }


@router.get("", dependencies=[Depends(require_perm("users.view"))])
def list_users(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(User).order_by(User.id).limit(limit).offset(offset)
    ).scalars().all()
    return [_out(u) for u in rows]


@router.post("", status_code=201, dependencies=[Depends(require_perm("users.create"))])
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    if db.execute(select(User.id).where(User.username == username)).first():
        raise HTTPException(400, "Tên đăng nhập đã tồn tại")

    perms = normalize_permissions(payload.permissions)
    # Người không phải ADMIN không thể cấp cho tài khoản mới nhiều quyền hơn mình
    if not is_admin(request):
        mine = set(getattr(request.state, "user_permissions", []) or [])
        excess = set(perms) - mine
        if excess:
            raise HTTPException(
                403, "Không thể cấp quyền mà chính bạn không có: " + ", ".join(sorted(excess)))

    u = User(
        username=username,
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or "").strip() or None,
        role="USER",
        is_active=bool(payload.is_active),
        permissions=json.dumps(perms) if perms else None,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return _out(u)


@router.put("/{user_id}", dependencies=[Depends(require_perm("users.update"))])
def update_user(user_id: int, payload: UserUpdate, request: Request,
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    _guard_target(request, u)

    if payload.full_name is not None:
        u.full_name = payload.full_name.strip() or None

    if payload.is_active is not None:
        if not payload.is_active and str(u.role or "").upper() == "ADMIN" \
                and _count_active_admins(db, exclude_id=u.id) == 0:
            raise HTTPException(400, "Không thể vô hiệu hoá quản trị viên cuối cùng")
        u.is_active = bool(payload.is_active)

    if payload.password:
        if len(payload.password) < MIN_PASSWORD:
            raise HTTPException(400, f"Mật khẩu tối thiểu {MIN_PASSWORD} ký tự")
        u.password_hash = hash_password(payload.password)

    if payload.permissions is not None:
        perms = normalize_permissions(payload.permissions)
        if not is_admin(request):
            mine = set(getattr(request.state, "user_permissions", []) or [])
            excess = set(perms) - mine
            if excess:
                raise HTTPException(
                    403, "Không thể cấp quyền mà chính bạn không có: " + ", ".join(sorted(excess)))
        u.permissions = json.dumps(perms) if perms else None

    db.commit()
    db.refresh(u)
    return _out(u)


@router.delete("/{user_id}", dependencies=[Depends(require_perm("users.delete"))])
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    _guard_target(request, u)

    if user_id == getattr(request.state, "user_id", None):
        raise HTTPException(400, "Không thể tự xoá tài khoản đang đăng nhập")
    if str(u.role or "").upper() == "ADMIN" and _count_active_admins(db, exclude_id=u.id) == 0:
        raise HTTPException(400, "Không thể xoá quản trị viên cuối cùng")

    db.delete(u)
    db.commit()
    return {"ok": True}


@router.post("/me/change-password")
def change_own_password(payload: PasswordChange, request: Request,
                        db: Session = Depends(get_db)):
    """
    Tự đổi mật khẩu. Có luồng này thì không ai cần quyền users.update chỉ để
    nhờ đặt lại mật khẩu — chính là quyền tạo ra lỗ hổng leo thang.
    """
    from ..auth import verify_password

    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(401, "Chưa đăng nhập")
    u = db.get(User, uid)
    if not u or not verify_password(payload.current_password, u.password_hash):
        raise HTTPException(400, "Mật khẩu hiện tại không đúng")
    if payload.new_password == payload.current_password:
        raise HTTPException(400, "Mật khẩu mới phải khác mật khẩu cũ")

    u.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}
