#!/usr/bin/env bash
#
# Cài đặt IT-QLTB trên một máy mới.
#
#   ./scripts/setup.sh              cài trọn gói, có hỏi từng bước
#   ./scripts/setup.sh --quick      cài trọn gói, tự sinh hết, không hỏi
#   ./scripts/setup.sh --external   nối tới MySQL và S3 có sẵn
#   ./scripts/setup.sh --check      chỉ kiểm tra máy có đủ điều kiện chưa
#   ./scripts/setup.sh --dry-run    chỉ tạo .env, không dựng Docker
#
# Script chạy lại được nhiều lần. Nếu .env đã có, nó hỏi trước khi ghi đè.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="$ROOT/.env"
COMPOSE_FULL="docker-compose.full.yml"
COMPOSE_APP="docker-compose.yml"

MODE="guided"     # guided | quick | external
DO_CHECK_ONLY=0
DRY_RUN=0

# ---------------------------------------------------------------- hiển thị

if [[ -t 1 ]]; then
  B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0m'
  GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BLUE=$'\033[36m'
else
  B=''; DIM=''; R=''; GREEN=''; RED=''; YELLOW=''; BLUE=''
fi

step()  { printf '\n%s▸ %s%s\n' "$B$BLUE" "$*" "$R"; }
ok()    { printf '  %s✓%s %s\n' "$GREEN" "$R" "$*"; }
warn()  { printf '  %s!%s %s\n' "$YELLOW" "$R" "$*"; }
fail()  { printf '  %s✗%s %s\n' "$RED" "$R" "$*"; }
info()  { printf '  %s%s%s\n' "$DIM" "$*" "$R"; }
die()   { printf '\n%s✗ %s%s\n\n' "$B$RED" "$*" "$R" >&2; exit 1; }

trap 'fail "Dừng ở dòng $LINENO. Sửa lỗi rồi chạy lại script."' ERR

# ---------------------------------------------------------------- tham số

for arg in "$@"; do
  case "$arg" in
    --quick)    MODE="quick" ;;
    --external) MODE="external" ;;
    --check)    DO_CHECK_ONLY=1 ;;
    --dry-run)  DRY_RUN=1 ;;
    -h|--help)  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          die "Tham số lạ: $arg. Chạy --help để xem cách dùng." ;;
  esac
done

# ---------------------------------------------------------------- tiện ích

have() { command -v "$1" >/dev/null 2>&1; }

# Đọc một dòng từ bàn phím, có giá trị mặc định
ask() {
  local prompt="$1" default="${2-}" answer
  if [[ "$MODE" == "quick" ]]; then printf '%s' "$default"; return; fi
  if [[ -n "$default" ]]; then
    read -r -p "  $prompt [$default]: " answer </dev/tty || true
    printf '%s' "${answer:-$default}"
  else
    read -r -p "  $prompt: " answer </dev/tty || true
    printf '%s' "$answer"
  fi
}

ask_secret() {
  local prompt="$1" answer
  if [[ "$MODE" == "quick" ]]; then printf ''; return; fi
  read -r -s -p "  $prompt: " answer </dev/tty || true
  printf '\n' >&2
  printf '%s' "$answer"
}

# confirm "câu hỏi" [mặc_định_khi_chạy_nhanh: y|n]
confirm() {
  local prompt="$1" default="${2:-n}" answer
  if [[ "$MODE" == "quick" ]]; then [[ "$default" == "y" ]]; return; fi
  read -r -p "  $prompt [y/N]: " answer </dev/tty || true
  [[ "$answer" =~ ^[YyCc]$ ]]   # y / Y / c / C (có)
}

# Chuỗi ngẫu nhiên an toàn, chỉ chữ và số để không vỡ chuỗi kết nối.
# Không dùng `head -c` đọc /dev/urandom: head đóng ống sớm, tr chết vì SIGPIPE
# và `set -o pipefail` sẽ coi cả script là lỗi. openssl cho nguồn hữu hạn nên
# `cut` đọc hết rồi mới cắt, không sinh SIGPIPE.
randpw() {
  local n="${1:-24}"
  LC_ALL=C openssl rand -base64 $(( n * 3 )) | tr -dc 'A-Za-z0-9' | cut -c1-"$n"
}
randkey() { openssl rand -base64 48 | tr -d '\n=' | tr '+/' '-_'; }

