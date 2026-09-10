# IT-QLTB — Tài liệu bàn giao

Máy chủ và giao diện, cả hai đã hoàn tất.

## Chạy thử tại máy

```bash
cp .env.example .env          # điền DB_URL, APP_SECRET_KEY, S3, SMTP
python -c "import secrets; print(secrets.token_urlsafe(64))"   # sinh APP_SECRET_KEY

pip install -r requirements.txt
pytest -q                     # 55 test nghiệp vụ
uvicorn app.main:app --reload
```

Docker:

```bash
docker compose up -d --build                                     # chạy thật
docker compose -f docker-compose.yml -f docker-compose.dev.yml up # phát triển
```

---

## Mô hình dữ liệu

Bảng cũ **được giữ nguyên, không xoá** — vẫn tra cứu được lịch sử. Nghiệp vụ mới
chạy trên bộ bảng riêng:

| Bảng | Vai trò |
|---|---|
| `device_models` | LOẠI thiết bị: `LAP` = Laptop Dell Latitude 7420 |
| `device_units` | TỪNG MÁY: `LAP-01` … `LAP-20`, mỗi máy một trạng thái, một người giữ |
| `loan_tickets` | Phiếu mượn, **không có cột hạn trả** |
| `loan_ticket_items` | Từng máy trong phiếu, cờ `returned` riêng |
| `unit_returns` | Nhật ký nhận trả, **một dòng một máy**, có `note` riêng |
| `unit_maintenances` | Lịch bảo trì gắn với một máy |
| `stock_imports` / `stock_exports` | Kho hàng bán, tách hẳn khỏi thiết bị cho mượn |
| `photos` | Ảnh dùng chung, phân biệt bằng `(owner_type, owner_id)` |

Thêm một cột vào bảng cũ: `departments.head_staff_id` — trưởng bộ phận.

`init_db()` tạo bảng còn thiếu và thêm cột theo kiểu thêm-nếu-chưa-có, chạy lại
nhiều lần vẫn an toàn.

### Nhập danh mục lần đầu

Bạn chọn làm mới hoàn toàn, nên bảng `device_models` và `device_units` bắt đầu
rỗng. Hai cách nạp:

1. `GET /api/v2/devices/import-template` tải file mẫu, điền rồi
   `POST /api/v2/devices/import-excel`. Mỗi dòng là một loại, cột `quantity`
   quyết định sinh bao nhiêu máy. Trùng `model_code` thì chỉ cập nhật thông tin,
   không sinh thêm máy.
2. Tạo từng loại qua `POST /api/v2/devices/models`.

---

## Ba quy tắc nghiệp vụ đã cài

**Mỗi máy là một thực thể.** Phiếu mượn trỏ tới `unit_id`, không trỏ tới số
lượng. Luôn biết LAP-20 đang ở chỗ ai, và lịch sử riêng của đúng máy đó.

**Không có hạn trả, tính theo 10 ngày.** `LOAN_OVERDUE_DAYS` trong `.env`. Trạng
thái suy ra từ số ngày đã mượn, không lưu cột trạng thái:

| Số ngày | Trạng thái | Nhãn |
|---|---|---|
| 0–7 | `open` | Đang mượn |
| 8–9 | `soon` | Sắp quá 10n |
| ≥ 10 | `over` | **Quá 10n** |
| đã trả hết | `done` | Đã trả |

`overdue_service` chạy mỗi giờ, gửi cảnh báo cho phiếu quá ngưỡng. Chạy tay:
`POST /api/v2/tickets/run-overdue-sweep`.

**Email đi thẳng tới trưởng bộ phận.** Lấy `departments.head_staff_id` của phòng
người mượn. Chưa đặt trưởng bộ phận thì rơi về `EMAIL_MANAGE`.

---

## Chính sách gửi email

Nguyên tắc: **không làm phiền nhân sự.** Toàn bộ email hệ thống chỉ có bốn loại.

| Thư | Gửi cho | Tần suất |
|---|---|---|
| Phiếu mượn mới | Trưởng bộ phận của người mượn | 1 lần / phiếu |
| Cảnh báo quá 10 ngày | Trưởng bộ phận của người mượn | **1 lần / phiếu, không bao giờ lặp** |
| Báo cáo thiết bị còn đang mượn | `EMAIL_MANAGE` | Thứ Bảy hàng tuần |
| Lịch sử cho mượn tháng trước | `EMAIL_MANAGE` | Ngày 1 hàng tháng |

Cảnh báo quá hạn gửi **đúng một lần cho mỗi phiếu**. Cột `overdue_notified_at`
một khi đã có giá trị là phiếu vĩnh viễn không gửi thêm thư nào, dù còn treo bao
lâu. Bản thân thư cũng nói rõ với người nhận rằng đây là thư duy nhất.

Không nhắc lại không có nghĩa là mất dấu: phiếu vẫn hiển thị **Quá 10n** màu đỏ
trên màn hình Tổng quan và tab Mượn - Trả cho tới khi hoàn trả, và vẫn nằm trong
báo cáo tuần gửi cho quản lý.

