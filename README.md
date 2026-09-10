# IT-QLTB — Quản lý thiết bị phòng IT

Theo dõi **từng máy một**, không theo số lượng. Laptop số 20 đang ở chỗ ai,
cuộn quang số 3 hư sợi nào — mỗi thứ có một mã riêng và một lịch sử riêng.

## Cài trên máy mới

```bash
./scripts/setup.sh
```

Script tự dựng MySQL, kho ảnh, sinh mật khẩu, tạo tài khoản quản trị đầu tiên
rồi in địa chỉ đăng nhập ra màn hình. Chưa có Docker thì nó hỏi và cài giúp.

Đã có sẵn MySQL và S3 của công ty: `./scripts/setup.sh --external`

Chi tiết và cách cài thủ công: [docs/CAI-DAT.md](docs/CAI-DAT.md)

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [HUONG-DAN-SU-DUNG.md](docs/HUONG-DAN-SU-DUNG.md) | Cách dùng hằng ngày: mượn trả, nhập Excel, quá hạn, phân quyền |
| [CAI-DAT.md](docs/CAI-DAT.md) | Cài đặt, cấu hình, sao lưu, vận hành máy chủ |
| [BACKEND.md](docs/BACKEND.md) | Ghi chú kỹ thuật: mô hình dữ liệu, API, quyết định thiết kế |

Giao diện cố tình không chèn lời giải thích — mọi quy tắc nghiệp vụ nằm trong
bản hướng dẫn sử dụng.

## Hệ thống làm gì

| Phần | Nội dung |
|---|---|
| **Thiết bị** | Loại thiết bị → từng máy đánh số. Máy hỏng có ghi chú nguyên văn kèm thời điểm |
| **Mượn / trả** | Một phiếu nhiều máy. Không có hạn trả, quá 10 ngày thì cảnh báo |
| **Trả từng máy** | Bấm một máy là trả riêng máy đó, có ô ghi chú riêng cho từng máy |
| **Nhập / xuất** | Hàng mua về để BÁN, tách hẳn khỏi kho cho mượn. Ghi rõ ai nhập, ai xuất |
| **Tem QR** | Mỗi máy một mã QR in được, quét vào là máy nhảy thẳng vào phiếu mượn |
| **Bảo trì** | Máy hỏng chuyển sang bảo trì, xong thì quay lại kho |
| **Nhân sự** | Phòng ban → nhân viên. Mỗi phòng có một trưởng bộ phận nhận email |
| **Phân quyền** | 7 nhóm × 4 thao tác = 28 quyền, giao diện tự ẩn phần không có quyền |

## Email

Bốn loại, không loại nào lặp lại hằng ngày:

| Thư | Gửi cho | Tần suất |
|---|---|---|
| Phiếu mượn mới | Trưởng bộ phận của người mượn | 1 lần / phiếu |
| Cảnh báo quá hạn | Trưởng bộ phận của người mượn | **1 lần / phiếu, không bao giờ nhắc lại** |
| Thiết bị còn đang mượn | `EMAIL_MANAGE` | Thứ Bảy hàng tuần |
| Lịch sử cho mượn tháng trước | `EMAIL_MANAGE` | Ngày 1 hàng tháng |

## Lệnh hay dùng

```bash
./scripts/healthcheck.sh                              # soát lại hệ thống
./scripts/backup.sh                                   # sao lưu database + ảnh
python3 scripts/create-admin.py --user admin --reset  # quên mật khẩu admin
pytest -q                                             # 55 test
```

## Kiến trúc

FastAPI + SQLAlchemy 2.0 + MySQL 8, giao diện Jinja2 và JavaScript thuần —
không framework, không bước build. Ảnh nằm trên S3/MinIO, trình duyệt tải
thẳng lên bằng URL đã ký.

Ghi chú kỹ thuật: [docs/BACKEND.md](docs/BACKEND.md)
