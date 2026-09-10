# Hướng dẫn sử dụng

Toàn bộ quy tắc nghiệp vụ và cách thao tác. Giao diện được giữ gọn, không chèn
lời giải thích — mọi thứ cần biết nằm ở đây.

Cài đặt và vận hành máy chủ: xem [CAI-DAT.md](CAI-DAT.md).

---

## Mục lục

1. [Nguyên tắc chung](#1-nguyên-tắc-chung)
2. [Thiết bị cho mượn](#2-thiết-bị-cho-mượn)
3. [Nhập danh mục từ Excel](#3-nhập-danh-mục-từ-excel)
   · [Tem QR dán lên máy](#3b-tem-qr-dán-lên-máy)
4. [Cho mượn](#4-cho-mượn)
5. [Nhận trả](#5-nhận-trả)
6. [Quá hạn và email](#6-quá-hạn-và-email)
7. [Bảo trì và máy hỏng](#7-bảo-trì-và-máy-hỏng)
8. [Nhập / Xuất kho hàng bán](#8-nhập--xuất-kho-hàng-bán)
9. [Nhân sự và phòng ban](#9-nhân-sự-và-phòng-ban)
10. [Tài khoản và phân quyền](#10-tài-khoản-và-phân-quyền)
11. [Giao diện](#11-giao-diện)

---

## 1. Nguyên tắc chung

**Quản lý theo từng máy, không theo số lượng.** Hai mươi cái laptop là hai mươi
bản ghi riêng — LAP-01 đến LAP-20 — chứ không phải một dòng "Laptop, số lượng
20". Nhờ vậy mới biết chính xác LAP-17 đang ở chỗ ai và LAP-03 hỏng gì.

Hệ thống chia làm hai kho hoàn toàn tách biệt:

| | Thiết bị | Nhập / Xuất |
|---|---|---|
| Dùng để | Cho nhân sự mượn rồi trả | Mua về để **bán** |
| Theo dõi | Từng máy có mã riêng | Số lượng tồn theo mặt hàng |
| Liên quan nhau | Không. Hai kho độc lập hoàn toàn |

**Bốn trạng thái của một máy:**

| Trạng thái | Nghĩa |
|---|---|
| Sẵn sàng | Đang ở kho, cho mượn được |
| Đang mượn | Nhân sự đang giữ |
| Bảo trì | Đang sửa, không cho mượn được |
| Hỏng | Chờ xử lý, không cho mượn được |

---

## 2. Thiết bị cho mượn

Tab **Thiết bị** liệt kê theo **loại** — tên, mã, hãng, và số máy ở từng trạng
thái. Bấm một dòng để mở chi tiết loại đó: ảnh sản phẩm, thông số chung, và
lưới toàn bộ máy thuộc loại.

Gõ tìm hoặc chọn bộ lọc (Sẵn sàng / Đang mượn / Đang bảo trì / Đang hỏng / Có
ghi chú) thì danh sách đổi sang **từng máy**: mã máy, ai đang giữ, ghi chú tình
trạng. Trên điện thoại vẫn là dạng thẻ, trên máy tính là bảng.

### Thêm máy mới

Nút **Thêm máy mới** có hai chế độ:

- **Loại đã có** — mua bổ sung máy cùng loại. Hệ thống đánh số tiếp theo số
  lớn nhất hiện có. Loại LAP đang có 20 máy, thêm 5 máy nữa sẽ ra LAP-21 đến
  LAP-25.
- **Loại mới** — khai báo tên, mã loại, hãng, thông số, rồi sinh số máy ban đầu.

**Mã loại** là tiền tố của từng máy, chỉ gồm chữ và số, dài 2–12 ký tự. Hệ
thống gợi ý sẵn từ tên nhưng sửa được.

**Thông số chung** áp dụng cho mọi máy thuộc loại đó — mỗi dòng một thông số.

**Ảnh sản phẩm** chụp bằng camera điện thoại hoặc chọn từ máy. Ảnh chỉ hiện khi
mở chi tiết loại thiết bị, không hiện ngoài danh sách.

### Ghi chú tình trạng

Khi nhận trả mà ghi chú có chữ **hư, hỏng, lỗi, gãy, vỡ, bể, nứt, móp, chập,
cháy, đứt, kẹt, rè, xước, trầy, mất, thiếu, yếu, chờn, lỏng, liệt, đơ, treo,
chết**, hệ thống tự gắn **nguyên văn** ghi chú đó lên máy, tô đỏ, kèm thời
điểm ghi nhận và mã phiếu.

Ví dụ trả cuộn quang số 1 với ghi chú "hư sợi 1,3" thì trong tab Thiết bị,
QUANG-01 sẽ mang đúng dòng chữ "hư sợi 1,3" cho tới khi có người xoá.

Hệ thống so khớp **theo từ**, không theo chuỗi con — nên "như", "chưa", "thư",
"nhưng" không bị nhận nhầm là "hư".

Xoá ghi chú: mở máy đó → **Xoá ghi chú tình trạng**. Lần trả sau sạch sẽ, ghi
chú cũ tự mất.

---

## 3b. Tem QR dán lên máy

Cột **QR** trong bảng Thiết bị hiện sẵn mã QR của từng loại. Bấm vào ô QR đó mở
bảng xem lớn, trong đó có hai kiểu in:

| Kiểu tem | Nội dung | Dán ở đâu |
|---|---|---|
| **Tem từng máy** | Mỗi máy một tem mang mã riêng (`LAP-01`, `LAP-02`…) | Dán lên chính máy đó |
| **Một tem mã loại** | Một tem mang mã loại (`LAP`) | Dán lên thùng hoặc kệ chứa cả lô |

Trang tem mở ở thẻ mới, khổ **50 × 30 mm**, bấm **In** hoặc Ctrl+P. In ra giấy
decal A4 rồi cắt theo nét đứt.

QR chỉ chứa đúng mã máy, **không nhúng địa chỉ máy chủ** — sau này đổi IP hay
tên miền thì tem cũ vẫn quét được.

### Camera và địa chỉ http

Trình duyệt chỉ cho mở camera trực tiếp khi trang chạy trên **https**. Hệ thống
chạy trên `http://<máy chủ>:8000` thì nút Quét vẫn dùng được, chỉ khác một nhịp:
nó mở camera chụp một tấm ảnh tem rồi đọc mã từ ảnh đó. Muốn quét liên tục
không phải chụp thì dựng HTTPS cho máy chủ (xem [CAI-DAT.md](CAI-DAT.md)).

Thư viện đọc QR nằm sẵn trong máy chủ, không gọi ra Internet — mạng nội bộ
không ra ngoài được vẫn quét bình thường.

---

## 3. Nhập danh mục từ Excel

Tab **Thiết bị** → **Nhập Excel**. Hai bước: tải file mẫu, điền xong thì chọn
file và bấm nhập.

File có sáu cột, giữ nguyên tên cột ở dòng đầu:

| Cột | Bắt buộc | Nội dung |
|---|---|---|
| `model_code` | Có | Mã loại, 2–12 ký tự chữ và số |
| `model_name` | Có | Tên loại thiết bị |
| `brand` | Không | Hãng sản xuất |
| `quantity` | Không | Số máy sinh ra, để trống là 0 |
| `info` | Không | Thông số chung, xuống dòng được |
| `note` | Không | Ghi chú |

Mỗi dòng là một **loại**. `LAP` với `quantity = 20` tạo LAP-01 đến LAP-20.

**Ba quy tắc:**

| Trường hợp | Hệ thống làm gì |
|---|---|
| Mã loại **đã có** | Cập nhật tên, hãng, thông số, ghi chú. **Không sinh thêm máy** — nhập lại cùng file không làm nhân đôi kho |
| Mã loại **mới** | Tạo loại và sinh đủ số máy theo `quantity` |
| Dòng **lỗi** | Bỏ riêng dòng đó, các dòng còn lại vẫn vào |

Sau khi nhập, hệ thống báo: bao nhiêu loại mới, bao nhiêu loại được cập nhật,
sinh ra mấy máy, và **dòng thứ mấy trong file** bị bỏ qua vì lý do gì.

**Những gì bị chặn:** mã loại để trống, mã có ký tự lạ, số lượng không phải số,
số lượng âm, và số lượng quá 2000 máy trong một dòng. Dòng trống ở cuối file
được bỏ qua, không tính là lỗi.

Nút **Xuất Excel** bên cạnh kết xuất toàn bộ máy kèm người đang giữ và ghi chú
tình trạng — tiện đối chiếu kiểm kê.

---

## 4. Cho mượn

Nút **Tạo phiếu mượn**, ba bước:

1. **Chọn người mượn** — chọn phòng ban trước, rồi chọn nhân sự trong phòng đó.
   Hoặc gõ thẳng tên để tìm nhanh. Cùng bước này chọn **người cho mượn**: ô này
   chỉ liệt kê nhân sự **phòng IT**, vì máy do phòng IT giữ và giao. Mặc định là
   chính tài khoản đang đăng nhập nếu người đó thuộc phòng IT.
2. **Chọn máy** — ba cách, dùng lẫn nhau được:
   * **Quét mã** — nút vuông có góc ngắm cạnh ô nhập mã. Đưa tem QR trên máy vào
     khung, quét xong một máy là thêm ngay rồi quét tiếp máy sau, không phải mở
     lại từng lần. Quét nhầm tem mã loại thì hệ thống mở đúng nhóm đó ra chọn tay.
   * **Gõ mã** — nhập `LAP-07` rồi Enter.
   * **Bấm chọn** — mở từng loại, bấm vào ô máy còn Sẵn sàng.
   Một phiếu chứa được nhiều máy thuộc nhiều loại khác nhau.
3. **Xác nhận** — xem lại rồi tạo. Ở bước này có ô **Ngày mượn**, mặc định là
   hôm nay. Giao máy từ hôm trước mà hôm nay mới nhập thì sửa lại đúng ngày đã
   giao — số ngày quá hạn được đếm từ ngày này, không phải từ lúc bấm nút. Không
   chọn được ngày ở tương lai.

**Phiếu không có hạn trả.** Không phải chọn ngày trả.

Phòng **IT** được hệ thống tạo sẵn ngay lần chạy đầu, không phải tự thêm. Muốn
đổi tên phòng đứng ra cho mượn thì đặt biến `LENDER_DEPARTMENT` trong `.env`.

Máy đang được người khác mượn thì không chọn được. Nếu hai người cùng lập phiếu
cho một máy trong cùng lúc, người sau nhận báo lỗi và phiếu không được tạo —
hệ thống khoá bản ghi từng máy nên không bao giờ có chuyện một máy nằm trong
hai phiếu đang mở.

Tạo phiếu xong, hệ thống gửi **một email xác nhận** tới trưởng bộ phận của
người mượn. Phòng chưa đặt trưởng bộ phận thì thư về địa chỉ quản lý mặc định
(`EMAIL_MANAGE` trong cấu hình).

---

## 5. Nhận trả

Hai đường:

- **Trả cả phiếu** — mở phiếu → **Nhận trả N máy**. Bỏ chọn những máy chưa
  mang về được.
- **Trả nhanh một máy** — bấm thẳng vào một máy đang mượn → **Trả máy này**.
  Phiếu vẫn mở với những máy còn lại.

Mỗi máy trong phiếu trả có **ô ghi chú riêng** và **ba lựa chọn tình trạng**:

| Chọn | Máy về trạng thái | Hệ quả |
|---|---|---|
| Bình thường | Sẵn sàng | Cho mượn tiếp được ngay |
| Cần bảo trì | Bảo trì | Tự sinh một lịch bảo trì dùng đúng ghi chú vừa nhập |
| Hỏng | Hỏng | Vào danh sách máy hỏng |

Cả **Cần bảo trì** và **Hỏng** đều **không** đưa máy về Sẵn sàng.

Ghi chú riêng cho từng máy là chỗ ghi những hỏng hóc cục bộ — ví dụ một cuộn
quang 6 đầu bị hư 2 đầu: ghi "hư sợi 1,3" cho đúng cuộn đó, không ảnh hưởng
các cuộn khác trong cùng phiếu.

Trả hết máy thì phiếu tự chuyển sang **Đã trả**.

---

## 6. Quá hạn và email

Phiếu không đặt hạn trả, nhưng vẫn tính quá hạn theo số ngày đã mượn:

| Số ngày | Trạng thái |
|---|---|
| Dưới 8 ngày | Đang mượn |
| Từ 8 ngày | Sắp quá 10n |
| Từ 10 ngày | **Quá 10n** |

Ngưỡng 10 ngày đổi được bằng `LOAN_OVERDUE_DAYS` trong cấu hình máy chủ.

Khi một phiếu chạm ngưỡng, hệ thống gửi **đúng một** email cảnh báo tới trưởng
bộ phận của người mượn và **không bao giờ nhắc lại** — kể cả phiếu để quên hàng
tháng. Chủ ý là không làm phiền nhân sự.

### Bốn loại thư hệ thống gửi

| Thư | Gửi cho | Tần suất |
|---|---|---|
| Phiếu mượn mới | Trưởng bộ phận của người mượn | 1 lần mỗi phiếu |
| Cảnh báo quá hạn | Trưởng bộ phận của người mượn | **1 lần mỗi phiếu, không lặp** |
| Thiết bị còn đang mượn | Địa chỉ quản lý | Thứ Bảy hàng tuần |
| Lịch sử cho mượn tháng trước | Địa chỉ quản lý | Ngày 1 hàng tháng |

Không có loại thư nào nhắc lại hằng ngày.

Xem thư đã gửi ở **Lịch sử gửi mail** — có tiêu đề, người nhận, thời điểm, và
lý do nếu gửi hỏng.

---

## 7. Bảo trì và máy hỏng

Tab **Bảo trì & hỏng** có ba mục: Đang bảo trì, Đang hỏng, Đã xong.

Đưa một máy vào bảo trì: mở máy đó → **Đưa vào bảo trì**, ghi nội dung cần sửa.
Máy chuyển sang trạng thái Bảo trì và **không cho mượn được** cho tới khi đánh
dấu hoàn tất.

Sửa xong bấm **Hoàn tất** — máy về Sẵn sàng.

Máy nhận trả với tình trạng **Cần bảo trì** tự sinh lịch bảo trì, không phải
tạo tay.

---

## 8. Nhập / Xuất kho hàng bán

Kho này dành cho **hàng hoá kinh doanh** — mua về để bán, hoàn toàn không liên
quan tới thiết bị cho mượn.

Ba mục:

- **Tồn kho** — mỗi mặt hàng một dòng: đã nhập, đã xuất, còn lại. Tồn kho =
  tổng nhập − tổng xuất, tính theo từng cặp *tên sản phẩm + model*.
- **Phiếu nhập** — từng lô hàng mua về, kèm hãng, tình trạng hàng và ảnh.
- **Phiếu xuất** — mỗi lần bán hoặc cấp đi, có mục đích và nơi nhận, trừ thẳng
  vào tồn.

Nhập tay từng phiếu, chụp ảnh sản phẩm được. **Model** dùng để gộp tồn kho, nên
nhập thống nhất giữa các lần — "RT-AX3000" và "RT AX3000" sẽ bị tính thành hai
mặt hàng khác nhau.

Mọi phiếu nhập và xuất đều **ghi lại tài khoản người thực hiện**, xem được
trong chi tiết phiếu.

---

## 9. Nhân sự và phòng ban

Dựng theo đúng thứ tự này, vì bước sau phụ thuộc bước trước:

1. **Phòng ban** — tạo các phòng.
2. **Nhân sự** — thêm người vào phòng. Ai sẽ làm trưởng bộ phận thì **bắt buộc
   có email**.
3. Quay lại **Phòng ban** → mở từng phòng → đặt **trưởng bộ phận**.

Bước 3 quan trọng: chưa đặt trưởng bộ phận thì mọi email của phòng đó rơi về
địa chỉ quản lý chung thay vì đúng người phụ trách.

Danh sách nhân sự đi hai cấp: chọn phòng ban trước rồi mới liệt kê người của
phòng đó. Muốn tìm nhanh thì gõ thẳng tên vào ô tìm kiếm.

Nhân sự **đang giữ máy** không chuyển sang "Đã nghỉ" được — phải nhận trả hết
trước đã.

---

## 10. Tài khoản và phân quyền

**Thêm → Tài khoản & phân quyền** (trên máy tính là mục ở cột trái).

### Tạo tài khoản mới

Nút **Tạo tài khoản** ở góc phải thanh tiêu đề. Điền họ tên, tên đăng nhập
(tối thiểu 5 ký tự, chỉ chữ thường, số và `. _ -`) và mật khẩu (tối thiểu 6
ký tự). Bấm **Sinh giúp tôi** nếu muốn hệ thống tự tạo mật khẩu 14 ký tự —
nhớ chép lại đưa cho nhân sự trước khi đóng hộp thoại, hệ thống không hiện lại
lần nữa.

Chọn quyền ngay trong cùng hộp thoại: bấm một mẫu dựng sẵn rồi tick thêm bớt.

Tài khoản mới luôn là **USER**. Muốn thêm một quản trị viên nữa thì chạy trên
máy chủ:

```bash
python3 scripts/create-admin.py --user <tên> 
```

Đây là chủ ý: vai trò ADMIN không nhận được từ trình duyệt, nên một tài khoản
bị chiếm cũng không tự nâng mình lên quản trị viên.

### 28 quyền

Có 7 nhóm chức năng × 4 thao tác = **28 quyền**:

- Nhóm: Thiết bị, Nhân sự, Phòng ban, Mượn trả, Bảo trì, Nhập/Xuất, Người dùng
- Thao tác mỗi nhóm: Xem, Thêm, Sửa, Xoá

Bốn mẫu dựng sẵn để khỏi tick từng ô:

| Mẫu | Nội dung |
|---|---|
| Toàn quyền | Đủ 28 quyền |
| Nhóm cho mượn | Thiết bị, nhân sự, phòng ban, mượn trả, bảo trì |
| Chỉ xem | Xem được hết, không sửa được gì |
| Bỏ hết | Bắt đầu từ trắng |

Tài khoản **quản trị viên (ADMIN)** luôn có toàn quyền, không cần cấp từng
quyền. Chỉ quản trị viên khác mới sửa hay vô hiệu hoá được tài khoản quản trị.

Vài rào chắn có sẵn: không cấp được quyền mà chính mình không có, không xoá hay
vô hiệu hoá được quản trị viên cuối cùng, và không tự xoá tài khoản của mình.

Giao diện tự ẩn những mục tài khoản không có quyền xem, ngay từ lần vẽ đầu.

Ai cũng tự đổi mật khẩu được ở **Đổi mật khẩu** — tối thiểu 6 ký tự — nên
không cần nhờ quản trị viên đặt lại.

### Nhân sự quên mật khẩu

Không có chức năng tự khôi phục qua email — quản trị viên đặt lại hộ:

1. Vào **Tài khoản & quyền**, bấm vào dòng của người đó.
2. Kéo xuống mục **Mật khẩu**.
3. Bấm **Sinh ngẫu nhiên** (hoặc tự gõ một mật khẩu), rồi **Đặt lại mật khẩu**.
4. Mật khẩu mới hiện ra kèm nút **Sao chép** — gửi cho nhân sự ngay.

Đóng cửa sổ là **không xem lại được**, vì hệ thống chỉ lưu bản băm chứ không
lưu mật khẩu. Quên chép thì đặt lại lần nữa.

Nhắc nhân sự tự đổi lại ở **Đổi mật khẩu** sau khi đăng nhập được.

Quản trị viên quên mật khẩu của chính mình thì chạy trên máy chủ:

```bash
python3 scripts/create-admin.py --user <tên> --reset
```

### Đăng nhập

Ô **Duy trì đăng nhập** ở màn đăng nhập quyết định phiên sống bao lâu trên máy
đó: tick thì giữ 12 giờ, bỏ tick thì đóng trình duyệt là mất — nên bỏ tick khi
đăng nhập trên máy dùng chung ở quầy.

Sai mật khẩu 5 lần liên tiếp thì tài khoản đó bị khoá tạm 5 phút trên máy đang
gõ, tránh dò mật khẩu.

---

## 11. Giao diện

**Trên điện thoại** — điều hướng ở thanh dưới trong tầm ngón cái, danh sách
dạng thẻ, thao tác chính nằm ở nút tròn góc phải, các biểu mẫu trượt lên từ đáy.

**Trên máy tính** (màn hình rộng từ 1024px) — cột điều hướng cố định bên trái
với đủ mọi mục, danh sách chuyển thành bảng nhiều cột có hàng tiêu đề dính khi
cuộn, thao tác chính nằm ở góc phải thanh tiêu đề, biểu mẫu là hộp thoại giữa
màn hình.

Cùng một địa chỉ, cùng một tài khoản — giao diện tự đổi theo bề ngang cửa sổ.

### Giao diện sáng / tối

Nút hình **mặt trăng / mặt trời** ở thanh tiêu đề, cạnh nút thư. Bấm một cái là
đổi, lựa chọn được nhớ lại cho những lần đăng nhập sau trên chính máy đó.

Chưa bấm bao giờ thì hệ thống đi theo thiết lập sáng / tối của máy.

### Lỡ bấm ra ngoài khi đang lập phiếu

Phiếu đang nhập dở mà bấm nhầm ra vùng tối bên ngoài thì bảng **không đóng** —
nó chỉ lắc nhẹ và nhắc. Muốn bỏ thật thì bấm **✕** ở góc, và hệ thống còn hỏi
lại một câu nữa. Áp dụng cho phiếu mượn, nhận trả, thêm máy, phiếu nhập, phiếu
xuất và tạo tài khoản.

### Nút Quay lại của trình duyệt

Nút Quay lại đi ngược trong ứng dụng — về đúng tab vừa xem, không văng ra màn
hình đăng nhập. Địa chỉ trên thanh trình duyệt cũng đổi theo tab đang mở
(`…/#devices`), nên gửi đường dẫn cho đồng nghiệp là họ mở đúng tab đó.

### Nhận diện thương hiệu

Màu chủ đạo là cam **#FF7506** lấy nguyên từ logo Alta Media. Chữ trên nền cam
luôn là màu gần đen, không phải trắng — trắng trên cam chỉ đạt độ tương phản
2.9:1, đọc không nổi ở cỡ chữ nhỏ, còn gần đen đạt 7:1.

Muốn đổi màu hay logo về sau:

| Thay gì | Ở đâu |
|---|---|
| Toàn bộ màu | Khối `:root` đầu file `static/css/app.css` — sửa `--brand` và ba biến `--brand-*` |
| Logo nền sáng | `static/images/logo.png` |
| Logo nền tối (chữ trắng) | `static/images/logo-dark.png` |
| Logo nằm ngang ở cột trái | `static/images/logo-row.png`, `logo-row-dark.png` |
| Dấu hiệu vuông, favicon | `static/images/mark.png`, `favicon.ico`, `apple-touch-icon.png` |

Bốn màu trạng thái thiết bị (xanh lá / xanh dương / vàng đất / đỏ) cố tình giữ
nguyên, không đổi theo thương hiệu — đó là mã màu để đọc trạng thái, đổi đi thì
mất ý nghĩa.

### Thông báo

Mọi thông báo hiện ở **giữa mép trên màn hình** rồi tự tắt sau vài giây. Đặt ở
đó vì đáy màn hình bị bàn phím, thanh điều hướng và chân bảng trượt che mất.

### Dấu hiệu trên màn hình

| Dấu hiệu | Nghĩa |
|---|---|
| Vạch đỏ bên trái dòng | Có vấn đề: phiếu quá hạn, máy có ghi chú hư |
| Vạch vàng bên trái dòng | Cần để ý: sắp quá hạn, đang bảo trì |
| Chấm đỏ góc ô máy | Máy đó có ghi chú tình trạng |
| Số đỏ cạnh "Mượn - Trả" | Số phiếu đang quá hạn |
