/* =============================================================
   Lõi dùng chung: gọi API, kiểm tra quyền, bảng trượt, ảnh chụp.
   Mọi file khác dựa trên các hàm trong đây.
   ============================================================= */
'use strict';

const API = '/api/v2';
const ME = window.QLTB.user;
const OVERDUE_DAYS = window.QLTB.overdueDays;
/** Phòng đứng ra cho mượn — máy chủ tạo sẵn phòng này lúc khởi động. */
const LENDER_DEPT = (window.QLTB.lenderDepartment || 'IT');

/** Nhân sự này có thuộc phòng cho mượn không (không phân biệt hoa thường). */
function isLenderStaff(s) {
  return String(s.department_name || '').trim().toLowerCase()
    === LENDER_DEPT.trim().toLowerCase();
}

/* ---------------------------------------------------------------- tiện ích */

const $ = (id) => document.getElementById(id);

/* ---------------------------------------------------------------- giao diện sáng / tối */

const ICON_SUN = '<circle cx="12" cy="12" r="4.2"/>'
  + '<path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6'
  + 'M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6"/>';
const ICON_MOON = '<path d="M20.5 14.4A8.6 8.6 0 019.6 3.5a8.6 8.6 0 1010.9 10.9z"/>';

/** Chủ đề đang áp dụng thật sự, kể cả khi đang để theo máy. */
function currentTheme() {
  const set = document.documentElement.dataset.theme;
  if (set === 'dark' || set === 'light') return set;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Vẽ lại biểu tượng: đang sáng thì hiện mặt trăng (bấm để tối) và ngược lại. */
function paintThemeButton() {
  const icon = $('themeIcon');
  if (!icon) return;
  const dark = currentTheme() === 'dark';
  icon.innerHTML = dark ? ICON_SUN : ICON_MOON;
  $('themeBtn').setAttribute('aria-label',
    dark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối');
}

function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('qltb-theme', next); } catch (e) { /* bỏ qua */ }
  paintThemeButton();
  toast(next === 'dark' ? 'Đã bật giao diện tối' : 'Đã bật giao diện sáng');
}

/** Hôm nay theo giờ máy người dùng, dạng YYYY-MM-DD để đổ vào <input type="date">. */
function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/**
 * Đổi YYYY-MM-DD thành mốc thời gian gửi cho máy chủ.
 *
 * Chọn đúng hôm nay thì trả về null để máy chủ lấy giờ thật lúc lập phiếu.
 * Chọn ngày khác thì lấy 12 giờ trưa — nửa ngày cách xa cả hai mốc nửa đêm,
 * nên dù máy chủ và máy trạm lệch múi giờ, ngày hiện ra vẫn đúng ngày đã chọn.
 */
function isoAtNoonUTC(ymd) {
  if (!ymd || ymd === todayISO()) return null;
  const [y, m, d] = ymd.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(Date.UTC(y, m - 1, d, 12, 0, 0)).toISOString();
}

/** Chặn XSS: mọi dữ liệu người dùng nhập đều phải đi qua đây trước khi ghép chuỗi HTML. */
function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

const initials = (name) =>
  String(name || '?').trim().split(/\s+/).slice(-2).map((w) => w[0]).join('').toUpperCase();

const shortName = (name) => String(name || '').trim().split(/\s+/).pop() || '';

