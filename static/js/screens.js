/* =============================================================
   Vẽ các màn hình. Mỗi hàm render* tự nạp dữ liệu và tự xử lý lỗi.
   ============================================================= */
'use strict';

/* ================================================================
   TỔNG QUAN
   ================================================================ */

let homeShowAllTodo = false;

async function renderHome() {
  const box = $('s-home');
  if (!box.dataset.loaded) {
    box.innerHTML = `<div class="kpis">${'<div class="skeleton sk-kpi"></div>'.repeat(4)}</div>
      <div style="height:22px"></div>${skeletonRows(3)}`;
  }

  let data;
  try {
    data = await apiGet('dashboard');
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderHome()');
    return;
  }
  box.dataset.loaded = '1';

  const u = data.units;
  const todo = [
    ...data.todo.overdue.map((t) => ({ kind: 'over', t })),
    ...data.todo.soon.map((t) => ({ kind: 'soon', t })),
    ...data.todo.issues.map((x) => ({ kind: 'issue', x })),
    ...data.todo.maintenance.map((m) => ({ kind: 'maint', m })),
  ];
  const shown = homeShowAllTodo ? todo : todo.slice(0, 4);

  box.innerHTML = `
    <div class="kpis">
      <button class="kpi" onclick="goDevices('AVAIL')">
        <div class="k"><span class="dot" style="background:var(--ok)"></span>Sẵn sàng</div>
        <div class="v">${u.avail}</div><div class="sub">trên tổng ${u.total} máy</div>
      </button>
      <button class="kpi" onclick="goLoans('open')">
        <div class="k"><span class="dot" style="background:var(--out)"></span>Đang mượn</div>
        <div class="v">${u.out}</div>
        <div class="sub">${data.tickets.open} phiếu còn mở</div>
      </button>
      <button class="kpi ${data.tickets.overdue ? 'alert' : ''}" onclick="goLoans('over')">
        <div class="k"><span class="dot" style="background:var(--bad)"></span>Quá ${data.overdue_days} ngày</div>
        <div class="v">${data.tickets.overdue}</div>
        <div class="sub">${data.tickets.overdue
          ? data.todo.overdue.reduce((a, t) => a + t.open_units, 0) + ' máy cần thu hồi'
          : 'không có phiếu quá hạn'}</div>
      </button>
      <button class="kpi" onclick="openScreen('maint')">
        <div class="k"><span class="dot" style="background:var(--maint)"></span>Bảo trì / hỏng</div>
        <div class="v">${u.maint + u.broken}</div>
        <div class="sub">${u.maint} bảo trì · ${u.broken} hỏng</div>
      </button>
    </div>

    <h2 class="sec">Cần xử lý <span class="count">${todo.length}</span>
      ${todo.length > 4 ? `<span class="lnk" onclick="homeShowAllTodo=!homeShowAllTodo;renderHome()">
        ${homeShowAllTodo ? 'Thu gọn' : 'Xem tất cả ' + todo.length}</span>` : ''}</h2>
    <div class="rows${isWide() && shown.length > 2 ? ' two' : ''}">${
      shown.map(todoRow).join('') || emptyBox('Không có việc nào cần xử lý hôm nay')}</div>

    <h2 class="sec">Biểu đồ</h2>
    <div class="${isWide() ? 'grid2' : ''}">
      <div class="chartcard">
        <div class="ct">Thiết bị cho mượn theo trạng thái</div>
        <div class="cs">${u.total} máy · cập nhật ${fmtDateTime(new Date().toISOString())}</div>
        ${stackedBar([
          ['Sẵn sàng', u.avail, 'var(--ok)'],
          ['Đang mượn', u.out, 'var(--out)'],
          ['Bảo trì', u.maint, 'var(--maint)'],
          ['Hỏng', u.broken, 'var(--bad)'],
        ], u.total)}
      </div>
      ${isWide() ? '' : '<div style="height:14px"></div>'}
      <div class="chartcard">
        <div class="ct">Lượt mượn &amp; trả · 7 ngày</div>
        <div class="cs">${data.series7[0].date} – ${data.series7[6].date}</div>
        ${barChart(data.series7.map((d) => (
          { label: d.date, a: d.borrowed, b: d.returned })), ['Mượn', 'Trả'])}
      </div>
    </div>`;
}

function todoRow(item) {
  if (item.kind === 'issue') {
    const x = item.x;
    return `<button class="row flag" onclick="openUnit(${x.unit_id})">
      <div class="main">
        <div class="title"><span class="mono">${esc(x.code)}</span> · ${esc(x.model_name)}</div>
        <div class="meta" style="color:var(--bad);font-weight:500;white-space:normal">${esc(x.issue_text)}</div>
        <div class="meta">Ghi nhận ${fmtDateTime(x.issue_at)} · máy đang ${
          esc((UNIT_LABEL_LONG[x.status] || '').toLowerCase())}</div>
      </div>
      <div class="rt"><span class="pill p-bad">Tình trạng</span></div>${CHEVRON}</button>`;
  }
  if (item.kind === 'maint') {
    const m = item.m;
    return `<button class="row warn" onclick="openScreen('maint')">
      <div class="main">
        <div class="title"><span class="mono">${esc(m.code)}</span> · ${esc(m.model_name)}</div>
        <div class="meta">Bảo trì từ ${fmtDate(m.scheduled_at)}${m.note ? ' · ' + esc(m.note) : ''}</div>
      </div>
      <div class="rt"><span class="pill p-maint">${m.days} ngày</span></div>${CHEVRON}</button>`;
  }
  const t = item.t;
  const isOver = item.kind === 'over';
  return `<button class="row ${isOver ? 'flag' : 'warn'}" onclick="openTicket('${esc(t.code)}')">
    <div class="main">
      <div class="title">${esc(t.borrower_name || '—')}</div>
      <div class="meta"><span class="mono">#${esc(t.code)}</span> · mượn ${fmtDate(t.borrowed_at)}${
        t.department ? ' · ' + esc(t.department) : ''}</div>
    </div>
    <div class="rt">
      <span class="pill ${isOver ? 'p-bad' : 'p-maint'}">${t.days_elapsed} ngày</span>
      <span class="num">${t.open_units}<span style="font-size:13px;color:var(--muted)"> máy</span></span>
    </div>${CHEVRON}</button>`;
}

function stackedBar(segments, total) {
  if (!total) return emptyBox('Chưa có thiết bị nào trong hệ thống');
  return `<div class="stack">${segments.map(([, value, color]) =>
      value ? `<i style="background:${color};flex:${value}">${
        value / total > 0.12 ? `<span>${value}</span>` : ''}</i>` : '').join('')}</div>
    <div class="slegend">${segments.map(([label, value, color]) =>
      `<span><b style="background:${color}"></b>${esc(label)}<em>${value}</em></span>`).join('')}</div>`;
}

/**
 * Biểu đồ cột đôi. Một hàm dùng chung cho cả trang Tổng quan lẫn bảng kho.
 *
 * `rows`  : [{ label, a, b }] — a vẽ cột trái, b vẽ cột phải
 * `names` : [tên chuỗi a, tên chuỗi b] dùng cho chú giải và tooltip
 *
 * Hai màu --out (xanh dương) và --ok (xanh lá) đã được kiểm bằng máy: cách
 * nhau ΔE 17.8 với mắt thường và ≥16 với ba dạng mù màu phổ biến, ở cả nền
 * sáng lẫn nền tối. Chú giải luôn có, nên màu không phải dấu hiệu duy nhất.
 */
function barChart(rows, names) {
  // Khung vẽ rộng theo số cột. Cột cố định 320 thì trên màn hình rộng ảnh bị
  // kéo giãn ngang, chữ trục cũng giãn theo và nhìn rất xấu.
  const H = 132, padL = 26, padB = 20, padT = 8;
  const W = Math.max(320, padL + rows.length * 62);
  const max = Math.max(4, ...rows.map((r) => Math.max(r.a, r.b)));
  const step = (W - padL) / rows.length;
  const bw = Math.min(13, (step - 10) / 2);
  const y = (v) => padT + (H - padT - padB) * (1 - v / max);
  const base = y(0);
  let out = '';
  [0, Math.round(max / 2), max].forEach((v) => {
    out += `<line x1="${padL - 4}" y1="${y(v)}" x2="${W}" y2="${y(v)}"/>`;
    out += `<text x="0" y="${y(v) + 3.4}">${v}</text>`;
  });
  rows.forEach((r, i) => {
    const cx = padL + step * i + step / 2;
    // Cách nhau 3px để hai cột không dính vào nhau khi in trắng đen
    [[r.a, cx - bw - 1.5, 'var(--out)', names[0]],
     [r.b, cx + 1.5, 'var(--ok)', names[1]]].forEach(([v, x, color, nm]) => {
      if (v > 0) {
        out += `<rect x="${x}" y="${y(v)}" width="${bw}" height="${base - y(v)}"
          rx="3" fill="${color}"><title>${esc(r.label)} · ${esc(nm)}: ${v}</title></rect>`;
      }
    });
    out += `<text x="${cx}" y="${H - 6}" text-anchor="middle">${esc(r.label)}</text>`;
  });
  return `<svg class="bars" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
    aria-label="Biểu đồ ${esc(names[0])} và ${esc(names[1])}">${out}</svg>
    <div class="blegend">
      <span><b style="background:var(--out)"></b>${esc(names[0])}</span>
      <span><b style="background:var(--ok)"></b>${esc(names[1])}</span>
    </div>`;
}

/**
 * Lịch sử ra vào của MỘT mặt hàng trong kho.
 *
 * Đây là mảnh còn thiếu của tab Nhập / Xuất: trước chỉ lập được phiếu, không
 * tra ngược được một mặt hàng đã vào ra những lần nào, ai lập, hàng đi đâu.
 */