# Ghi một biến vào .env, thay nếu đã có.
# Không dùng sed vì giá trị người dùng nhập có thể chứa &, \, | làm vỡ lệnh thay thế.
setenv() {
  local key="$1" value="$2"
  KEY="$key" VALUE="$value" python3 - "$ENV_FILE" <<'PY'
import os, sys

path = sys.argv[1]
key, value = os.environ["KEY"], os.environ["VALUE"]

# Giá trị có khoảng trắng, dấu # hay $ phải bọc nháy đơn, nếu không Docker
# Compose và thư viện đọc .env sẽ cắt mất phần sau hoặc thay biến môi trường.
# Trong nháy đơn thì mọi ký tự đều giữ nguyên — trừ chính dấu nháy đơn.
if value and (set(value) & set(" \t#$\"'\\") or value != value.strip()):
    if "'" in value:
        sys.stderr.write(
            f"  ! {key} có dấu nháy đơn — ghi nguyên văn, kiểm tra lại .env\n")
    else:
        value = "'" + value + "'"

line = f"{key}={value}"
try:
    lines = open(path, encoding="utf-8").read().splitlines()
except FileNotFoundError:
    lines = []

if any(l.startswith(key + "=") for l in lines):
    lines = [line if l.startswith(key + "=") else l for l in lines]
else:
    lines.append(line)

open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

# Đọc một biến ra khỏi .env mà không cần `source` — giá trị có thể chứa
# khoảng trắng hoặc $ nên source sẽ hỏng hoặc chạy nhầm lệnh.
getenv() {
  local key="$1" default="${2-}"
  KEY="$key" python3 - "$ENV_FILE" "$default" <<'PY'
import os, sys
key, default = os.environ["KEY"], sys.argv[2]
val = default
try:
    for line in open(sys.argv[1], encoding="utf-8"):
        if line.startswith(key + "="):
            val = line.split("=", 1)[1].rstrip("\n")
            # bỏ lớp nháy mà setenv đã thêm vào
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                val = val[1:-1]
except FileNotFoundError:
    pass
print(val)
PY
}

# Địa chỉ IP của máy này trong mạng LAN, để máy khác truy cập được
host_ip() {
  local ip
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  printf '%s' "${ip:-127.0.0.1}"
}

# Chạy lệnh với quyền root. Máy mới thường phải nhập mật khẩu sudo, nên xin
# quyền TRƯỚC khi vào pipeline — nếu để sudo hỏi mật khẩu giữa `curl | sudo sh`
# thì lời nhắc bị lẫn vào output rất khó nhìn.
SUDO=""
need_root() {
  [[ $EUID -eq 0 ]] && { SUDO=""; return 0; }
  have sudo || die "Cần quyền root hoặc sudo. Đăng nhập bằng root rồi chạy lại."
  SUDO="sudo"
  sudo -n true 2>/dev/null || {
    info "Cần quyền quản trị — nhập mật khẩu của $USER:"
    sudo -v || die "Không lấy được quyền quản trị."
  }
}

# Trình quản lý gói của máy này
pkg_manager() {
  for m in apt-get dnf yum zypper pacman apk; do
    have "$m" && { printf '%s' "$m"; return 0; }
  done
  return 1
}

APT_UPDATED=0
pkg_install() {
  local mgr; mgr=$(pkg_manager) || return 1
  need_root
  case "$mgr" in
    apt-get)
      [[ $APT_UPDATED -eq 1 ]] || { $SUDO apt-get update -qq && APT_UPDATED=1; }
      DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq "$@" ;;
    dnf|yum) $SUDO "$mgr" install -y "$@" ;;
    zypper)  $SUDO zypper --non-interactive install "$@" ;;
    pacman)  $SUDO pacman -Sy --noconfirm "$@" ;;
    apk)     $SUDO apk add --no-cache "$@" ;;
  esac
}

