"""
Điểm khởi động ứng dụng.

Bản cũ dồn 957 dòng vào một file: middleware, auth, trang, users, staff,
departments, nhập xuất, presign S3, email. Ở đây main.py chỉ còn phần khung —
tạo app, middleware xác thực, trang HTML, đăng nhập — mọi nghiệp vụ nằm trong
app/routers/.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .auth import (
    COOKIE_MAX_AGE_SECONDS, COOKIE_NAME, hash_password, make_session_token,
    read_session_user_id, verify_password,
)
from .config import settings
from .db import SessionLocal, get_db
from .init_db import init_db
from .models import Department, User
from .security import PERMISSIONS_ALL, parse_permissions
from .services import overdue_service
from .services.weekly_report_service import (
    send_monthly_loan_history_report_now, send_weekly_outstanding_report_now,
    start_weekly_report_scheduler, stop_weekly_report_scheduler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="IT-QLTB", docs_url=None, redoc_url=None, openapi_url="/openapi.json")

# ---------------------------------------------------------------- CORS
_origins = [o.strip() for o in (settings.allow_origins or "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    # Cookie chỉ được gửi kèm khi origin đã được liệt kê tường minh
    allow_credentials=bool(_origins) and _origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

PUBLIC_PATHS = {"/login", "/logout", "/health", "/favicon.ico",
                "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"}


# ---------------------------------------------------------------- vòng đời

@app.on_event("startup")
async def _startup() -> None:
    init_db()
    _bootstrap_lender_department()
    _bootstrap_admin()
    start_weekly_report_scheduler(app)
    overdue_service.start(app)
    logger.info("Ứng dụng sẵn sàng — ngưỡng quá hạn %s ngày", settings.loan_overdue_days)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await stop_weekly_report_scheduler(app)
    await overdue_service.stop(app)


def _bootstrap_lender_department() -> None:
    """Tạo sẵn phòng cho mượn (mặc định IT) — phiếu mượn nào cũng cần nó.

    So sánh không phân biệt hoa thường để một phòng đã đặt tên "it" hay "It"
    không bị tạo trùng thành phòng thứ hai.
    """
    name = (settings.lender_department or "").strip()
    if not name:
        return
    with SessionLocal() as db:
        exists = db.execute(
            select(Department).where(func.lower(Department.name) == name.lower())
        ).scalars().first()
        if exists:
            return
        db.add(Department(name=name))
        db.commit()
        logger.info("Đã tạo sẵn phòng ban %s để đứng tên cho mượn", name)


def _bootstrap_admin() -> None:
    """Tạo tài khoản quản trị đầu tiên nếu chưa có, và bảo đảm ADMIN đủ 28 quyền."""
    with SessionLocal() as db:
        if settings.bootstrap_admin_user and settings.bootstrap_admin_pass:
            exists = db.execute(
                select(User).where(User.username == settings.bootstrap_admin_user)
            ).scalar_one_or_none()
            if not exists:
                db.add(User(
                    username=settings.bootstrap_admin_user,
                    password_hash=hash_password(settings.bootstrap_admin_pass),
                    full_name="Quản trị viên",
                    role="ADMIN",
                    is_active=True,
                    permissions=json.dumps(sorted(PERMISSIONS_ALL)),
                ))
                logger.warning(
                    "Đã tạo tài khoản quản trị %s từ biến môi trường — hãy đổi mật khẩu ngay",
                    settings.bootstrap_admin_user)

        for u in db.execute(select(User).where(User.role == "ADMIN")).scalars().all():
            if not u.permissions:
                u.permissions = json.dumps(sorted(PERMISSIONS_ALL))
        db.commit()


# ---------------------------------------------------------------- xác thực

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Chỉ lo XÁC THỰC: biết người gọi là ai, gắn vào request.state.
    Việc PHÂN QUYỀN do từng endpoint tự khai báo qua Depends(require_perm(...)).
    """
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    token = request.cookies.get(COOKIE_NAME)
    uid = read_session_user_id(settings.app_secret_key, token) if token else None
    if uid is None:
        if path.startswith("/api"):
            return JSONResponse({"detail": "Chưa đăng nhập"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)

    with SessionLocal() as db:
        user = db.get(User, uid)
        if not user or not user.is_active:
            if path.startswith("/api"):
                return JSONResponse({"detail": "Tài khoản không hợp lệ"}, status_code=401)
            resp = RedirectResponse(url="/login", status_code=302)
            resp.delete_cookie(COOKIE_NAME)
            return resp

        request.state.user_id = user.id
        request.state.user_role = user.role
        request.state.user_username = user.username
        request.state.user_full_name = user.full_name
        request.state.user_permissions = sorted(parse_permissions(user.permissions))

    return await call_next(request)


# --- Chặn dò mật khẩu -------------------------------------------------------
# Bản cũ không giới hạn số lần đăng nhập sai. Bộ đếm trong bộ nhớ đủ cho một
# tiến trình; chạy nhiều worker thì nên chuyển sang Redis.
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _login_blocked(key: str) -> int:
    """Trả về số giây còn bị khoá, 0 nếu chưa bị khoá."""
    now = time.time()
    window = settings.login_lockout_seconds
    hits = [t for t in _login_attempts[key] if now - t < window]
    _login_attempts[key] = hits
    if len(hits) < settings.login_max_attempts:
        return 0
    return int(window - (now - hits[0])) + 1


def _record_failure(key: str) -> None:
    _login_attempts[key].append(time.time())


def _clear_failures(key: str) -> None:
    _login_attempts.pop(key, None)


# ---------------------------------------------------------------- trang

@app.get("/health")
def health(db: Session = Depends(get_db)):
    """
    Điểm kiểm tra sống/chết, không cần đăng nhập.

    Có kèm trạng thái cơ sở dữ liệu nhưng KHÔNG kèm thông báo lỗi chi tiết —
    chuỗi lỗi của SQLAlchemy thường lộ cả host và tên tài khoản database.
    Muốn xem lỗi cụ thể thì gọi /api/health/db sau khi đã đăng nhập.
    """
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": db_ok, "db": db_ok, "time": datetime.utcnow().isoformat()}


@app.get("/api/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/favicon.ico")
def favicon():
    return FileResponse("static/images/favicon.ico")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None):
    """
    Đang đăng nhập rồi mà vào /login thì đưa thẳng về trang chính.

    Trình duyệt lưu /login trong lịch sử; không có chỗ này thì bấm nút Quay lại
    ở bất kỳ tab nào cũng rơi ra màn hình đăng nhập dù phiên vẫn còn.
    """
    if not error:
        token = request.cookies.get(COOKIE_NAME)
        uid = read_session_user_id(settings.app_secret_key, token) if token else None
        if uid is not None:
            with SessionLocal() as db:
                user = db.get(User, uid)
            if user and user.is_active:
                return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...),
                 remember: str | None = Form(None)):
    ip = request.client.host if request.client else "?"
    key = f"{ip}|{username.strip().lower()}"

    if (wait := _login_blocked(key)):
        return templates.TemplateResponse(
            request, "login.html",
            {"error": f"Sai quá nhiều lần. Thử lại sau {wait} giây."},
            status_code=429,
        )

    with SessionLocal() as db:
        user = db.execute(
            select(User).where(User.username == username.strip())
        ).scalar_one_or_none()

        # Thông báo giống nhau cho mọi trường hợp sai, tránh lộ tài khoản nào có thật
        if not user or not verify_password(password, user.password_hash):
            _record_failure(key)
            return templates.TemplateResponse(
                request, "login.html",
                {"error": "Sai tài khoản hoặc mật khẩu"},
                status_code=401,
            )
        if not user.is_active:
            _record_failure(key)
            return templates.TemplateResponse(
                request, "login.html",
                {"error": "Tài khoản đã bị vô hiệu hoá. Liên hệ quản trị viên."},
                status_code=403,
            )

        _clear_failures(key)
        token = make_session_token(settings.app_secret_key, user.id)

    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True,
        samesite="strict",           # ứng dụng nội bộ, không cần điều hướng chéo site
        secure=settings.cookie_secure,  # bật COOKIE_SECURE=true khi chạy sau HTTPS
        # Bỏ tick "Duy trì đăng nhập" thì cookie sống theo cửa sổ trình duyệt,
        # đóng trình duyệt là mất — hợp với máy dùng chung ở quầy.
        # Chữ ký phiên vẫn hết hạn sau 12 giờ dù chọn kiểu nào.
        max_age=COOKIE_MAX_AGE_SECONDS if remember else None,
        path="/",
    )
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@app.get("/", response_class=HTMLResponse)
def app_shell(request: Request):
    """Toàn bộ giao diện là một trang; điều hướng do JavaScript lo."""
    return templates.TemplateResponse(request, "app.html", {
        "username": getattr(request.state, "user_username", ""),
        "full_name": getattr(request.state, "user_full_name", "") or "",
        "role": getattr(request.state, "user_role", ""),
        "permissions": getattr(request.state, "user_permissions", []),
        "overdue_days": settings.loan_overdue_days,
        "lender_department": settings.lender_department,
    })


@app.get("/api/v2/me")
def me(request: Request):
    return {
        "id": getattr(request.state, "user_id", None),
        "username": getattr(request.state, "user_username", ""),
        "full_name": getattr(request.state, "user_full_name", ""),
        "role": getattr(request.state, "user_role", ""),
        "permissions": getattr(request.state, "user_permissions", []),
        "overdue_days": settings.loan_overdue_days,
    }


# ---------------------------------------------------------------- router

from .routers import (  # noqa: E402
    devices_v2, maint_v2, org_v2, reports_v2, stock_v2, tickets_v2, uploads_v2, users_v2,
)

app.include_router(devices_v2.router)
app.include_router(tickets_v2.router)
app.include_router(maint_v2.router)
app.include_router(stock_v2.router)
app.include_router(org_v2.router)
app.include_router(users_v2.router)
app.include_router(uploads_v2.router)
app.include_router(reports_v2.router)