async function openStockProduct(json) {
  const [name, code] = JSON.parse(json);
  Sheet.open({ title: 'Đang tải…', body: loadingBox(), foot: '' });
  let d;
  try {
    d = await apiGet('stock/product', { name, code });
  } catch (err) {
    Sheet.setBody(errorBox(err));
    return;
  }

  const pct = d.imported ? Math.round(d.on_hand / d.imported * 100) : 0;
  Sheet.setTitle(esc(d.product_name));
  Sheet.setBody(`
    <div class="card" style="margin-bottom:14px">
      <dl class="kv" style="margin:0">
        <dt>Model</dt><dd class="mono">${esc(d.model_code)}</dd>
        ${d.brand ? `<dt>Hãng</dt><dd>${esc(d.brand)}</dd>` : ''}
        <dt>Đã nhập</dt><dd>${d.imported}</dd>
        <dt>Đã xuất</dt><dd>${d.exported}</dd>
        <dt>Tồn kho</dt>
        <dd><b style="font-size:19px">${d.on_hand}</b>
          <span class="pill ${d.on_hand > 0 ? 'p-ok' : 'p-bad'}" style="margin-left:8px">${
            d.on_hand > 0 ? 'còn ' + pct + '%' : 'Hết hàng'}</span></dd>
        ${d.first_in ? `<dt>Nhập lần đầu</dt><dd>${fmtDate(d.first_in)}</dd>` : ''}
      </dl>
      <div class="qbar" style="margin-top:12px">
        <i style="background:var(--ok);flex:${Math.max(d.on_hand, 0.001)}"></i>
        <i style="background:var(--out);flex:${Math.max(d.exported, 0.001)}"></i>
      </div>
    </div>

    ${placeCard(d)}

    <h2 class="sec">Lịch sử <span class="count">${d.moves.length}</span></h2>
    <div class="rows">${d.moves.map(stockMoveRow).join('')
      || emptyBox('Chưa có phiếu nào')}</div>
    <div style="height:8px"></div>`);

  Place.mount(d);

  Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Đóng</button>
    ${d.on_hand > 0 && can('import_export.create')
      ? `<button class="btn" onclick="Sheet.close();StockExport.open(${
          esc(JSON.stringify(JSON.stringify(
            { product_name: d.product_name, model_code: d.model_code })))})">Xuất hàng</button>`
      : ''}`);
}

/**
 * Ô "để ở đâu trong kho" của một mặt hàng.
 *
 * Người có quyền sửa kho thì gõ được chỗ để và chụp được ảnh chỗ đó; người chỉ
 * xem thì đọc thôi. Ảnh giúp người mới vào kho tìm đúng kệ mà không phải hỏi.
 */
function placeCard(d) {
  if (!can('import_export.update')) {
    if (!d.location && !d.image_url) return '';
    return `<div class="card" style="margin-bottom:14px">
      <div class="ct">Vị trí trong kho</div>
      <div class="placeval">${d.location ? esc(d.location) : 'Chưa khai'}</div>
      ${d.location_note ? `<div class="meta">${esc(d.location_note)}</div>` : ''}
      ${d.image_url ? `<div class="placeshot"><img src="${esc(d.image_url)}"
        alt="Ảnh vị trí kho" onclick="openViewer(${
          esc(JSON.stringify(d.image_url))})"></div>` : ''}
    </div>`;
  }
  return `<div class="card" style="margin-bottom:14px">
    <div class="ct">Vị trí trong kho</div>
    <div class="field" style="margin:10px 0 0">
      <label for="placeInput">Chỗ để</label>
      <input id="placeInput" maxlength="160" placeholder="Ví dụ: Kệ A3 — tầng 2"
             value="${esc(d.location || '')}">
    </div>
    <div class="field" style="margin:12px 0 0">
      <label for="placeNote">Ghi chú</label>
      <input id="placeNote" placeholder="Ví dụ: hộp ngoài cùng bên trái"
             value="${esc(d.location_note || '')}">
    </div>
    <div id="placeBox"></div>
    <button class="btn ghost sm" style="margin-top:12px;width:auto;padding:0 18px"
            onclick="Place.save(this)">Lưu vị trí</button>
  </div>`;
}

function stockMoveRow(m) {
  const isIn = m.kind === 'IN';
  const where = isIn
    ? (m.detail || '')
    : [m.detail, m.to].filter(Boolean).join(' — ');
  return `<button class="row" onclick="openStockRecord('${m.kind}', ${m.id})">
    <div class="main">
      <div class="title">${isIn ? 'Nhập kho' : 'Xuất kho'}${
        where ? ` · ${esc(where)}` : ''}</div>
      <div class="meta">${fmtDate(m.at)}${m.who ? ' · ' + esc(m.who) : ''}</div>
      ${m.note ? `<div class="meta">${esc(m.note)}</div>` : ''}
    </div>
    <div class="rt">
      <span class="pill ${isIn ? 'p-ok' : 'p-out'}">${isIn ? '+' : '−'}${m.qty}</span>
    </div>
  </button>`;
}

/* ================================================================
   MƯỢN - TRẢ
   ================================================================ */

const Loans = { tab: 'open', q: '' };

function goLoans(tab) { Loans.tab = tab; openScreen('loans'); }

function loansShell() {
  return `
    <div class="seg" id="loanSeg">
      ${[['open', 'Đang mượn'], ['over', `Quá ${OVERDUE_DAYS}n`], ['done', 'Đã trả']]
        .map(([k, label]) => `<button class="${Loans.tab === k ? 'on' : ''}" data-k="${k}"
          onclick="Loans.setTab('${k}')">${esc(label)}</button>`).join('')}
    </div>
    <div class="search">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
      <input id="loanQ" placeholder="Tìm người mượn, mã phiếu hoặc mã máy…"
             value="${esc(Loans.q)}" oninput="Loans.onSearch(this.value)">
    </div>
    <div id="loanList">${skeletonRows(3)}</div>`;
}

Loans.setTab = function (key) {
  Loans.tab = key;
  const seg = $('loanSeg');
  if (!seg) { renderLoans(); return; }
  seg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.k === key));
  renderLoanList();
};

let loanSearchTimer = null;
Loans.onSearch = function (value) {
  Loans.q = value;
  clearTimeout(loanSearchTimer);
  loanSearchTimer = setTimeout(() => renderLoanList(), 300);
};

async function renderLoans() {
  const focused = document.activeElement && document.activeElement.id === 'loanQ';
  const caret = focused ? document.activeElement.selectionStart : null;
  $('s-loans').innerHTML = loansShell();
  if (focused) {
    const input = $('loanQ');
    input.focus();
    if (caret != null) input.setSelectionRange(caret, caret);
  }
  await renderLoanList();
}

async function renderLoanList() {
  const box = $('loanList');
  if (!box) return;
  let tickets;
  try {
    tickets = await apiGet('tickets', { state: Loans.tab, q: Loans.q || undefined, limit: 200 });
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderLoanList()');
    return;
  }
  if (!tickets.length) {
    box.innerHTML = emptyBox(Loans.q ? 'Không tìm thấy phiếu nào khớp'
      : Loans.tab === 'over' ? `Không có phiếu nào quá ${OVERDUE_DAYS} ngày`
      : Loans.tab === 'done' ? 'Chưa có phiếu nào hoàn tất' : 'Chưa có phiếu nào đang mượn');
    return;
  }
  const rowClass = (t) => t.state === 'over' ? 'flag' : t.state === 'soon' ? 'warn' : '';

  if (isWide()) {
    box.className = '';
    box.innerHTML = dataTable(
      [{ t: 'Người mượn' }, { t: 'Phòng ban' }, { t: 'Phiếu', cls: 'nowrap' },
       { t: 'Máy trong phiếu' }, { t: 'Ngày mượn', cls: 'nowrap' },
       { t: 'Số ngày', cls: 'num' }, { t: 'Còn giữ', cls: 'num' }, { t: 'Trạng thái', cls: 'nowrap' }],
      tickets.map((t) => ({
        click: `openTicket('${esc(t.code)}')`,
        cls: rowClass(t),
        cells: [
          `<span class="strong">${esc(t.borrower_name || '—')}</span>`,
          esc(t.borrower_department || '—'),
          `<span class="mono">#${esc(t.code)}</span>`,
          `<span class="mono" style="font-size:15px">${esc(t.summary)}</span>`,
          fmtDate(t.borrowed_at),
          String(t.days_elapsed),
          String(t.open_units || 0),
          `<span class="pill ${TICKET_PILL[t.state]}">${esc(t.state_label)}</span>`,
        ],
      })));
    return;
  }

  box.className = 'rows';
  box.innerHTML = tickets.map((t) => `
    <button class="row ${rowClass(t)}" onclick="openTicket('${esc(t.code)}')">
      <div class="main">
        <div class="title">${esc(t.borrower_name || '—')}</div>
        <div class="meta"><span class="mono">#${esc(t.code)}</span>${
          t.borrower_department ? ' · ' + esc(t.borrower_department) : ''} · mượn ${fmtDate(t.borrowed_at)}</div>
        <div class="meta mono" style="margin-top:4px">${esc(t.summary)}</div>
      </div>
      <div class="rt">
        <span class="pill ${TICKET_PILL[t.state]}">${esc(t.state_label)}</span>
        <span class="num">${t.open_units || t.total_units}<span
          style="font-size:13px;color:var(--muted)"> máy</span></span>
      </div>${CHEVRON}</button>`).join('');
}

/* ================================================================
   THIẾT BỊ
   ================================================================ */

const Devices = { filter: 'ALL', q: '', open: null };
const DEVICE_FILTERS = [
  ['ALL', 'Tất cả'], ['AVAIL', 'Sẵn sàng'], ['OUT', 'Đang mượn'],
  ['MAINT', 'Đang bảo trì'], ['BROKEN', 'Đang hỏng'], ['ISSUE', 'Có ghi chú'],
];

function goDevices(filter) { Devices.filter = filter || 'ALL'; openScreen('devices'); }

/**
 * Đổi bộ lọc mà KHÔNG vẽ lại cả màn hình.
 * Vẽ lại toàn bộ sẽ dựng lại dải chip, mà dải chip cuộn ngang được — nên trên
 * điện thoại nó tụt về đầu, cái chip vừa bấm biến khỏi tầm nhìn.
 */
Devices.setFilter = function (key) {
  Devices.filter = key;
  const strip = $('devChips');
  if (!strip) { renderDevices(); return; }
  strip.querySelectorAll('.chip').forEach((b) => b.classList.toggle('on', b.dataset.k === key));
  const active = strip.querySelector('.chip.on');
  if (active) active.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  renderDeviceList();
};

let deviceSearchTimer = null;
Devices.onSearch = function (value) {
  Devices.q = value;
  clearTimeout(deviceSearchTimer);
  deviceSearchTimer = setTimeout(() => renderDeviceList(), 300);
};

async function renderDevices() {
  const focused = document.activeElement && document.activeElement.id === 'devQ';
  const caret = focused ? document.activeElement.selectionStart : null;
  $('s-devices').innerHTML = `
    <div class="toolrow">
      <div class="search">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input id="devQ" placeholder="Tìm loại thiết bị, mã máy hoặc ghi chú…"
               value="${esc(Devices.q)}" oninput="Devices.onSearch(this.value)">
      </div>
      ${can('loan.devices.create') ? `
        <button class="btn ghost sm tool" onclick="ImportExcel.open()">
          <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
          Nhập Excel</button>` : ''}
      <button class="btn ghost sm tool" onclick="downloadFile('devices/export')">
        <svg viewBox="0 0 24 24"><path d="M12 3v12M7 11l5 5 5-5M5 21h14"/></svg>
        Xuất Excel</button>
      <button class="btn ghost sm tool" onclick="printAllLabels()"
              title="In tem QR cho toàn bộ máy — hỏi lại trước khi chạy">
        <svg viewBox="0 0 24 24"><path d="M6 9V3h12v6M6 18H4a1 1 0 01-1-1v-6a1 1 0 011-1h16a1 1 0 011 1v6a1 1 0 01-1 1h-2"/><path d="M6 14h12v7H6z"/></svg>
        In tem toàn bộ</button>
    </div>
    <div class="chips" id="devChips">${DEVICE_FILTERS.map(([k, label]) =>
      `<button class="chip ${Devices.filter === k ? 'on' : ''}" data-k="${k}"
        onclick="Devices.setFilter('${k}')">${esc(label)}</button>`).join('')}</div>
    <div id="devList">${skeletonRows(4)}</div>`;
  if (focused) {
    const input = $('devQ');
    input.focus();
    if (caret != null) input.setSelectionRange(caret, caret);
  }
  await renderDeviceList();
}

