"""
Test các luồng nghiệp vụ quan trọng nhất.

Đây là những chỗ mà một lỗi âm thầm sẽ làm sai số liệu tồn kho hoặc mở lỗ hổng
quyền, nên đáng được phủ test trước tiên.

Chạy:  pytest -q
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Cấu hình môi trường trước khi nạp app
_DB = Path(tempfile.gettempdir()) / "qltb_pytest.db"
if _DB.exists():
    _DB.unlink()
os.environ.update({
    "DB_URL": f"sqlite:///{_DB}",
    "S3_BUCKET": "test", "S3_REGION": "ap-southeast-1",
    "APP_SECRET_KEY": "test-secret-key-please-change",
    "BOOTSTRAP_ADMIN_USER": "admin", "BOOTSTRAP_ADMIN_PASS": "Admin@123456",
    "SMTP_ENABLED": "false", "LOAN_OVERDUE_DAYS": "10",
})

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Department, Staff, StaffStatus, User  # noqa: E402
from app.models_v2 import (  # noqa: E402
    DeviceModel, DeviceUnit, MaintStatus, ReturnCondition, UnitMaintenance,
    UnitReturn, UnitStatus,
)
from app.security import PERMISSIONS_ALL, normalize_permissions, parse_permissions  # noqa: E402
from app.services import issue_service, loan_service, unit_service  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def world(db):
    """Một phòng IT, một phòng Kế toán, và 5 cuộn quang 6 đầu."""
    it = Department(name="IT")
    acc = Department(name="Kế toán")
    db.add_all([it, acc])
    db.flush()

    hau = Staff(full_name="Trương Hữu Hậu", email="hau@x.vn",
                department_id=it.id, status=StaffStatus.ACTIVE)
    linh = Staff(full_name="Đặng Thị Mỹ Linh", email="linh@x.vn",
                 department_id=acc.id, status=StaffStatus.ACTIVE)
    ha = Staff(full_name="Lê Thị Thu Hà", email="ha@x.vn",
               department_id=acc.id, status=StaffStatus.ACTIVE)
    db.add_all([hau, linh, ha])
    db.flush()

    acc.head_staff_id = linh.id  # Linh là trưởng bộ phận Kế toán

    quang = DeviceModel(code="QUANG", name="Cuộn quang 6 đầu",
                        info="Số đầu nối: 6 đầu / cuộn")
    db.add(quang)
    db.flush()
    unit_service.create_units(db, quang, 5)
    db.commit()

    return {"it": it, "acc": acc, "hau": hau, "linh": linh, "ha": ha, "model": quang}


# ------------------------------------------------------------------ sinh mã máy

def test_unit_codes_are_sequential(db, world):
    codes = [u.code for u in db.query(DeviceUnit).order_by(DeviceUnit.no).all()]
    assert codes == ["QUANG-01", "QUANG-02", "QUANG-03", "QUANG-04", "QUANG-05"]


def test_adding_units_continues_numbering(db, world):
    unit_service.create_units(db, world["model"], 3)
    db.commit()
    codes = [u.code for u in db.query(DeviceUnit).order_by(DeviceUnit.no).all()]
    assert codes[-3:] == ["QUANG-06", "QUANG-07", "QUANG-08"]


# ------------------------------------------------------------------ dò từ khoá

@pytest.mark.parametrize("note,expected", [
    ("hư sợi 1,3", True),
    ("Hư 1 trong 2 đầu nối", True),
    ("Hỏng nút nguồn", True),
    ("Vỏ máy xước nhẹ", True),
    # Không được bắt nhầm những từ chỉ CHỨA chuỗi "hư"
    ("Máy chạy như bình thường", False),
    ("Chưa kiểm tra kỹ", False),
    ("Thư viện phần mềm đầy đủ", False),
    ("Nhưng vẫn dùng tốt", False),
    ("", False),
    (None, False),
])
def test_issue_keyword_detection(note, expected):
    assert issue_service.has_issue_keyword(note) is expected


def test_normal_return_with_damage_note_flags_unit(db, world):
    """Đúng trường hợp thực tế: trả ở tình trạng bình thường nhưng ghi chú có 'hư'."""
    unit = db.query(DeviceUnit).filter_by(code="QUANG-01").one()
    ticket = loan_service.borrow(
        db, borrower_staff_id=world["ha"].id, lender_staff_id=world["hau"].id,
        unit_ids=[unit.id],
    )
    db.commit()

    loan_service.return_units(
        db, ticket=ticket,
        lines=[loan_service.ReturnLine(unit.id, "NORMAL", "hư sợi 1,3")],
        receiver_staff_id=world["hau"].id,
    )
    db.commit()
    db.refresh(unit)

    # Máy trở lại sẵn sàng NHƯNG vẫn mang cảnh báo, kèm thời điểm ghi nhận
    assert unit.status == UnitStatus.AVAIL
    assert unit.issue_text == "hư sợi 1,3"
    assert unit.issue_at is not None
    assert unit.issue_source == ticket.code


def test_clean_return_clears_previous_issue(db, world):
    unit = db.query(DeviceUnit).filter_by(code="QUANG-02").one()
    unit.issue_text, unit.issue_at = "hư sợi 2", datetime.utcnow()
    db.commit()

    ticket = loan_service.borrow(
        db, borrower_staff_id=world["ha"].id, lender_staff_id=world["hau"].id,
        unit_ids=[unit.id])
    db.commit()
    loan_service.return_units(
        db, ticket=ticket,
        lines=[loan_service.ReturnLine(unit.id, "NORMAL", "Đã thay đầu nối, chạy tốt")])
    db.commit()
    db.refresh(unit)
    assert unit.issue_text is None


# ------------------------------------------------------------------ mượn

def test_cannot_borrow_same_unit_twice(db, world):
    unit = db.query(DeviceUnit).filter_by(code="QUANG-03").one()
    loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                        lender_staff_id=world["hau"].id, unit_ids=[unit.id])
    db.commit()

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        loan_service.borrow(db, borrower_staff_id=world["linh"].id,
                            lender_staff_id=world["hau"].id, unit_ids=[unit.id])
    assert exc.value.status_code == 409
    assert "QUANG-03" in exc.value.detail


def test_borrow_sets_holder(db, world):
    units = db.query(DeviceUnit).filter(DeviceUnit.code.in_(["QUANG-04", "QUANG-05"])).all()
    loan_service.borrow(db, borrower_staff_id=world["linh"].id,
                        lender_staff_id=world["hau"].id,
                        unit_ids=[u.id for u in units])
    db.commit()
    for u in units:
        db.refresh(u)
        assert u.status == UnitStatus.OUT
        assert u.holder_staff_id == world["linh"].id


# ------------------------------------------------------------------ trả

def test_partial_return_keeps_ticket_open(db, world):
    units = db.query(DeviceUnit).order_by(DeviceUnit.no).limit(3).all()
    ticket = loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                                 lender_staff_id=world["hau"].id,
                                 unit_ids=[u.id for u in units])
    db.commit()

    # Trả đúng MỘT máy — luồng "trả nhanh" từ màn hình chi tiết máy
    loan_service.return_units(
        db, ticket=ticket,
        lines=[loan_service.ReturnLine(units[0].id, "NORMAL", None)])
    db.commit()

    assert ticket.returned_at is None
    assert len(loan_service.ticket_open_items(ticket)) == 2

    loan_service.return_units(
        db, ticket=ticket,
        lines=[loan_service.ReturnLine(u.id, "NORMAL", None) for u in units[1:]])
    db.commit()
    assert ticket.returned_at is not None
    assert loan_service.ticket_state(ticket) == "done"


def test_return_maint_creates_schedule_with_the_unit_note(db, world):
    """Ghi chú riêng của máy phải trở thành nội dung lịch bảo trì."""
    unit = db.query(DeviceUnit).filter_by(code="QUANG-01").one()
    ticket = loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                                 lender_staff_id=world["hau"].id, unit_ids=[unit.id])
    db.commit()

    loan_service.return_units(
        db, ticket=ticket,
        lines=[loan_service.ReturnLine(unit.id, "MAINT", "hư 2 / 6 đầu nối")])
    db.commit()
    db.refresh(unit)

    assert unit.status == UnitStatus.MAINT
    sched = db.query(UnitMaintenance).filter_by(unit_id=unit.id).one()
    assert sched.status == MaintStatus.SCHEDULED
    assert sched.note == "hư 2 / 6 đầu nối"


def test_each_unit_keeps_its_own_note(db, world):
    a, b = db.query(DeviceUnit).order_by(DeviceUnit.no).limit(2).all()
    ticket = loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                                 lender_staff_id=world["hau"].id, unit_ids=[a.id, b.id])
    db.commit()

    loan_service.return_units(db, ticket=ticket, lines=[
        loan_service.ReturnLine(a.id, "BROKEN", "hư sợi 1,3"),
        loan_service.ReturnLine(b.id, "NORMAL", None),
    ])
    db.commit()

    notes = {r.unit_id: r.note for r in db.query(UnitReturn).all()}
    assert notes[a.id] == "hư sợi 1,3"
    assert notes[b.id] is None
    db.refresh(a); db.refresh(b)
    assert a.status == UnitStatus.BROKEN and a.issue_text == "hư sợi 1,3"
    assert b.status == UnitStatus.AVAIL and b.issue_text is None


def test_cannot_return_unit_not_in_ticket(db, world):
    from fastapi import HTTPException
    a, b = db.query(DeviceUnit).order_by(DeviceUnit.no).limit(2).all()
    ticket = loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                                 lender_staff_id=world["hau"].id, unit_ids=[a.id])
    db.commit()
    with pytest.raises(HTTPException) as exc:
        loan_service.return_units(
            db, ticket=ticket, lines=[loan_service.ReturnLine(b.id, "NORMAL", None)])
    assert exc.value.status_code == 400


# ------------------------------------------------------------------ quá hạn 10 ngày

def test_ticket_state_by_elapsed_days(db, world):
    unit = db.query(DeviceUnit).first()
    ticket = loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                                 lender_staff_id=world["hau"].id, unit_ids=[unit.id])
    db.commit()
    now = datetime.utcnow()

    ticket.borrowed_at = now - timedelta(days=1)
    assert loan_service.ticket_state(ticket, now) == "open"

    ticket.borrowed_at = now - timedelta(days=8)
    assert loan_service.ticket_state(ticket, now) == "soon"

    ticket.borrowed_at = now - timedelta(days=10)
    assert loan_service.ticket_state(ticket, now) == "over"
    assert loan_service.STATE_LABEL["over"] == "Quá 10n"

    ticket.borrowed_at = now - timedelta(days=30)
    assert loan_service.ticket_state(ticket, now) == "over"


def test_overdue_query_finds_only_open_tickets(db, world):
    units = db.query(DeviceUnit).order_by(DeviceUnit.no).limit(2).all()
    old = loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                              lender_staff_id=world["hau"].id, unit_ids=[units[0].id],
                              borrowed_at=datetime.utcnow() - timedelta(days=20))
    fresh = loan_service.borrow(db, borrower_staff_id=world["linh"].id,
                                lender_staff_id=world["hau"].id, unit_ids=[units[1].id])
    db.commit()

    codes = [t.code for t in loan_service.overdue_tickets(db)]
    assert old.code in codes
    assert fresh.code not in codes

    loan_service.return_units(
        db, ticket=old, lines=[loan_service.ReturnLine(units[0].id, "NORMAL", None)])
    db.commit()
    assert old.code not in [t.code for t in loan_service.overdue_tickets(db)]


def test_overdue_email_is_sent_only_once_ever(db, world, monkeypatch):
    """
    Cảnh báo quá hạn chỉ gửi một lần cho mỗi phiếu.

    Rà lại nhiều ngày liên tiếp trên cùng một phiếu vẫn treo thì không được gửi
    thêm email nào — tránh làm phiền trưởng bộ phận mỗi ngày.
    """
    from app.services import mail_service, overdue_service

    sent: list[str] = []
    monkeypatch.setattr(
        mail_service, "notify_ticket_overdue",
        lambda db_, ticket, days: (sent.append(ticket.code), True)[1],
    )
    monkeypatch.setattr(
        overdue_service, "mail_service", mail_service, raising=False)

    unit = db.query(DeviceUnit).first()
    ticket = loan_service.borrow(
        db, borrower_staff_id=world["ha"].id, lender_staff_id=world["hau"].id,
        unit_ids=[unit.id], borrowed_at=datetime.utcnow() - timedelta(days=12))
    db.commit()

    assert overdue_service.sweep_overdue(db) == 1
    assert sent == [ticket.code]
    assert ticket.overdue_notified_at is not None

    # Chạy lại ngay, và giả lập rà tiếp trong 30 ngày sau đó
    assert overdue_service.sweep_overdue(db) == 0
    for extra_days in range(1, 31):
        later = datetime.utcnow() + timedelta(days=extra_days)
        assert overdue_service.sweep_overdue(db, later) == 0

    assert sent == [ticket.code], "Phiếu chỉ được cảnh báo đúng một lần"


def test_overdue_email_covers_each_ticket_separately(db, world, monkeypatch):
    """Một phiếu đã cảnh báo không chặn phiếu khác nhận cảnh báo của nó."""
    from app.services import mail_service, overdue_service

    sent: list[str] = []
    monkeypatch.setattr(
        mail_service, "notify_ticket_overdue",
        lambda db_, ticket, days: (sent.append(ticket.code), True)[1],
    )

    old = datetime.utcnow() - timedelta(days=15)
    units = db.query(DeviceUnit).order_by(DeviceUnit.no).limit(2).all()
    t1 = loan_service.borrow(db, borrower_staff_id=world["ha"].id,
                             lender_staff_id=world["hau"].id,
                             unit_ids=[units[0].id], borrowed_at=old)
    db.commit()
    assert overdue_service.sweep_overdue(db) == 1

    t2 = loan_service.borrow(db, borrower_staff_id=world["linh"].id,
                             lender_staff_id=world["hau"].id,
                             unit_ids=[units[1].id], borrowed_at=old)
    db.commit()
    assert overdue_service.sweep_overdue(db) == 1
    assert sorted(sent) == sorted([t1.code, t2.code])

    assert overdue_service.sweep_overdue(db) == 0


def test_department_head_is_the_email_recipient(db, world):
    from app.services.mail_service import department_head
    head = department_head(db, world["ha"])       # Hà thuộc Kế toán
    assert head is not None and head.id == world["linh"].id
    assert department_head(db, world["hau"]) is None  # IT chưa đặt trưởng bộ phận


# ------------------------------------------------------------------ phân quyền

def test_permission_catalog_has_28_entries():
    assert len(PERMISSIONS_ALL) == 28


def test_legacy_permissions_still_resolve():
    perms = parse_permissions('["devices.manage", "users.manage"]')
    assert "loan.devices.create" in perms
    assert "users.delete" in perms


def test_normalize_drops_unknown_permissions():
    assert normalize_permissions(["loan.devices.view", "khong.ton.tai"]) == ["loan.devices.view"]


def test_bcrypt_password_roundtrip():
    from app.auth import hash_password, verify_password
    h = hash_password("Mật khẩu rất dài 123!")
    assert verify_password("Mật khẩu rất dài 123!", h)
    assert not verify_password("sai", h)


# ================================================================
# NHẬP DANH MỤC TỪ EXCEL
#
# Chỗ này từng có một lỗi âm thầm: ô mã loại bỏ trống trong Excel về Python
# là NaN, str(NaN) ra chuỗi "nan", và hệ thống lặng lẽ tạo ra một loại thiết
# bị tên "NAN" kèm đủ số máy — không báo lỗi dòng nào.
# ================================================================

import io  # noqa: E402

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def _xlsx(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=["model_code", "model_name", "brand",
                                "quantity", "info", "note"]).to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture()
def admin_client(db):
    """Client đã đăng nhập bằng tài khoản đủ quyền."""
    import json as _json
    from app.auth import hash_password
    from app.main import app

    db.add(User(username="importer", password_hash=hash_password("Admin@123456"),
                full_name="Người nhập", role="ADMIN", is_active=True,
                permissions=_json.dumps(sorted(PERMISSIONS_ALL))))
    db.commit()

    client = TestClient(app)
    res = client.post("/login", data={"username": "importer", "password": "Admin@123456"},
                      follow_redirects=False)
    assert res.status_code in (302, 303), res.text
    return client


def _post_xlsx(client, rows):
    return client.post(
        "/api/v2/devices/import-excel",
        files={"file": ("nhap.xlsx", _xlsx(rows),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_import_creates_models_and_units(admin_client, db):
    res = _post_xlsx(admin_client, [
        {"model_code": "KEY", "model_name": "Bàn phím cơ", "brand": "Keychron",
         "quantity": 7, "info": "Switch đỏ", "note": ""},
    ])
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["created_models"], body["created_units"], body["failed"]) == (1, 7, 0)

    model = db.execute(select(DeviceModel).where(DeviceModel.code == "KEY")).scalar_one()
    codes = [u.code for u in db.execute(
        select(DeviceUnit).where(DeviceUnit.model_id == model.id).order_by(DeviceUnit.no)
    ).scalars()]
    assert codes == [f"KEY-{i:02d}" for i in range(1, 8)]


def test_import_blank_model_code_is_rejected_not_named_nan(admin_client, db):
    """Ô mã loại bỏ trống phải báo lỗi dòng, tuyệt đối không tạo loại 'NAN'."""
    res = _post_xlsx(admin_client, [
        {"model_code": None, "model_name": "Dòng thiếu mã", "brand": "X",
         "quantity": 3, "info": "", "note": ""},
    ])
    body = res.json()
    assert body["failed"] == 1
    assert body["created_models"] == 0 and body["created_units"] == 0
    assert "model_code" in body["errors"][0]["error"]
    assert db.execute(select(DeviceModel).where(DeviceModel.code == "NAN")).first() is None


def test_import_reimport_updates_without_duplicating_units(admin_client, db):
    """Nhập lại cùng file không được nhân đôi số máy trong kho."""
    rows = [{"model_code": "SW", "model_name": "Switch 8 cổng", "brand": "TP-Link",
             "quantity": 6, "info": "", "note": ""}]
    _post_xlsx(admin_client, rows)

    rows[0]["model_name"] = "Switch PoE 8 cổng"
    rows[0]["quantity"] = 99
    body = _post_xlsx(admin_client, rows).json()

    assert (body["created_models"], body["updated_models"], body["created_units"]) == (0, 1, 0)
    model = db.execute(select(DeviceModel).where(DeviceModel.code == "SW")).scalar_one()
    assert model.name == "Switch PoE 8 cổng"
    assert db.execute(select(func.count(DeviceUnit.id))
                      .where(DeviceUnit.model_id == model.id)).scalar_one() == 6


def test_import_bad_row_does_not_stop_the_good_ones(admin_client, db):
    body = _post_xlsx(admin_client, [
        {"model_code": "MIC", "model_name": "Micro không dây", "brand": "Shure",
         "quantity": 4, "info": "", "note": ""},
        {"model_code": "!!", "model_name": "Mã sai", "brand": "", "quantity": 2,
         "info": "", "note": ""},
        {"model_code": "CAM", "model_name": "Camera hội nghị", "brand": "Logitech",
         "quantity": 2, "info": "", "note": ""},
    ]).json()

    assert body["created_models"] == 2 and body["created_units"] == 6
    assert body["failed"] == 1 and body["errors"][0]["row"] == 3
    assert db.execute(select(func.count(DeviceModel.id))).scalar_one() == 2


def test_import_quantity_must_be_a_sane_number(admin_client, db):
    body = _post_xlsx(admin_client, [
        {"model_code": "AAA", "model_name": "Số lượng chữ", "brand": "", "quantity": "nhiều",
         "info": "", "note": ""},
        {"model_code": "BBB", "model_name": "Số lượng âm", "brand": "", "quantity": -5,
         "info": "", "note": ""},
        {"model_code": "CCC", "model_name": "Gõ nhầm số 0", "brand": "", "quantity": 99999,
         "info": "", "note": ""},
    ]).json()

    assert body["failed"] == 3 and body["created_models"] == 0
    assert db.execute(select(func.count(DeviceUnit.id))).scalar_one() == 0


def test_import_ignores_trailing_blank_rows(admin_client, db):
    body = _post_xlsx(admin_client, [
        {"model_code": "PRJ", "model_name": "Máy chiếu", "brand": "Epson",
         "quantity": 2, "info": "", "note": ""},
        {"model_code": None, "model_name": None, "brand": None,
         "quantity": None, "info": None, "note": None},
    ]).json()

    assert body["created_models"] == 1 and body["failed"] == 0


def test_import_template_has_the_expected_columns(admin_client):
    res = admin_client.get("/api/v2/devices/import-template")
    assert res.status_code == 200
    df = pd.read_excel(io.BytesIO(res.content))
    assert list(df.columns) == ["model_code", "model_name", "brand",
                                "quantity", "info", "note"]


# ================================================================
# TẠO TÀI KHOẢN
# ================================================================

def _mk_user(db, username, perms, role="USER"):
    import json as _json
    from app.auth import hash_password
    u = User(username=username, password_hash=hash_password("Admin@123456"),
             full_name=username, role=role, is_active=True,
             permissions=_json.dumps(sorted(perms)))
    db.add(u); db.commit()
    return u


def _login(client, username, password="Admin@123456"):
    res = client.post("/login", data={"username": username, "password": password},
                      follow_redirects=False)
    assert res.status_code in (302, 303), res.text


def test_create_user_with_permissions(admin_client, db):
    res = admin_client.post("/api/v2/users", json={
        "username": "binh.tran", "password": "MatKhau@2026x",
        "full_name": "Trần Thị Bình", "is_active": True,
        "permissions": ["loan.devices.view", "loan.loans.view"],
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["username"] == "binh.tran"
    assert body["role"] == "USER"
    assert sorted(body["permissions"]) == ["loan.devices.view", "loan.loans.view"]

    created = db.execute(select(User).where(User.username == "binh.tran")).scalar_one()
    assert created.password_hash != "MatKhau@2026x"     # phải là băm, không phải chữ thật


def test_create_user_rejects_duplicate_username(admin_client):
    payload = {"username": "trung.le", "password": "MatKhau@2026x", "permissions": []}
    assert admin_client.post("/api/v2/users", json=payload).status_code == 201
    res = admin_client.post("/api/v2/users", json=payload)
    assert res.status_code == 400 and "tồn tại" in res.json()["detail"].lower()


def test_create_user_rejects_short_password(admin_client):
    res = admin_client.post("/api/v2/users", json={
        "username": "ngan.vo", "password": "12345", "permissions": []})
    assert res.status_code == 422


def test_new_account_can_log_in_and_has_only_its_permissions(admin_client, db):
    from app.main import app
    admin_client.post("/api/v2/users", json={
        "username": "chixem.nv", "password": "MatKhau@2026x",
        "permissions": ["loan.devices.view"]})

    other = TestClient(app)
    _login(other, "chixem.nv", "MatKhau@2026x")
    assert other.get("/api/v2/devices/models").status_code == 200      # có quyền xem
    assert other.get("/api/v2/users").status_code == 403               # không có quyền users.view


def test_non_admin_cannot_grant_permissions_it_lacks(db):
    """Người có users.create nhưng quyền hẹp không thể tự nhân bản quyền rộng hơn."""
    from app.main import app
    _mk_user(db, "nguoitao", ["users.view", "users.create", "loan.devices.view"])

    client = TestClient(app)
    _login(client, "nguoitao")

    ok = client.post("/api/v2/users", json={
        "username": "hep.nv", "password": "MatKhau@2026x",
        "permissions": ["loan.devices.view"]})
    assert ok.status_code == 201

    over = client.post("/api/v2/users", json={
        "username": "rong.nv", "password": "MatKhau@2026x",
        "permissions": ["loan.devices.view", "users.delete"]})
    assert over.status_code == 403
    assert "users.delete" in over.json()["detail"]
    assert db.execute(select(User).where(User.username == "rong.nv")).first() is None


def test_creating_user_requires_the_create_permission(db):
    from app.main import app
    _mk_user(db, "chixemthoi", ["users.view"])

    client = TestClient(app)
    _login(client, "chixemthoi")
    res = client.post("/api/v2/users", json={
        "username": "aido.nv", "password": "MatKhau@2026x", "permissions": []})
    assert res.status_code == 403


def test_admin_can_reset_a_user_password(admin_client, db):
    """Nhân sự quên mật khẩu: quản trị viên đặt lại, tài khoản đăng nhập được ngay."""
    from app.main import app
    admin_client.post("/api/v2/users", json={
        "username": "quenmk.nv", "password": "CuKy@2026", "permissions": ["loan.devices.view"]})

    old_hash = db.execute(
        select(User.password_hash).where(User.username == "quenmk.nv")).scalar_one()

    res = admin_client.put(
        f"/api/v2/users/{db.execute(select(User.id).where(User.username=='quenmk.nv')).scalar_one()}",
        json={"password": "MoiKy@2026"})
    assert res.status_code == 200, res.text

    db.expire_all()
    new_hash = db.execute(
        select(User.password_hash).where(User.username == "quenmk.nv")).scalar_one()
    assert new_hash != old_hash

    client = TestClient(app)
    _login(client, "quenmk.nv", "MoiKy@2026")            # mật khẩu mới vào được
    assert client.get("/api/v2/devices/models").status_code == 200

    old = TestClient(app)
    fail = old.post("/login", data={"username": "quenmk.nv", "password": "CuKy@2026"},
                    follow_redirects=False)
    assert fail.status_code == 401                        # mật khẩu cũ hết hiệu lực


def test_password_of_six_characters_is_accepted(admin_client):
    res = admin_client.post("/api/v2/users", json={
        "username": "sauky.nv", "password": "abc123", "permissions": []})
    assert res.status_code == 201, res.text


def test_non_admin_cannot_reset_an_admin_password(db):
    """Chặn leo thang: người có users.update không được đổi mật khẩu quản trị viên."""
    from app.main import app
    _mk_user(db, "nguoisua", ["users.view", "users.update"])
    target = _mk_user(db, "septo", ["users.view"], role="ADMIN")

    client = TestClient(app)
    _login(client, "nguoisua")
    res = client.put(f"/api/v2/users/{target.id}", json={"password": "ChiemQuyen@1"})
    assert res.status_code == 403


# ---------------------------------------------------------------- phòng cho mượn

def test_lender_department_is_created_on_startup(db):
    """Phòng IT phải có sẵn, không bắt người dùng tự tạo trước khi lập phiếu."""
    from app.main import _bootstrap_lender_department
    from app.config import settings

    db.query(Department).delete()
    db.commit()

    _bootstrap_lender_department()
    db.expire_all()
    names = db.execute(select(Department.name)).scalars().all()
    assert settings.lender_department in names


def test_lender_department_is_not_duplicated(db):
    """Chạy lại nhiều lần, và tên viết thường, đều không sinh phòng thứ hai."""
    from app.main import _bootstrap_lender_department

    db.query(Department).delete()
    db.add(Department(name="it"))
    db.commit()

    _bootstrap_lender_department()
    _bootstrap_lender_department()
    db.expire_all()
    it_rows = [n for n in db.execute(select(Department.name)).scalars().all()
               if n.strip().lower() == "it"]
    assert it_rows == ["it"]


# ---------------------------------------------------------------- ngày mượn

def _borrow(client, world, **extra):
    """Mượn một cuộn quang, cho phép chèn thêm trường vào phần thân yêu cầu."""
    units = client.get("/api/v2/devices/units").json()
    return client.post("/api/v2/tickets", json={
        "borrower_staff_id": world["linh"].id,
        "lender_staff_id": world["hau"].id,
        "unit_ids": [units[0]["id"]],
        **extra})


def test_borrow_date_defaults_to_now(admin_client, db, world):
    """Không gửi ngày thì phiếu lấy đúng lúc lập."""
    before = datetime.utcnow() - timedelta(seconds=5)
    res = _borrow(admin_client, world)
    assert res.status_code == 201, res.text
    got = datetime.fromisoformat(res.json()["borrowed_at"])
    assert before <= got <= datetime.utcnow() + timedelta(seconds=5)


def test_borrow_date_can_be_backdated(admin_client, db, world):
    """Giao máy hôm trước, hôm nay mới nhập thì phải ghi được đúng ngày cũ."""
    when = datetime.utcnow() - timedelta(days=4)
    res = _borrow(admin_client, world, borrowed_at=when.isoformat())
    assert res.status_code == 201, res.text
    got = datetime.fromisoformat(res.json()["borrowed_at"])
    assert abs((got - when).total_seconds()) < 2
    assert res.json()["days_elapsed"] == 4       # phiếu lùi ngày vẫn đếm đúng


def test_borrow_date_in_the_future_is_rejected(admin_client, db, world):
    res = _borrow(admin_client, world,
                  borrowed_at=(datetime.utcnow() + timedelta(days=30)).isoformat())
    assert res.status_code == 422


# ---------------------------------------------------------------- tem QR

def test_model_qr_is_a_standalone_svg(admin_client, db, world):
    """Ô QR trong bảng tải bằng <img>, nên SVG bắt buộc phải có xmlns."""
    res = admin_client.get(f"/api/v2/devices/models/{world['model'].id}/qr.svg")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/svg+xml")
    body = res.text
    assert 'xmlns="http://www.w3.org/2000/svg"' in body
    assert body.lstrip().startswith("<svg")


def test_unit_labels_cover_every_machine(admin_client, db, world):
    """Mỗi máy một tem, và mã in ra phải là mã máy chứ không phải mã loại."""
    res = admin_client.get(f"/api/v2/devices/models/{world['model'].id}/labels")
    assert res.status_code == 200
    page = res.text
    assert page.count('class="lb"') == 5           # 5 cuộn quang trong world
    for n in range(1, 6):
        assert f"QUANG-0{n}" in page


def test_model_label_prints_one_ticket(admin_client, db, world):
    res = admin_client.get(f"/api/v2/devices/models/{world['model'].id}/labels?kind=model")
    assert res.status_code == 200
    assert res.text.count('class="lb"') == 1


def test_labels_reject_unknown_kind(admin_client, db, world):
    res = admin_client.get(f"/api/v2/devices/models/{world['model'].id}/labels?kind=xyz")
    assert res.status_code == 422


def test_labels_need_view_permission(db):
    """Không có quyền xem thiết bị thì không lấy được tem."""
    from app.main import app
    _mk_user(db, "khongquyen", ["loan.loans.view"])
    client = TestClient(app)
    _login(client, "khongquyen")
    assert client.get("/api/v2/devices/models/1/labels").status_code == 403
    assert client.get("/api/v2/devices/models/1/qr.svg").status_code == 403
