"""
Sinh tờ tem QR để dán lên thiết bị.

Khổ giấy đang dùng: **decal 2 tem, khổ 98mm, mỗi tem 50 × 30 mm**, in trên
**Godex Z530**. Mỗi lần đẩy giấy ra đúng một hàng, tức là **2 tem**.

Vì vậy trang in được dựng theo đúng một hàng = một trang giấy:

    @page { size: 98mm 30mm; margin: 0 }

Mỗi hàng có hai ô tem nằm sát nhau, mỗi ô 49mm (49 × 2 = 98). Lề trong ô để
rộng 2,5mm nên giấy chạy lệch một chút vẫn không cắt vào QR hay chữ.

Trên mỗi tem:

* **QR mang MÃ thiết bị** — chỉ để máy quét đọc khi lập phiếu mượn.
* **Chữ duy nhất trên tem là TÊN thiết bị** — người đọc bằng mắt chỉ cần biết
  đó là máy gì; mã đã nằm trong QR nên không in lại, dành hết chỗ cho cái tên.

QR chỉ chứa đúng mã, **không nhúng địa chỉ máy chủ** — đổi IP hay tên miền về
sau thì tem cũ vẫn dùng được.
"""
from __future__ import annotations

from html import escape

import segno

# Khổ giấy đang dùng. Đổi giấy thì sửa ba con số này là xong.
PAPER_W_MM = 98.0        # bề ngang cả tờ decal
LABEL_W_MM = 49.0        # một ô tem — hai ô vừa khít 98mm
LABEL_H_MM = 30.0
PER_ROW = 2              # mỗi lần đẩy giấy ra hai tem

PRINTER = "Godex Z530"


def qr_svg(text: str, size_mm: float | None = None) -> str:
    """
    QR dạng SVG. Nhúng thẳng vào trang nên in ra sắc nét ở mọi cỡ giấy.

    size_mm=None thì để SVG tự co theo khung chứa — dùng cho ô xem trước
    trên giao diện; có size_mm thì khoá cứng bằng milimét để in đúng khổ tem.
    """
    qr = segno.make(text, error="m")
    svg = qr.svg_inline(
        scale=4,
        border=0,
        svgclass=None,
        lineclass=None,
        omitsize=True,
        # đen trắng thuần để máy in nhiệt lẫn máy in laser đều đọc tốt
        dark="#000000",
        light=None,
    )
    box = (f'width="{size_mm}mm" height="{size_mm}mm"' if size_mm
           else 'width="100%" height="100%"')
    # xmlns bắt buộc phải có: nhúng trong HTML thì trình duyệt tự đoán được,
    # nhưng tải qua <img src="…svg"> mà thiếu nó là ảnh hỏng.
    return svg.replace("<svg", f'<svg xmlns="http://www.w3.org/2000/svg" {box}', 1)


def _name_fit(longest: int) -> tuple[float, int, float]:
    """
    Chọn cỡ chữ, số dòng và cỡ QR theo TÊN dài nhất trong lô.

    Tên càng dài thì chữ nhỏ lại, cho phép xuống nhiều dòng hơn, và QR thu bớt
    để nhường chỗ ngang. QR 18mm ở 300dpi vẫn thừa sức chứa một mã thiết bị.

    Trả về (cỡ chữ pt, số dòng tối đa, cạnh QR mm).
    """
    if longest <= 14:
        return 10.0, 3, 23.0
    if longest <= 22:
        return 9.0, 4, 23.0
    if longest <= 32:
        return 8.0, 4, 21.0
    if longest <= 46:
        return 7.0, 5, 19.0
    return 6.0, 6, 18.0


def _blank_cell() -> str:
    """Ô trống bù vào hàng lẻ — giữ tem còn lại đúng vị trí bên trái."""
    return '<div class="lb blank"></div>'


def _cell(code: str, name: str, qr_mm: float) -> str:
    # title= để lúc xem trước trên màn hình rê chuột vẫn biết tem này của máy nào
    return (
        f'<div class="lb" title="{escape(code)}">'
        f'<div class="qr">{qr_svg(code, qr_mm)}</div>'
        f'<div class="tx"><b>{escape(name or code)}</b></div>'
        "</div>"
    )


