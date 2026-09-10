"""
Trường "tình trạng ghi nhận" của một máy.

Khi nhận trả, nhân viên IT ghi chú riêng cho từng máy. Nếu ghi chú nhắc tới hư
hại — ví dụ "hư sợi 1,3" trên một cuộn quang 6 đầu — thì ghi chú đó phải nổi lên
ngay ở chi tiết thiết bị, chứ không nằm im trong lịch sử. Máy vẫn có thể ở trạng
thái Sẵn sàng nhưng mang cảnh báo này.

Cách dò: tách ghi chú thành từng TỪ rồi so khớp với danh sách từ khoá. Cố tình
không dùng tìm chuỗi con, vì "hư" nằm trong "như", "nhưng", "chưa", "thư"…
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from ..models_v2 import DeviceUnit, ReturnCondition

# Từ khoá cho thấy máy có vấn đề. Viết thường, có dấu.
ISSUE_KEYWORDS: set[str] = {
    "hư", "hử", "hỏng", "hong", "lỗi", "loi",
    "gãy", "vỡ", "bể", "nứt", "móp",
    "chập", "cháy", "đứt", "kẹt", "rè",
    "xước", "trầy", "mất", "thiếu", "yếu",
    "chờn", "lỏng", "liệt", "đơ", "treo", "chết",
}

# Tách theo mọi ký tự không phải chữ/số (Unicode), giữ nguyên dấu tiếng Việt
_SPLIT = re.compile(r"[^\w]+", re.UNICODE)


def _words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text or "").lower()
    return [w for w in _SPLIT.split(normalized) if w]


def has_issue_keyword(note: str | None) -> bool:
    """True nếu ghi chú chứa ít nhất một từ khoá hư hại (so khớp theo từ)."""
    if not note:
        return False
    return any(w in ISSUE_KEYWORDS for w in _words(note))


def should_flag(note: str | None, condition: ReturnCondition | str | None) -> bool:
    """
    Có gắn tình trạng cho máy không?
      - Ghi chú chứa từ khoá hư hại  -> có, kể cả khi trả ở tình trạng bình thường
      - Trả ở tình trạng Hỏng/Bảo trì mà có ghi chú -> có
    """
    text = (note or "").strip()
    if not text:
        return False
    if has_issue_keyword(text):
        return True
    cond = condition.value if isinstance(condition, ReturnCondition) else str(condition or "")
    return cond in {"BROKEN", "MAINT"}


def apply_issue(
    unit: DeviceUnit,
    note: str | None,
    condition: ReturnCondition | str | None,
    at: datetime,
    source: str | None = None,
) -> bool:
    """
    Cập nhật trường tình trạng của máy sau một lần nhận trả.

    Trả về True nếu máy đang mang cảnh báo sau lời gọi này.
    Ghi chú mới đè lên ghi chú cũ; nếu lần trả này sạch thì cảnh báo cũ được gỡ.
    """
    text = (note or "").strip()
    if not text:
        return unit.issue_text is not None  # không có ghi chú thì giữ nguyên trạng thái cũ

    if should_flag(text, condition):
        unit.issue_text = text
        unit.issue_at = at
        unit.issue_source = source
        return True

    clear_issue(unit)
    return False


def clear_issue(unit: DeviceUnit) -> None:
    unit.issue_text = None
    unit.issue_at = None
    unit.issue_source = None