Đã **bỏ hẳn** một việc chạy nền của bản cũ: nó gửi thư nhắc quá hạn tới từng
người mượn, lặp lại **mỗi ngày**, chạy trên bảng `loans` cũ. Vừa trùng chức năng
vừa đúng là kiểu spam cần tránh. Biến `LOAN_REMINDER_DAYS` trong `.env` không
còn tác dụng.

Hai báo cáo định kỳ cũng đã được viết lại để đọc từ bảng mới — trước đó chúng
vẫn truy vấn bảng `loans` cũ nên sẽ gửi số liệu sai mỗi tuần.

---

## Trường tình trạng thiết bị

Nhận trả có ghi chú riêng cho **từng máy**. Ghi chú được tách thành từng từ rồi
đối chiếu danh sách từ khoá hư hại trong `app/services/issue_service.py`:

> hư, hỏng, lỗi, gãy, vỡ, bể, nứt, móp, chập, cháy, đứt, kẹt, rè, xước, trầy,
> mất, thiếu, yếu, chờn, lỏng, liệt, đơ, treo, chết

Khớp thì ghi chú được gắn nguyên văn lên `device_units.issue_text`, kèm
`issue_at` và mã phiếu nguồn.

So khớp theo **từ**, không phải chuỗi con — nên `như`, `chưa`, `thư`, `nhưng`
không bị bắt nhầm. Có test cho đúng các trường hợp này.

Ví dụ thực tế: cuộn quang 6 đầu trả về ở tình trạng *Bình thường* với ghi chú
`hư sợi 1,3`. Máy trở lại `AVAIL` nhưng mang cảnh báo, nên không bị cho mượn
tiếp mà người sau không biết. Gỡ cảnh báo:
`POST /api/v2/devices/units/{id}/clear-issue`.

Lần trả sau ghi chú mới đè lên ghi chú cũ; ghi chú sạch thì cảnh báo tự gỡ.

---

## Kho nhập / xuất

Tách hoàn toàn khỏi thiết bị cho mượn: bảng riêng, mã riêng, không ảnh hưởng số
máy sẵn sàng.

- Tồn kho = tổng nhập − tổng xuất, theo cặp `(product_name, model_code)`
- Xuất quá tồn bị chặn ở tầng máy chủ, không chỉ ở giao diện
- Mọi phiếu lưu `created_by_user_id` lấy từ phiên đăng nhập, không tin client
- Mục đích xuất: Bán / Bảo hành / Cấp nội bộ / Trả nhà cung cấp

---

## Bảo mật đã vá

| Vấn đề | Cách xử lý |
|---|---|
| Leo thang đặc quyền qua `PUT /api/users` | Chỉ ADMIN mới chạm được tài khoản ADMIN; không cấp được quyền mình không có; chặn xoá/khoá admin cuối cùng; thêm luồng tự đổi mật khẩu |
| Mượn trùng do không khoá dòng | `SELECT … FOR UPDATE` theo thứ tự id trong `loan_service`; mượn trùng trả 409 |
| Hai đường trả cho kết quả khác nhau | Gộp còn một hàm `return_units` |
| `/media` lỗi 500 mọi lần gọi | Viết lại, chặn path traversal, giới hạn trong hai prefix S3 cho phép |
| Không giới hạn đăng nhập sai | Khoá tạm theo IP + tài khoản, mặc định 5 lần / 5 phút |
| Cookie không bắt buộc HTTPS | `COOKIE_SECURE` trong `.env`, `SameSite=Strict` |
| Secret nằm trong repo | Thêm `.gitignore` và `.env.example` |
| Tạo boto3 client mỗi tấm ảnh | `@lru_cache` trên `s3_client()` |
| Phân quyền đặt xa endpoint | `Depends(require_perm(...))` ngay tại route |
| Mật khẩu tối thiểu 6 ký tự | Nâng lên 10 |

**Việc bạn phải tự làm:** đổi toàn bộ credential đang nằm trong `.env` cũ — mật
khẩu MySQL, key S3, mật khẩu SMTP — và sinh `APP_SECRET_KEY` mới. Khoá cũ ký
cookie phiên nên ai có nó là vào được bằng quyền admin.

---

## Bản đồ API

Tất cả dưới `/api/v2`, đều yêu cầu đăng nhập.

**Thiết bị** `/devices`
`GET|POST /models` · `GET|PUT|DELETE /models/{id}` · `POST /models/{id}/units` ·
`GET /units` (lọc `status`, `has_issue`, `q` tìm cả trong ghi chú tình trạng) ·
`GET|PUT|DELETE /units/{id}` · `POST /units/{id}/clear-issue` ·
`GET /import-template` · `POST /import-excel` · `GET /export`

**Mượn trả** `/tickets`
`GET ?state=open|over|soon|done` · `POST` tạo phiếu ·
`GET /{code}` · `POST /{code}/return` (một hoặc nhiều máy, mỗi máy một ghi chú) ·
`GET /staff/{id}/holding` · `POST /run-overdue-sweep`