def labels_html(rows: list[tuple[str, str]], *, heading: str,
                warn_continuous: bool = False) -> str:
    """
    rows: danh sách (mã thiết bị, tên thiết bị) — mỗi phần tử là MỘT tem.

    warn_continuous=True thì trang hiện cảnh báo in liên tục và bắt bấm xác
    nhận trước khi mở hộp thoại in.
    """
    name_pt, name_lines, qr_mm = _name_fit(max((len(n or c) for c, n in rows), default=12))

    # Xếp thành từng hàng đúng bằng một lần đẩy giấy
    chunks = [rows[i:i + PER_ROW] for i in range(0, len(rows), PER_ROW)]
    sheet = "".join(
        '<div class="row">'
        + "".join(_cell(code, name, qr_mm) for code, name in chunk)
        + _blank_cell() * (PER_ROW - len(chunk))
        + "</div>"
        for chunk in chunks
    )

    n = len(rows)
    feeds = len(chunks)
    length_cm = feeds * LABEL_H_MM / 10

    confirm = ""
    if warn_continuous:
        confirm = f"""
    <div class="warn">
      <b>In liên tục {n} tem</b>
      Máy sẽ chạy hết {feeds} lần đẩy giấy, khoảng {length_cm:.0f}cm decal, không
      dừng giữa chừng. Kiểm tra giấy trong máy đủ chưa rồi hãy bấm In.
      <label><input type="checkbox" id="ok"> Đã kiểm tra giấy, cho in liên tục</label>
    </div>"""

    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>Tem QR — {escape(heading)}</title>
<style>
  /* Một trang giấy = một hàng = một lần đẩy = {PER_ROW} tem */
  @page {{ size: {PAPER_W_MM}mm {LABEL_H_MM}mm; margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:"Segoe UI",Arial,sans-serif; color:#000; background:#F3F1EF; }}

  .bar {{ position:sticky; top:0; z-index:2; padding:13px 16px; background:#fff;
          border-bottom:1px solid #DDD8D3; display:flex; align-items:center; gap:14px;
          flex-wrap:wrap; }}
  .bar h1 {{ margin:0; font-size:17px; font-weight:600; }}
  .bar .meta {{ flex:1; min-width:220px; color:#6E675F; font-size:13.5px; line-height:1.5; }}
  .bar button {{ font:inherit; font-weight:600; border:0; border-radius:9px;
                 background:#FF7506; color:#1A1207; padding:10px 20px; cursor:pointer; }}
  .bar button[disabled] {{ background:#E4DED8; color:#9A938C; cursor:not-allowed; }}
  .warn {{ margin:0; padding:13px 16px; background:#FFF1E4; border-bottom:1px solid #FFCB9A;
           color:#8A3E00; font-size:14px; line-height:1.55; }}
  .warn b {{ display:block; font-size:15px; margin-bottom:3px; }}
  .warn label {{ display:flex; align-items:center; gap:8px; margin-top:9px;
                 font-weight:600; cursor:pointer; }}

  .sheet {{ padding:8mm; }}
  .row {{ width:{PAPER_W_MM}mm; height:{LABEL_H_MM}mm; display:flex; margin:0 auto 2mm;
          background:#fff; }}
  .lb {{ width:{LABEL_W_MM}mm; height:{LABEL_H_MM}mm; padding:2.5mm 2mm;
         display:flex; align-items:center; gap:1.8mm; overflow:hidden;
         border:1px dashed #C4BDB6; }}
  .lb.blank {{ border-style:dotted; border-color:#E2DCD6; }}
  .lb .qr {{ flex:0 0 auto; line-height:0; }}
  .lb .tx {{ flex:1; min-width:0; }}
  /* TÊN thiết bị là chữ duy nhất trên tem — dùng hết chỗ còn lại */
  .lb b {{ display:-webkit-box; -webkit-line-clamp:{name_lines}; -webkit-box-orient:vertical;
           overflow:hidden; font-size:{name_pt}pt; font-weight:700; line-height:1.22;
           letter-spacing:-.01em; overflow-wrap:anywhere; }}

  @media print {{
    body {{ background:#fff; }}
    .bar, .warn {{ display:none !important; }}
    .sheet {{ padding:0; }}
    /* Mỗi hàng ra đúng một trang giấy, không có lề, không có viền cắt */
    .row {{ margin:0; break-after:page; page-break-after:always; }}
    .row:last-child {{ break-after:auto; page-break-after:auto; }}
    .lb {{ border:0; }}
  }}
</style></head>
<body>
  <div class="bar">
    <h1>Tem QR · {escape(heading)}</h1>
    <div class="meta">
      {n} tem · {feeds} lần đẩy giấy · decal 2 tem khổ {PAPER_W_MM:.0f}mm
      ({LABEL_W_MM:.0f} × {LABEL_H_MM:.0f}mm) · máy in {PRINTER}<br>
      Trong hộp thoại in: khổ giấy <b>{PAPER_W_MM:.0f} × {LABEL_H_MM:.0f}mm</b>,
      lề <b>0</b>, tỉ lệ <b>100%</b>, tắt đầu trang / chân trang.
    </div>
    <button id="go" {'disabled' if warn_continuous else ''}>In {n} tem</button>
  </div>{confirm}
  <div class="sheet">{sheet}</div>
<script>
  (function () {{
    var go = document.getElementById('go');
    var ok = document.getElementById('ok');
    if (ok) ok.addEventListener('change', function () {{ go.disabled = !ok.checked; }});
    go.addEventListener('click', function () {{ window.print(); }});
  }})();
</script>
</body></html>"""