function deptInitials(name) {
  const words = String(name || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().split(/\s+/);
  return (words.length > 1 ? words.slice(0, 2).map((w) => w[0]).join('') : words[0].slice(0, 2))
    .toUpperCase();
}

/** Ngày giờ từ máy chủ về dạng ISO không có múi giờ — coi là UTC. */
function parseServerDate(value) {
  if (!value) return null;
  const s = String(value);
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z';
  const d = new Date(iso);
  return isNaN(d) ? null : d;
}

function fmtDate(value) {
  const d = parseServerDate(value);
  if (!d) return '—';
  return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function fmtDateTime(value) {
  const d = parseServerDate(value);
  if (!d) return '—';
  const time = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${fmtDate(value)} ${time}`;
}

function greeting() {
  const h = new Date().getHours();
  if (h < 11) return 'Chào buổi sáng';
  if (h < 14) return 'Chào buổi trưa';
  if (h < 18) return 'Chào buổi chiều';
  return 'Chào buổi tối';
}

/* ---------------------------------------------------------------- quyền */

const IS_ADMIN = String(ME.role || '').toUpperCase() === 'ADMIN';
const PERMS = new Set(ME.permissions || []);

/** ADMIN đi qua tất cả; ngoài ra chỉ cần MỘT trong các quyền liệt kê. */
function can(...names) {
  if (IS_ADMIN) return true;
  return names.some((n) => PERMS.has(n));
}

/* ---------------------------------------------------------------- gọi API */

class ApiError extends Error {
  constructor(status, detail) {
    super(detail || 'Yêu cầu thất bại');
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, options = {}) {
  const opts = { credentials: 'same-origin', headers: {}, ...options };
  if (opts.body !== undefined && !(opts.body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }

  let res;
  try {
    res = await fetch(path.startsWith('/') ? path : `${API}/${path}`, opts);
  } catch (_) {
    throw new ApiError(0, 'Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.');
  }

  if (res.status === 401) {
    window.location.href = '/login';
    throw new ApiError(401, 'Phiên đăng nhập đã hết hạn');
  }
  if (res.status === 204) return null;

  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }

  if (!res.ok) {
    const detail = (data && typeof data === 'object' && data.detail) ||
      (typeof data === 'string' && data) || `Lỗi ${res.status}`;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

const apiGet = (path, params) => {
  const qs = params
    ? '?' + new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    : '';
  return api(path + qs);
};
const apiPost = (path, body) => api(path, { method: 'POST', body: body ?? {} });

/** Gửi một tệp lên. api() đã biết bỏ qua FormData nên không đụng Content-Type. */
const apiUpload = (path, file, field = 'file') => {
  const form = new FormData();
  form.append(field, file, file.name);
  return api(path, { method: 'POST', body: form });
};

/**
 * Tải một tệp do máy chủ sinh ra.
 * Đi bằng thẻ <a> chứ không dùng fetch: trình duyệt tự gửi cookie phiên và tự
 * đặt tên tệp theo Content-Disposition, khỏi phải dựng blob rồi thu dọn.
 */
function downloadFile(path) {
  const a = document.createElement('a');
  a.href = path.startsWith('/') ? path : `${API}/${path}`;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
}
const apiPut = (path, body) => api(path, { method: 'PUT', body: body ?? {} });
const apiDel = (path) => api(path, { method: 'DELETE' });

/* ---------------------------------------------------------------- thông báo */

let toastTimer = null;

function toast(message, isError = false) {
  const box = $('toast');
  $('toastMsg').textContent = message;
  box.classList.toggle('err', !!isError);
  box.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove('on'), isError ? 5000 : 3400);
}

const toastError = (err) =>
  toast(err instanceof ApiError ? err.detail : (err && err.message) || 'Có lỗi xảy ra', true);

/* ---------------------------------------------------------------- khối HTML dùng lại */

const spinner = '<span class="spinner"></span>';

const loadingBox = (label = 'Đang tải…') =>
  `<div class="loading">${spinner}<span>${esc(label)}</span></div>`;

const skeletonRows = (n = 3) =>
  Array.from({ length: n }, () => '<div class="skeleton sk-row"></div>').join('');

function emptyBox(message) {
  return `<div class="empty">
    <svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>
    <div>${esc(message)}</div></div>`;
}

function errorBox(err, retryFn) {
  const detail = err instanceof ApiError ? err.detail : (err && err.message) || 'Lỗi không rõ';
  const retry = retryFn
    ? `<button onclick="${retryFn}">Thử lại</button>` : '';
  return `<div class="errbox"><b>Không tải được dữ liệu</b>${esc(detail)}${retry}</div>`;
}

const CHEVRON = '<svg class="chev" viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>';

/* ---------------------------------------------------------------- màn hình rộng */

/**
 * Từ 1024px trở lên là bố cục máy tính: cột điều hướng bên trái, danh sách
 * chính đổi sang dạng bảng nhiều cột. Dưới ngưỡng đó giữ nguyên bản điện thoại.
 */
const WIDE = window.matchMedia('(min-width: 1024px)');
const isWide = () => WIDE.matches;

/**
 * Dựng một bảng dữ liệu.
 *
 *   head: [{ t:'Mã máy', cls:'nowrap' }, …]  — cls dùng chung cho cả cột
 *   rows: [{ cells:['<b>x</b>', …], click:'openUnit(3)', cls:'flag' }, …]
 *
 * Nội dung ô là HTML, nên MỌI dữ liệu người dùng nhập phải qua esc() trước.
 */
function dataTable(head, rows) {
  if (!rows.length) return '';
  const ths = head.map((h) => `<th class="${h.cls || ''}">${esc(h.t)}</th>`).join('');
  const trs = rows.map((r) => {
    const tds = r.cells.map((c, i) =>
      `<td class="${head[i] && head[i].cls ? head[i].cls : ''}">${c}</td>`).join('');
    const cls = [r.cls || '', r.click ? 'clickable' : ''].filter(Boolean).join(' ');
    return `<tr class="${cls}"${r.click ? ` onclick="${r.click}"` : ''}>${tds}</tr>`;
  }).join('');
  return `<div class="tblwrap"><table class="tbl">
      <thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`;
}
const CAM_ICON = '<svg viewBox="0 0 24 24"><path d="M4 8h3l1.6-2h6.8L17 8h3v11H4z"/>' +
  '<circle cx="12" cy="13" r="3.4"/></svg>';

/** Khoá nút và hiện vòng xoay trong lúc chờ máy chủ trả lời. */
async function withBusy(button, label, fn) {
  if (!button) return fn();
  const original = button.innerHTML;
  button.disabled = true;
  button.innerHTML = `${spinner}<span>${esc(label)}</span>`;
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.innerHTML = original;
  }
}

/* ---------------------------------------------------------------- bảng trượt */

const Sheet = {
  onClose: null,
  // Hàm trả về true khi trong bảng đang có dữ liệu chưa lưu. Có nó thì một cú
  // bấm nhầm ra ngoài không cuốn mất công nhập của người dùng.
  guard: null,

  open({ title, body, foot, steps = null, stepLabel = '', onClose = null, guard = null }) {
    $('sheetTitle').innerHTML = title;
    $('sheetBody').innerHTML = body ?? '';
    $('sheetFoot').innerHTML = foot ?? '';

    const stepsEl = $('sheetSteps');
    const labelEl = $('sheetStepLabel');
    if (steps) {
      stepsEl.hidden = false;
      labelEl.hidden = false;
      [...stepsEl.children].forEach((el, i) => el.classList.toggle('on', i < steps));
      labelEl.textContent = stepLabel;
    } else {
      stepsEl.hidden = true;
      labelEl.hidden = true;
    }

    this.onClose = onClose;
    this.guard = guard;
    $('scrim').classList.add('on');
    $('sheet').classList.add('on');
    $('sheetBody').scrollTop = 0;
  },

  setBody(html) { $('sheetBody').innerHTML = html; },
  setFoot(html) { $('sheetFoot').innerHTML = html; },
  setTitle(html) { $('sheetTitle').innerHTML = html; },

  setSteps(step, label) {
    const stepsEl = $('sheetSteps');
    stepsEl.hidden = false;
    $('sheetStepLabel').hidden = false;
    [...stepsEl.children].forEach((el, i) => el.classList.toggle('on', i < step));
    $('sheetStepLabel').textContent = label;
  },

  close() {
    $('scrim').classList.remove('on');
    $('sheet').classList.remove('on');
    const cb = this.onClose;
    this.onClose = null;
    this.guard = null;
    if (cb) cb();
  },

  /** Đang có dữ liệu chưa lưu hay không. */
  isDirty() {
    try { return !!(this.guard && this.guard()); } catch (_) { return false; }
  },

  /**
   * Đóng theo yêu cầu rõ ràng của người dùng (nút ✕, phím Esc).
   * Còn dữ liệu dở thì hỏi lại một câu trước khi bỏ.
   */
  requestClose() {
    if (this.isDirty() &&
        !window.confirm('Bỏ dở phiếu đang lập? Những gì đã chọn sẽ mất.')) return;
    this.close();
  },

  /**
   * Bấm ra vùng tối bên ngoài. Đây gần như luôn là bấm nhầm, nên khi còn dữ
   * liệu dở thì KHÔNG đóng — chỉ lắc nhẹ và nhắc chỗ cần bấm.
   */
  requestCloseFromScrim() {
    if (!this.isDirty()) { this.close(); return; }
    const box = $('sheet');
    box.classList.remove('nudge');
    void box.offsetWidth;                       // ép trình duyệt chạy lại hiệu ứng
    box.classList.add('nudge');
    toast('Phiếu đang lập dở. Bấm ✕ ở góc nếu muốn bỏ.');
  },

  isOpen() { return $('sheet').classList.contains('on'); },
};

/* ---------------------------------------------------------------- xem ảnh */

function openViewer(src) {
  $('viewerImg').src = src;
  $('viewer').classList.add('on');
}

function closeViewer() {
  $('viewer').classList.remove('on');
  $('viewerImg').src = '';
}

/* ---------------------------------------------------------------- ảnh chụp */

/**
 * Chụp hoặc chọn ảnh rồi tải thẳng lên S3 bằng URL đã ký.
 * Máy chủ không trung chuyển byte nào; ta chỉ giữ lại object key.
 *
 * Ảnh được thu nhỏ tối đa 1400px và nén JPEG trước khi gửi, nên ảnh 8MB từ
 * điện thoại xuống còn vài trăm KB.
 */
const Photos = {
  target: null,

  pick(folder, onAdded) {
    this.target = { folder, onAdded };
    const input = $('picker');
    input.value = '';
    input.click();
  },

  async handleFiles(files) {
    const target = this.target;
    this.target = null;
    if (!target || !files.length) return;

    const keys = [];
    for (const file of files) {
      try {
        keys.push(await this.uploadOne(file, target.folder));
      } catch (err) {
        toastError(err);
      }
    }
    if (keys.length && target.onAdded) target.onAdded(keys);
  },

  async uploadOne(file, folder) {
    const { blob, type } = await this.shrink(file);
    const presign = await apiPost('uploads/presign', {
      filename: file.name || 'anh.jpg',
      content_type: type,
      folder,
    });
    const res = await fetch(presign.upload_url, {
      method: 'PUT',
      headers: { 'Content-Type': presign.content_type },
      body: blob,
    });
    if (!res.ok) throw new ApiError(res.status, 'Tải ảnh lên thất bại');
    return presign.key;
  },

  shrink(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('Không đọc được ảnh'));
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => reject(new Error('Tệp không phải ảnh hợp lệ'));
        img.onload = () => {
          const MAX = 1400;
          const scale = Math.min(1, MAX / Math.max(img.width, img.height));
          const canvas = document.createElement('canvas');
          canvas.width = Math.round(img.width * scale);
          canvas.height = Math.round(img.height * scale);
          canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
          canvas.toBlob(
            (blob) => blob ? resolve({ blob, type: 'image/jpeg' })
                           : reject(new Error('Không nén được ảnh')),
            'image/jpeg', 0.78);
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  },
};

/** Lưới ảnh. `onDelete` là tên hàm toàn cục nhận chỉ số ảnh. */
function photoGrid(photos, { onDelete = null } = {}) {
  if (!photos || !photos.length) {
    return '<div class="nophoto">Chưa có ảnh sản phẩm</div>';
  }
  return `<div class="photos">${photos.map((p, i) => {
    const url = typeof p === 'string' ? p : p.url;
    const del = onDelete
      ? `<span class="del" role="button" tabindex="0" aria-label="Xoá ảnh"
             onclick="event.stopPropagation();${onDelete}(${i})">
           <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></span>`
      : '';
    return `<button class="thumb" onclick="openViewer('${esc(url)}')" aria-label="Xem ảnh ${i + 1}">
      <img src="${esc(url)}" alt="Ảnh sản phẩm ${i + 1}" loading="lazy">${del}</button>`;
  }).join('')}</div>`;
}

const cameraButton = (handler, label = 'Chụp / thêm ảnh') =>
  `<div class="camrow"><button class="btn ghost sm" onclick="${handler}">${CAM_ICON}${esc(label)}</button></div>`;

/* ---------------------------------------------------------------- nhãn trạng thái */

const UNIT_LABEL = { AVAIL: 'Rảnh', OUT: 'Đang mượn', MAINT: 'Bảo trì', BROKEN: 'Hỏng' };
const UNIT_LABEL_LONG = {
  AVAIL: 'Sẵn sàng', OUT: 'Đang cho mượn', MAINT: 'Đang bảo trì', BROKEN: 'Đang hỏng',
};
const UNIT_PILL = { AVAIL: 'p-ok', OUT: 'p-out', MAINT: 'p-maint', BROKEN: 'p-bad' };
const TICKET_PILL = { open: 'p-out', soon: 'p-maint', over: 'p-bad', done: 'p-ok' };
const COND_LABEL = { NORMAL: 'Bình thường', BROKEN: 'Hỏng', MAINT: 'Cần bảo trì' };
const COND_DOT = { NORMAL: 'ok', BROKEN: 'bad', MAINT: 'mt' };

/** Một ô số trong lưới máy. Chấm đỏ góc trên = máy có ghi chú tình trạng. */
function unitTile(unit, { pick = false, selected = [], disabled = false, handler = null } = {}) {
  const caption = unit.holder_name ? shortName(unit.holder_name) : UNIT_LABEL[unit.status];
  const tip = `${unit.code} · ${unit.holder_name
    ? 'đang ở chỗ ' + unit.holder_name : UNIT_LABEL_LONG[unit.status]}` +
    (unit.issue_text ? ` · ${unit.issue_text}` : '');
  const onclick = handler || (pick ? `Borrow.toggle(${unit.id})` : `openUnit(${unit.id})`);
  return `<button class="u ${unit.status} ${unit.issue_text ? 'flagged' : ''} ${
    selected.includes(unit.id) ? 'on' : ''}"
    ${disabled ? 'disabled' : ''} onclick="${onclick}" title="${esc(tip)}">
    <b>${String(unit.no).padStart(2, '0')}</b><i>${esc(caption)}</i></button>`;
}

const UNIT_LEGEND = `<div class="ulegend">
  <span><b style="background:var(--ok)"></b>Sẵn sàng</span>
  <span><b style="background:var(--out)"></b>Đang mượn · tên người giữ</span>
  <span><b style="background:var(--maint)"></b>Bảo trì</span>
  <span><b style="background:var(--bad)"></b>Hỏng</span>
  <span><b class="dot" style="background:var(--bad)"></b>Có ghi chú tình trạng</span></div>`;

/** Khung đỏ hiển thị tình trạng ghi nhận của một máy. */
function issueBanner(unit, { withClearButton = false } = {}) {
  if (!unit.issue_text) return '';
  const clear = withClearButton && can('loan.devices.update')
    ? `<div class="act"><button class="btn ghost sm" onclick="clearUnitIssue(${unit.id}, this)">
         Đã xử lý xong — xoá ghi chú</button></div>` : '';
  return `<div class="issue">
    <div class="lbl">
      <svg viewBox="0 0 24 24"><path d="M12 9v5M12 17.5v.01"/>
        <path d="M10.3 3.9L2.4 17.4A2 2 0 004.1 20.4h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/></svg>
      Tình trạng ghi nhận</div>
    <div class="txt">${esc(unit.issue_text)}</div>
    <div class="when">Cập nhật ${fmtDateTime(unit.issue_at)} · từ phiếu nhận trả</div>
    ${clear}</div>`;
}

/* ---------------------------------------------------------------- bộ nhớ đệm */

/**
 * Danh mục ít đổi (nhân sự, phòng ban, loại thiết bị) được giữ lại để các màn
 * hình sau không phải gọi lại. Mọi thao tác ghi đều gọi Cache.clear().
 */
const Cache = {
  data: {},

  async get(key, loader) {
    if (this.data[key] === undefined) this.data[key] = await loader();
    return this.data[key];
  },

  clear(...keys) {
    if (!keys.length) { this.data = {}; return; }
    keys.forEach((k) => { delete this.data[k]; });
  },
};

const loadDepartments = () => Cache.get('departments', () => apiGet('departments'));
const loadStaff = () => Cache.get('staff', () => apiGet('staff'));
const loadModels = () => Cache.get('models', () => apiGet('devices/models'));

/* ---------------------------------------------------------------- sự kiện chung */

document.addEventListener('DOMContentLoaded', () => {
  $('picker').addEventListener('change', (e) => Photos.handleFiles([...e.target.files]));
  $('scrim').addEventListener('click', () => Sheet.requestCloseFromScrim());
  $('sheetClose').addEventListener('click', () => Sheet.requestClose());
  $('viewer').addEventListener('click', closeViewer);
  $('viewerClose').addEventListener('click', closeViewer);

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if ($('viewer').classList.contains('on')) closeViewer();
    else if (Sheet.isOpen()) Sheet.requestClose();
  });
});