async function renderDeviceList() {
  const box = $('devList');
  if (!box) return;

  let models, units;
  try {
    const unitParams = { limit: 2000 };
    if (Devices.filter === 'ISSUE') unitParams.has_issue = true;
    else if (Devices.filter !== 'ALL') unitParams.status = Devices.filter;
    if (Devices.q) unitParams.q = Devices.q;

    [models, units] = await Promise.all([
      apiGet('devices/models', Devices.q ? { q: Devices.q } : undefined),
      apiGet('devices/units', unitParams),
    ]);
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderDeviceList()');
    return;
  }

  // Khi đang tìm kiếm, một loại vẫn hiện nếu TÊN LOẠI khớp dù không máy nào khớp mã
  const byModel = {};
  units.forEach((u) => { (byModel[u.model_id] ||= []).push(u); });
  const modelById = Object.fromEntries(models.map((m) => [m.id, m]));
  const allModels = await loadModels();
  allModels.forEach((m) => { if (!modelById[m.id] && byModel[m.id]) modelById[m.id] = m; });

  const visible = Object.values(modelById).filter((m) => {
    if (Devices.filter === 'ALL' && !Devices.q) return true;
    return (byModel[m.id] || []).length > 0;
  }).sort((a, b) => a.name.localeCompare(b.name, 'vi'));

  if (!visible.length) {
    box.innerHTML = emptyBox('Không tìm thấy thiết bị nào phù hợp');
    return;
  }

  const expandAll = !!Devices.q || Devices.filter !== 'ALL';
  box.className = '';

  // Trên máy tính, khi đang lọc hoặc tìm thì người dùng đang săn một vài máy cụ
  // thể — bảng phẳng đọc nhanh hơn nhiều so với mở từng nhóm ra xem.
  if (isWide() && expandAll) {
    const flat = [];
    visible.forEach((m) => (byModel[m.id] || []).forEach((u) => flat.push([m, u])));
    if (!flat.length) {
      box.innerHTML = emptyBox('Không có máy nào khớp bộ lọc');
      return;
    }
    box.innerHTML = dataTable(
      [{ t: 'Mã máy', cls: 'nowrap' }, { t: 'Loại thiết bị' }, { t: 'Hãng' },
       { t: 'Trạng thái', cls: 'nowrap' }, { t: 'Đang ở chỗ' }, { t: 'Ghi chú tình trạng' }],
      flat.map(([m, u]) => ({
        click: `openUnit(${u.id})`,
        cls: u.issue_text ? 'flag' : '',
        cells: [
          `<span class="mono strong">${esc(u.code)}</span>`,
          esc(m.name),
          esc(m.brand || '—'),
          `<span class="pill ${UNIT_PILL[u.status]}">${esc(UNIT_LABEL_LONG[u.status])}</span>`,
          esc(u.holder_name || '—'),
          u.issue_text
            ? `<span class="bad">${esc(u.issue_text)}</span>
               <span class="sub">Cập nhật ${fmtDateTime(u.issue_at)}</span>`
            : '<span style="color:var(--muted)">—</span>',
        ],
      })));
    return;
  }

  // Không lọc gì: bảng theo LOẠI thiết bị. Bấm một dòng mở chi tiết loại đó,
  // trong đó có sẵn lưới toàn bộ máy, ảnh và thông số.
  if (isWide()) {
    box.innerHTML = dataTable(
      [{ t: 'Loại thiết bị' }, { t: 'Mã', cls: 'nowrap' }, { t: 'QR', cls: 'nowrap' },
       { t: 'Hãng' },
       { t: 'Tổng', cls: 'num' }, { t: 'Sẵn sàng', cls: 'num' }, { t: 'Đang mượn', cls: 'num' },
       { t: 'Bảo trì', cls: 'num' }, { t: 'Hỏng', cls: 'num' }, { t: 'Tình trạng' }],
      visible.map((m) => {
        const c = m.counters || {};
        return {
          click: `openModel(${m.id})`,
          cls: c.issues ? 'flag' : (c.broken ? 'warn' : ''),
          cells: [
            `<span class="strong">${esc(m.name)}</span>${
              m.photo_count ? `<span class="sub">${m.photo_count} ảnh sản phẩm</span>` : ''}`,
            `<span class="mono">${esc(m.code)}</span>`,
            qrCell(m),
            esc(m.brand || '—'),
            String(c.total || 0),
            `<span style="color:var(--ok)">${c.avail || 0}</span>`,
            c.out ? `<span style="color:var(--out)">${c.out}</span>` : '—',
            c.maint ? `<span style="color:var(--maint)">${c.maint}</span>` : '—',
            c.broken ? `<span style="color:var(--bad)">${c.broken}</span>` : '—',
            c.issues
              ? `<span class="issue-mini"><span>${c.issues} máy có ghi chú</span></span>`
              : '<span style="color:var(--muted)">bình thường</span>',
          ],
        };
      }));
    return;
  }

  box.innerHTML = visible.map((m) => {
    const c = m.counters || {};
    const shownUnits = byModel[m.id] || [];
    const isOpen = expandAll || Devices.open === m.id;
    const bar = [[c.avail, 'var(--ok)'], [c.out, 'var(--out)'],
                 [c.maint, 'var(--maint)'], [c.broken, 'var(--bad)']]
      .map(([v, color]) => v ? `<i style="background:${color};flex:${v}"></i>` : '').join('');

    return `<div class="acc">
      <button class="ah" onclick="Devices.open = Devices.open===${m.id} ? null : ${m.id}; renderDeviceList()">
        <div class="nm">
          <b>${esc(m.name)}</b>
          <em><span class="mono">${esc(m.code)}</span> · ${c.total || 0} máy${
            m.brand ? ' · ' + esc(m.brand) : ''}${m.photo_count ? ` · ${m.photo_count} ảnh` : ''}</em>
          ${c.issues ? `<span class="issue-mini"><span>${c.issues} máy có ghi chú tình trạng</span></span>` : ''}
        </div>
        <div style="text-align:right;flex:0 0 auto;display:flex;align-items:center;gap:9px">
          <span class="pill ${c.avail ? 'p-ok' : 'p-mute'}">${c.avail || 0} sẵn sàng</span>
          ${qrCell(m)}
        </div>
        <svg class="chev" viewBox="0 0 24 24" style="transform:rotate(${isOpen ? 90 : 0}deg)">
          <path d="M9 18l6-6-6-6"/></svg>
      </button>
      <div class="qbar" style="margin:0 13px 12px">${bar}</div>
      ${isOpen ? `<div class="ab">
        <div class="ugrid">${shownUnits.map((u) => unitTile(u)).join('')
          || emptyBox('Không có máy nào khớp bộ lọc')}</div>
        ${shownUnits.length ? UNIT_LEGEND : ''}
        <button class="btn ghost sm" style="margin-top:12px" onclick="openModel(${m.id})">
          Xem thông số &amp; ghi chú</button>
      </div>` : ''}
    </div>`;
  }).join('');
}

/* ---------- tem QR ---------- */

/**
 * Ô QR trong danh sách. Ảnh do máy chủ vẽ theo mã loại, bấm vào thì mở bảng
 * xem lớn kèm nút in. Dừng sự kiện lại để không mở luôn chi tiết loại.
 */
function qrCell(model) {
  return `<button class="qrcell" title="Xem và in tem QR · ${esc(model.code)}"
    aria-label="Tem QR của ${esc(model.name)}"
    onclick="event.stopPropagation();openQr(${model.id})">
    <img src="${API}/devices/models/${model.id}/qr.svg" alt="" loading="lazy" width="34" height="34">
  </button>`;
}

/** Bảng xem tem QR của một loại, kèm hai kiểu in. */
async function openQr(modelId) {
  Sheet.open({ title: 'Tem QR', body: loadingBox(), foot: '' });
  let m;
  try {
    m = await apiGet(`devices/models/${modelId}`);
  } catch (err) {
    Sheet.setBody(errorBox(err));
    return;
  }

  const total = (m.units || []).length;
  Sheet.setTitle(`Tem QR · ${esc(m.name)}`);
  Sheet.setBody(`
    <div class="qrbig">
      <img src="${API}/devices/models/${m.id}/qr.svg" alt="Mã QR ${esc(m.code)}"
           width="220" height="220">
      <b class="mono">${esc(m.code)}</b>
      <em>${esc(m.name)}</em>
    </div>

    <h2 class="sec">In tem để dán</h2>
    <div class="qropt">
      <button class="btn ghost" onclick="printLabels(${m.id},'units')" ${total ? '' : 'disabled'}>
        Tem từng máy · ${total} tem
      </button>
      <button class="btn ghost" onclick="printLabels(${m.id},'model')">
        Tem mã loại · 2 tem
      </button>
    </div>
    <p class="qrnote">Trên tem chỉ có <b>QR</b> và <b>tên thiết bị</b> — mã nằm
      trong QR, không in ra. Tem từng máy mang mã riêng của máy (${
      esc(total ? m.units[0].code : m.code + '-01')}…), quét vào là máy đó nhảy
      thẳng vào phiếu mượn; tem mã loại dán lên thùng hoặc kệ chứa cả lô.</p>
    <p class="qrnote">Giấy decal 2 tem khổ 98mm (mỗi tem 50×30mm), máy in Godex
      Z530 — mỗi lần đẩy giấy ra 2 tem. Trang tem mở ở thẻ mới, bấm <b>In</b>.</p>`);
  Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Đóng</button>
    <button class="btn" onclick="openModel(${m.id})">Xem loại thiết bị</button>`);
}

/** Mở trang tem in được ở thẻ mới — trình duyệt tự gửi cookie phiên. */
function printLabels(modelId, kind) {
  window.open(`${API}/devices/models/${modelId}/labels?kind=${kind}`, '_blank', 'noopener');
}

/**
 * In tem cho TOÀN BỘ thiết bị.
 *
 * Việc này chạy liên tục hàng trăm lần đẩy giấy, nên hỏi lại bằng con số thật
 * lấy từ máy chủ — bao nhiêu tem, bao nhiêu lần đẩy, tốn bao nhiêu decal — chứ
 * không bắt người dùng đoán. Trang tem còn một lớp tick xác nhận nữa.
 */
async function printAllLabels() {
  let info;
  try {
    info = await apiGet('devices/labels/count');
  } catch (err) {
    toast(err.detail || 'Không đếm được số tem.', true);
    return;
  }
  if (!info.units) { toast('Chưa có máy nào trong hệ thống để in tem.', true); return; }

  const metres = (info.length_cm / 100).toFixed(1);
  const ok = window.confirm(
    `In tem cho toàn bộ ${info.units} máy?\n\n`
    + `· ${info.feeds} lần đẩy giấy (mỗi lần 2 tem)\n`
    + `· khoảng ${metres}m decal, máy chạy liên tục không dừng\n\n`
    + 'Mở trang tem bây giờ?');
  if (!ok) return;
  window.open(`${API}/devices/labels/all`, '_blank', 'noopener');
}

/* ---------- chi tiết một loại thiết bị ---------- */

let currentModel = null;

async function openModel(modelId) {
  Sheet.open({ title: 'Đang tải…', body: loadingBox(), foot: '' });
  let m;
  try {
    m = await apiGet(`devices/models/${modelId}`);
  } catch (err) {
    Sheet.setBody(errorBox(err));
    return;
  }
  currentModel = m;
  drawModelSheet();
}

function drawModelSheet() {
  const m = currentModel;
  const c = m.counters || {};
  const flagged = (m.units || []).filter((u) => u.issue_text);
  const canEdit = can('loan.devices.update');

  Sheet.setTitle(esc(m.name));
  Sheet.setBody(`
    <h2 class="sec" style="margin-top:0">Ảnh sản phẩm <span class="count">${m.photos.length}</span></h2>
    ${photoGrid(m.photos, { onDelete: canEdit ? 'deleteModelPhoto' : null })}
    ${canEdit ? cameraButton('addModelPhoto()', 'Chụp / thêm ảnh') : ''}

    <h2 class="sec">Thông tin</h2>
    <dl class="kv" style="margin:0 0 18px">
      <dt>Mã loại</dt><dd class="mono">${esc(m.code)}</dd>
      <dt>Hãng</dt><dd>${esc(m.brand || '—')}</dd>
      <dt>Số máy</dt><dd>${c.total || 0} máy · ${c.avail || 0} sẵn sàng</dd>
    </dl>

    <h2 class="sec">Thông số chung</h2>
    <div class="spec">${esc(m.info || 'Chưa có thông tin')}</div>
    ${m.note ? `<h2 class="sec">Ghi chú</h2><div class="note">${esc(m.note)}</div>` : ''}

    ${flagged.length ? `<h2 class="sec">Máy có ghi chú tình trạng
        <span class="count">${flagged.length}</span></h2>
      ${flagged.map((u) => `<button class="row flag" style="margin-bottom:8px"
          onclick="openUnit(${u.id})">
        <div class="main">
          <div class="title"><span class="mono">${esc(u.code)}</span></div>
          <div class="meta" style="color:var(--bad);font-weight:500;white-space:normal">${esc(u.issue_text)}</div>
          <div class="meta">Cập nhật ${fmtDateTime(u.issue_at)}</div>
        </div>${CHEVRON}</button>`).join('')}` : ''}

    <h2 class="sec">Toàn bộ máy <span class="count">${(m.units || []).length}</span></h2>
    <div class="ugrid">${(m.units || []).map((u) => unitTile(u)).join('')}</div>
    ${UNIT_LEGEND}
    <div style="height:8px"></div>`);

  Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Đóng</button>
    ${can('loan.devices.create')
      ? `<button class="btn" onclick="AddDevice.open(${m.id})">Thêm máy</button>` : ''}`);
}