# Bảo đảm có một lệnh; thiếu thì tự cài. Trả về 1 nếu chịu thua.
ensure_tool() {
  local cmd="$1" pkg="${2:-$1}" why="${3-}"
  have "$cmd" && { ok "$cmd"; return 0; }
  fail "Chưa có $cmd${why:+ ($why)}"
  if ! pkg_manager >/dev/null; then
    info "Không nhận ra trình quản lý gói — cài $pkg thủ công rồi chạy lại."
    return 1
  fi
  if ! confirm "Cài $pkg ngay?" y; then
    info "Bỏ qua. Cài bằng: sudo $(pkg_manager) install $pkg"
    return 1
  fi
  pkg_install "$pkg" >/dev/null 2>&1 || pkg_install "$pkg" || true
  have "$cmd" && { ok "Đã cài $cmd"; return 0; }
  fail "Cài $pkg không thành công"
  info "Cài tay rồi chạy lại script: sudo $(pkg_manager) install $pkg"
  info "Máy không ra được Internet thì kiểm tra mạng và proxy trước."
  return 1
}

compose() {
  local file="$1"; shift
  if docker compose version >/dev/null 2>&1; then
    $DOCKER_SUDO docker compose -f "$file" "$@"
  else
    $DOCKER_SUDO docker-compose -f "$file" "$@"
  fi
}
DOCKER_SUDO=""

# ---------------------------------------------------------------- kiểm tra máy

install_docker() {
  step "Cài Docker"
  need_root

  if have curl; then
    info "Tải bộ cài chính thức từ get.docker.com — mất vài phút."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh \
      && $SUDO sh /tmp/get-docker.sh \
      && rm -f /tmp/get-docker.sh
  else
    # Không có curl thì lấy bản Docker trong kho của bản phân phối.
    # Cũ hơn bản chính thức một chút nhưng chạy tốt.
    info "Không có curl — cài Docker từ kho phần mềm của hệ điều hành."
    case "$(pkg_manager)" in
      apt-get) pkg_install docker.io docker-compose-v2 ;;
      dnf|yum) pkg_install docker docker-compose-plugin ;;
      pacman)  pkg_install docker docker-compose ;;
      *)       die "Không tự cài Docker được. Cài thủ công rồi chạy lại." ;;
    esac
  fi

  have systemctl && $SUDO systemctl enable --now docker >/dev/null 2>&1 || true

  # Cho tài khoản hiện tại dùng docker mà không cần sudo — nhưng nhóm mới chỉ
  # có hiệu lực ở phiên đăng nhập sau, nên phiên NÀY vẫn phải mượn sudo.
  if [[ $EUID -ne 0 ]]; then
    $SUDO usermod -aG docker "$USER" >/dev/null 2>&1 || true
    info "Đã thêm $USER vào nhóm docker (có hiệu lực từ lần đăng nhập sau)"
  fi
}

