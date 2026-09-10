#!/usr/bin/env python3
"""
Tạo hoặc đặt lại tài khoản quản trị.

Dùng khi quên mật khẩu admin, hoặc cần thêm một quản trị viên nữa.

    python3 scripts/create-admin.py                     # hỏi từng bước
    python3 scripts/create-admin.py --user admin --reset  # đặt mật khẩu mới ngẫu nhiên

Chạy trong Docker:
    docker compose -f docker-compose.full.yml exec web python3 scripts/create-admin.py
"""
from __future__ import annotations

import argparse
import getpass
import json
import secrets
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import hash_password           # noqa: E402
from app.db import SessionLocal              # noqa: E402
from app.init_db import init_db              # noqa: E402
from app.models import User                  # noqa: E402
from app.security import PERMISSIONS_ALL     # noqa: E402

MIN_PASSWORD = 6


def random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> int:
    ap = argparse.ArgumentParser(description="Tạo hoặc đặt lại tài khoản quản trị")
    ap.add_argument("--user", help="Tên đăng nhập")
    ap.add_argument("--password", help="Mật khẩu (bỏ trống để tự sinh)")
    ap.add_argument("--name", help="Họ tên hiển thị")
    ap.add_argument("--reset", action="store_true",
                    help="Đặt lại mật khẩu nếu tài khoản đã tồn tại")
    args = ap.parse_args()

    init_db()

    username = (args.user or input("Tên đăng nhập: ")).strip().lower()
    if len(username) < 5:
        print("Tên đăng nhập tối thiểu 5 ký tự.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        existing = db.query(User).filter(User.username == username).one_or_none()

        if existing and not args.reset:
            print(f"Tài khoản {username} đã tồn tại.")
            print("Thêm --reset nếu muốn đặt lại mật khẩu.")
            return 1

        password = args.password
        if not password:
            if sys.stdin.isatty() and not args.reset:
                password = getpass.getpass(f"Mật khẩu (tối thiểu {MIN_PASSWORD} ký tự): ")
                if password != getpass.getpass("Nhập lại mật khẩu: "):
                    print("Hai lần nhập không khớp.", file=sys.stderr)
                    return 1
            else:
                password = random_password()
                print(f"\nMật khẩu tự sinh: {password}\n")

        if len(password) < MIN_PASSWORD:
            print(f"Mật khẩu tối thiểu {MIN_PASSWORD} ký tự.", file=sys.stderr)
            return 1

        perms = json.dumps(sorted(PERMISSIONS_ALL))
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = "ADMIN"
            existing.is_active = True
            existing.permissions = perms
            action = "Đã đặt lại mật khẩu cho"
        else:
            db.add(User(
                username=username,
                password_hash=hash_password(password),
                full_name=(args.name or "Quản trị viên").strip(),
                role="ADMIN",
                is_active=True,
                permissions=perms,
            ))
            action = "Đã tạo tài khoản quản trị"
        db.commit()

    print(f"{action} {username} — đủ {len(PERMISSIONS_ALL)} quyền.")
    print("Đăng nhập rồi đổi mật khẩu ngay ở Thêm → Đổi mật khẩu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
