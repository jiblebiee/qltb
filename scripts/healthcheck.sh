#!/usr/bin/env bash
#
# Kiểm tra hệ thống có đang chạy đúng không.
# Chạy sau khi cài, hoặc bất cứ lúc nào thấy nghi ngờ.
#
#   ./scripts/healthcheck.sh

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -t 1 ]]; then
  B=$'\033[1m'; R=$'\033[0m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'
else B=''; R=''; GREEN=''; RED=''; YELLOW=''; DIM=''; fi

PASS=0; FAIL=0; WARN=0
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$R" "$*"; PASS=$((PASS+1)); }
bad()  { printf '  %s✗%s %s\n' "$RED" "$R" "$*"; FAIL=$((FAIL+1)); }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$R" "$*"; WARN=$((WARN+1)); }
info() { printf '    %s%s%s\n' "$DIM" "$*" "$R"; }
head_() { printf '\n%s%s%s\n' "$B" "$*" "$R"; }

[[ -f .env ]] || { printf '%sKhông thấy .env — hệ thống chưa được cài.%s\n' "$RED" "$R"; exit 1; }

# Đọc .env bằng trình phân tích riêng, KHÔNG dùng `source`: giá trị như
# MAIL_FROM=IT QLTB <no-reply@x.com> có dấu < sẽ bị bash hiểu là chuyển hướng.
cfg() {
  KEY="$1" python3 - ./.env "${2-}" <<'PY'
import os, sys
key, val = os.environ["KEY"], sys.argv[2]
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith(key + "="):
        val = line.split("=", 1)[1]
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
print(val)
PY
}

APP_SECRET_KEY=$(cfg APP_SECRET_KEY)
BOOTSTRAP_ADMIN_PASS=$(cfg BOOTSTRAP_ADMIN_PASS)
COOKIE_SECURE=$(cfg COOKIE_SECURE false)
S3_ENDPOINT_URL=$(cfg S3_ENDPOINT_URL)
S3_PUBLIC_ENDPOINT_URL=$(cfg S3_PUBLIC_ENDPOINT_URL)
AWS_ACCESS_KEY_ID=$(cfg AWS_ACCESS_KEY_ID)
MINIO_ROOT_USER=$(cfg MINIO_ROOT_USER)
SMTP_ENABLED=$(cfg SMTP_ENABLED false)
SMTP_HOST=$(cfg SMTP_HOST)
SMTP_PORT=$(cfg SMTP_PORT)
EMAIL_MANAGE=$(cfg EMAIL_MANAGE)
PORT=$(cfg APP_PORT 8000)
BASE="http://127.0.0.1:${PORT}"