check_prereqs() {
  step "Kiểm tra máy"
  local missing=0

  # Ba công cụ cơ bản phải có TRƯỚC, vì chính bước cài Docker cần tới curl.
  # Máy Ubuntu cài mới hay thiếu curl.
  if [[ $DO_CHECK_ONLY -eq 1 ]]; then
    have curl    && ok "curl"    || { fail "Chưa có curl";                        missing=1; }
    have openssl && ok "openssl" || { fail "Chưa có openssl (cần để sinh khoá)";  missing=1; }
    have python3 && ok "python3" || { fail "Chưa có python3 (cần ghi cấu hình)";  missing=1; }
  else
    ensure_tool curl    curl    "cần để tải bộ cài Docker" || missing=1
    ensure_tool openssl openssl "cần để sinh khoá"         || missing=1
    ensure_tool python3 python3 "cần để ghi file cấu hình" || missing=1
  fi

  if ! have docker && [[ $DO_CHECK_ONLY -eq 0 ]]; then
    fail "Chưa có Docker"
    if confirm "Cài Docker ngay bây giờ?" y; then
      install_docker
    fi
  fi

  if have docker; then
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
  else
    fail "Chưa có Docker"
    info "Cài bằng: curl -fsSL https://get.docker.com | sudo sh"
    missing=1
  fi

  if docker compose version >/dev/null 2>&1; then
    ok "Docker Compose $(docker compose version --short 2>/dev/null || echo v2)"
  elif have docker-compose; then
    warn "Đang dùng docker-compose bản cũ (v1) — vẫn chạy được"
  elif have docker && [[ $DO_CHECK_ONLY -eq 0 ]]; then
    fail "Có Docker nhưng thiếu Docker Compose"
    if confirm "Cài Docker Compose ngay?" y; then
      case "$(pkg_manager 2>/dev/null)" in
        apt-get) pkg_install docker-compose-v2 || pkg_install docker-compose-plugin || true ;;
        dnf|yum) pkg_install docker-compose-plugin || true ;;
        *)       pkg_install docker-compose || true ;;
      esac
    fi
    docker compose version >/dev/null 2>&1 || have docker-compose || {
      fail "Vẫn chưa có Docker Compose"; missing=1; }
  else
    fail "Chưa có Docker Compose"
    info "Cài gói docker-compose-plugin, hoặc cài lại Docker theo lệnh ở trên"
    missing=1
  fi

  # Vừa cài Docker xong thì tài khoản hiện tại chưa thuộc nhóm docker cho tới
  # lần đăng nhập sau. Thay vì bắt đăng xuất, phiên này cứ mượn sudo cho gọn.
  if [[ $missing -eq 0 ]] && ! docker info >/dev/null 2>&1; then
    if [[ $EUID -ne 0 ]] && have sudo && sudo docker info >/dev/null 2>&1; then
      DOCKER_SUDO="sudo"
      warn "Phiên này chạy docker qua sudo"
      info "Đăng xuất rồi đăng nhập lại là dùng docker được trực tiếp, không cần sudo"
    else
      fail "Docker đã cài nhưng chưa chạy được"
      info "Thử: sudo systemctl start docker"
      info "Nếu báo permission denied: sudo usermod -aG docker \$USER rồi đăng nhập lại"
      missing=1
    fi
  fi

  # Dung lượng trống
  local free_mb
  free_mb=$(df -Pm "$ROOT" | awk 'NR==2{print $4}')
  if [[ "$free_mb" -lt 2048 ]]; then
    warn "Chỉ còn ${free_mb}MB trống — nên có ít nhất 2GB"
  else
    ok "Còn $((free_mb / 1024))GB trống"
  fi

  [[ $missing -eq 0 ]] || die "Thiếu công cụ bắt buộc. Cài xong rồi chạy lại script."
  ok "Máy đủ điều kiện cài đặt"
}

# Cổng đã có ai chiếm chưa
port_free() {
  local port="$1"
  if have ss; then
    ! ss -lntH "sport = :$port" 2>/dev/null | grep -q .
  elif have lsof; then
    ! lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 0
  fi
}

pick_port() {
  local want="$1" label="$2"
  while ! port_free "$want"; do
    warn "Cổng $want đang bị chiếm ($label)"
    want=$(ask "Chọn cổng khác cho $label" "$((want + 1))")
  done
  printf '%s' "$want"
}

# ---------------------------------------------------------------- tạo .env