function addModelPhoto() {
  Photos.pick('images', async (keys) => {
    try {
      currentModel = await apiPost(`devices/models/${currentModel.id}/photos`,
                                   { photo_keys: keys });
      drawModelSheet();
      Cache.clear('models');
      renderDeviceList();
      toast(`Đã thêm ${keys.length} ảnh cho ${currentModel.name}.`);
    } catch (err) {
      toastError(err);
    }
  });
}

async function deleteModelPhoto(index) {
  const photo = currentModel.photos[index];
  if (!photo) return;
  try {
    await apiDel(`devices/models/${currentModel.id}/photos/${photo.id}`);
    currentModel = await apiGet(`devices/models/${currentModel.id}`);
    drawModelSheet();
    Cache.clear('models');
    renderDeviceList();
  } catch (err) {
    toastError(err);
  }
}

/* ---------- chi tiết một máy ---------- */

async function openUnit(unitId) {
  Sheet.open({ title: 'Đang tải…', body: loadingBox(), foot: '' });
  let data;
  try {
    data = await apiGet(`devices/units/${unitId}`);
  } catch (err) {
    Sheet.setBody(errorBox(err));
    return;
  }
  drawUnitSheet(data);
}

function drawUnitSheet(data) {
  const u = data.unit;
  const m = data.model;
  const history = [
    ...data.returns.map((r) => ({ at: r.returned_at, kind: 'return', r })),
    ...data.borrows.map((b) => ({ at: b.borrowed_at, kind: 'borrow', b })),
  ].sort((a, b) => new Date(b.at) - new Date(a.at));

  Sheet.setTitle(`<span class="mono">${esc(u.code)}</span>`);
  Sheet.setBody(`
    <div style="margin-bottom:16px">
      <span class="pill ${UNIT_PILL[u.status]}">${esc(UNIT_LABEL_LONG[u.status])}</span>
    </div>
    ${issueBanner(u, { withClearButton: true })}

    <dl class="kv" style="margin:0 0 18px">
      <dt>Loại</dt><dd>${esc(m.name)}</dd>
      <dt>Số thứ tự</dt><dd>Máy số ${u.no}</dd>
      ${u.holder_name ? `<dt>Đang ở chỗ</dt><dd>${esc(u.holder_name)}</dd>` : ''}
      ${u.serial ? `<dt>Serial</dt><dd class="mono">${esc(u.serial)}</dd>` : ''}
      ${u.note ? `<dt>Ghi chú</dt><dd>${esc(u.note)}</dd>` : ''}
    </dl>

    <h2 class="sec" style="margin-top:0">Thông số</h2>
    <div class="spec">${esc(m.info || 'Chưa có thông tin')}</div>

    <h2 class="sec">Lịch sử máy này <span class="count">${history.length}</span></h2>
    ${history.length ? `<div class="card"><ul class="tl">${history.map((h) => {
      if (h.kind === 'return') {
        const r = h.r;
        return `<li class="${COND_DOT[r.condition] || 'ok'}">
          <b>Nhận trả · ${esc((COND_LABEL[r.condition] || '').toLowerCase())}</b>
          <em>${fmtDate(r.returned_at)}${r.ticket_code ? ' · phiếu #' + esc(r.ticket_code) : ''}</em>
          ${r.note ? `<em style="color:var(--ink-2);margin-top:4px">Ghi chú: ${esc(r.note)}</em>` : ''}</li>`;
      }
      const b = h.b;
      return `<li class="${b.returned ? 'ok' : 'out'}">
        <b>${esc(b.borrower_name || '—')} mượn</b>
        <em>${fmtDate(b.borrowed_at)} → ${b.returned ? fmtDate(b.returned_at) : 'chưa trả'}
          · phiếu #${esc(b.ticket_code)}${b.lender_name ? ' · cho mượn: ' + esc(b.lender_name) : ''}</em></li>`;
    }).join('')}</ul></div>` : emptyBox('Máy này chưa từng được cho mượn')}
    <div style="height:8px"></div>`);

  const canLoan = can('loan.loans.create');
  const canReturn = can('loan.loans.update');
  let foot = '<button class="btn ghost" onclick="Sheet.close()">Đóng</button>';
  if (u.status === 'AVAIL' && canLoan) {
    foot += `<button class="btn" onclick="Borrow.open(${u.id})">Cho mượn máy này</button>`;
  } else if (u.status === 'OUT') {
    const openTicket = data.borrows.find((b) => !b.returned);
    foot = `<button class="btn ghost" onclick="openTicket('${esc(openTicket ? openTicket.ticket_code : '')}')">
        Mở phiếu</button>`;
    if (canReturn && openTicket) {
      foot += `<button class="btn" onclick="Return.open('${esc(openTicket.ticket_code)}', ${u.id})">
        Trả máy này</button>`;
    }
  } else if ((u.status === 'BROKEN' || u.status === 'MAINT') && can('loan.maintenance.create')
             && u.status === 'BROKEN') {
    foot += `<button class="btn" onclick="Maint.schedule(${u.id})">Đưa vào bảo trì</button>`;
  }
  Sheet.setFoot(foot);
}

async function clearUnitIssue(unitId, button) {
  try {
    await withBusy(button, 'Đang xoá…', () => apiPost(`devices/units/${unitId}/clear-issue`));
    toast('Đã xoá ghi chú tình trạng.');
    await openUnit(unitId);
    renderDeviceList();
    if ($('s-home').dataset.loaded) renderHome();
  } catch (err) {
    toastError(err);
  }
}

/* ---------- chi tiết phiếu ---------- */

