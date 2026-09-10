"""
Sinh tờ tem QR để dán lên máy.

Mỗi tem in mã máy dạng chữ và cùng mã đó dạng QR. Quét tem bằng nút "Quét mã"
trong bước chọn máy của phiếu mượn là máy nhảy thẳng vào phiếu.

QR chỉ chứa **đúng mã máy** ("LAP-07"), không nhúng địa chỉ máy chủ — đổi IP hay
tên miền về sau thì tem cũ vẫn dùng được. Bộ đọc cũng nhận tem in kèm đường dẫn
(`…?unit=LAP-07`) nếu công ty đã có sẵn tem kiểu đó.

Kết quả là một trang HTML in được thẳng từ trình duyệt, không cần cài thêm gì để
xuất PDF: Ctrl+P là ra.
"""
from __future__ import annotations

from html import escape

import segno

# Khổ tem mặc định: 50 × 30 mm, vừa cạnh laptop và mặt thiết bị nhỏ.
LABEL_W_MM = 50
LABEL_H_MM = 30


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


def _code_pt(longest: int) -> float:
    """Cỡ chữ mã máy, thu lại theo mã dài nhất để không bị cắt mất đuôi số."""
    if longest <= 9:
        return 12.0
    if longest <= 12:
        return 10.0
    if longest <= 15:
        return 8.5
    if longest <= 19:
        return 7.0
    return 6.0


def labels_html(rows: list[tuple[str, str]], *, heading: str) -> str:
    """
    rows: danh sách (mã máy, tên loại).
    """
    qr_mm = LABEL_H_MM - 9
    code_pt = _code_pt(max((len(c) for c, _ in rows), default=8))
    cells = []
    for code, model_name in rows:
        cells.append(
            f'<div class="lb">'
            f'<div class="qr">{qr_svg(code, qr_mm)}</div>'
            f'<div class="tx"><b>{escape(code)}</b>'
            f'<em>{escape(model_name or "")}</em></div>'
            f"</div>"
        )

    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>Tem QR — {escape(heading)}</title>
<style>
  @page {{ size: A4; margin: 8mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: "Segoe UI", Arial, sans-serif; color:#000;
         background:#F3F1EF; }}
  .bar {{ padding:14px 16px; background:#fff; border-bottom:1px solid #DDD8D3;
          display:flex; align-items:center; gap:14px; }}
  .bar h1 {{ margin:0; font-size:17px; font-weight:600; flex:1; }}
  .bar button {{ font:inherit; font-weight:600; border:0; border-radius:9px;
                 background:#FF7506; color:#1A1207; padding:9px 16px; cursor:pointer; }}
  .bar span {{ color:#6E675F; font-size:14px; }}
  .sheet {{ padding:10mm 8mm; display:flex; flex-wrap:wrap; gap:3mm; }}
  .lb {{ width:{LABEL_W_MM}mm; height:{LABEL_H_MM}mm; border:1px dashed #B9B2AA;
         border-radius:2mm; background:#fff; padding:2.5mm;
         display:flex; align-items:center; gap:2mm; overflow:hidden; }}
  .lb .qr {{ flex:0 0 auto; line-height:0; }}
  .lb .tx {{ flex:1; min-width:0; }}
  /* Mã máy KHÔNG được cắt bớt — nó là thứ duy nhất khiến tem có ích.
     Cỡ chữ đã thu theo mã dài nhất, và cho phép xuống dòng nếu vẫn chưa vừa. */
  .lb b {{ display:block; font-family:"Consolas","DejaVu Sans Mono",monospace;
           font-size:{code_pt}pt; font-weight:700; letter-spacing:-.03em;
           line-height:1.15; overflow-wrap:anywhere; }}
  .lb em {{ display:block; font-style:normal; font-size:6.5pt; color:#4A443E;
            line-height:1.2; margin-top:.8mm;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  @media print {{
    body {{ background:#fff; }}
    .bar {{ display:none; }}
    .sheet {{ padding:0; gap:2mm; }}
    .lb {{ border-color:#CFCAC4; break-inside:avoid; }}
  }}
</style></head>
<body>
  <div class="bar">
    <h1>Tem QR · {escape(heading)}</h1>
    <span>{len(rows)} tem · khổ {LABEL_W_MM}×{LABEL_H_MM}mm</span>
    <button onclick="window.print()">In</button>
  </div>
  <div class="sheet">{''.join(cells)}</div>
</body></html>"""
