from __future__ import annotations

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext

COOKIE_NAME = "it_assets_session"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 12  # 12 giờ

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(pw: str) -> str:
    # bcrypt gioi han 72 bytes
    if len(pw.encode("utf-8")) > 72:
        raise ValueError("Mat khau qua dai (bcrypt gioi han 72 bytes). Hay dat mat khau ngan hon.")
    return _pwd_ctx.hash(pw)


def verify_password(pw: str, pw_hash: str) -> bool:
    return _pwd_ctx.verify(pw, pw_hash)


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="it-assets-session-v1")


def make_session_token(secret_key: str, user_id: int) -> str:
    s = _serializer(secret_key)
    return s.dumps({"uid": int(user_id)})


def read_session_user_id(secret_key: str, token: str) -> int | None:
    s = _serializer(secret_key)
    try:
        data = s.loads(token, max_age=COOKIE_MAX_AGE_SECONDS)
        uid = data.get("uid")
        return int(uid) if uid is not None else None
    except (BadSignature, SignatureExpired, Exception):
        return None