async function openTicket(code) {
  if (!code) return;
  Sheet.open({ title: 'Đang tải…', body: loadingBox(), foot: '' });
  let t;
  try {
    t = await apiGet(`tickets/${encodeURIComponent(code)}`);
  } catch (err) {
    Sheet.setBody(errorBox(err));
    return;
  }

  const byModel = {};
  t.items.forEach((i) => { (byModel[i.model_name] ||= []).push(i); });

  Sheet.setTitle(`Phiếu <span class="mono">#${esc(t.code)}</span>`);
  Sheet.setBody(`
    <div style="margin-bottom:14px">
      <span class="pill ${TICKET_PILL[t.state]}">${esc(t.state_label)}</span>
    </div>
    <dl class="kv" style="margin:0 0 18px">
      <dt>Người mượn</dt><dd>${esc(t.borrower_name || '—')}${
        t.borrower_department ? ' · ' + esc(t.borrower_department) : ''}</dd>
      <dt>Người cho mượn</dt><dd>${esc(t.lender_name || '—')}</dd>
      <dt>Ngày mượn</dt><dd>${fmtDate(t.borrowed_at)}</dd>
      <dt>Đã mượn</dt><dd>${t.days_elapsed} ngày${
        t.returned_at ? ` (trả xong ${fmtDate(t.returned_at)})` : ''}</dd>
      ${t.note ? `<dt>Ghi chú</dt><dd>${esc(t.note)}</dd>` : ''}
    </dl>

    <h2 class="sec" style="margin-top:0">Máy trong phiếu <span class="count">${t.items.length}</span></h2>
    ${Object.entries(byModel).map(([name, items]) => `
      <div class="acc"><div class="ah" style="cursor:default">
        <div class="nm"><b>${esc(name)}</b>
          <em>${items.length} máy · ${items.filter((i) => !i.returned).length} chưa trả</em></div></div>
        <div class="ab"><div class="ugrid">${items.map((i) => `
          <button class="u ${i.returned ? 'AVAIL' : 'OUT'}" onclick="openUnit(${i.unit_id})"
                  title="${esc(i.code)}">
            <b>${esc(i.code.split('-').pop())}</b><i>${i.returned ? 'Đã trả' : 'Chưa trả'}</i>
          </button>`).join('')}</div></div>
      </div>`).join('')}

    ${t.returns.length ? `<h2 class="sec">Ghi chú khi trả <span class="count">${t.returns.length}</span></h2>
      <div class="card"><ul class="tl">${t.returns.map((r) => `
        <li class="${COND_DOT[r.condition] || 'ok'}">
          <b><span class="mono">${esc(r.unit_code)}</span> · ${
            esc((COND_LABEL[r.condition] || '').toLowerCase())}</b>
          <em>${fmtDate(r.returned_at)}${r.note ? ' — ' + esc(r.note) : ' — không có ghi chú riêng'}</em>
        </li>`).join('')}</ul></div>` : ''}
    <div style="height:8px"></div>`);

  Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Đóng</button>
    ${t.open_units > 0 && can('loan.loans.update')
      ? `<button class="btn" onclick="Return.open('${esc(t.code)}')">Nhận trả ${t.open_units} máy</button>`
      : ''}`);
}

/* ================================================================
   NHẬP / XUẤT KHO
   ================================================================ */

const Stock = { tab: 'imports' };

Stock.setTab = function (key) {
  Stock.tab = key;
  const seg = document.querySelector('#s-stock .seg');
  if (!seg) { renderStock(); return; }
  seg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.k === key));
  $('stockBody').innerHTML = skeletonRows(3);
  renderStockBody();
};


async function renderStock() {
  $('s-stock').innerHTML = `
    <div class="seg">
      ${[['imports', 'Phiếu nhập'], ['exports', 'Phiếu xuất']]
        .map(([k, label]) => `<button class="${Stock.tab === k ? 'on' : ''}" data-k="${k}"
          onclick="Stock.setTab('${k}')">${esc(label)}</button>`).join('')}
    </div>
    <div id="stockBody">${skeletonRows(3)}</div>`;
  await renderStockBody();
}

async function renderStockBody() {
  const box = $('stockBody');
  if (!box) return;
  try {

    const isImport = Stock.tab === 'imports';
    const rows = await apiGet(isImport ? 'stock/imports' : 'stock/exports', { limit: 200 });

    if (isWide()) {
      box.innerHTML = (dataTable(
        [{ t: 'Ngày', cls: 'nowrap' }, { t: 'Sản phẩm' }, { t: 'Model', cls: 'nowrap' },
         isImport ? { t: 'Hãng' } : { t: 'Mục đích' },
         isImport ? { t: 'Tình trạng' } : { t: 'Nơi nhận' },
         { t: 'Số lượng', cls: 'num' }, { t: 'Ảnh', cls: 'num' }, { t: 'Người thực hiện' }],
        rows.map((r) => ({
          click: `openStockRecord('${isImport ? 'IN' : 'OUT'}', ${r.id})`,
          cells: [
            fmtDate(r.at),
            `<span class="strong">${esc(r.product_name)}</span>`,
            `<span class="mono">${esc(r.model_code)}</span>`,
            esc((isImport ? r.brand : r.purpose) || '—'),
            esc((isImport ? r.condition : r.destination) || '—'),
            `<span class="pill ${isImport ? 'p-ok' : 'p-out'}">${isImport ? '+' : '−'}${r.qty}</span>`,
            (r.photos && r.photos.length) ? String(r.photos.length) : '—',
            `${esc(r.created_by_name || '—')}<span class="sub mono">${
              esc(r.created_by_username || '')}</span>`,
          ],
        })))
        || emptyBox(isImport ? 'Chưa có phiếu nhập nào' : 'Chưa có phiếu xuất nào'));
      return;
    }

    box.innerHTML = (rows.length ? `<div class="rows">${rows.map((r) => `
      <button class="row" onclick="openStockRecord('${isImport ? 'IN' : 'OUT'}', ${r.id})">
        <div class="main">
          <div class="title">${esc(r.product_name)}</div>
          <div class="meta mono">${esc(r.model_code)}${r.brand ? ' · ' + esc(r.brand) : ''}</div>
          <div class="meta">${fmtDate(r.at)}${
            isImport ? (r.condition ? ' · ' + esc(r.condition) : '')
                     : ' · ' + esc(r.purpose || '') + (r.destination ? ' — ' + esc(r.destination) : '')}${
            r.photos && r.photos.length ? ` · ${r.photos.length} ảnh` : ''}</div>
        </div>
        <div class="rt">
          <span class="pill ${isImport ? 'p-ok' : 'p-out'}">${isImport ? '+' : '−'}${r.qty}</span>
          <span class="pill p-mute" style="font-family:'IBM Plex Mono',monospace">${
            esc(r.created_by_username || '—')}</span>
        </div>${CHEVRON}</button>`).join('')}</div>`
      : emptyBox(isImport ? 'Chưa có phiếu nhập nào' : 'Chưa có phiếu xuất nào'));
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderStockBody()');
  }
}

async function openStockRecord(kind, id) {
  Sheet.open({ title: 'Đang tải…', body: loadingBox(), foot: '' });
  try {
    const rows = await apiGet(kind === 'IN' ? 'stock/imports' : 'stock/exports', { limit: 500 });
    const r = rows.find((x) => x.id === id);
    if (!r) { Sheet.setBody(emptyBox('Không tìm thấy phiếu')); return; }

    Sheet.setTitle(`${kind === 'IN' ? 'Phiếu nhập' : 'Phiếu xuất'} · ${esc(r.product_name)}`);
    Sheet.setBody(`
      <div style="margin-bottom:14px">
        <span class="pill ${kind === 'IN' ? 'p-ok' : 'p-out'}">${
          kind === 'IN' ? '+' + r.qty + ' vào kho' : '−' + r.qty + ' ra khỏi kho'}</span>
      </div>
      <dl class="kv" style="margin:0 0 18px">
        <dt>Sản phẩm</dt><dd>${esc(r.product_name)}</dd>
        <dt>Model</dt><dd class="mono">${esc(r.model_code)}</dd>
        ${kind === 'IN'
          ? `${r.brand ? `<dt>Hãng</dt><dd>${esc(r.brand)}</dd>` : ''}
             ${r.condition ? `<dt>Tình trạng</dt><dd>${esc(r.condition)}</dd>` : ''}`
          : `<dt>Mục đích</dt><dd>${esc(r.purpose || '—')}</dd>
             ${r.destination ? `<dt>Nơi nhận</dt><dd>${esc(r.destination)}</dd>` : ''}`}
        <dt>Số lượng</dt><dd>${r.qty}</dd>
        <dt>Ngày</dt><dd>${fmtDate(r.at)}</dd>
        <dt>Người thực hiện</dt><dd>${esc(r.created_by_name || '—')}<br>
          <span class="mono" style="font-weight:400;color:var(--muted);font-size:14.5px">${
            esc(r.created_by_username || '')}</span></dd>
        ${r.note ? `<dt>Ghi chú</dt><dd>${esc(r.note)}</dd>` : ''}
      </dl>
      <h2 class="sec" style="margin-top:0">Ảnh sản phẩm
        <span class="count">${(r.photos || []).length}</span></h2>
      ${photoGrid(r.photos)}
      <div style="height:8px"></div>`);
    Sheet.setFoot('<button class="btn ghost" onclick="Sheet.close()">Đóng</button>');
  } catch (err) {
    Sheet.setBody(errorBox(err));
  }
}

/* ================================================================
   NHÂN SỰ · PHÒNG BAN · BẢO TRÌ · TÀI KHOẢN · EMAIL
   ================================================================ */

const StaffScreen = { dept: null, q: '' };

let staffSearchTimer = null;
StaffScreen.onSearch = function (value) {
  StaffScreen.q = value;
  clearTimeout(staffSearchTimer);
  staffSearchTimer = setTimeout(() => renderStaffBody(), 300);
};

async function renderStaffScreen() {
  const focused = document.activeElement && document.activeElement.id === 'staffQ';
  $('s-staff').innerHTML = `
    <div class="search">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
      <input id="staffQ" placeholder="Hoặc gõ thẳng tên nhân sự…"
             value="${esc(StaffScreen.q)}" oninput="StaffScreen.onSearch(this.value)">
    </div>
    <div id="staffBody">${skeletonRows(3)}</div>`;
  if (focused) $('staffQ').focus();
  await renderStaffBody();
}

async function renderStaffBody() {
  const box = $('staffBody');
  if (!box) return;
  let departments, staff;
  try {
    [departments, staff] = await Promise.all([loadDepartments(), loadStaff()]);
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderStaffBody()');
    return;
  }

  const q = StaffScreen.q.trim().toLowerCase();
  box.className = 'rows';

  if (q) {
    const matches = staff.filter((s) =>
      `${s.full_name} ${s.department_name || ''} ${s.email || ''}`.toLowerCase().includes(q));
    box.className = isWide() ? '' : 'rows';
    box.innerHTML = isWide()
      ? (staffTable(matches, true) || emptyBox('Không tìm thấy nhân sự'))
      : (matches.map((s) => staffRow(s, true)).join('') || emptyBox('Không tìm thấy nhân sự'));
    $('barSub').textContent = `${matches.length} kết quả`;
    return;
  }

  // Hai cấp: chọn phòng ban trước, rồi mới liệt kê nhân sự của phòng đó
  if (StaffScreen.dept === null) {
    if (isWide()) {
      box.className = '';
      box.innerHTML = dataTable(
        [{ t: 'Phòng ban' }, { t: 'Trưởng bộ phận' }, { t: 'Email trưởng bộ phận' },
         { t: 'Nhân sự', cls: 'num' }, { t: 'Đang giữ máy', cls: 'num' }],
        departments.map((d) => ({
          click: `StaffScreen.dept=${d.id};renderStaffBody()`,
          cells: [
            `<span class="strong">${esc(d.name)}</span>`,
            esc(d.head_name || '— chưa đặt'),
            d.head_email ? `<span class="mono" style="font-size:15px">${esc(d.head_email)}</span>` : '—',
            String(d.staff_count),
            d.units_held ? String(d.units_held) : '—',
          ],
        })))
        || emptyBox('Chưa có phòng ban nào');
    } else {
      box.className = 'rows';
      box.innerHTML = departments.map((d) => `
        <button class="row" onclick="StaffScreen.dept=${d.id};renderStaffBody()">
          <div class="pick" style="border:0;padding:0;background:none;width:auto;flex:0 0 auto">
            <div class="av">${esc(deptInitials(d.name))}</div></div>
          <div class="main">
            <div class="title">${esc(d.name)}</div>
            <div class="meta">${d.staff_count} nhân sự</div>
            <div class="meta">Trưởng bộ phận: ${esc(d.head_name || 'chưa đặt')}</div>
          </div>
          <div class="rt">
            <span class="num">${d.staff_count}</span>
            ${d.units_held ? `<span class="pill p-out">${d.units_held} máy</span>` : ''}
          </div>${CHEVRON}</button>`).join('') || emptyBox('Chưa có phòng ban nào');
    }
    $('barSub').textContent = `${departments.length} phòng ban · chọn phòng để xem nhân sự`;
    return;
  }

  const dept = departments.find((d) => d.id === StaffScreen.dept);
  if (!dept) { StaffScreen.dept = null; return renderStaffBody(); }
  const people = staff.filter((s) => s.department_id === dept.id);

  box.className = isWide() ? '' : 'rows';
  box.innerHTML = `
    <button class="chip" style="margin-bottom:12px;align-self:flex-start"
            onclick="StaffScreen.dept=null;renderStaffBody()">‹ Tất cả phòng ban</button>
    <div style="font-size:14.5px;color:var(--muted);margin-bottom:10px">
      Phòng <b style="color:var(--ink)">${esc(dept.name)}</b> · ${people.length} nhân sự ·
      trưởng bộ phận ${esc(dept.head_name || 'chưa đặt')}</div>
    ${(isWide() ? staffTable(people, false) : people.map((s) => staffRow(s, false)).join(''))
      || emptyBox('Phòng này chưa có nhân sự nào')}`;
  $('barSub').textContent = `Phòng ${dept.name} · ${people.length} nhân sự`;
}

function staffTable(people, showDept) {
  const clickable = can('loan.staff.update');
  const head = [{ t: 'Họ tên' }];
  if (showDept) head.push({ t: 'Phòng ban' });
  head.push({ t: 'Email' }, { t: 'Vai trò', cls: 'nowrap' },
            { t: 'Đang giữ' }, { t: 'Số máy', cls: 'num' });

  return dataTable(head, people.map((s) => {
    const cells = [`<span class="strong">${esc(s.full_name)}</span>`];
    if (showDept) cells.push(esc(s.department_name || '—'));
    cells.push(
      s.email ? `<span class="mono" style="font-size:15px">${esc(s.email)}</span>`
              : '<span style="color:var(--muted)">chưa có email</span>',
      `${s.is_head ? '<span class="pill p-out">Trưởng bộ phận</span>' : ''}${
        s.status === 'ACTIVE' ? '' : '<span class="pill p-mute">Đã nghỉ</span>'}${
        s.is_head || s.status !== 'ACTIVE' ? '' : '<span style="color:var(--muted)">Nhân viên</span>'}`,
      s.units_held.length
        ? `<span class="mono" style="font-size:15px;color:var(--out)">${esc(s.units_held.join(', '))}</span>`
        : '<span style="color:var(--muted)">—</span>',
      s.units_held.length ? String(s.units_held.length) : '—');
    return { cells, click: clickable ? `StaffForm.open(${s.id})` : null };
  }));
}

function staffRow(s, showDept) {
  const clickable = can('loan.staff.update');
  return `<${clickable ? 'button' : 'div'} class="row"
      ${clickable ? `onclick="StaffForm.open(${s.id})"` : 'style="cursor:default"'}>
    <div class="pick" style="border:0;padding:0;background:none;width:auto;flex:0 0 auto">
      <div class="av">${esc(initials(s.full_name))}</div></div>
    <div class="main">
      <div class="title">${esc(s.full_name)}</div>
      <div class="meta">${showDept && s.department_name ? esc(s.department_name) + ' · ' : ''}${
        s.is_head ? 'trưởng bộ phận · ' : ''}${esc(s.email || 'chưa có email')}</div>
      ${s.units_held.length ? `<div class="meta mono" style="margin-top:4px;color:var(--out)">
        Đang giữ: ${esc(s.units_held.join(', '))}</div>` : ''}
    </div>
    <div class="rt">
      ${s.status === 'ACTIVE' ? '' : '<span class="pill p-mute">Đã nghỉ</span>'}
      ${s.units_held.length ? `<span class="pill p-out">${s.units_held.length} máy</span>` : ''}
    </div>${clickable ? CHEVRON : ''}</${clickable ? 'button' : 'div'}>`;
}

async function renderDepartments() {
  const box = $('s-depts');
  box.innerHTML = `<div class="rows">${skeletonRows(4)}</div>`;
  let departments;
  try {
    departments = await loadDepartments();
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderDepartments()');
    return;
  }
  const clickable = can('loan.departments.update');
  if (isWide()) {
    box.innerHTML = (dataTable(
      [{ t: 'Phòng ban' }, { t: 'Trưởng bộ phận' },
       { t: 'Email nhận thông báo' }, { t: 'Nhân sự', cls: 'num' }, { t: 'Đang giữ máy', cls: 'num' }],
      departments.map((d) => ({
        click: clickable ? `DeptForm.open(${d.id})` : null,
        cls: d.head_name ? '' : 'warn',
        cells: [
          `<span class="strong">${esc(d.name)}</span>`,
          d.head_name ? esc(d.head_name)
            : '<span class="bad">chưa đặt — thư sẽ về địa chỉ quản lý chung</span>',
          d.head_email ? `<span class="mono" style="font-size:15px">${esc(d.head_email)}</span>` : '—',
          String(d.staff_count),
          d.units_held ? String(d.units_held) : '—',
        ],
      })))
      || emptyBox('Chưa có phòng ban nào'));
    return;
  }

  box.innerHTML = `<div class="rows">${departments.map((d) => `
    <${clickable ? 'button' : 'div'} class="row"
        ${clickable ? `onclick="DeptForm.open(${d.id})"` : 'style="cursor:default"'}>
      <div class="pick" style="border:0;padding:0;background:none;width:auto;flex:0 0 auto">
        <div class="av">${esc(deptInitials(d.name))}</div></div>
      <div class="main">
        <div class="title">${esc(d.name)}</div>
        <div class="meta">Trưởng bộ phận: ${esc(d.head_name || 'chưa đặt')}</div>
        ${d.head_email ? `<div class="meta mono" style="font-size:14px">${esc(d.head_email)}</div>` : ''}
        <div class="meta">${d.staff_count} nhân sự${
          d.units_held ? ' · đang giữ ' + d.units_held + ' máy' : ''}</div>
      </div>
      <div class="rt"><span class="num">${d.staff_count}</span></div>
      ${clickable ? CHEVRON : ''}</${clickable ? 'button' : 'div'}>`).join('')
    || emptyBox('Chưa có phòng ban nào')}</div>`;
}

const MaintScreen = { tab: 'open' };

MaintScreen.setTab = function (key) {
  MaintScreen.tab = key;
  const seg = document.querySelector('#s-maint .seg');
  if (!seg) { renderMaint(); return; }
  seg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.k === key));
  renderMaintList();
};

async function renderMaint() {
  $('s-maint').innerHTML = `
    <div class="seg">
      ${[['open', 'Đang bảo trì'], ['broken', 'Đang hỏng'], ['done', 'Đã xong']]
        .map(([k, label]) => `<button class="${MaintScreen.tab === k ? 'on' : ''}" data-k="${k}"
          onclick="MaintScreen.setTab('${k}')">${esc(label)}</button>`).join('')}
    </div>
    <div class="rows" id="maintList">${skeletonRows(3)}</div>`;
  await renderMaintList();
}

async function renderMaintList() {
  const box = $('maintList');
  if (!box) return;
  box.innerHTML = skeletonRows(3);
  try {
    if (MaintScreen.tab === 'broken') {
      const rows = await apiGet('maintenance/broken');
      if (isWide()) {
        box.className = '';
        box.innerHTML = dataTable(
          [{ t: 'Mã máy', cls: 'nowrap' }, { t: 'Loại thiết bị' }, { t: 'Ghi chú tình trạng' },
           { t: 'Trạng thái', cls: 'nowrap' }],
          rows.map((u) => ({
            click: `openUnit(${u.unit_id})`,
            cls: 'flag',
            cells: [
              `<span class="mono strong">${esc(u.code)}</span>`,
              esc(u.model_name),
              u.issue_text ? `<span class="bad">${esc(u.issue_text)}</span>`
                           : '<span style="color:var(--muted)">không có ghi chú</span>',
              '<span class="pill p-bad">Hỏng</span>',
            ],
          })))
          || emptyBox('Không có máy nào đang hỏng');
        return;
      }
      box.className = 'rows';
      box.innerHTML = rows.map((u) => `
        <button class="row flag" onclick="openUnit(${u.unit_id})">
          <div class="main">
            <div class="title"><span class="mono">${esc(u.code)}</span> · ${esc(u.model_name)}</div>
            ${u.issue_text ? `<div class="meta" style="color:var(--bad);white-space:normal">${
              esc(u.issue_text)}</div>` : ''}
            <div class="meta">Không thể cho mượn cho đến khi sửa xong</div>
          </div>
          <div class="rt"><span class="pill p-bad">Hỏng</span></div>${CHEVRON}</button>`).join('')
        || emptyBox('Không có máy nào đang hỏng');
      return;
    }
    const rows = await apiGet('maintenance', {
      status: MaintScreen.tab === 'open' ? 'SCHEDULED' : 'DONE', limit: 300,
    });
    const canFinish = can('loan.maintenance.update');

    if (isWide()) {
      box.className = '';
      const head = [{ t: 'Mã máy', cls: 'nowrap' }, { t: 'Loại thiết bị' }, { t: 'Lý do / ghi chú' },
                    { t: 'Bắt đầu', cls: 'nowrap' }, { t: 'Hoàn tất', cls: 'nowrap' },
                    { t: 'Trạng thái', cls: 'nowrap' }];
      if (MaintScreen.tab === 'open' && canFinish) head.push({ t: '', cls: 'nowrap' });

      box.innerHTML = dataTable(head, rows.map((m) => {
        const cells = [
          `<span class="mono strong">${esc(m.unit_code)}</span>`,
          esc(m.model_name),
          m.note ? esc(m.note) : '<span style="color:var(--muted)">—</span>',
          fmtDate(m.scheduled_at),
          m.completed_at ? fmtDate(m.completed_at) : '—',
          `<span class="pill ${m.status === 'DONE' ? 'p-ok' : 'p-maint'}">${
            m.status === 'DONE' ? 'Đã xong' : 'Đang bảo trì'}</span>`,
        ];
        if (MaintScreen.tab === 'open' && canFinish) {
          cells.push(`<button class="btn ghost sm" style="width:auto;padding:0 12px"
            onclick="event.stopPropagation();Maint.complete(${m.id}, this)">Hoàn tất</button>`);
        }
        return { cells, cls: MaintScreen.tab === 'open' ? 'warn' : '' };
      })) || emptyBox(MaintScreen.tab === 'open'
        ? 'Không có máy nào đang bảo trì' : 'Chưa có lịch nào hoàn tất');
      return;
    }

    box.className = 'rows';
    box.innerHTML = rows.map((m) => `
      <div class="row ${MaintScreen.tab === 'open' ? 'warn' : ''}"
           style="cursor:default;flex-direction:column;align-items:stretch;gap:0">
        <div style="display:flex;gap:12px;width:100%;align-items:flex-start">
          <div class="main">
            <div class="title"><span class="mono">${esc(m.unit_code)}</span> · ${esc(m.model_name)}</div>
            ${m.note ? `<div class="meta" style="white-space:normal">${esc(m.note)}</div>` : ''}
            <div class="meta" style="margin-top:3px">Bắt đầu ${fmtDate(m.scheduled_at)}${
              m.completed_at ? ' · xong ' + fmtDate(m.completed_at) : ''}</div>
          </div>
          <div class="rt"><span class="pill ${m.status === 'DONE' ? 'p-ok' : 'p-maint'}">${
            m.status === 'DONE' ? 'Đã xong' : 'Đang bảo trì'}</span></div>
        </div>
        ${m.status === 'SCHEDULED' && can('loan.maintenance.update')
          ? `<button class="btn ghost sm" style="margin-top:11px"
              onclick="Maint.complete(${m.id}, this)">Đánh dấu hoàn tất</button>` : ''}
      </div>`).join('') || emptyBox(MaintScreen.tab === 'open'
        ? 'Không có máy nào đang bảo trì' : 'Chưa có lịch nào hoàn tất');
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderMaint()');
  }
}

async function renderUsers() {
  const box = $('s-users');
  box.innerHTML = `<div class="rows">${skeletonRows(3)}</div>`;
  try {
    const users = await apiGet('users', { limit: 200 });
    const admins = users.filter((u) => u.role === 'ADMIN').length;
    const head = `<div style="font-size:15px;color:var(--muted);margin-bottom:12px">
      ${users.length} tài khoản · ${admins} quản trị viên</div>`;

    if (isWide()) {
      box.innerHTML = head + dataTable(
        [{ t: 'Họ tên' }, { t: 'Tài khoản', cls: 'nowrap' }, { t: 'Vai trò', cls: 'nowrap' },
         { t: 'Quyền', cls: 'nowrap' }, { t: 'Trạng thái', cls: 'nowrap' }],
        users.map((u) => ({
          click: `Perms.open(${u.id})`,
          cells: [
            `<span class="strong">${esc(u.full_name || u.username)}</span>${
              u.username === ME.username ? '<span class="sub">đang đăng nhập</span>' : ''}`,
            `<span class="mono">${esc(u.username)}</span>`,
            `<span class="pill ${u.role === 'ADMIN' ? 'p-out' : 'p-mute'}">${esc(u.role)}</span>`,
            u.role === 'ADMIN' ? 'Toàn quyền' : `${u.permissions.length} / 28`,
            u.is_active ? '<span class="pill p-ok">Đang dùng</span>'
                        : '<span class="pill p-bad">Vô hiệu</span>',
          ],
        })));
      return;
    }

    box.innerHTML = head + `<div class="rows">${users.map((u) => `
      <button class="row" onclick="Perms.open(${u.id})">
        <div class="pick" style="border:0;padding:0;background:none;width:auto;flex:0 0 auto">
          <div class="av">${esc(initials(u.full_name || u.username))}</div></div>
        <div class="main">
          <div class="title">${esc(u.full_name || u.username)}${
            u.username === ME.username ? ' · đang đăng nhập' : ''}</div>
          <div class="meta mono">${esc(u.username)}</div>
          <div class="meta">${u.role === 'ADMIN' ? 'Toàn quyền' : u.permissions.length + ' / 28 quyền'}</div>
        </div>
        <div class="rt">
          <span class="pill ${u.role === 'ADMIN' ? 'p-out' : 'p-mute'}">${esc(u.role)}</span>
          ${u.is_active ? '' : '<span class="pill p-bad">Vô hiệu</span>'}
        </div>${CHEVRON}</button>`).join('')}</div>`;
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderUsers()');
  }
}

async function renderEmailLogs() {
  const box = $('s-email');
  box.innerHTML = `<div class="rows">${skeletonRows(4)}</div>`;
  try {
    const rows = await apiGet('email-logs', { limit: 100 });
    const statusPill = (s) => s === 'DONE'
      ? '<span class="pill p-ok">Đã gửi</span>'
      : s === 'SKIPPED' ? '<span class="pill p-mute">Bỏ qua</span>'
                        : '<span class="pill p-bad">Thất bại</span>';

    if (isWide()) {
      box.innerHTML = dataTable(
        [{ t: 'Thời điểm', cls: 'nowrap' }, { t: 'Tiêu đề' }, { t: 'Người nhận' },
         { t: 'Kết quả', cls: 'nowrap' }],
        rows.map((r) => ({
          cls: r.error_message ? 'flag' : '',
          cells: [
            `<span class="mono" style="font-size:15px">${fmtDateTime(r.created_at)}</span>`,
            `<span class="strong">${esc(r.subject)}</span>${
              r.error_message ? `<span class="sub" style="color:var(--bad)">${esc(r.error_message)}</span>` : ''}`,
            `<span style="font-size:15px">${esc(r.recipients)}</span>`,
            statusPill(r.status),
          ],
        }))) || emptyBox('Chưa có thư nào được gửi');
      return;
    }

    box.innerHTML = `<div class="rows">${rows.map((r) => `
      <div class="row" style="cursor:default">
        <div class="main">
          <div class="title" style="white-space:normal">${esc(r.subject)}</div>
          <div class="meta" style="white-space:normal">${esc(r.recipients)}</div>
          <div class="meta mono" style="margin-top:3px">${fmtDateTime(r.created_at)}</div>
          ${r.error_message ? `<div class="meta" style="color:var(--bad);white-space:normal">${
            esc(r.error_message)}</div>` : ''}
        </div>
        <div class="rt"><span class="pill ${
          r.status === 'DONE' ? 'p-ok' : r.status === 'SKIPPED' ? 'p-mute' : 'p-bad'}">${
          r.status === 'DONE' ? 'Đã gửi' : r.status === 'SKIPPED' ? 'Bỏ qua' : 'Thất bại'}</span></div>
      </div>`).join('') || emptyBox('Chưa có thư nào được gửi')}</div>`;
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderEmailLogs()');
  }
}

/* ---------- màn hình Thêm ---------- */

function renderMore() {
  // Trên máy tính, mọi mục đã nằm sẵn ở cột trái — lặp lại ở đây chỉ gây rối.
  // Màn hình này khi đó chỉ còn là trang tài khoản.
  const rows = [];
  if (isWide()) return renderAccountPage();

  // Thanh dưới chỉ đủ 5 mục; Kho hàng chiếm chỗ nên lập phiếu lùi vào đây
  if (can('import_export.view')) {
    rows.push(['stock', 'Nhập / Xuất kho', 'Lập phiếu nhập và phiếu xuất']);
  }
  if (can('loan.staff.view')) {
    rows.push(['staff', 'Nhân sự', 'Xem theo từng phòng ban, ai đang giữ máy nào']);
  }
  if (can('loan.departments.view')) {
    rows.push(['depts', 'Phòng ban &amp; trưởng bộ phận', 'Người nhận email thông báo của phòng']);
  }
  if (can('loan.maintenance.view')) {
    rows.push(['maint', 'Bảo trì &amp; hỏng', 'Máy không sẵn sàng cho mượn']);
  }

  const system = [];
  if (can('users.view')) {
    system.push(['users', 'Tài khoản &amp; phân quyền', 'Quản lý người dùng và 28 quyền']);
  }
  if (can('loan.loans.view')) {
    system.push(['email', 'Lịch sử gửi mail', 'Thư báo phiếu mới, cảnh báo quá hạn, báo cáo']);
  }

  const link = ([key, title, meta]) => `
    <button class="row" onclick="openScreen('${key}')">
      <div class="main"><div class="title">${title}</div>
        <div class="meta">${meta}</div></div>${CHEVRON}</button>`;

  $('s-more').innerHTML = `
    <div class="locked" style="margin-bottom:6px">
      <div class="av">${esc(initials(ME.fullName || ME.username))}</div>
      <div><b>${esc(ME.fullName || ME.username)}</b><em>${esc(ME.username)}</em></div>
      <span class="pill ${IS_ADMIN ? 'p-out' : 'p-mute'}" style="margin-left:auto">${esc(ME.role)}</span>
    </div>

    ${rows.length ? `<h2 class="sec">Danh mục</h2>
      <div class="rows">${rows.map(link).join('')}</div>` : ''}

    <h2 class="sec">Hệ thống</h2>
    <div class="rows">
      ${system.map(link).join('')}
      <button class="row" onclick="ChangePassword.open()">
        <div class="main"><div class="title">Đổi mật khẩu</div>
          <div class="meta">Cập nhật mật khẩu của chính bạn</div></div>${CHEVRON}</button>
      <a class="row" href="/logout" style="text-decoration:none;color:inherit">
        <div class="main"><div class="title">Đăng xuất</div>
          <div class="meta">Kết thúc phiên làm việc</div></div>${CHEVRON}</a>
    </div>

    <div style="height:12px"></div>`;
}

/** Trang tài khoản trên máy tính — không lặp lại các mục đã có ở cột trái. */
function renderAccountPage() {
  $('s-more').innerHTML = `
    <div style="max-width:460px">
        <h2 class="sec" style="margin-top:0">Tài khoản đang đăng nhập</h2>
        <div class="card">
          <div class="locked" style="background:none;padding:0;margin-bottom:16px">
            <div class="av" style="width:44px;height:44px;flex:0 0 44px;font-size:17.5px">${
              esc(initials(ME.fullName || ME.username))}</div>
            <div><b style="font-size:18.5px">${esc(ME.fullName || ME.username)}</b>
              <em>${esc(ME.username)}</em></div>
            <span class="pill ${IS_ADMIN ? 'p-out' : 'p-mute'}" style="margin-left:auto">${
              esc(ME.role)}</span>
          </div>
          <dl class="kv" style="margin:0 0 16px">
            <dt>Quyền</dt><dd>${IS_ADMIN ? 'Toàn quyền (28 / 28)'
              : `${PERMS.size} / 28 quyền`}</dd>
          </dl>
          <div style="display:flex;gap:9px">
            <button class="btn ghost sm" style="flex:1" onclick="ChangePassword.open()">
              Đổi mật khẩu</button>
            <a class="btn ghost sm" href="/logout"
               style="text-decoration:none;flex:1">Đăng xuất</a>
          </div>
        </div>
    </div>`;
}

/* ================================================================
   KHO HÀNG — bảng điều khiển hàng hoá đang lưu kho.

   Trang này chỉ ĐỌC. Số liệu đổ sang từ các phiếu ở màn Nhập / Xuất:
   tồn kho = tổng nhập − tổng xuất, gom theo cặp (tên sản phẩm + model).
   Lập phiếu vẫn nằm bên màn Nhập / Xuất, ở đây chỉ mở thẳng sang.
   ================================================================ */

const Wh = {
  q: '',
  sort: 'on_hand',        // on_hand | imported | exported | last_in | name
  only: 'all',            // all | low | out
  place: '',              // '' = mọi vị trí, '--' = chưa khai vị trí
  summary: null,
  rows: [],
  timer: null,
};

async function renderWarehouse() {
  const box = $('s-warehouse');
  box.innerHTML = `<div id="whHead"></div><div id="whBody">${skeletonRows(4)}</div>`;

  try {
    const [summary, rows] = await Promise.all([
      apiGet('stock/summary'),
      apiGet('stock/levels'),
    ]);
    Wh.summary = summary;
    Wh.rows = rows;
  } catch (err) {
    box.innerHTML = errorBox(err, 'renderWarehouse()');
    return;
  }

  const s = Wh.summary;

  $('whHead').innerHTML = `
    <div class="kpis" style="margin-bottom:14px">
      <div class="kpi" style="cursor:default">
        <div class="k"><span class="dot" style="background:var(--ok)"></span>Tồn kho</div>
        <div class="v">${s.on_hand}</div>
        <div class="sub">${s.products} mặt hàng</div>
      </div>
      <div class="kpi" style="cursor:default">
        <div class="k"><span class="dot" style="background:var(--out)"></span>Đã nhập</div>
        <div class="v">${s.imported}</div>
      </div>
      <div class="kpi" style="cursor:default">
        <div class="k"><span class="dot" style="background:var(--maint)"></span>Đã xuất</div>
        <div class="v">${s.exported}</div>
      </div>
      <button class="kpi ${s.out_of_stock ? 'alert' : ''}"
              onclick="Wh.setOnly('${s.out_of_stock ? 'out' : 'low'}')">
        <div class="k"><span class="dot" style="background:var(--bad)"></span>Cần nhập thêm</div>
        <div class="v">${s.out_of_stock + (s.low_stock || 0)}</div>
        <div class="sub">${s.out_of_stock} hết · ${s.low_stock || 0} sắp hết</div>
      </button>
    </div>
    <div class="toolrow" style="margin-bottom:12px">
      <div class="search" style="flex:1 1 220px;margin:0">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input id="whQ" placeholder="Tìm tên hàng hoá, model, vị trí…"
               value="${esc(Wh.q)}" oninput="Wh.onSearch(this.value)">
      </div>
      <select class="minisel" onchange="Wh.setOnly(this.value)">
        ${[['all', 'Tất cả mặt hàng'], ['low', 'Sắp hết'], ['out', 'Hết hàng']]
          .map(([k, t]) => `<option value="${k}" ${Wh.only === k ? 'selected' : ''}>${t}</option>`).join('')}
      </select>
      <select class="minisel" id="whPlaceSel" onchange="Wh.setPlace(this.value)">
        ${whPlaceOptions()}
      </select>
      <select class="minisel" onchange="Wh.setSort(this.value)">
        ${[['on_hand', 'Tồn nhiều nhất'], ['exported', 'Xuất nhiều nhất'],
           ['imported', 'Nhập nhiều nhất'], ['last_in', 'Nhập gần đây'],
           ['name', 'Tên A→Z']]
          .map(([k, t]) => `<option value="${k}" ${Wh.sort === k ? 'selected' : ''}>${t}</option>`).join('')}
      </select>
      <button class="btn ghost sm tool" onclick="downloadFile('stock/export-excel')">
        <svg viewBox="0 0 24 24"><path d="M12 3v12M7 11l5 5 5-5M5 21h14"/></svg>
        Xuất Excel</button>
      <button class="btn ghost sm tool" onclick="openScreen('stock')">
        <svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h10M4 18h7M20 15l-3 3 3 3"/></svg>
        Phiếu nhập / xuất</button>
    </div>`;
  drawWarehouseList();
}

/** Danh sách vị trí lấy thẳng từ dữ liệu: kho khai tới đâu lọc được tới đó. */
function whPlaceOptions() {
  const places = [...new Set(Wh.rows.map((r) => r.location).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'vi'));
  return `<option value="" ${Wh.place === '' ? 'selected' : ''}>Mọi vị trí kho</option>
    <option value="--" ${Wh.place === '--' ? 'selected' : ''}>Chưa khai vị trí</option>
    ${places.map((p) => `<option value="${esc(p)}" ${
      Wh.place === p ? 'selected' : ''}>${esc(p)}</option>`).join('')}`;
}

/** Lọc và sắp xếp ngay trên máy — kho chỉ vài trăm dòng, khỏi gọi lại máy chủ. */
function warehouseRows() {
  const kw = Wh.q.trim().toLowerCase();
  const low = (Wh.summary && Wh.summary.low_threshold) || 3;
  const out = Wh.rows.filter((r) => {
    if (Wh.only === 'out' && r.on_hand > 0) return false;
    if (Wh.only === 'low' && !(r.on_hand > 0 && r.on_hand <= low)) return false;
    if (Wh.place === '--' && r.location) return false;
    if (Wh.place && Wh.place !== '--' && r.location !== Wh.place) return false;
    if (!kw) return true;
    return `${r.product_name} ${r.model_code} ${r.location || ''}`.toLowerCase().includes(kw);
  });
  const by = Wh.sort;
  if (by === 'name') {
    out.sort((a, b) => a.product_name.localeCompare(b.product_name, 'vi'));
  } else if (by === 'last_in') {
    out.sort((a, b) => String(b.last_in || '').localeCompare(String(a.last_in || '')));
  } else {
    out.sort((a, b) => b[by] - a[by] || a.product_name.localeCompare(b.product_name, 'vi'));
  }
  return out;
}

function warehouseEmpty() {
  if (Wh.only === 'out') return 'Không có mặt hàng nào hết hàng';
  if (Wh.only === 'low') return 'Không có mặt hàng nào sắp hết';
  if (Wh.place === '--') return 'Mặt hàng nào cũng đã khai vị trí kho';
  if (Wh.place) return `Không có mặt hàng nào ở ${Wh.place}`;
  return Wh.q ? `Không có mặt hàng nào khớp "${Wh.q}"` : 'Kho chưa có mặt hàng nào';
}

/** Ô ảnh vị trí kho: bấm vào xem to, chưa có ảnh thì để một ô trống mờ. */
function whThumb(r) {
  if (!r.image_url) return '<span class="dash">—</span>';
  return `<img class="whshot" src="${esc(r.image_url)}" alt="Vị trí ${esc(r.location || '')}"
    loading="lazy" onclick="event.stopPropagation();openViewer(${
      esc(JSON.stringify(r.image_url))})">`;
}