write_env() {
  step "Tạo file cấu hình .env"

  if [[ -f "$ENV_FILE" ]]; then
    warn "Đã có file .env"
    if ! confirm "Sao lưu rồi tạo lại?" y; then
      info "Giữ nguyên .env hiện tại"
      return
    fi
    local backup="$ENV_FILE.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$ENV_FILE" "$backup"
    ok "Đã sao lưu sang $(basename "$backup")"
  fi

  cp .env.example "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  # --- khoá ký phiên: luôn sinh mới, không bao giờ hỏi ---
  setenv APP_SECRET_KEY "$(randkey)"
  ok "Đã sinh APP_SECRET_KEY mới (64 byte ngẫu nhiên)"

  # --- cổng ứng dụng ---
  local app_port
  app_port=$(ask "Cổng chạy ứng dụng" "8000")
  app_port=$(pick_port "$app_port" "ứng dụng")
  setenv APP_PORT "$app_port"

  if [[ "$MODE" == "external" ]]; then
    write_env_external
  else
    write_env_bundled "$app_port"
  fi

  # --- email ---
  step "Cấu hình email"
  info "Hệ thống gửi 4 loại thư: phiếu mượn mới, cảnh báo quá hạn,"
  info "báo cáo tuần và báo cáo tháng. Có thể bỏ qua và cấu hình sau."
  if confirm "Cấu hình SMTP ngay?" n; then
    setenv SMTP_ENABLED "true"
    setenv SMTP_HOST "$(ask 'Máy chủ SMTP' 'smtp.gmail.com')"
    setenv SMTP_PORT "$(ask 'Cổng SMTP' '587')"
    setenv SMTP_USERNAME "$(ask 'Tài khoản SMTP')"
    setenv SMTP_PASSWORD "$(ask_secret 'Mật khẩu SMTP')"
    setenv SMTP_USE_TLS "true"
    setenv MAIL_FROM "$(ask 'Tên người gửi hiển thị' 'IT QLTB <no-reply@localhost>')"
    setenv EMAIL_MANAGE "$(ask 'Email nhận báo cáo tuần và tháng')"
    ok "Đã cấu hình SMTP"
  else
    setenv SMTP_ENABLED "false"
    warn "Tắt email. Bật sau bằng cách sửa SMTP_* trong .env rồi khởi động lại."
  fi

  # --- nghiệp vụ ---
  step "Quy tắc nghiệp vụ"
  local overdue
  overdue=$(ask "Sau bao nhiêu ngày chưa trả thì cảnh báo" "10")
  setenv LOAN_OVERDUE_DAYS "$overdue"
  info "Cảnh báo chỉ gửi MỘT lần cho mỗi phiếu, không nhắc lại."

  # --- bảo mật ---
  if confirm "Máy chủ chạy sau HTTPS?" n; then
    setenv COOKIE_SECURE "true"
    ok "Bật COOKIE_SECURE — cookie chỉ gửi qua HTTPS"
  else
    setenv COOKIE_SECURE "false"
    warn "Chạy HTTP thường. Khi có HTTPS, đổi COOKIE_SECURE=true trong .env."
  fi

  # --- tài khoản quản trị đầu tiên ---
  ADMIN_USER=$(ask "Tên đăng nhập quản trị" "admin")
  ADMIN_PASS=$(randpw 16)
  setenv BOOTSTRAP_ADMIN_USER "$ADMIN_USER"
  setenv BOOTSTRAP_ADMIN_PASS "$ADMIN_PASS"

  chmod 600 "$ENV_FILE"
  ok "Đã ghi .env (chỉ chủ sở hữu đọc được)"
}

write_env_bundled() {
  step "Dựng MySQL và MinIO kèm theo"
  info "Máy mới chưa có sẵn database và kho ảnh, script tự dựng cả hai."

  local db_pass root_pass s3_key s3_secret console_port api_port ip
  db_pass=$(randpw 24)
  root_pass=$(randpw 24)
  s3_key="qltb-$(randpw 8)"
  s3_secret=$(randpw 32)
  ip=$(host_ip)

  setenv MYSQL_ROOT_PASSWORD "$root_pass"
  setenv MYSQL_DATABASE "it_qltb"
  setenv MYSQL_USER "qltb"
  setenv MYSQL_PASSWORD "$db_pass"
  # DB_URL cho lúc chạy ngoài Docker; trong Docker thì compose ghi đè bằng host "db"
  setenv DB_URL "mysql+pymysql://qltb:${db_pass}@127.0.0.1:3306/it_qltb?charset=utf8mb4"

  setenv AWS_ACCESS_KEY_ID "$s3_key"
  setenv AWS_SECRET_ACCESS_KEY "$s3_secret"
  # MinIO nhận khoá quản trị qua tên riêng — xem chú thích trong
  # docker-compose.full.yml. Hai cặp này bắt buộc phải trùng nhau.
  setenv MINIO_ROOT_USER "$s3_key"
  setenv MINIO_ROOT_PASSWORD "$s3_secret"
  setenv S3_BUCKET "it-qltb"
  setenv S3_REGION "ap-southeast-1"

  api_port=$(pick_port "9000" "kho ảnh MinIO")
  setenv MINIO_API_PORT "$api_port"
  # Máy chủ gọi kho ảnh qua mạng nội bộ Docker...
  setenv S3_ENDPOINT_URL "http://127.0.0.1:${api_port}"
  # ...còn trình duyệt phải gọi bằng IP thật thì mới tải ảnh lên được.
  # Chữ ký S3 gắn với tên miền nên phải ký sẵn bằng đúng địa chỉ này.
  setenv S3_PUBLIC_ENDPOINT_URL "http://${ip}:${api_port}"
  ok "Trình duyệt sẽ tải ảnh lên http://${ip}:${api_port}"

  console_port=$(pick_port "9001" "bảng điều khiển MinIO")
  setenv MINIO_CONSOLE_PORT "$console_port"

  setenv ALLOW_ORIGINS "*"
  ok "Đã sinh mật khẩu MySQL và khoá MinIO ngẫu nhiên"
}

