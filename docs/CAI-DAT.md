# Hướng dẫn triển khai

Tài liệu này nói về **cài đặt và vận hành máy chủ**. Cách dùng phần mềm hằng
ngày — quy tắc mượn trả, quá hạn, phân quyền — nằm ở
[HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md).

Hai đường: **cài nhanh bằng script** cho máy mới tinh, hoặc **cài thủ công**
khi công ty đã có sẵn MySQL và S3 riêng. Chọn một.

---

# A. Cài nhanh trên máy mới

Dành cho một máy Linux trắng, chưa có gì. Script tự lo MySQL, kho ảnh, mật
khẩu, khoá ký phiên và tài khoản quản trị đầu tiên.

```bash
cd it_qltb
./scripts/setup.sh
```

Script hỏi 6 câu (cổng, SMTP, số ngày quá hạn, HTTPS, tên tài khoản admin),
mọi thứ còn lại tự sinh. Chạy xong nó in địa chỉ và mật khẩu admin ra màn hình.

Các chế độ khác:

| Lệnh | Dùng khi |
|---|---|
| `./scripts/setup.sh` | Máy mới, cài trọn gói, có hỏi từng bước |
| `./scripts/setup.sh --quick` | Cài trọn gói, không hỏi gì, tự sinh hết |
| `./scripts/setup.sh --external` | Công ty đã có MySQL và S3 riêng |
| `./scripts/setup.sh --check` | Chỉ xem máy đủ điều kiện chưa |
| `./scripts/setup.sh --dry-run` | Chỉ tạo `.env`, chưa dựng Docker |

Máy trắng thiếu `curl`, `openssl`, `python3` hay Docker thì script hỏi và cài
giúp bằng trình quản lý gói của máy (apt, dnf, yum, zypper, pacman, apk). Cần
nhập mật khẩu `sudo` một lần ở đầu.

Vừa cài Docker xong, tài khoản hiện tại chưa thuộc nhóm `docker` cho tới lần
đăng nhập sau — script biết điều đó và tự chạy docker qua `sudo` cho phiên
này, không bắt anh đăng xuất giữa chừng. Lần đăng nhập sau thì dùng thẳng.

Máy không ra được Internet thì cài tay trước rồi chạy lại script:

```bash
sudo apt update && sudo apt install -y curl openssl python3 docker.io docker-compose-v2
```

## Script tự sinh những gì

| Giá trị | Cách sinh |
|---|---|
| `APP_SECRET_KEY` | 48 byte ngẫu nhiên — luôn mới, không bao giờ hỏi |
| Mật khẩu MySQL (`root` và `qltb`) | 24 ký tự ngẫu nhiên |
| Khoá MinIO | 32 ký tự ngẫu nhiên |
| Mật khẩu admin đầu tiên | 16 ký tự ngẫu nhiên |

`.env` và `.admin-credentials.txt` được đặt quyền `600`, chỉ chủ máy đọc được.
Xoá `.admin-credentials.txt` sau khi đã đổi mật khẩu.

Cổng bị chiếm thì script phát hiện và hỏi đổi sang cổng khác.

## Ba script đi kèm

```bash
./scripts/healthcheck.sh     # kiểm tra hệ thống, đếm đạt / cảnh báo / lỗi
./scripts/backup.sh          # dump database + ảnh + cấu hình vào ./backups
python3 scripts/create-admin.py --user admin --reset   # quên mật khẩu admin
```

Nên đặt `backup.sh` vào cron chạy hằng đêm:

```
0 2 * * * cd /opt/it-qltb && ./scripts/backup.sh >> /var/log/qltb-backup.log 2>&1
```

## Một điểm dễ vướng: ảnh chụp từ máy trạm

Trình duyệt tải ảnh **thẳng** lên kho ảnh, không đi qua máy chủ ứng dụng. Nên
máy trạm phải mở được cổng `9000` của máy chủ. Script đã ghi sẵn địa chỉ IP
thật vào `S3_PUBLIC_ENDPOINT_URL`. Nếu đổi IP máy chủ, sửa lại dòng đó rồi:

```bash
docker compose -f docker-compose.full.yml restart web
```

Cài xong thì bỏ qua phần B, đi thẳng tới **mục 4** trở xuống (nạp thiết bị,
dựng phòng ban, tạo tài khoản).

---

# B. Cài thủ công

Các bước theo đúng thứ tự. Đọc hết trước khi chạy bước đầu tiên.

## 1. Đổi toàn bộ mật khẩu cũ (bắt buộc, làm trước tiên)

File `.env` của bản cũ đã lộ theo mã nguồn. Phải đổi hết trước khi chạy:

- Mật khẩu MySQL của tài khoản `it_alta`
- Access key và secret của S3
- Mật khẩu hộp thư SMTP
- `APP_SECRET_KEY` — khoá này ký cookie phiên, ai có nó là đăng nhập được
  bằng quyền admin mà không cần mật khẩu

Sinh khoá mới:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 2. Tạo file .env

```bash
cp .env.example .env
```

Điền các giá trị mới. Ba biến cần chú ý:

| Biến | Ý nghĩa |
|---|---|
| `LOAN_OVERDUE_DAYS` | Số ngày trước khi phiếu bị coi là quá hạn. Mặc định 10 |
| `COOKIE_SECURE` | Đặt `true` khi chạy sau HTTPS |
| `EMAIL_MANAGE` | Địa chỉ nhận báo cáo tuần và tháng |
| `S3_PUBLIC_ENDPOINT_URL` | Chỉ điền khi trình duyệt gọi kho ảnh bằng địa chỉ khác máy chủ |
| `LENDER_DEPARTMENT` | Phòng đứng tên cho mượn, tạo sẵn lúc khởi động. Mặc định `IT` |

Giá trị có khoảng trắng hoặc dấu `#`, `<`, `>` phải bọc trong nháy đơn, ví dụ
`MAIL_FROM='IT QLTB <no-reply@alta.com.vn>'`.

`.env` đã nằm trong `.gitignore`, không commit lên Git.

## 3. Chạy thử trước khi đụng vào cơ sở dữ liệu thật

Trỏ `DB_URL` sang một bản sao của database, rồi:

```bash
pip install -r requirements.txt
pytest -q                       # 55 test, phải xanh hết
uvicorn app.main:app --reload
```

Mở `http://localhost:8000`, đăng nhập bằng `BOOTSTRAP_ADMIN_USER`.

## 4. Nạp danh mục thiết bị

Bảng thiết bị bắt đầu rỗng vì ta làm mới hoàn toàn. Bảng cũ giữ nguyên để tra
cứu lịch sử.

Vào tab **Thiết bị** → nút **Nhập Excel**: tải file mẫu, điền, rồi nhập lên.
Mỗi dòng là một LOẠI thiết bị, cột `quantity` quyết định sinh bao nhiêu máy.

Chi tiết cột, quy tắc cập nhật và các trường hợp bị chặn: xem
[HUONG-DAN-SU-DUNG.md § 3](HUONG-DAN-SU-DUNG.md#3-nhập-danh-mục-từ-excel).

## 5. Dựng cơ cấu tổ chức

Theo thứ tự này, vì bước sau phụ thuộc bước trước:

1. **Phòng ban** — tạo các phòng (phòng `IT` đã có sẵn, không phải tạo lại)
2. **Nhân sự** — thêm người, mỗi người phải có email nếu sẽ làm trưởng bộ phận
3. Quay lại **Phòng ban**, mở từng phòng và đặt **trưởng bộ phận**

Bước 3 quan trọng: chưa đặt trưởng bộ phận thì email thông báo rơi về địa chỉ
`EMAIL_MANAGE` thay vì đúng người phụ trách.

## 6. Tài khoản cho nhân viên

Tab **Thêm → Tài khoản & phân quyền**. Có 4 mẫu quyền dựng sẵn:

- **Toàn quyền** — đủ 28 quyền
- **Nhóm cho mượn** — thiết bị, nhân sự, phòng ban, mượn trả, bảo trì
- **Chỉ xem** — xem hết nhưng không sửa được gì
- **Bỏ hết** — bắt đầu từ trắng rồi tick từng quyền

Tài khoản thường tự đổi mật khẩu được ở **Thêm → Đổi mật khẩu**, nên không ai
cần quyền `users.update` chỉ để nhờ đặt lại mật khẩu.

## 7. Chạy thật

Đã có MySQL và S3 riêng:

```bash
docker compose up -d --build
```

Chưa có gì, muốn Docker dựng luôn MySQL và MinIO:

```bash
docker compose -f docker-compose.full.yml up -d --build
```

Kiểm tra `docker compose logs -f web` không có lỗi, rồi mở
`http://<máy chủ>:8000`. Chạy `./scripts/healthcheck.sh` để soát lại một lượt.

Sau khi đăng nhập lần đầu và đổi mật khẩu admin, **xoá hai dòng**
`BOOTSTRAP_ADMIN_USER` và `BOOTSTRAP_ADMIN_PASS` khỏi `.env`.

---

## Lưu ý vận hành

**Chỉ chạy một worker.** Việc gửi báo cáo và rà phiếu quá hạn chạy trong tiến
trình web. Nhiều worker sẽ có nguy cơ gửi trùng email. `docker-compose.yml` đã
đặt sẵn `--workers 1`.

**Email gửi rất ít.** Bốn loại, không có loại nào lặp lại hằng ngày:

| Thư | Gửi cho | Tần suất |
|---|---|---|
| Phiếu mượn mới | Trưởng bộ phận của người mượn | 1 lần / phiếu |
| Cảnh báo quá hạn | Trưởng bộ phận của người mượn | 1 lần / phiếu, không lặp |
| Báo cáo thiết bị còn đang mượn | `EMAIL_MANAGE` | Thứ Bảy hàng tuần |
| Lịch sử cho mượn tháng trước | `EMAIL_MANAGE` | Ngày 1 hàng tháng |

Muốn thử ngay không cần đợi lịch: `POST /api/v2/tickets/run-overdue-sweep`.

**Sao lưu.** Trước mỗi lần nâng cấp:

```bash
./scripts/backup.sh
```

Script tự nhận biết MySQL nằm trong Docker hay ở máy khác, dump database, chép
`.env`, đóng gói ảnh trong MinIO, rồi xoá bản sao lưu cũ hơn 30 ngày.

**Ảnh.** Lưu trên S3, database chỉ giữ object key. Sao lưu database không kèm
ảnh — cần sao lưu bucket riêng.