function drawWarehouseList() {
  const box = $('whBody');
  if (!box) return;
  const rows = warehouseRows();
  const open = (r) => `openStockProduct(${esc(JSON.stringify(JSON.stringify(
    [r.product_name, r.model_code])))})`;

  if (isWide()) {
    const cols = [{ t: 'Tên hàng hoá' }, { t: 'Số lượng', cls: 'num' },
                  { t: 'Ngày nhập', cls: 'nowrap' }, { t: 'Vị trí kho' },
                  { t: 'Số lượng tồn', cls: 'num' }, { t: 'Đã xuất', cls: 'num' },
                  { t: 'Còn lại', cls: 'nowrap' }, { t: 'Ảnh vị trí', cls: 'nowrap' }];

    box.innerHTML = dataTable(cols, rows.map((r) => ({
      cells: [
        `<span class="strong">${esc(r.product_name)}</span>
         <span class="mono sub2">${esc(r.model_code)}</span>`,
        String(r.imported),
        r.last_in ? fmtDate(r.last_in) : '—',
        r.location ? esc(r.location) : '<span class="dash">Chưa khai</span>',
        `<span class="strong">${r.on_hand}</span>`,
        String(r.exported),
        `<span class="pill ${r.on_hand > 0 ? 'p-ok' : 'p-bad'}">${
          r.on_hand > 0 ? r.on_hand + ' / ' + r.imported : 'Hết hàng'}</span>`,
        whThumb(r),
      ],
      cls: r.on_hand > 0 ? '' : 'warn',
      click: open(r),
    }))) || emptyBox(warehouseEmpty());
    return;
  }

  box.innerHTML = rows.length ? `<div class="rows">${rows.map((r) => `
    <div class="row" style="flex-direction:column;align-items:stretch;gap:0"
         onclick="${open(r)}">
      <div style="display:flex;gap:12px;width:100%;align-items:flex-start">
        <div class="main">
          <div class="title">${esc(r.product_name)}</div>
          <div class="meta mono">${esc(r.model_code)}</div>
        </div>
        <div class="rt">
          <span class="pill ${r.on_hand > 0 ? 'p-ok' : 'p-bad'}">${
            r.on_hand > 0 ? 'Còn ' + r.on_hand : 'Hết hàng'}</span>
        </div>
      </div>
      <div class="qbar">
        <i style="background:var(--ok);flex:${Math.max(r.on_hand, 0.001)}"></i>
        <i style="background:var(--out);flex:${Math.max(r.exported, 0.001)}"></i>
      </div>
      <div class="qlegend">
        <span><b style="background:var(--ok)"></b>Tồn <em>${r.on_hand}</em></span>
        <span><b style="background:var(--out)"></b>Đã xuất <em>${r.exported}</em></span>
        <span>Số lượng <em>${r.imported}</em></span>
      </div>
      <div class="whfoot">
        <div>
          <div class="meta">Ngày nhập ${r.last_in ? fmtDate(r.last_in) : '—'}</div>
          <div class="meta">Vị trí ${r.location ? esc(r.location) : 'chưa khai'}</div>
        </div>
        ${whThumb(r)}
      </div>
    </div>`).join('')}</div>` : emptyBox(warehouseEmpty());
}