**Bảo trì** `/maintenance`
`GET` · `POST` · `GET /broken` · `POST /{id}/complete` · `POST /{id}/cancel` ·
`POST /units/{id}/mark-broken`

**Kho** `/stock`
`GET /levels` · `GET /summary` · `GET|POST /imports` · `GET|POST /exports` ·
`GET /export-excel` · `DELETE /photos/{id}`

**Tổ chức**
`GET|POST /departments` · `PUT|DELETE /departments/{id}` ·
`GET|POST /staff` · `PUT|DELETE /staff/{id}`

**Tài khoản** `/users`
`GET /permission-catalog` · `GET|POST` · `PUT|DELETE /{id}` ·
`POST /me/change-password`

**Khác**
`GET /me` · `GET /dashboard` · `GET /email-logs` ·
`POST /uploads/presign` · `GET /media/{key}`

---

## Kiểm thử

`pytest -q` — 55 test phủ: sinh mã máy, dò từ khoá hư hại (kể cả các trường hợp
dễ bắt nhầm), chặn mượn trùng, trả một phần, ghi chú riêng theo máy, ngưỡng 10
ngày, chỉ gửi cảnh báo quá hạn đúng một lần, trưởng bộ phận nhận email,
bộ 28 quyền, nhập Excel (7 test, có ca ô trống không được thành loại "NAN"),
tạo tài khoản (6 test), đặt lại mật khẩu 6 ký tự (3 test), phòng cho mượn được
tạo sẵn và không nhân đôi (2 test), và ngày mượn — mặc định, lùi ngày, chặn
ngày tương lai (3 test), và tem QR — SVG đứng một mình phải có xmlns, mỗi máy
một tem, chặn người không có quyền xem (5 test).

Ngoài ra có bộ kiểm tra API qua HTTP thật, 46 mục, chạy hết trong quá trình bàn
giao — bao gồm cả các bản vá leo thang đặc quyền.

---

## Giao diện

Ưu tiên thao tác trên điện thoại. Điều hướng ở đáy màn hình trong tầm ngón cái,
thao tác chính đưa vào bảng trượt từ đáy, danh sách dạng thẻ thay cho bảng ngang.
Trên máy tính, ứng dụng giữ một cột giữa rộng 520px.

| Tệp | Nội dung |
|---|---|
| `templates/login.html` | Màn hình đăng nhập, render từ máy chủ |
| `templates/app.html` | Khung ứng dụng, truyền sẵn phiên đăng nhập vào `window.QLTB` |
| `static/css/app.css` | Hệ thống thiết kế: biến màu, sáng/tối, mọi thành phần |
| `static/js/core.js` | Gọi API, kiểm tra quyền, bảng trượt, chụp ảnh, khối HTML dùng lại |
| `static/js/screens.js` | Vẽ 10 màn hình |
| `static/js/flows.js` | Mượn, trả, thêm máy, nhân sự, phòng ban, nhập xuất, phân quyền |
| `static/js/app.js` | Điều hướng và khởi động |

Không dùng thư viện ngoài — chỉ JavaScript thuần, nên không cần bước build.

### Ẩn hiện theo quyền

`app.html` nhúng sẵn quyền của phiên vào `window.QLTB.user.permissions`, nên
giao diện ẩn đúng chức năng ngay từ lần vẽ đầu, không nhấp nháy. Hàm `can()`
trong `core.js` quyết định: mục nào hiện trên thanh dưới, nút tròn có xuất hiện
không, hàng nào bấm được. Đây chỉ là lớp thuận tiện — máy chủ vẫn kiểm tra lại
mọi request bằng `Depends(require_perm(...))`.

### Ảnh chụp

Trình duyệt xin URL đã ký qua `POST /uploads/presign` rồi PUT thẳng lên S3; máy
chủ không trung chuyển byte nào. Trước khi gửi, ảnh được thu về tối đa 1400px và
nén JPEG, nên ảnh 8MB từ điện thoại còn vài trăm KB. Trên điện thoại nút chụp mở
thẳng camera sau nhờ `capture="environment"`.

### Sáng và tối

Toàn bộ màu khai báo bằng biến CSS ở `:root`, có bộ biến riêng cho
`prefers-color-scheme: dark`. Giao diện tự đổi theo cài đặt máy, không cần nút.

---

## Kiểm thử

| Bộ | Số mục | Phủ những gì |
|---|---|---|
| `pytest -q` | 29 | Sinh mã máy, dò từ khoá hư hại, chặn mượn trùng, trả một phần, ghi chú riêng theo máy, ngưỡng quá hạn, chỉ gửi cảnh báo một lần, 28 quyền |
| Kiểm tra API qua HTTP | 46 | Đăng nhập, phân quyền, mượn trả, kho, và các bản vá leo thang đặc quyền |
| Kiểm tra giao diện qua trình duyệt | 29 | Cả 5 luồng thao tác chính trên màn hình 430px, không lỗi runtime |