write_env_external() {
  step "Kết nối tới MySQL có sẵn"
  local host port name user pass
  host=$(ask "Địa chỉ MySQL" "127.0.0.1")
  port=$(ask "Cổng MySQL" "3306")
  name=$(ask "Tên database" "it_qltb")
  user=$(ask "Tài khoản MySQL" "qltb")
  pass=$(ask_secret "Mật khẩu MySQL")

  # Mật khẩu có ký tự đặc biệt phải mã hoá URL, nếu không chuỗi kết nối sẽ vỡ
  local enc
  enc=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$pass")
  setenv DB_URL "mysql+pymysql://${user}:${enc}@${host}:${port}/${name}?charset=utf8mb4"
  ok "Đã ghi chuỗi kết nối MySQL"

  step "Kết nối tới S3 hoặc MinIO có sẵn"
  setenv S3_ENDPOINT_URL "$(ask 'Địa chỉ S3' 'https://s3.example.com')"
  # S3 sẵn có thường đã là địa chỉ công khai, trình duyệt gọi được luôn
  setenv S3_PUBLIC_ENDPOINT_URL ""
  setenv S3_BUCKET "$(ask 'Tên bucket' 'it-qltb')"
  setenv S3_REGION "$(ask 'Vùng' 'ap-southeast-1')"
  setenv AWS_ACCESS_KEY_ID "$(ask 'Access key')"
  setenv AWS_SECRET_ACCESS_KEY "$(ask_secret 'Secret key')"
  setenv ALLOW_ORIGINS "$(ask 'Origin được phép (phân tách bằng dấu phẩy, * là tất cả)' '*')"
  ok "Đã ghi cấu hình S3"
}

# ---------------------------------------------------------------- khởi chạy

start_stack() {
  local file="$1"
  step "Dựng ảnh Docker"
  info "Lần đầu mất vài phút để tải ảnh nền và cài thư viện."
  compose "$file" build --quiet 2>&1 | tail -3 || compose "$file" build
  ok "Đã dựng xong"

  step "Khởi động dịch vụ"
  compose "$file" up -d
  ok "Đã khởi động"
}

wait_healthy() {
  local port="$1" file="${2:-$COMPOSE_FULL}" tries=60
  step "Chờ ứng dụng sẵn sàng"
  while (( tries-- > 0 )); do
    if curl -fsS -m 3 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      ok "Ứng dụng đã trả lời"
      return 0
    fi
    sleep 2
    printf '.'
  done
  printf '\n'
  fail "Ứng dụng không phản hồi sau 2 phút"
  info "Xem log bằng: ${DOCKER_SUDO:+sudo }docker compose -f $file logs -f web"
  return 1
}

verify_db() {
  local port="$1"
  local body
  body=$(curl -fsS -m 5 "http://127.0.0.1:${port}/health" 2>/dev/null || echo '{}')
  if grep -q '"db":true' <<< "$body"; then
    ok "Kết nối cơ sở dữ liệu tốt"
  else
    fail "Không kết nối được cơ sở dữ liệu"
    info "$body"
    return 1
  fi
}

# ---------------------------------------------------------------- kết thúc