head_ "Cấu hình"
if [[ -n "$APP_SECRET_KEY" ]]; then
  ok "APP_SECRET_KEY đã có"
  [[ ${#APP_SECRET_KEY} -ge 32 ]] \
    || warn "APP_SECRET_KEY hơi ngắn (${#APP_SECRET_KEY} ký tự) — nên từ 32 trở lên"
else
  bad "Thiếu APP_SECRET_KEY"
fi
perm=$(stat -c '%a' .env 2>/dev/null || echo '?')
[[ "$perm" == "600" ]] && ok ".env chỉ chủ sở hữu đọc được" \
  || warn ".env đang ở quyền $perm — nên đặt: chmod 600 .env"
[[ -n "$BOOTSTRAP_ADMIN_PASS" ]] \
  && warn "BOOTSTRAP_ADMIN_PASS còn trong .env — xoá sau khi đã đổi mật khẩu" \
  || ok "Đã xoá mật khẩu khởi tạo khỏi .env"
[[ "$COOKIE_SECURE" == "true" ]] && ok "COOKIE_SECURE bật" \
  || warn "COOKIE_SECURE tắt — bật khi chạy sau HTTPS"

# Cài trọn gói: khoá của MinIO và khoá ứng dụng phải trùng nhau, lệch một ký tự
# là mọi lần tải ảnh lên đều 403 mà không có thông báo rõ ràng.
if [[ -n "$MINIO_ROOT_USER" ]]; then
  [[ "$MINIO_ROOT_USER" == "$AWS_ACCESS_KEY_ID" ]] \
    && ok "Khoá MinIO khớp khoá ứng dụng" \
    || bad "MINIO_ROOT_USER khác AWS_ACCESS_KEY_ID — sửa cho trùng rồi khởi động lại"
fi
# Trình duyệt PUT ảnh thẳng lên kho, nên địa chỉ ký không được là tên nội bộ
case "${S3_PUBLIC_ENDPOINT_URL:-$S3_ENDPOINT_URL}" in
  *//minio:*|*//localhost:*|*//127.0.0.1:*)
    warn "Địa chỉ kho ảnh cho trình duyệt là ${S3_PUBLIC_ENDPOINT_URL:-$S3_ENDPOINT_URL}"
    info "Máy trạm khác sẽ không tải ảnh lên được. Đặt S3_PUBLIC_ENDPOINT_URL thành IP thật." ;;
  "") : ;;
  *) ok "Trình duyệt tải ảnh lên ${S3_PUBLIC_ENDPOINT_URL:-$S3_ENDPOINT_URL}" ;;
esac

head_ "Dịch vụ Docker"
running=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  for f in docker-compose.full.yml docker-compose.yml; do
    [[ -f "$f" ]] || continue
    running=$(docker compose -f "$f" ps --services --filter status=running 2>/dev/null | tr '\n' ' ')
    [[ -n "${running// }" ]] && { ok "Đang chạy ($f): ${running}"; break; }
  done
  [[ -z "${running// }" ]] && warn "Không thấy dịch vụ nào chạy qua Docker Compose"
else
  info "Bỏ qua — Docker không dùng được hoặc không cài"
fi

head_ "Ứng dụng"
if curl -fsS -m 5 "$BASE/health" >/dev/null 2>&1; then
  ok "Máy chủ trả lời ở $BASE"
else
  bad "Máy chủ không trả lời ở $BASE"
  info "Xem log: docker compose -f docker-compose.full.yml logs --tail=50 web"
fi

# /health có kèm trạng thái database và không cần đăng nhập
db=$(curl -fsS -m 5 "$BASE/health" 2>/dev/null || echo '{}')
grep -q '"db":true' <<< "$db" && ok "Kết nối cơ sở dữ liệu tốt" || {
  bad "Không kết nối được cơ sở dữ liệu"
  info "Đăng nhập rồi mở $BASE/api/health/db để xem lỗi cụ thể"; }

code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$BASE/login" 2>/dev/null || echo 000)
[[ "$code" == "200" ]] && ok "Trang đăng nhập mở được" || bad "Trang đăng nhập trả về HTTP $code"

code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$BASE/api/v2/me" 2>/dev/null || echo 000)
[[ "$code" == "401" ]] && ok "API chặn đúng khi chưa đăng nhập" \
  || bad "API trả về HTTP $code khi chưa đăng nhập — đáng lẽ phải 401"

code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$BASE/static/css/app.css" 2>/dev/null || echo 000)
[[ "$code" == "200" ]] && ok "Tệp giao diện tải được" || bad "Không tải được CSS (HTTP $code)"

head_ "Kho ảnh"
if [[ -n "$S3_ENDPOINT_URL" ]]; then
  if curl -fsS -m 5 "${S3_ENDPOINT_URL}/minio/health/live" >/dev/null 2>&1 \
     || curl -fsS -m 5 -o /dev/null "${S3_ENDPOINT_URL}" 2>/dev/null; then
    ok "S3 phản hồi ở ${S3_ENDPOINT_URL}"
  else
    warn "Không gọi được ${S3_ENDPOINT_URL} — kiểm tra lại nếu tính năng ảnh không chạy"
  fi
else
  warn "Chưa đặt S3_ENDPOINT_URL"
fi

head_ "Email"
if [[ "$SMTP_ENABLED" == "true" ]]; then
  ok "SMTP bật — máy chủ ${SMTP_HOST:-?}:${SMTP_PORT:-?}"
  [[ -n "$EMAIL_MANAGE" ]] && ok "Địa chỉ nhận báo cáo: ${EMAIL_MANAGE}" \
    || warn "Chưa đặt EMAIL_MANAGE — báo cáo tuần và tháng sẽ không gửi được"
else
  warn "SMTP tắt — không có thư nào được gửi"
fi

printf '\n%s─────────────────────────────────%s\n' "$B" "$R"
printf '  %s%d đạt%s   %s%d cảnh báo%s   %s%d lỗi%s\n\n' \
  "$GREEN" "$PASS" "$R" "$YELLOW" "$WARN" "$R" "$RED" "$FAIL" "$R"
[[ $FAIL -eq 0 ]] || exit 1
