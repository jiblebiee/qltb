"""
Phân quyền đặt ngay tại từng endpoint.

Bản cũ so khớp tiền tố URL trong middleware (main.py:204-265). Cách đó mặc định
từ chối nên an toàn, nhưng logic quyền nằm xa endpoint: thêm route mới mà quên
khai báo là user thường nhận 403 không rõ lý do. Ở đây mỗi route tự khai báo
quyền của mình bằng Depends(require_perm(...)).
"""
from __future__ import annotations

import json

from fastapi import Depends, HTTPException, Request

# 7 nhóm × 4 hành động = 28 quyền
PERMISSION_GROUPS: list[tuple[str, str]] = [
    ("loan.devices", "Thiết bị cho mượn"),
    ("loan.staff", "Nhân sự"),
    ("loan.departments", "Phòng ban"),
    ("loan.loans", "Mượn - Trả"),
    ("loan.maintenance", "Bảo trì"),
    ("import_export", "Nhập / Xuất kho"),
    ("users", "Tài khoản"),
]
PERMISSION_ACTIONS: list[tuple[str, str]] = [
    ("view", "Xem"), ("create", "Thêm"), ("update", "Sửa"), ("delete", "Xoá"),
]
PERMISSIONS_ALL: set[str] = {
    f"{g}.{a}" for g, _ in PERMISSION_GROUPS for a, _ in PERMISSION_ACTIONS
}

# Ánh xạ các quyền kiểu cũ sang bộ quyền mới, để tài khoản cũ không mất quyền
_LEGACY_MAP: dict[str, list[str]] = {
    "devices.read": ["loan.devices.view"],
    "devices.manage": [f"loan.devices.{a}" for a, _ in PERMISSION_ACTIONS],
    "loans.read": ["loan.loans.view"],
    "loans.manage": [f"loan.loans.{a}" for a, _ in PERMISSION_ACTIONS],
    "maintenance.manage": [f"loan.maintenance.{a}" for a, _ in PERMISSION_ACTIONS],
    "departments.manage": [f"loan.departments.{a}" for a, _ in PERMISSION_ACTIONS],
    "staff.manage": [f"loan.staff.{a}" for a, _ in PERMISSION_ACTIONS],
    "users.manage": [f"users.{a}" for a, _ in PERMISSION_ACTIONS],
    "import_export.manage": [f"import_export.{a}" for a, _ in PERMISSION_ACTIONS],
}


def parse_permissions(raw: str | None) -> set[str]:
    if not raw:
        return set()
    try:
        data = json.loads(raw)
    except Exception:
        return set()
    if not isinstance(data, list):
        return set()

    out: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        if item in PERMISSIONS_ALL:
            out.add(item)
        out.update(_LEGACY_MAP.get(item, []))
    return out


def normalize_permissions(perms: list[str] | None) -> list[str]:
    return sorted({p for p in (perms or []) if p in PERMISSIONS_ALL})


# ---------------------------------------------------------------- dependencies

def current_user_id(request: Request) -> int:
    """Middleware đã xác thực và gắn user vào request.state."""
    uid = getattr(request.state, "user_id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    return int(uid)


def is_admin(request: Request) -> bool:
    return str(getattr(request.state, "user_role", "")).upper() == "ADMIN"


def user_permissions(request: Request) -> set[str]:
    return set(getattr(request.state, "user_permissions", []) or [])


def require_perm(*needed: str):
    """
    Trả về dependency chặn request nếu tài khoản thiếu quyền.
    ADMIN luôn đi qua. Chỉ cần MỘT trong các quyền liệt kê là đủ.

        @router.post("", dependencies=[Depends(require_perm("loan.devices.create"))])
    """
    unknown = [p for p in needed if p not in PERMISSIONS_ALL]
    if unknown:  # bắt lỗi gõ sai ngay lúc khởi động, không đợi tới runtime
        raise ValueError(f"Quyền không tồn tại: {unknown}")

    def _dep(request: Request) -> int:
        uid = current_user_id(request)
        if is_admin(request):
            return uid
        if user_permissions(request) & set(needed):
            return uid
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này")

    return _dep


def require_admin(request: Request) -> int:
    uid = current_user_id(request)
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên mới thực hiện được")
    return uid