Wh.onSearch = function (value) {
  Wh.q = value;
  clearTimeout(Wh.timer);
  Wh.timer = setTimeout(drawWarehouseList, 200);
};
Wh.setSort = function (value) { Wh.sort = value; drawWarehouseList(); };
Wh.setPlace = function (value) { Wh.place = value; drawWarehouseList(); };
Wh.setOnly = function (value) {
  Wh.only = value;
  const sel = document.querySelectorAll('#whHead .minisel')[0];
  if (sel) sel.value = value;
  drawWarehouseList();
};

/* ---------------------------------------------- khai vị trí để trong kho */

/**
 * Ô khai chỗ để của một mặt hàng, nằm trong phiếu chi tiết mặt hàng.
 * Ảnh tải thẳng lên S3 như mọi ảnh khác, ở đây chỉ giữ object key.
 */
const Place = {
  name: '', code: '', url: null, key: undefined,

  /** `key === undefined` nghĩa là chưa đụng tới ảnh, lưu xong vẫn giữ ảnh cũ. */
  mount(d) {
    this.name = d.product_name;
    this.code = d.model_code;
    this.url = d.image_url || null;
    this.key = undefined;
    this.draw();
  },

  draw() {
    const box = $('placeBox');
    if (!box) return;
    box.innerHTML = `
      <div class="placeshot">
        ${this.url
          ? `<img src="${esc(this.url)}" alt="Ảnh vị trí kho"
               onclick="openViewer(${esc(JSON.stringify(this.url))})">
             <button class="x" onclick="Place.dropPhoto()" aria-label="Bỏ ảnh">
               <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>`
          : `<button class="addshot" onclick="Place.pickPhoto()">
               ${CAM_ICON}<span>Chụp ảnh chỗ để</span></button>`}
      </div>`;
  },

  /**
   * Ảnh lưu ngay khi chọn xong: máy chủ trả lại URL đã ký để hiện lên, khỏi
   * phải tự dựng URL tạm rồi lại thay bằng URL thật sau khi bấm Lưu.
   */
  pickPhoto() {
    Photos.pick('im_export', (keys) => {
      if (!keys.length) return;
      this.key = keys[0];
      this.save();
    });
  },

  dropPhoto() {
    this.key = '';
    this.save();
  },

  async save(btn) {
    const input = $('placeInput');
    const note = $('placeNote');
    await withBusy(btn, 'Đang lưu', async () => {
      const body = {
        product_name: this.name, model_code: this.code,
        location: input ? input.value.trim() : null,
        note: note ? note.value.trim() : null,
      };
      // Không đụng tới ảnh thì không gửi trường này, máy chủ giữ nguyên ảnh cũ
      if (this.key !== undefined) body.image_key = this.key;
      try {
        const saved = await apiPut('stock/location', body);
        this.key = undefined;
        this.url = saved.image_url || null;
        this.draw();
        toast('Đã lưu vị trí kho');
        // Bảng ngoài kia đang giữ số liệu cũ, cập nhật đúng dòng vừa sửa
        const row = Wh.rows.find((r) => r.product_name === this.name
          && r.model_code === this.code);
        if (row) { row.location = saved.location; row.image_url = saved.image_url; }
        // Vị trí mới khai phải có mặt luôn trong ô lọc, khỏi đợi tải lại trang
        const sel = $('whPlaceSel');
        if (sel) sel.innerHTML = whPlaceOptions();
        drawWarehouseList();
      } catch (err) {
        toastError(err);
      }
    });
  },
};
