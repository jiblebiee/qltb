#!/usr/bin/env bash
#
# Sao lưu cơ sở dữ liệu và ảnh.
#
#   ./scripts/backup.sh              lưu vào ./backups
#   ./scripts/backup.sh /duong/dan   lưu vào thư mục chỉ định
#
# Chạy trước mỗi lần nâng cấp. Nên đặt vào cron chạy hằng đêm:
#   0 2 * * * cd /opt/it-qltb && ./scripts/backup.sh >> /var/log/qltb-backup.log 2>&1

set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEST="${1:-$ROOT/backups}"
STAMP=$(date +%Y%m%d-%H%M%S)
KEEP_DAYS=30

[[ -f .env ]] || { echo "Không thấy .env"; exit 1; }

# Đọc .env bằng trình phân tích riêng, KHÔNG `source`: giá trị như
# MAIL_FROM=IT QLTB <no-reply@x.com> sẽ bị bash hiểu là chuyển hướng tệp.
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

DB_URL=$(cfg DB_URL)
MYSQL_ROOT_PASSWORD=$(cfg MYSQL_ROOT_PASSWORD)
MYSQL_DATABASE=$(cfg MYSQL_DATABASE it_qltb)
mkdir -p "$DEST"

echo "▸ Sao lưu cơ sở dữ liệu"
DB_FILE="$DEST/qltb-db-$STAMP.sql.gz"

if docker compose -f docker-compose.full.yml ps db 2>/dev/null | grep -q 'Up\|running'; then
  # MySQL chạy trong Docker của chính bộ này
  docker compose -f docker-compose.full.yml exec -T db \
    mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" \
      --single-transaction --routines --triggers --default-character-set=utf8mb4 \
      "${MYSQL_DATABASE:-it_qltb}" | gzip > "$DB_FILE"
else
  # MySQL ở máy khác — bóc thông tin từ DB_URL.
  # Đọc từng phần một chứ không eval: mật khẩu có thể chứa " hoặc $
  # và eval sẽ chạy nhầm thành lệnh.
  dburl_part() {
    DB_URL="$DB_URL" python3 - "$1" <<'PY'
import os, sys, urllib.parse
raw = os.environ["DB_URL"]
url = urllib.parse.urlparse(raw.split("+", 1)[-1] if "+" in raw.split("://", 1)[0] else raw)
part = sys.argv[1]
out = {
    "host": url.hostname or "127.0.0.1",
    "port": str(url.port or 3306),
    "user": urllib.parse.unquote(url.username or ""),
    "pass": urllib.parse.unquote(url.password or ""),
    "name": (url.path or "/").lstrip("/").split("?")[0],
}[part]
print(out)
PY
  }
  H=$(dburl_part host); P=$(dburl_part port)
  U=$(dburl_part user); W=$(dburl_part pass); D=$(dburl_part name)

  command -v mysqldump >/dev/null || { echo "Cần cài mysql-client để sao lưu database ngoài"; exit 1; }
  MYSQL_PWD="$W" mysqldump -h "$H" -P "$P" -u "$U" \
    --single-transaction --routines --triggers --default-character-set=utf8mb4 \
    "$D" | gzip > "$DB_FILE"
fi

SIZE=$(du -h "$DB_FILE" | cut -f1)
echo "  ✓ $(basename "$DB_FILE") ($SIZE)"

echo "▸ Sao lưu cấu hình"
cp .env "$DEST/qltb-env-$STAMP.bak"
chmod 600 "$DEST/qltb-env-$STAMP.bak"
echo "  ✓ qltb-env-$STAMP.bak"

echo "▸ Ảnh sản phẩm"
if docker compose -f docker-compose.full.yml ps minio 2>/dev/null | grep -q 'Up\|running'; then
  IMG_FILE="$DEST/qltb-images-$STAMP.tar.gz"
  # Mượn đúng volume của container minio đang chạy, không dò theo tên volume —
  # trên máy có nhiều dự án, dò theo tên rất dễ vớ nhầm volume của dự án khác.
  MINIO_CID=$(docker compose -f docker-compose.full.yml ps -q minio)
  docker run --rm \
    --volumes-from "$MINIO_CID":ro \
    -v "$DEST":/backup alpine \
    tar czf "/backup/$(basename "$IMG_FILE")" -C /data . 2>/dev/null \
    && echo "  ✓ $(basename "$IMG_FILE") ($(du -h "$IMG_FILE" | cut -f1))" \
    || echo "  ! Không sao lưu được ảnh — làm thủ công nếu cần"
else
  echo "  · Ảnh nằm trên S3 bên ngoài, sao lưu theo quy trình của S3 đó"
fi

echo "▸ Dọn bản cũ hơn $KEEP_DAYS ngày"
DELETED=$(find "$DEST" -name 'qltb-*' -type f -mtime +$KEEP_DAYS -print -delete | wc -l)
echo "  ✓ Đã xoá $DELETED tệp"

echo
echo "Xong. Thư mục: $DEST"
echo "Phục hồi database: gunzip -c FILE.sql.gz | mysql -h HOST -u USER -p TÊN_DB"