print_summary() {
  local port="$1" file="$2"
  local ip; ip=$(host_ip)
  # Nếu phiên này phải mượn sudo thì lệnh gợi ý cho người dùng cũng phải có sudo
  local DC="${DOCKER_SUDO:+sudo }docker compose"

  cat <<SUMMARY

$B$GREEN════════════════════════════════════════════════════════$R
$B  CÀI ĐẶT XONG$R
$B$GREEN════════════════════════════════════════════════════════$R

  Địa chỉ      ${B}http://${ip}:${port}${R}
  Tài khoản    ${B}${ADMIN_USER}${R}
  Mật khẩu     ${B}${ADMIN_PASS}${R}

  ${YELLOW}Đăng nhập rồi đổi mật khẩu ngay ở Thêm → Đổi mật khẩu.${R}
  ${YELLOW}Đổi xong, xoá hai dòng BOOTSTRAP_ADMIN_* khỏi .env.${R}

$B  BƯỚC TIẾP THEO$R

  1. Tạo phòng ban, thêm nhân sự kèm email
  2. Quay lại phòng ban, đặt trưởng bộ phận cho từng phòng
  3. Nạp danh mục thiết bị bằng file Excel mẫu ở tab Thiết bị

  Chi tiết trong docs/CAI-DAT.md

$B  LỆNH HAY DÙNG$R

  Xem log        ${DC} -f ${file} logs -f web
  Khởi động lại  ${DC} -f ${file} restart web
  Dừng           ${DC} -f ${file} down
  Sao lưu        ./scripts/backup.sh
  Kiểm tra       ./scripts/healthcheck.sh

SUMMARY

  if [[ "$file" == "$COMPOSE_FULL" ]]; then
    printf '%s  KHO ẢNH (MinIO)%s\n\n' "$B" "$R"
    printf '  Bảng điều khiển  http://%s:%s\n' "$ip" "$(getenv MINIO_CONSOLE_PORT 9001)"
    printf '  Tài khoản        %s\n' "$(getenv AWS_ACCESS_KEY_ID)"
    printf '  Mật khẩu         %s\n\n' "$(getenv AWS_SECRET_ACCESS_KEY)"
    printf '  %sMáy trạm phải mở được cổng %s thì chụp ảnh mới tải lên được.%s\n\n' \
      "$YELLOW" "$(getenv MINIO_API_PORT 9000)" "$R"
  fi

  # Ghi lại thông tin đăng nhập vào file riêng, quyền 600
  local cred="$ROOT/.admin-credentials.txt"
  cat > "$cred" <<CRED
IT-QLTB — tài khoản quản trị đầu tiên
Tạo lúc: $(date '+%d/%m/%Y %H:%M:%S')

Địa chỉ:   http://${ip}:${port}
Tài khoản: ${ADMIN_USER}
Mật khẩu:  ${ADMIN_PASS}

Đổi mật khẩu ngay sau lần đăng nhập đầu tiên, rồi xoá file này.
CRED
  chmod 600 "$cred"
  info "Thông tin trên cũng được lưu ở .admin-credentials.txt (xoá sau khi đổi mật khẩu)"
}

# ---------------------------------------------------------------- chạy

main() {
  cat <<'BANNER'

  ┌────────────────────────────────────────────┐
  │  IT-QLTB · Quản lý thiết bị phòng IT       │
  │  Script cài đặt cho máy mới                │
  └────────────────────────────────────────────┘
BANNER

  [[ -f .env.example ]] || die "Không thấy .env.example — chạy script từ trong thư mục dự án."

  [[ $DRY_RUN -eq 1 ]] || check_prereqs
  if [[ $DO_CHECK_ONLY -eq 1 ]]; then
    printf '\n%sMáy sẵn sàng. Chạy lại không kèm --check để cài.%s\n\n' "$GREEN" "$R"
    exit 0
  fi

  case "$MODE" in
    quick)    info "Chế độ nhanh: tự sinh mọi thứ, không hỏi." ;;
    external) info "Chế độ nối ngoài: dùng MySQL và S3 có sẵn." ;;
    *)        info "Nhấn Enter để lấy giá trị trong ngoặc vuông." ;;
  esac

  write_env

  # Đọc lại các giá trị vừa ghi. Không `source` file .env: mật khẩu SMTP
  # người dùng nhập có thể chứa $ hoặc dấu nháy, source vào sẽ hỏng.
  ADMIN_USER=$(getenv BOOTSTRAP_ADMIN_USER admin)
  ADMIN_PASS=$(getenv BOOTSTRAP_ADMIN_PASS "")
  local port; port=$(getenv APP_PORT 8000)

  local file="$COMPOSE_FULL"
  [[ "$MODE" == "external" ]] && file="$COMPOSE_APP"

  if [[ $DRY_RUN -eq 1 ]]; then
    step "Chạy thử"
    ok "Đã tạo .env, dừng trước bước dựng Docker (--dry-run)"
    info "Bỏ --dry-run để cài thật bằng: docker compose -f $file up -d"
    exit 0
  fi

  start_stack "$file"
  wait_healthy "$port" "$file"
  verify_db "$port"
  print_summary "$port" "$file"
}

main "$@"
