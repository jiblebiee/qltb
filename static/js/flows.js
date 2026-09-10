/* =============================================================
   Các luồng thao tác: mượn, trả, thêm máy, nhân sự, phòng ban,
   nhập xuất kho, phân quyền, đổi mật khẩu.
   ============================================================= */
'use strict';

/* ================================================================
   TẠO PHIẾU MƯỢN — 3 bước
   ================================================================ */

const Borrow = {
  step: 1,
  deptId: null,
  borrowerId: null,
  lenderId: null,
  borrowedOn: '',
  lenders: [],
  lenderFallback: false,
  selected: [],
  note: '',
  openModel: null,
  q: '',
  departments: [],
  staff: [],
  models: [],
  units: [],

  async open(preselectUnitId = null) {
    this.step = 1;
    this.deptId = null;
    this.borrowerId = null;
    this.lenderId = null;
    this.borrowedOn = todayISO();
    this.lenders = [];
    this.lenderFallback = false;
    this.selected = preselectUnitId ? [preselectUnitId] : [];
    this.note = '';
    this.openModel = null;
    this.q = '';

    Sheet.open({
      title: 'Tạo phiếu mượn',
      body: loadingBox('Đang tải danh mục…'),
      foot: '',
      steps: 1,
      stepLabel: 'Bước 1 / 3 · Chọn phòng ban rồi chọn nhân sự',
      // Đã chọn người hoặc đã nhặt máy nào là coi như đang làm dở
      guard: () => !!(Borrow.borrowerId || Borrow.selected.length || Borrow.note.trim()),
    });

    try {
      const [departments, staff, models, units] = await Promise.all([
        loadDepartments(), loadStaff(), loadModels(),
        apiGet('devices/units', { limit: 2000 }),
      ]);
      this.departments = departments;
      this.staff = staff.filter((s) => s.status === 'ACTIVE');
      this.models = models;
      this.units = units;
      if (preselectUnitId) {
        const u = units.find((x) => x.id === preselectUnitId);
        if (u) this.openModel = u.model_id;
      }
      // Người cho mượn là người của phòng IT. Chỉ khi phòng IT chưa có ai thì
      // mới đổ toàn bộ nhân sự vào ô này, để phiếu vẫn lập được.
      this.lenders = this.staff.filter(isLenderStaff);
      this.lenderFallback = this.lenders.length === 0;
      if (this.lenderFallback) this.lenders = this.staff;
      // Trong nhóm đó, mặc định chọn chính người đang đăng nhập nếu có.
      const self = this.lenders.find((s) => s.full_name === ME.fullName);
      this.lenderId = self ? self.id : (this.lenders[0] && this.lenders[0].id) || null;
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.draw();
  },

  go(step) { this.step = step; this.draw(); },

  draw() {
    const labels = [
      'Bước 1 / 3 · Chọn phòng ban rồi chọn nhân sự',
      'Bước 2 / 3 · Chọn từng máy theo mã',
      'Bước 3 / 3 · Xác nhận phiếu',
    ];
    Sheet.setSteps(this.step, labels[this.step - 1]);
    if (this.step === 1) this.drawStep1();
    else if (this.step === 2) this.drawStep2();
    else this.drawStep3();
  },

  /* ---------- bước 1: phòng ban → nhân sự ---------- */

  drawStep1() {
    Sheet.setBody(`
      <div class="search" style="margin-bottom:12px">
        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input id="bq" placeholder="Hoặc gõ thẳng tên nhân sự…" value="${esc(this.q)}"
               oninput="Borrow.q=this.value;Borrow.drawPeople()">
      </div>
      <div id="bpeople"></div>
      <h2 class="sec">Người cho mượn${this.lenderFallback
        ? '' : ' · ' + esc(LENDER_DEPT)}</h2>
      <div class="field" style="margin:0">
        <select onchange="Borrow.lenderId=+this.value">
          ${this.lenders.map((s) => `<option value="${s.id}" ${
            s.id === this.lenderId ? 'selected' : ''}>${esc(s.full_name)}${
            s.department_name ? ' · ' + esc(s.department_name) : ''}</option>`).join('')}
        </select>
      </div>`);
    this.drawPeople();
    Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
      <button class="btn" id="bnext" onclick="Borrow.go(2)" ${
        this.borrowerId ? '' : 'disabled'}>Tiếp tục</button>`);
  },

  drawPeople() {
    const box = $('bpeople');
    if (!box) return;
    const q = this.q.trim().toLowerCase();

    if (q) {
      const matches = this.staff.filter((s) =>
        `${s.full_name} ${s.department_name || ''}`.toLowerCase().includes(q));
      box.innerHTML = `<div class="picks">${matches.map((s) => this.personRow(s, true)).join('')
        || emptyBox('Không tìm thấy nhân sự')}</div>`;
      return;
    }

    if (this.deptId === null) {
      box.innerHTML = `<div class="picks">${this.departments.map((d) => {
        const n = this.staff.filter((s) => s.department_id === d.id).length;
        return `<button class="pick" onclick="Borrow.deptId=${d.id};Borrow.drawPeople()">
          <div class="av">${esc(deptInitials(d.name))}</div>
          <div class="nm"><b>${esc(d.name)}</b><em>${n} nhân sự${
            d.units_held ? ' · đang giữ ' + d.units_held + ' máy' : ''}</em></div>
          ${CHEVRON}</button>`;
      }).join('') || emptyBox('Chưa có phòng ban nào')}</div>`;
      return;
    }

    const dept = this.departments.find((d) => d.id === this.deptId);
    const people = this.staff.filter((s) => s.department_id === this.deptId);
    box.innerHTML = `
      <button class="chip" style="margin-bottom:11px"
              onclick="Borrow.deptId=null;Borrow.drawPeople()">‹ Tất cả phòng ban</button>
      <div style="font-size:14.5px;color:var(--muted);margin-bottom:9px">
        Phòng <b style="color:var(--ink)">${esc(dept ? dept.name : '')}</b> · ${people.length} nhân sự
        ${dept && dept.head_name ? ' · trưởng bộ phận ' + esc(dept.head_name) : ''}</div>
      <div class="picks">${people.map((s) => this.personRow(s, false)).join('')
        || emptyBox('Phòng này chưa có nhân sự')}</div>`;
  },

  personRow(s, showDept) {
    return `<button class="pick ${this.borrowerId === s.id ? 'on' : ''}"
        onclick="Borrow.pickPerson(${s.id})">
      <div class="av">${esc(initials(s.full_name))}</div>
      <div class="nm"><b>${esc(s.full_name)}</b>
        <em>${showDept ? esc(s.department_name || '—') : esc(s.email || '')}${
          s.units_held.length ? ' · đang giữ ' + s.units_held.length + ' máy' : ''}</em></div>
      <div class="tick"></div></button>`;
  },

  pickPerson(id) {
    this.borrowerId = id;
    const s = this.staff.find((x) => x.id === id);
    if (s) this.deptId = s.department_id;
    this.drawPeople();
    const next = $('bnext');
    if (next) next.disabled = false;
  },

  /* ---------- bước 2: chọn từng máy ---------- */

  drawStep2() {
    Sheet.setBody(`
      <div class="quick">
        <input id="bcode" placeholder="Nhập mã máy, VD: LAP-07" autocapitalize="characters"
               onkeydown="if(event.key==='Enter'){event.preventDefault();Borrow.quickAdd()}">
        <button class="scan" onclick="Borrow.scan()" aria-label="Quét mã QR trên máy"
                title="Quét mã QR dán trên máy">
          <svg viewBox="0 0 24 24">
            <path d="M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3"/>
            <path d="M7.5 12h9"/></svg></button>
        <button onclick="Borrow.quickAdd()" aria-label="Thêm nhanh">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg></button>
      </div>
      <div id="bselbar"></div>
      <h2 class="sec" style="margin-top:4px">Chọn theo loại</h2>
      <div id="bmodels"></div>`);
    this.drawSelected();
    this.drawModels();
    Sheet.setFoot(`<button class="btn ghost" onclick="Borrow.go(1)">Quay lại</button>
      <button class="btn" id="bnext" onclick="Borrow.go(3)" ${
        this.selected.length ? '' : 'disabled'}>Tiếp tục</button>`);
  },

  unitById(id) { return this.units.find((u) => u.id === id); },

  /**
   * Quét mã dán trên máy. Khung quét mở liên tục: quét xong một máy là thêm
   * ngay rồi quét tiếp máy sau, không phải bấm mở lại từng lần.
   */
  scan() {
    Scan.open((text) => {
      const code = Borrow.codeFromScan(text);
      if (!code) { Scan.say('Không đọc ra mã thiết bị nào.'); return false; }

      // Tem dán trên máy mang mã máy — thêm thẳng vào phiếu
      if (Borrow.units.some((u) => u.code.toUpperCase() === code)) {
        const added = Borrow.addByCode(code);
        Scan.say(added
          ? `Đã thêm ${code} · tổng ${Borrow.selected.length} máy`
          : `${code}: không thêm được`);
        return false;               // giữ khung mở để quét máy kế tiếp
      }

      // Tem dán trên thùng mang mã LOẠI — mở đúng nhóm đó ra chọn tay
      const model = Borrow.models.find((m) => m.code.toUpperCase() === code);
      if (model) {
        Borrow.openModel = model.id;
        Borrow.refreshStep2();
        Scan.say(`${code} là mã loại — đã mở ${model.name} để chọn máy.`);
        return true;                // đóng khung, người dùng chọn máy trong danh sách
      }

      Scan.say(`Không có thiết bị nào mang mã ${code}.`);
      return false;
    }, { title: 'Quét mã trên thiết bị' });
  },

  /**
   * Rút mã ra khỏi nội dung vừa quét. Nhận cả mã máy (LAP-07) lẫn mã loại
   * (LAP), in trần hoặc nằm trong đường dẫn kiểu `…/#devices?unit=LAP-07`.
   */
  codeFromScan(text) {
    let raw = String(text || '').trim();
    const m = raw.match(/[?&#](?:unit|code|ma)=([^&#\s]+)/i);
    if (m) raw = decodeURIComponent(m[1]);
    else if (/^https?:\/\//i.test(raw)) raw = raw.split(/[/?#]/).filter(Boolean).pop() || '';
    raw = raw.trim().toUpperCase();
    return /^[A-Z0-9]{2,12}(-\d{2,})?$/.test(raw) ? raw : null;
  },

  quickAdd() {
    const input = $('bcode');
    const code = (input.value || '').trim().toUpperCase();
    if (!code) return;
    if (this.addByCode(code)) input.value = '';
  },

  /**
   * Thêm một máy theo mã. Dùng chung cho gõ tay và quét mã.
   * Trả về true khi máy đó đã nằm trong phiếu sau lệnh này.
   */
  addByCode(code) {
    const unit = this.units.find((u) => u.code.toUpperCase() === code);
    if (!unit) { toast(`Không có máy nào mang mã ${code}.`, true); return false; }
    if (unit.status !== 'AVAIL') {
      toast(`${code} không sẵn sàng — đang ${UNIT_LABEL_LONG[unit.status].toLowerCase()}.`, true);
      return false;
    }
    if (this.selected.includes(unit.id)) {
      toast(`${code} đã có trong phiếu.`);
      return true;
    }
    this.selected.push(unit.id);
    this.openModel = unit.model_id;
    this.refreshStep2();
    toast(`Đã thêm ${code} vào phiếu.`);
    return true;
  },

  toggle(unitId) {
    const i = this.selected.indexOf(unitId);
    if (i < 0) this.selected.push(unitId); else this.selected.splice(i, 1);
    this.refreshStep2();
  },

  pickMany(modelId, count) {
    const free = this.units.filter((u) =>
      u.model_id === modelId && u.status === 'AVAIL' && !this.selected.includes(u.id));
    if (!free.length) { toast('Loại này không còn máy sẵn sàng.', true); return; }
    free.slice(0, count).forEach((u) => this.selected.push(u.id));
    this.refreshStep2();
  },

  clearAll() { this.selected = []; this.refreshStep2(); },

  refreshStep2() {
    this.drawSelected();
    this.drawModels();
    const next = $('bnext');
    if (next) next.disabled = !this.selected.length;
  },

  drawSelected() {
    const box = $('bselbar');
    if (!box) return;
    if (!this.selected.length) { box.innerHTML = ''; return; }
    box.innerHTML = `<div class="selbar">
      <div class="top">Đã chọn ${this.selected.length} máy<em onclick="Borrow.clearAll()">Bỏ hết</em></div>
      <div class="tokens">${this.selected.map((id) => {
        const u = this.unitById(id);
        return `<button class="token" onclick="Borrow.toggle(${id})">${esc(u ? u.code : id)}
          <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></button>`;
      }).join('')}</div></div>`;
  },

  drawModels() {
    const box = $('bmodels');
    if (!box) return;
    box.innerHTML = this.models.map((m) => {
      const units = this.units.filter((u) => u.model_id === m.id);
      const free = units.filter((u) => u.status === 'AVAIL').length;
      const chosen = this.selected.filter((id) => {
        const u = this.unitById(id);
        return u && u.model_id === m.id;
      }).length;
      const isOpen = this.openModel === m.id;
      return `<div class="acc">
        <button class="ah" onclick="Borrow.openModel = Borrow.openModel===${m.id} ? null : ${m.id}; Borrow.drawModels()">
          <div class="nm"><b>${esc(m.name)}</b>
            <em><span class="mono">${esc(m.code)}</span> · ${free} / ${units.length} máy sẵn sàng</em></div>
          ${chosen ? `<span class="pill p-out">${chosen} đã chọn</span>` : ''}
          <svg class="chev" viewBox="0 0 24 24" style="transform:rotate(${isOpen ? 90 : 0}deg)">
            <path d="M9 18l6-6-6-6"/></svg>
        </button>
        ${isOpen ? `<div class="ab">
          <div class="bulk">
            <button class="chip" onclick="Borrow.pickMany(${m.id},1)">+1 máy rảnh</button>
            <button class="chip" onclick="Borrow.pickMany(${m.id},5)">+5 máy</button>
            <button class="chip" onclick="Borrow.pickMany(${m.id},9999)">Chọn hết ${free} máy</button>
          </div>
          <div class="ugrid">${units.map((u) => unitTile(u, {
            pick: true, selected: this.selected, disabled: u.status !== 'AVAIL',
          })).join('')}</div>
          ${UNIT_LEGEND}</div>` : ''}
      </div>`;
    }).join('') || emptyBox('Chưa có thiết bị nào trong hệ thống');
  },

  /* ---------- bước 3: xác nhận ---------- */

  drawStep3() {
    const person = this.staff.find((s) => s.id === this.borrowerId);
    const dept = this.departments.find((d) => d.id === (person && person.department_id));
    const lender = this.staff.find((s) => s.id === this.lenderId);

    const grouped = {};
    this.selected.forEach((id) => {
      const u = this.unitById(id);
      if (!u) return;
      const m = this.models.find((x) => x.id === u.model_id);
      (grouped[m ? m.name : '—'] ||= []).push(u.code);
    });

    Sheet.setBody(`
      <div class="card" style="margin-bottom:16px">
        <dl class="kv" style="margin:0">
          <dt>Người mượn</dt><dd>${esc(person ? person.full_name : '—')}<br>
            <span style="font-weight:400;color:var(--muted);font-size:15px">${
              esc(person && person.department_name || '')}</span></dd>
          <dt>Người cho mượn</dt><dd>${esc(lender ? lender.full_name : '—')}</dd>
          <dt>Ngày mượn</dt>
          <dd><input type="date" id="bdate" class="datecell" max="${todayISO()}"
                     value="${esc(this.borrowedOn)}"
                     onchange="Borrow.setDate(this.value)"></dd>
          <dt>Tổng số máy</dt><dd>${this.selected.length} máy</dd>
          <dt>Email báo tới</dt><dd>${dept && dept.head_name
            ? `${esc(dept.head_name)}<br><span class="mono" style="font-weight:400;
                 color:var(--muted);font-size:15px">${esc(dept.head_email || '')}</span>`
            : '<span style="color:var(--muted)">địa chỉ quản lý mặc định</span>'}</dd>
        </dl>
      </div>

      <div class="field" style="margin-top:16px">
        <label for="bnote">Ghi chú</label>
        <textarea id="bnote" placeholder="Ví dụ: mang đi công tác Đà Nẵng…"
                  oninput="Borrow.note=this.value">${esc(this.note)}</textarea>
      </div>

      <h2 class="sec">Danh sách máy bàn giao</h2>
      ${Object.entries(grouped).map(([name, codes]) => `
        <div class="acc"><div class="ah" style="cursor:default">
          <div class="nm"><b>${esc(name)}</b><em>${codes.length} máy</em></div></div>
          <div class="ab"><div class="tokens">${codes.map((c) =>
            `<span class="token" style="cursor:default">${esc(c)}</span>`).join('')}</div></div>
        </div>`).join('')}
      <div style="height:8px"></div>`);

    Sheet.setFoot(`<button class="btn ghost" onclick="Borrow.go(2)">Quay lại</button>
      <button class="btn" onclick="Borrow.submit(this)">Xác nhận mượn</button>`);
  },

  /** Ngày mượn không được ở tương lai; để trống thì quay về hôm nay. */
  setDate(value) {
    const today = todayISO();
    this.borrowedOn = (!value || value > today) ? today : value;
    const box = $('bdate');
    if (box && box.value !== this.borrowedOn) box.value = this.borrowedOn;
  },

  async submit(button) {
    try {
      const ticket = await withBusy(button, 'Đang tạo phiếu…', () => apiPost('tickets', {
        borrower_staff_id: this.borrowerId,
        lender_staff_id: this.lenderId,
        unit_ids: this.selected,
        note: this.note.trim() || null,
        borrowed_at: isoAtNoonUTC(this.borrowedOn),
      }));
      Sheet.close();
      Cache.clear('models', 'staff');
      const person = this.staff.find((s) => s.id === this.borrowerId);
      toast(`Đã tạo phiếu #${ticket.code} — ${this.selected.length} máy cho ${
        person ? person.full_name : ''}. Email đã gửi tới trưởng bộ phận.`);
      Loans.tab = 'open';
      openScreen('loans');
      refreshBackground();
    } catch (err) {
      toastError(err);
      // Máy vừa bị người khác mượn mất — nạp lại danh sách rồi quay về bước chọn
      if (err.status === 409) {
        this.units = await apiGet('devices/units', { limit: 2000 });
        this.selected = this.selected.filter((id) => {
          const u = this.unitById(id);
          return u && u.status === 'AVAIL';
        });
        this.go(2);
      }
    }
  },
};

/* ================================================================
   NHẬN TRẢ
   ================================================================ */

const Return = {
  code: null,
  ticket: null,
  lines: [],
  single: false,
  receiverId: null,
  staff: [],

  async open(code, onlyUnitId = null) {
    this.code = code;
    this.single = !!onlyUnitId;
    Sheet.open({ title: 'Đang tải…', body: loadingBox(), foot: '',
      guard: () => Return.lines.some((l) => l.note.trim() || l.condition !== 'NORMAL') });

    try {
      const [ticket, staff] = await Promise.all([
        apiGet(`tickets/${encodeURIComponent(code)}`), loadStaff(),
      ]);
      this.ticket = ticket;
      this.staff = staff.filter((s) => s.status === 'ACTIVE');
      const self = this.staff.find((s) => s.full_name === ME.fullName);
      this.receiverId = self ? self.id : (this.staff[0] && this.staff[0].id) || null;

      let items = ticket.items.filter((i) => !i.returned);
      if (onlyUnitId) items = items.filter((i) => i.unit_id === onlyUnitId);
      if (!items.length) {
        Sheet.setBody(emptyBox('Không còn máy nào cần trả trong phiếu này'));
        Sheet.setFoot('<button class="btn ghost" onclick="Sheet.close()">Đóng</button>');
        return;
      }
      this.lines = items.map((i) => ({
        unit_id: i.unit_id, code: i.code, model_name: i.model_name,
        take: true, condition: 'NORMAL', note: '', showNote: false,
      }));
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.draw();
  },

  draw() {
    const t = this.ticket;
    const openCount = t.items.filter((i) => i.returned === false).length;
    const grouped = {};
    this.lines.forEach((l, i) => { (grouped[l.model_name] ||= []).push(i); });

    Sheet.setTitle(this.single
      ? `Trả máy <span class="mono">${esc(this.lines[0].code)}</span>`
      : 'Nhận trả thiết bị');

    Sheet.setBody(`
      <div class="note" style="margin-bottom:14px">
        ${esc(t.borrower_name || '—')} · phiếu <b class="mono">#${esc(t.code)}</b> ·
        mượn ${fmtDate(t.borrowed_at)} · đã ${t.days_elapsed} ngày
        ${t.state === 'over' ? `<b style="color:var(--bad)"> — quá ${OVERDUE_DAYS}n</b>` : ''}
        ${this.single && openCount > 1
          ? `<br><b style="color:var(--ink);cursor:pointer;text-decoration:underline;
             text-underline-offset:3px" onclick="Return.open('${esc(t.code)}')">Trả cả phiếu ${
             openCount} máy</b>` : ''}
      </div>

      ${this.lines.length > 1 ? `<div class="chips" style="margin-bottom:14px">
        <button class="chip" onclick="Return.setAllTake(true)">Nhận hết ${this.lines.length} máy</button>
        <button class="chip" onclick="Return.setAllTake(false)">Bỏ chọn hết</button>
        <button class="chip" onclick="Return.setAllCondition('NORMAL')">Tất cả bình thường</button>
      </div>` : ''}

      ${Object.entries(grouped).map(([name, indexes]) => `
        <h2 class="sec">${esc(name)} <span class="count">${indexes.length}</span></h2>
        ${indexes.map((i) => this.lineHtml(i)).join('')}`).join('')}

      <div class="field" style="margin-top:16px">
        <label for="rrecv">Người nhận</label>
        <select id="rrecv" onchange="Return.receiverId=+this.value">
          ${this.staff.map((s) => `<option value="${s.id}" ${
            s.id === this.receiverId ? 'selected' : ''}>${esc(s.full_name)}</option>`).join('')}
        </select>
      </div>

      <div style="height:8px"></div>`);

    const count = this.lines.filter((l) => l.take).length;
    Sheet.setFoot(`
      <button class="btn ghost" onclick="openTicket('${esc(t.code)}')">Quay lại</button>
      <button class="btn" onclick="Return.submit(this)" ${count ? '' : 'disabled'}>
        Xác nhận trả ${count} máy</button>`);
  },

  lineHtml(i) {
    const l = this.lines[i];
    const showNote = l.condition !== 'NORMAL' || l.showNote || l.note;
    const no = l.code.split('-').pop();
    return `<div class="runit">
      <div class="rh">
        <button class="u ${l.take ? 'AVAIL' : ''}" style="width:52px;flex:0 0 52px;padding:7px 2px"
                onclick="Return.toggleTake(${i})" aria-label="Chọn ${esc(l.code)}">
          <b>${esc(no)}</b><i>${l.take ? 'Nhận' : 'Bỏ qua'}</i></button>
        <em><span class="mono" style="color:var(--ink);font-weight:600">${esc(l.code)}</span></em>
      </div>
      ${l.take ? `
        <div class="conds">${[['NORMAL', 'Bình thường'], ['BROKEN', 'Hỏng'], ['MAINT', 'Cần bảo trì']]
          .map(([c, label]) => `<button data-c="${c}" class="${l.condition === c ? 'on' : ''}"
            onclick="Return.setCondition(${i},'${c}')">${esc(label)}</button>`).join('')}</div>
        ${showNote
          ? `<textarea class="unote" oninput="Return.lines[${i}].note=this.value"
               placeholder="${l.condition === 'NORMAL'
                 ? 'Ghi chú riêng cho máy này…'
                 : 'VD: hư 2 / 6 đầu nối, 4 đầu còn lại dùng bình thường'}">${esc(l.note)}</textarea>`
          : `<button class="chip" style="margin-top:9px" onclick="Return.showNote(${i})">
               + Ghi chú riêng cho máy này</button>`}
      ` : ''}
    </div>`;
  },

  toggleTake(i) { this.lines[i].take = !this.lines[i].take; this.draw(); },
  setCondition(i, c) { this.lines[i].condition = c; this.draw(); },
  showNote(i) { this.lines[i].showNote = true; this.draw(); },
  setAllTake(v) { this.lines.forEach((l) => { l.take = v; }); this.draw(); },
  setAllCondition(c) { this.lines.forEach((l) => { if (l.take) l.condition = c; }); this.draw(); },

  async submit(button) {
    const items = this.lines.filter((l) => l.take).map((l) => ({
      unit_id: l.unit_id,
      condition: l.condition,
      note: (l.note || '').trim() || null,
    }));
    if (!items.length) return;

    try {
      const res = await withBusy(button, 'Đang ghi nhận…',
        () => apiPost(`tickets/${encodeURIComponent(this.code)}/return`,
                      { items, receiver_staff_id: this.receiverId }));
      Sheet.close();
      Cache.clear('models', 'staff');

      const s = res.summary || {};
      let msg = `Đã nhận trả ${items.length} máy cho phiếu #${this.code}.`;
      if (s.maint) msg += ` Tạo ${s.maint} lịch bảo trì.`;
      if (s.broken) msg += ` Ghi nhận ${s.broken} máy hỏng.`;
      if (s.flagged && s.flagged.length) {
        msg += ` Gắn ghi chú tình trạng cho ${s.flagged.join(', ')}.`;
      }
      toast(msg);
      refreshBackground();
      if (currentScreen === 'loans') renderLoanList();
      if (currentScreen === 'devices') renderDeviceList();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   THÊM MÁY MỚI
   ================================================================ */

const AddDevice = {
  mode: 'exist',
  modelId: null,
  quantity: 5,
  name: '',
  code: '',
  codeTouched: false,
  brand: '',
  info: '',
  note: '',
  photos: [],
  models: [],

  async open(presetModelId = null) {
    this.mode = presetModelId ? 'exist' : 'exist';
    this.quantity = 5;
    this.name = ''; this.code = ''; this.codeTouched = false;
    this.brand = ''; this.info = ''; this.note = '';
    this.photos = [];

    Sheet.open({ title: 'Thêm máy mới', body: loadingBox(), foot: '',
      guard: () => !!(AddDevice.name.trim() || AddDevice.code.trim()
        || AddDevice.note.trim() || AddDevice.photos.length) });
    try {
      this.models = await loadModels();
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.modelId = presetModelId || (this.models[0] && this.models[0].id) || null;
    if (!this.models.length) this.mode = 'new';
    this.draw();
  },

  setMode(mode) { this.mode = mode; this.draw(); },

  nextCodes() {
    if (this.mode === 'exist') {
      const m = this.models.find((x) => x.id === this.modelId);
      if (!m) return { code: '???', from: 1, to: this.quantity };
      const start = (m.counters ? m.counters.total : 0) + 1;
      return { code: m.code, from: start, to: start + this.quantity - 1 };
    }
    return { code: this.code || '???', from: 1, to: this.quantity };
  },

  updatePreview() {
    const box = $('addPreview');
    const qty = $('aQty');
    const submit = $('aSubmit');
    if (qty) qty.textContent = this.quantity;
    if (submit) submit.textContent = `Tạo ${this.quantity} máy`;
    if (!box) return;
    const { code, from, to } = this.nextCodes();
    const pad = (n) => String(n).padStart(2, '0');
    box.innerHTML = `<div class="note" style="margin-bottom:14px">Sẽ tạo
      <b>${this.quantity} máy</b> mang mã
      <b class="mono">${esc(code)}-${pad(from)}</b>${this.quantity > 1
        ? ` → <b class="mono">${esc(code)}-${pad(to)}</b>` : ''},
      trạng thái ban đầu <b>Sẵn sàng</b>.</div>`;
  },

  bumpQty(delta) {
    this.quantity = Math.max(1, Math.min(2000, this.quantity + delta));
    this.updatePreview();
  },

  onName(value) {
    this.name = value;
    if (!this.codeTouched) {
      this.code = this.suggestCode(value);
      const input = $('aCode');
      if (input) input.value = this.code;
    }
    this.updatePreview();
  },

  onCode(value) {
    this.codeTouched = true;
    this.code = String(value || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/đ/gi, 'd').toUpperCase().replace(/[^A-Z0-9]/g, '');
    this.updatePreview();
  },

  suggestCode(name) {
    const plain = String(name || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/đ/gi, 'd').toUpperCase();
    const words = plain.split(/[^A-Z0-9]+/).filter(Boolean);
    if (!words.length) return '';
    let base = words.length === 1 ? words[0].slice(0, 4) : words.slice(0, 3).map((w) => w[0]).join('');
    let code = base, i = 2;
    while (this.models.some((m) => m.code === code)) { code = base + i; i += 1; }
    return code;
  },

  addPhoto() {
    Photos.pick('images', (keys) => {
      this.photos.push(...keys);
      this.draw();
      toast(`Đã đính kèm ${keys.length} ảnh.`);
    });
  },

  removePhoto(i) { this.photos.splice(i, 1); this.draw(); },

  draw() {
    const qtyBlock = `
      <div class="field">
        <label>${this.mode === 'exist' ? 'Số máy nhập thêm' : 'Số máy ban đầu'}</label>
        <div class="stepper" style="width:fit-content">
          <button onclick="AddDevice.bumpQty(-1)" aria-label="Giảm">−</button>
          <span id="aQty">${this.quantity}</span>
          <button onclick="AddDevice.bumpQty(1)" aria-label="Tăng">+</button>
        </div>
      </div>
      <div id="addPreview"></div>`;

    const photoBlock = `
      <h2 class="sec">Ảnh sản phẩm <span class="count">${this.photos.length}</span></h2>
      ${this.photos.length
        ? `<div class="photos">${this.photos.map((_, i) =>
            `<div class="thumb pending"><span class="mono" style="font-size:13px">Đã tải lên</span>
              <span class="del" role="button" onclick="AddDevice.removePhoto(${i})">
                <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></span></div>`).join('')}</div>`
        : '<div class="nophoto">Chưa có ảnh sản phẩm</div>'}
      ${cameraButton('AddDevice.addPhoto()', 'Chụp ảnh sản phẩm')}`;

    Sheet.setBody(`
      <div class="seg">
        <button class="${this.mode === 'exist' ? 'on' : ''}" ${this.models.length ? '' : 'disabled'}
                onclick="AddDevice.setMode('exist')">Loại đã có</button>
        <button class="${this.mode === 'new' ? 'on' : ''}"
                onclick="AddDevice.setMode('new')">Loại mới</button>
      </div>
      ${this.mode === 'exist' ? `
        <div class="field">
          <label for="aModel">Loại thiết bị</label>
          <select id="aModel" onchange="AddDevice.modelId=+this.value;AddDevice.updatePreview()">
            ${this.models.map((m) => `<option value="${m.id}" ${
              m.id === this.modelId ? 'selected' : ''}>${esc(m.name)} (${esc(m.code)} · ${
              m.counters ? m.counters.total : 0} máy)</option>`).join('')}
          </select>
        </div>
        ${qtyBlock}${photoBlock}
      ` : `
        <div class="field"><label for="aName">Tên loại thiết bị</label>
          <input id="aName" placeholder="VD: Laptop HP ProBook 450 G9"
                 value="${esc(this.name)}" oninput="AddDevice.onName(this.value)"></div>
        <div class="field"><label for="aCode">Mã loại</label>
          <input id="aCode" class="mono" style="text-transform:uppercase" placeholder="VD: LAP"
                 value="${esc(this.code)}" oninput="AddDevice.onCode(this.value)">
</div>
        <div class="field"><label for="aBrand">Hãng</label>
          <input id="aBrand" placeholder="VD: HP" value="${esc(this.brand)}"
                 oninput="AddDevice.brand=this.value"></div>
        ${qtyBlock}
        <div class="field"><label for="aInfo">Thông số chung</label>
          <textarea id="aInfo" placeholder="OS: Windows 11 Pro&#10;CPU: Intel i5&#10;RAM: 16GB"
                    oninput="AddDevice.info=this.value">${esc(this.info)}</textarea>
</div>
        ${photoBlock}
        <div class="field" style="margin-top:16px"><label for="aNote">Ghi chú</label>
          <textarea id="aNote" placeholder="VD: mua đợt tháng 9, bảo hành 24 tháng…"
                    oninput="AddDevice.note=this.value">${esc(this.note)}</textarea></div>
      `}
      <div style="height:4px"></div>`);

    Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
      <button class="btn" id="aSubmit" onclick="AddDevice.submit(this)">Tạo ${this.quantity} máy</button>`);
    this.updatePreview();
  },

  async submit(button) {
    try {
      let model;
      if (this.mode === 'new') {
        if (!this.name.trim()) { toast('Chưa nhập tên loại thiết bị.', true); return; }
        if (!this.code || this.code.length < 2) { toast('Mã loại cần ít nhất 2 ký tự.', true); return; }
        model = await withBusy(button, 'Đang tạo…', () => apiPost('devices/models', {
          name: this.name.trim(), code: this.code, brand: this.brand.trim() || null,
          info: this.info.trim() || null, note: this.note.trim() || null,
          quantity: this.quantity, photo_keys: this.photos,
        }));
      } else {
        model = await withBusy(button, 'Đang tạo…',
          () => apiPost(`devices/models/${this.modelId}/units`,
                        { quantity: this.quantity, photo_keys: this.photos }));
      }
      Sheet.close();
      Cache.clear('models');
      Devices.open = model.id;
      Devices.filter = 'ALL';
      toast(`Đã thêm ${this.quantity} máy vào ${model.name}.`);
      openScreen('devices');
      refreshBackground();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   NHÂN SỰ
   ================================================================ */

const StaffForm = {
  id: null, name: '', email: '', deptId: null, status: 'ACTIVE',
  departments: [], holding: [],

  async open(id = null) {
    Sheet.open({ title: id ? 'Sửa nhân sự' : 'Thêm nhân sự', body: loadingBox(), foot: '' });
    try {
      const [departments, staff] = await Promise.all([loadDepartments(), loadStaff()]);
      this.departments = departments;
      const s = id ? staff.find((x) => x.id === id) : null;
      this.id = id;
      this.name = s ? s.full_name : '';
      this.email = s ? (s.email || '') : '';
      this.deptId = s ? s.department_id : (StaffScreen.dept || (departments[0] && departments[0].id));
      this.status = s ? s.status : 'ACTIVE';
      this.holding = s ? s.units_held : [];
      this.isHead = s ? s.is_head : false;
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.draw();
  },

  draw() {
    Sheet.setBody(`
      <div class="field"><label for="sfName">Họ và tên</label>
        <input id="sfName" placeholder="VD: Nguyễn Văn An" value="${esc(this.name)}"
               oninput="StaffForm.name=this.value"></div>
      <div class="field"><label for="sfMail">Email</label>
        <input id="sfMail" type="email" inputmode="email" autocapitalize="none"
               placeholder="VD: an.nguyen@alta.com.vn" value="${esc(this.email)}"
               oninput="StaffForm.email=this.value">
</div>
      <div class="field"><label for="sfDept">Phòng ban</label>
        <select id="sfDept" onchange="StaffForm.deptId=+this.value">
          ${this.departments.map((d) => `<option value="${d.id}" ${
            d.id === this.deptId ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}
        </select></div>
      <div class="field"><label>Trạng thái</label>
        <div class="conds" style="margin-top:0">
          <button data-c="NORMAL" class="${this.status === 'ACTIVE' ? 'on' : ''}"
                  onclick="StaffForm.status='ACTIVE';StaffForm.draw()">Đang làm việc</button>
          <button data-c="BROKEN" class="${this.status === 'INACTIVE' ? 'on' : ''}"
                  onclick="StaffForm.setInactive()">Đã nghỉ</button>
        </div></div>
      ${this.holding.length ? `<div class="note" style="border-left-color:var(--out)">
        Đang giữ <b>${this.holding.length} máy</b>:
        <span class="mono">${esc(this.holding.join(', '))}</span></div>` : ''}
      <div style="height:8px"></div>`);

    Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
      <button class="btn" onclick="StaffForm.submit(this)">${
        this.id ? 'Lưu thay đổi' : 'Tạo nhân sự'}</button>`);
  },

  setInactive() {
    if (this.holding.length) {
      toast(`Không thể cho nghỉ khi còn giữ ${this.holding.length} máy chưa trả.`, true);
      return;
    }
    this.status = 'INACTIVE';
    this.draw();
  },

  async submit(button) {
    const body = {
      full_name: this.name.trim(),
      email: this.email.trim() || null,
      department_id: this.deptId,
      status: this.status,
    };
    if (!body.full_name) { toast('Chưa nhập họ tên.', true); return; }
    try {
      await withBusy(button, 'Đang lưu…', () => this.id
        ? apiPut(`staff/${this.id}`, body) : apiPost('staff', body));
      Sheet.close();
      Cache.clear('staff', 'departments');
      StaffScreen.dept = this.deptId;
      toast(this.id ? `Đã lưu thông tin ${body.full_name}.` : `Đã thêm ${body.full_name}.`);
      renderStaffBody();
      refreshBackground();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   PHÒNG BAN
   ================================================================ */

const DeptForm = {
  id: null, name: '', headId: null, people: [],

  async open(id = null) {
    Sheet.open({ title: id ? 'Sửa phòng ban' : 'Thêm phòng ban', body: loadingBox(), foot: '' });
    try {
      const [departments, staff] = await Promise.all([loadDepartments(), loadStaff()]);
      const d = id ? departments.find((x) => x.id === id) : null;
      this.id = id;
      this.name = d ? d.name : '';
      this.headId = d ? d.head_staff_id : null;
      this.people = id ? staff.filter((s) => s.department_id === id && s.status === 'ACTIVE') : [];
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.draw();
  },

  draw() {
    const withEmail = this.people.filter((s) => s.email);
    Sheet.setBody(`
      <div class="field"><label for="dfName">Tên phòng ban</label>
        <input id="dfName" placeholder="VD: Chăm sóc khách hàng" value="${esc(this.name)}"
               oninput="DeptForm.name=this.value"></div>

      <div class="field"><label for="dfHead">Trưởng bộ phận</label>
      ${!this.id
        ? '<div class="empty" style="padding:14px">Đặt được sau khi phòng đã có nhân sự</div>'
        : !withEmail.length
        ? '<div class="empty" style="padding:14px">Phòng chưa có nhân sự nào có email</div>'
        : `<select id="dfHead" onchange="DeptForm.headId=this.value?+this.value:null">
             <option value="">— Chưa đặt —</option>
             ${withEmail.map((s) => `<option value="${s.id}" ${
               s.id === this.headId ? 'selected' : ''}>${esc(s.full_name)} · ${
               esc(s.email)}</option>`).join('')}
           </select>`}
      </div>

      ${this.id ? `<h2 class="sec">Nhân sự trong phòng <span class="count">${this.people.length}</span></h2>
        ${this.people.length ? `<div class="picks">${this.people.map((s) => `
          <button class="pick" onclick="Sheet.close();StaffForm.open(${s.id})">
            <div class="av">${esc(initials(s.full_name))}</div>
            <div class="nm"><b>${esc(s.full_name)}</b><em>${esc(s.email || 'chưa có email')}${
              s.id === this.headId ? ' · trưởng bộ phận' : ''}</em></div>${CHEVRON}</button>`).join('')}</div>`
          : emptyBox('Chưa có nhân sự nào')}` : ''}
      <div style="height:8px"></div>`);

    Sheet.setFoot(`
      ${this.id && can('loan.departments.delete')
        ? '<button class="btn ghost" onclick="DeptForm.remove(this)">Xoá</button>'
        : '<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>'}
      <button class="btn" onclick="DeptForm.submit(this)">${
        this.id ? 'Lưu thay đổi' : 'Tạo phòng ban'}</button>`);
  },

  async submit(button) {
    const name = this.name.trim();
    if (!name) { toast('Chưa nhập tên phòng ban.', true); return; }
    try {
      await withBusy(button, 'Đang lưu…', () => this.id
        ? apiPut(`departments/${this.id}`, { name, head_staff_id: this.headId })
        : apiPost('departments', { name, head_staff_id: null }));
      Sheet.close();
      Cache.clear('departments', 'staff');
      toast(this.id ? `Đã lưu phòng ${name}.`
        : `Đã tạo phòng ${name}. Thêm nhân sự rồi đặt trưởng bộ phận.`);
      renderDepartments();
      refreshBackground();
    } catch (err) {
      toastError(err);
    }
  },

  async remove(button) {
    if (!window.confirm(`Xoá phòng ${this.name}?`)) return;
    try {
      await withBusy(button, 'Đang xoá…', () => apiDel(`departments/${this.id}`));
      Sheet.close();
      Cache.clear('departments');
      toast(`Đã xoá phòng ${this.name}.`);
      renderDepartments();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   BẢO TRÌ
   ================================================================ */

const Maint = {
  async complete(id, button) {
    try {
      await withBusy(button, 'Đang cập nhật…',
        () => apiPost(`maintenance/${id}/complete`, { clear_issue: true }));
      toast('Đã hoàn tất bảo trì — máy trở lại trạng thái sẵn sàng.');
      Cache.clear('models');
      renderMaint();
      refreshBackground();
    } catch (err) {
      toastError(err);
    }
  },

  schedule(unitId) {
    let note = '';
    Sheet.open({
      title: 'Đưa vào bảo trì',
      body: `<div class="field"><label for="mNote">Nội dung bảo trì</label>
          <textarea id="mNote" placeholder="VD: thay bóng đèn, vệ sinh quạt…"
                    oninput="Maint._note=this.value"></textarea></div>`,
      foot: `<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
        <button class="btn" onclick="Maint.submitSchedule(${unitId}, this)">Tạo lịch bảo trì</button>`,
    });
    Maint._note = note;
  },

  async submitSchedule(unitId, button) {
    try {
      await withBusy(button, 'Đang tạo…',
        () => apiPost('maintenance', { unit_id: unitId, note: (Maint._note || '').trim() || null }));
      Sheet.close();
      Cache.clear('models');
      toast('Đã tạo lịch bảo trì.');
      refreshBackground();
      if (currentScreen === 'devices') renderDeviceList();
      if (currentScreen === 'maint') renderMaint();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   NHẬP / XUẤT KHO
   ================================================================ */

function openStockChoice() {
  Sheet.open({
    title: 'Lập phiếu kho',
    body: `<div class="rows">
        <button class="row" onclick="StockImport.open()">
          <div class="main"><div class="title">Nhập hàng vào kho</div>
            <div class="meta">Ghi nhận lô hàng mới mua về để bán, kèm ảnh sản phẩm</div></div>
          ${CHEVRON}</button>
        <button class="row" onclick="StockExport.open()">
          <div class="main"><div class="title">Xuất hàng ra khỏi kho</div>
            <div class="meta">Bán, bảo hành, cấp nội bộ… trừ thẳng vào tồn kho</div></div>
          ${CHEVRON}</button>
      </div>`,
    foot: '<button class="btn ghost" onclick="Sheet.close()">Đóng</button>',
  });
}

const currentUserBadge = (role) => `
  <div class="locked" style="margin-bottom:16px">
    <div class="av">${esc(initials(ME.fullName || ME.username))}</div>
    <div><b>${esc(ME.fullName || ME.username)}</b><em>${esc(ME.username)}</em></div>
    <span class="pill p-mute" style="margin-left:auto">${esc(role)}</span>
  </div>`;

const StockImport = {
  product: '', brand: '', model: '', qty: 1, condition: 'Hàng mới', note: '', photos: [],

  open() {
    this.product = ''; this.brand = ''; this.model = '';
    this.qty = 1; this.condition = 'Hàng mới'; this.note = ''; this.photos = [];
    Sheet.open({ title: 'Phiếu nhập hàng', body: '', foot: '',
      guard: () => !!(StockImport.product.trim() || StockImport.note.trim()
        || StockImport.photos.length) });
    this.draw();
  },

  bump(delta) {
    this.qty = Math.max(1, Math.min(9999, this.qty + delta));
    const el = $('impQty');
    if (el) el.textContent = this.qty;
    const btn = $('impSubmit');
    if (btn) btn.textContent = `Nhập ${this.qty} cái`;
  },

  addPhoto() {
    Photos.pick('im_export', (keys) => { this.photos.push(...keys); this.draw(); });
  },
  removePhoto(i) { this.photos.splice(i, 1); this.draw(); },

  draw() {
    Sheet.setBody(`
      ${currentUserBadge('Người nhập')}
      <div class="field"><label for="iProd">Tên sản phẩm</label>
        <input id="iProd" placeholder="VD: Laptop Dell Vostro 3520" value="${esc(this.product)}"
               oninput="StockImport.product=this.value"></div>
      <div class="field"><label for="iBrand">Hãng</label>
        <input id="iBrand" placeholder="VD: Dell" value="${esc(this.brand)}"
               oninput="StockImport.brand=this.value"></div>
      <div class="field"><label for="iModel">Model</label>
        <input id="iModel" class="mono" style="text-transform:uppercase" placeholder="VD: VOS-3520"
               value="${esc(this.model)}" oninput="StockImport.model=this.value.toUpperCase()">
</div>
      <div class="field"><label>Số lượng nhập</label>
        <div class="stepper" style="width:fit-content">
          <button onclick="StockImport.bump(-1)" aria-label="Giảm">−</button>
          <span id="impQty">${this.qty}</span>
          <button onclick="StockImport.bump(1)" aria-label="Tăng">+</button>
        </div></div>
      <div class="field"><label for="iCond">Tình trạng hàng</label>
        <select id="iCond" onchange="StockImport.condition=this.value">
          ${['Hàng mới', 'Hàng tân trang', 'Hàng trưng bày'].map((c) =>
            `<option ${this.condition === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}
        </select></div>
      <div class="field"><label for="iNote">Ghi chú</label>
        <textarea id="iNote" placeholder="VD: lô nhập quý III, bảo hành 12 tháng…"
                  oninput="StockImport.note=this.value">${esc(this.note)}</textarea></div>
      <h2 class="sec">Ảnh sản phẩm <span class="count">${this.photos.length}</span></h2>
      ${this.photos.length
        ? `<div class="photos">${this.photos.map((_, i) =>
            `<div class="thumb pending"><span class="mono" style="font-size:13px">Đã tải lên</span>
              <span class="del" role="button" onclick="StockImport.removePhoto(${i})">
                <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></span></div>`).join('')}</div>`
        : '<div class="nophoto">Chưa có ảnh sản phẩm</div>'}
      ${cameraButton('StockImport.addPhoto()', 'Chụp ảnh sản phẩm')}
      <div style="height:8px"></div>`);

    Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
      <button class="btn" id="impSubmit" onclick="StockImport.submit(this)">Nhập ${this.qty} cái</button>`);
  },

  async submit(button) {
    if (!this.product.trim()) { toast('Chưa nhập tên sản phẩm.', true); return; }
    if (!this.model.trim()) { toast('Chưa nhập model — model dùng để tính tồn kho.', true); return; }
    try {
      await withBusy(button, 'Đang lưu…', () => apiPost('stock/imports', {
        product_name: this.product.trim(), brand: this.brand.trim() || null,
        model_code: this.model.trim(), qty: this.qty, condition: this.condition,
        note: this.note.trim() || null, photo_keys: this.photos,
      }));
      Sheet.close();
      toast(`Đã nhập ${this.qty} × ${this.product.trim()} — ghi nhận bởi ${ME.username}.`);
      Stock.tab = 'imports';
      renderStock();
    } catch (err) {
      toastError(err);
    }
  },
};

const StockExport = {
  levels: [], key: null, qty: 1, purpose: 'Bán', destination: '', note: '', photos: [],
  purposes: ['Bán', 'Bảo hành', 'Cấp nội bộ', 'Trả nhà cung cấp'],

  async open(presetJson = null) {
    this.qty = 1; this.purpose = 'Bán'; this.destination = ''; this.note = ''; this.photos = [];
    Sheet.open({ title: 'Phiếu xuất hàng', body: loadingBox(), foot: '',
      guard: () => !!(StockExport.destination.trim() || StockExport.note.trim()
        || StockExport.photos.length) });
    try {
      const all = await apiGet('stock/levels');
      this.levels = all.filter((r) => r.on_hand > 0);
      if (!this.levels.length) {
        Sheet.setBody(emptyBox('Kho đang hết hàng, chưa có gì để xuất.'));
        Sheet.setFoot('<button class="btn ghost" onclick="Sheet.close()">Đóng</button>');
        return;
      }
      let preset = null;
      if (presetJson) {
        try { preset = JSON.parse(presetJson); } catch (_) { preset = null; }
      }
      const match = preset && this.levels.find((r) =>
        r.product_name === preset.product_name && r.model_code === preset.model_code);
      const chosen = match || this.levels[0];
      this.key = `${chosen.product_name}||${chosen.model_code}`;
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.draw();
  },

  current() {
    const [product, model] = (this.key || '').split('||');
    return this.levels.find((r) => r.product_name === product && r.model_code === model)
      || this.levels[0];
  },

  bump(delta) {
    const row = this.current();
    this.qty = Math.max(1, Math.min(row.on_hand, this.qty + delta));
    const el = $('expQty');
    if (el) el.textContent = this.qty;
    const btn = $('expSubmit');
    if (btn) btn.textContent = `Xuất ${this.qty} cái`;
    const left = $('expLeft');
    if (left) {
      left.innerHTML = `Tồn hiện tại <b class="mono">${row.on_hand}</b> → sau khi xuất còn
        <b class="mono">${row.on_hand - this.qty}</b>`;
    }
  },

  addPhoto() {
    Photos.pick('im_export', (keys) => { this.photos.push(...keys); this.draw(); });
  },
  removePhoto(i) { this.photos.splice(i, 1); this.draw(); },

  draw() {
    const row = this.current();
    Sheet.setBody(`
      ${currentUserBadge('Người xuất')}
      <div class="field"><label for="eKey">Sản phẩm trong kho</label>
        <select id="eKey" onchange="StockExport.key=this.value;StockExport.qty=1;StockExport.draw()">
          ${this.levels.map((r) => {
            const key = `${r.product_name}||${r.model_code}`;
            return `<option value="${esc(key)}" ${key === this.key ? 'selected' : ''}>${
              esc(r.product_name)} — ${esc(r.model_code)} (còn ${r.on_hand})</option>`;
          }).join('')}
        </select></div>
      <div class="field"><label>Số lượng xuất</label>
        <div class="stepper" style="width:fit-content">
          <button onclick="StockExport.bump(-1)" aria-label="Giảm">−</button>
          <span id="expQty">${this.qty}</span>
          <button onclick="StockExport.bump(1)" aria-label="Tăng">+</button>
        </div>
        <div class="hint" id="expLeft">Tồn hiện tại <b class="mono">${row.on_hand}</b> →
          sau khi xuất còn <b class="mono">${row.on_hand - this.qty}</b></div></div>
      <div class="field"><label>Mục đích xuất</label>
        <div class="chips" style="margin-bottom:0">
          ${this.purposes.map((p) => `<button class="chip ${this.purpose === p ? 'on' : ''}"
            onclick="StockExport.purpose='${esc(p)}';StockExport.draw()">${esc(p)}</button>`).join('')}
        </div></div>
      <div class="field"><label for="eDest">Nơi nhận / khách hàng</label>
        <input id="eDest" placeholder="VD: Công ty TNHH Minh Phát" value="${esc(this.destination)}"
               oninput="StockExport.destination=this.value"></div>
      <div class="field"><label for="eNote">Ghi chú</label>
        <textarea id="eNote" placeholder="VD: giao kèm hoá đơn VAT…"
                  oninput="StockExport.note=this.value">${esc(this.note)}</textarea></div>
      <h2 class="sec">Ảnh bàn giao <span class="count">${this.photos.length}</span></h2>
      ${this.photos.length
        ? `<div class="photos">${this.photos.map((_, i) =>
            `<div class="thumb pending"><span class="mono" style="font-size:13px">Đã tải lên</span>
              <span class="del" role="button" onclick="StockExport.removePhoto(${i})">
                <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg></span></div>`).join('')}</div>`
        : '<div class="nophoto">Chưa có ảnh</div>'}
      ${cameraButton('StockExport.addPhoto()', 'Chụp ảnh sản phẩm')}
      <div style="height:8px"></div>`);

    Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
      <button class="btn" id="expSubmit" onclick="StockExport.submit(this)">Xuất ${this.qty} cái</button>`);
  },

  async submit(button) {
    const row = this.current();
    try {
      await withBusy(button, 'Đang lưu…', () => apiPost('stock/exports', {
        product_name: row.product_name, model_code: row.model_code, qty: this.qty,
        purpose: this.purpose, destination: this.destination.trim() || null,
        note: this.note.trim() || null, photo_keys: this.photos,
      }));
      Sheet.close();
      toast(`Đã xuất ${this.qty} × ${row.product_name} (${this.purpose.toLowerCase()}) — tồn còn ${
        row.on_hand - this.qty}. Ghi nhận bởi ${ME.username}.`);
      Stock.tab = 'exports';
      renderStock();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   PHÂN QUYỀN
   ================================================================ */

const Perms = {
  user: null, draft: [], catalog: null, newPw: null,

  async open(userId) {
    Sheet.open({ title: 'Đang tải…', body: loadingBox(), foot: '' });
    try {
      const [users, catalog] = await Promise.all([
        apiGet('users', { limit: 200 }),
        this.catalog ? Promise.resolve(this.catalog) : apiGet('users/permission-catalog'),
      ]);
      this.catalog = catalog;
      this.user = users.find((u) => u.id === userId);
      if (!this.user) { Sheet.setBody(emptyBox('Không tìm thấy tài khoản')); return; }
      this.draft = [...this.user.permissions];
      this.newPw = null;
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.draw();
  },

  preset(kind) { this.draft = [...(this.catalog.presets[kind] || [])]; this.draw(); },

  toggle(key) {
    const i = this.draft.indexOf(key);
    if (i < 0) this.draft.push(key); else this.draft.splice(i, 1);
    this.draw();
  },

  toggleGroup(groupKey) {
    const group = this.catalog.groups.find((g) => g.key === groupKey);
    const keys = group.actions.map((a) => a.key);
    const hasAll = keys.every((k) => this.draft.includes(k));
    this.draft = this.draft.filter((k) => !keys.includes(k));
    if (!hasAll) this.draft.push(...keys);
    this.draw();
  },

  draw() {
    const u = this.user;
    Sheet.setTitle(esc(u.full_name || u.username));
    Sheet.setBody(`
      <div class="locked" style="margin-bottom:14px">
        <div class="av">${esc(initials(u.full_name || u.username))}</div>
        <div><b>${esc(u.full_name || u.username)}</b><em>${esc(u.username)}</em></div>
        <span class="pill ${u.role === 'ADMIN' ? 'p-out' : 'p-mute'}"
              style="margin-left:auto">${esc(u.role)}</span>
      </div>

      ${u.role === 'ADMIN' ? '<div class="empty" style="padding:18px">Toàn quyền</div>'
      : `
      <div class="chips" style="margin-bottom:14px">
        <button class="chip" onclick="Perms.preset('all')">Toàn quyền</button>
        <button class="chip" onclick="Perms.preset('loan')">Nhóm cho mượn</button>
        <button class="chip" onclick="Perms.preset('view')">Chỉ xem</button>
        <button class="chip" onclick="Perms.preset('none')">Bỏ hết</button>
      </div>
      <div style="font-size:15px;color:var(--muted);margin-bottom:12px">
        Đang chọn <b class="mono" style="color:var(--ink)">${this.draft.length}/${
          this.catalog.total}</b> quyền</div>
      ${this.catalog.groups.map((g) => {
        const on = g.actions.filter((a) => this.draft.includes(a.key)).length;
        return `<div class="perm">
          <div class="ph"><b>${esc(g.label)}</b><span class="mini">${on}/4</span>
            <button class="chip" style="padding:5px 10px;font-size:14px"
                    onclick="Perms.toggleGroup('${esc(g.key)}')">${
              on === 4 ? 'Bỏ chọn' : 'Chọn hết'}</button></div>
          <div class="pb">${g.actions.map((a) => `
            <button class="${this.draft.includes(a.key) ? 'on' : ''}"
                    onclick="Perms.toggle('${esc(a.key)}')">
              <span class="box"></span>${esc(a.label)}</button>`).join('')}</div>
        </div>`;
      }).join('')}

      <h2 class="sec">Trạng thái tài khoản</h2>
      <div class="conds" style="margin-top:0">
        <button data-c="NORMAL" class="${u.is_active ? 'on' : ''}"
                onclick="Perms.user.is_active=true;Perms.draw()">Đang hoạt động</button>
        <button data-c="BROKEN" class="${u.is_active ? '' : 'on'}"
                onclick="Perms.user.is_active=false;Perms.draw()">Vô hiệu hoá</button>
      </div>`}

      ${this.canReset() ? `<h2 class="sec">Mật khẩu</h2>${this.resetBlock()}` : ''}
      <div style="height:8px"></div>`);

    const canEdit = can('users.update') && (u.role !== 'ADMIN' || IS_ADMIN);
    Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Đóng</button>
      ${canEdit ? '<button class="btn" onclick="Perms.submit(this)">Lưu thay đổi</button>' : ''}`);
  },

  /* ---------- đặt lại mật khẩu hộ nhân sự ---------- */

  canReset() {
    // Cùng luật với máy chủ: chỉ quản trị viên mới chạm được tài khoản quản trị
    return can('users.update') && (this.user.role !== 'ADMIN' || IS_ADMIN);
  },

  resetBlock() {
    if (this.newPw) {
      return `<div class="note" style="border-left-color:var(--ok)">
          Mật khẩu mới của <b>${esc(this.user.username)}</b>:
          <div class="pwshow"><code id="pwNew">${esc(this.newPw)}</code>
            <button class="btn ghost sm" style="width:auto;padding:0 12px"
                    onclick="Perms.copyPw(this)">Sao chép</button></div>
          Chép và gửi cho nhân sự ngay. Đóng cửa sổ này là không xem lại được.
        </div>`;
    }
    return `<div class="field" style="margin-bottom:10px">
        <div class="pwwrap">
          <input id="pwSet" type="text" placeholder="Nhập mật khẩu mới, tối thiểu 6 ký tự"
                 autocomplete="new-password">
        </div>
      </div>
      <div style="display:flex;gap:9px">
        <button class="btn ghost sm" style="flex:1" onclick="Perms.suggestPw()">Sinh ngẫu nhiên</button>
        <button class="btn ghost sm" style="flex:1" onclick="Perms.resetPw(this)">Đặt lại mật khẩu</button>
      </div>`;
  },

  suggestPw() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
    const bytes = new Uint32Array(12);
    crypto.getRandomValues(bytes);
    $('pwSet').value = Array.from(bytes, (n) => chars[n % chars.length]).join('');
  },

  async copyPw(button) {
    try {
      await navigator.clipboard.writeText(this.newPw);
      button.textContent = 'Đã chép';
    } catch (_) {
      // Trình duyệt chặn clipboard thì bôi đen sẵn để người dùng tự Ctrl+C
      const range = document.createRange();
      range.selectNodeContents($('pwNew'));
      const sel = window.getSelection();
      sel.removeAllRanges(); sel.addRange(range);
      toast('Trình duyệt chặn tự chép — mật khẩu đã được bôi đen, nhấn Ctrl+C.', true);
    }
  },

  async resetPw(button) {
    const pw = ($('pwSet').value || '').trim();
    if (pw.length < 6) { toast('Mật khẩu tối thiểu 6 ký tự.', true); $('pwSet').focus(); return; }
    try {
      await withBusy(button, 'Đang đặt…', () => apiPut(`users/${this.user.id}`, { password: pw }));
      this.newPw = pw;
      this.draw();
      toast(`Đã đặt mật khẩu mới cho ${this.user.username}.`);
    } catch (err) {
      toastError(err);
    }
  },

  async submit(button) {
    const u = this.user;
    try {
      await withBusy(button, 'Đang lưu…', () => apiPut(`users/${u.id}`, {
        is_active: u.is_active,
        permissions: u.role === 'ADMIN' ? undefined : this.draft,
      }));
      Sheet.close();
      toast(`Đã lưu thay đổi cho ${u.full_name || u.username}.`);
      renderUsers();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   TẠO TÀI KHOẢN MỚI

   Dùng lại đúng ma trận 28 quyền của màn phân quyền. Vai trò luôn là USER —
   máy chủ không nhận vai trò từ trình duyệt, muốn thêm quản trị viên thì chạy
   scripts/create-admin.py ngay trên máy chủ.
   ================================================================ */

const NewUser = {
  draft: [], catalog: null, active: true,

  async open() {
    if (!can('users.create')) { toast('Bạn không có quyền tạo tài khoản.', true); return; }
    this.draft = [];
    this.active = true;

    Sheet.open({ title: 'Tạo tài khoản', body: loadingBox(), foot: '',
      guard: () => {
        const t = NewUser.read();
        return !!(t.username.trim() || t.fullName.trim() || NewUser.draft.length);
      } });
    try {
      this.catalog = this.catalog || await apiGet('users/permission-catalog');
    } catch (err) {
      Sheet.setBody(errorBox(err));
      return;
    }
    this.draw();
  },

  preset(kind) { this.draft = [...(this.catalog.presets[kind] || [])]; this.draw(true); },

  toggle(key) {
    const i = this.draft.indexOf(key);
    if (i < 0) this.draft.push(key); else this.draft.splice(i, 1);
    this.draw(true);
  },

  toggleGroup(groupKey) {
    const group = this.catalog.groups.find((g) => g.key === groupKey);
    const keys = group.actions.map((a) => a.key);
    const hasAll = keys.every((k) => this.draft.includes(k));
    this.draft = this.draft.filter((k) => !keys.includes(k));
    if (!hasAll) this.draft.push(...keys);
    this.draw(true);
  },

  /** Vẽ lại nhưng giữ nguyên những gì đã gõ — bấm vào ô quyền không được xoá form. */
  read() {
    const get = (id) => { const el = $(id); return el ? el.value : ''; };
    return { username: get('nuUser'), fullName: get('nuName'), password: get('nuPass') };
  },

  draw(keepTyped) {
    const kept = keepTyped ? this.read() : { username: '', fullName: '', password: '' };

    Sheet.setTitle('Tạo tài khoản');
    Sheet.setBody(`
      <div class="field"><label for="nuName">Họ tên</label>
        <input id="nuName" placeholder="VD: Trần Thị Bình" value="${esc(kept.fullName)}"></div>

      <div class="field"><label for="nuUser">Tên đăng nhập</label>
        <input id="nuUser" class="mono" autocapitalize="none" autocorrect="off" spellcheck="false"
               placeholder="VD: binh.tran" value="${esc(kept.username)}">
        <div class="hint">Tối thiểu 5 ký tự, không dấu.</div></div>

      <div class="field"><label for="nuPass">Mật khẩu</label>
        <div class="pwwrap">
          <input id="nuPass" type="password" autocomplete="new-password"
                 placeholder="Tối thiểu 6 ký tự" value="${esc(kept.password)}">
          <button class="eye" type="button" onclick="NewUser.toggleEye(this)" aria-label="Hiện mật khẩu">
            <svg viewBox="0 0 24 24"><path d="M2 12s3.8-6.5 10-6.5S22 12 22 12s-3.8 6.5-10 6.5S2 12 2 12z"/>
              <circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
        <div class="hint">Tối thiểu 6 ký tự.
          <b style="cursor:pointer;text-decoration:underline;text-underline-offset:3px"
             onclick="NewUser.suggest()">Sinh giúp tôi</b></div></div>

      <h2 class="sec">Quyền</h2>
      <div class="chips" style="margin-bottom:14px">
        <button class="chip" onclick="NewUser.preset('all')">Toàn quyền</button>
        <button class="chip" onclick="NewUser.preset('loan')">Nhóm cho mượn</button>
        <button class="chip" onclick="NewUser.preset('view')">Chỉ xem</button>
        <button class="chip" onclick="NewUser.preset('none')">Bỏ hết</button>
      </div>
      <div style="font-size:15px;color:var(--muted);margin-bottom:12px">
        Đang chọn <b class="mono" style="color:var(--ink)">${this.draft.length}/${
          this.catalog.total}</b> quyền</div>
      ${this.catalog.groups.map((g) => {
        const on = g.actions.filter((a) => this.draft.includes(a.key)).length;
        return `<div class="perm">
          <div class="ph"><b>${esc(g.label)}</b><span class="mini">${on}/4</span>
            <button class="chip" style="padding:5px 10px;font-size:14px"
                    onclick="NewUser.toggleGroup('${esc(g.key)}')">${
              on === 4 ? 'Bỏ chọn' : 'Chọn hết'}</button></div>
          <div class="pb">${g.actions.map((a) => `
            <button class="${this.draft.includes(a.key) ? 'on' : ''}"
                    onclick="NewUser.toggle('${esc(a.key)}')">
              <span class="box"></span>${esc(a.label)}</button>`).join('')}</div>
        </div>`;
      }).join('')}

      <h2 class="sec">Trạng thái</h2>
      <div class="conds" style="margin-top:0">
        <button data-c="NORMAL" class="${this.active ? 'on' : ''}"
                onclick="NewUser.active=true;NewUser.draw(true)">Đang hoạt động</button>
        <button data-c="BROKEN" class="${this.active ? '' : 'on'}"
                onclick="NewUser.active=false;NewUser.draw(true)">Vô hiệu hoá</button>
      </div>
      <div style="height:8px"></div>`);

    Sheet.setFoot(`<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
      <button class="btn" onclick="NewUser.submit(this)">Tạo tài khoản</button>`);
  },

  toggleEye(button) {
    const input = $('nuPass');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-label', show ? 'Ẩn mật khẩu' : 'Hiện mật khẩu');
  },

  /** Mật khẩu ngẫu nhiên 14 ký tự, hiện luôn để người tạo chép cho nhân sự. */
  suggest() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
    const bytes = new Uint32Array(14);
    crypto.getRandomValues(bytes);
    const pw = Array.from(bytes, (n) => chars[n % chars.length]).join('');
    $('nuPass').value = pw;
    $('nuPass').type = 'text';
    toast('Đã sinh mật khẩu — nhớ chép lại trước khi đóng.');
  },

  async submit(button) {
    const { username, fullName, password } = this.read();
    const user = username.trim().toLowerCase();

    if (user.length < 5) { toast('Tên đăng nhập tối thiểu 5 ký tự.', true); $('nuUser').focus(); return; }
    if (!/^[a-z0-9._-]+$/.test(user)) {
      toast('Tên đăng nhập chỉ gồm chữ thường, số và . _ -', true); $('nuUser').focus(); return;
    }
    if (password.length < 6) { toast('Mật khẩu tối thiểu 6 ký tự.', true); $('nuPass').focus(); return; }

    try {
      const created = await withBusy(button, 'Đang tạo…', () => apiPost('users', {
        username: user,
        password,
        full_name: fullName.trim() || null,
        is_active: this.active,
        permissions: this.draft,
      }));
      Sheet.close();
      toast(`Đã tạo tài khoản ${created.username} với ${created.permissions.length} quyền.`);
      renderUsers();
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   ĐỔI MẬT KHẨU
   ================================================================ */

const ChangePassword = {
  open() {
    Sheet.open({
      title: 'Đổi mật khẩu',
      body: `<div class="field"><label for="cpOld">Mật khẩu hiện tại</label>
          <input id="cpOld" type="password" autocomplete="current-password"></div>
        <div class="field"><label for="cpNew">Mật khẩu mới</label>
          <input id="cpNew" type="password" autocomplete="new-password">
          <div class="hint">Tối thiểu 6 ký tự.</div></div>
        <div class="field"><label for="cpNew2">Nhập lại mật khẩu mới</label>
          <input id="cpNew2" type="password" autocomplete="new-password"></div>`,
      foot: `<button class="btn ghost" onclick="Sheet.close()">Huỷ</button>
        <button class="btn" onclick="ChangePassword.submit(this)">Đổi mật khẩu</button>`,
    });
  },

  async submit(button) {
    const oldPw = $('cpOld').value;
    const newPw = $('cpNew').value;
    const confirm = $('cpNew2').value;
    if (!oldPw || !newPw) { toast('Chưa nhập đủ thông tin.', true); return; }
    if (newPw.length < 6) { toast('Mật khẩu mới tối thiểu 6 ký tự.', true); return; }
    if (newPw !== confirm) { toast('Hai lần nhập mật khẩu mới không khớp.', true); return; }
    try {
      await withBusy(button, 'Đang đổi…', () => apiPost('users/me/change-password', {
        current_password: oldPw, new_password: newPw,
      }));
      Sheet.close();
      toast('Đã đổi mật khẩu.');
    } catch (err) {
      toastError(err);
    }
  },
};

/* ================================================================
   NHẬP DANH MỤC THIẾT BỊ TỪ EXCEL

   Mỗi dòng trong file là một LOẠI thiết bị; cột quantity quyết định hệ
   thống sinh bao nhiêu máy đơn chiếc cho loại đó. Loại đã có sẵn (trùng
   model_code) chỉ được cập nhật thông tin, KHÔNG sinh thêm máy — nếu không
   mỗi lần nhập lại file cũ sẽ nhân đôi số máy trong kho.
   ================================================================ */

const ImportExcel = {
  file: null,

  open() {
    if (!can('loan.devices.create')) {
      toast('Bạn không có quyền thêm thiết bị.', true);
      return;
    }
    this.file = null;
    Sheet.open({ title: 'Nhập thiết bị từ Excel', body: '', foot: '' });
    this.draw();
  },

  draw() {
    Sheet.setBody(`
      <h2 class="sec" style="margin-top:0">Bước 1 — Lấy file mẫu</h2>
      <button class="btn ghost" onclick="downloadFile('devices/import-template')">
        <svg viewBox="0 0 24 24"><path d="M12 3v12M7 11l5 5 5-5M5 21h14"/></svg>
        Tải file mẫu .xlsx
      </button>

      <h2 class="sec">Bước 2 — Chọn file đã điền</h2>
      <button class="btn ghost" onclick="ImportExcel.pick()">
        <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
        ${this.file ? 'Chọn file khác' : 'Chọn file .xlsx'}
      </button>
      ${this.file ? `<div class="locked" style="margin-top:10px">
          <div class="av">XLS</div>
          <div><b>${esc(this.file.name)}</b>
            <em>${(this.file.size / 1024).toFixed(0)} KB</em></div>
        </div>` : ''}

      <div style="height:8px"></div>`);

    Sheet.setFoot(`
      <button class="btn ghost" onclick="Sheet.close()">Đóng</button>
      <button class="btn" id="impGo" ${this.file ? '' : 'disabled'}
              onclick="ImportExcel.submit(this)">Nhập vào hệ thống</button>`);
  },

  pick() {
    const input = $('xlsxPicker');
    input.value = '';
    input.onchange = () => {
      const f = input.files && input.files[0];
      if (!f) return;
      if (!f.name.toLowerCase().endsWith('.xlsx')) {
        toast('Chỉ nhận file .xlsx. File .xls hoặc .csv phải lưu lại thành .xlsx trước.', true);
        return;
      }
      this.file = f;
      this.draw();
    };
    input.click();
  },

  async submit(button) {
    if (!this.file) return;
    let result;
    try {
      result = await withBusy(button, 'Đang nhập…',
        () => apiUpload('devices/import-excel', this.file));
    } catch (err) {
      toastError(err);
      return;
    }

    Cache.clear('models');
    renderDeviceList();
    refreshBackground();
    this.showResult(result);
  },

  showResult(r) {
    const ok = r.created_models + r.updated_models;
    Sheet.setTitle(r.failed && !ok ? 'Không nhập được dòng nào' : 'Đã nhập xong');
    Sheet.setBody(`
      <div class="kpis" style="margin-bottom:16px">
        <div class="kpi" style="cursor:default">
          <div class="k"><span class="dot" style="background:var(--ok)"></span>Loại mới</div>
          <div class="v">${r.created_models}</div>
          <div class="sub">${r.created_units} máy được sinh ra</div>
        </div>
        <div class="kpi" style="cursor:default">
          <div class="k"><span class="dot" style="background:var(--out)"></span>Loại cập nhật</div>
          <div class="v">${r.updated_models}</div>
          <div class="sub">giữ nguyên số máy cũ</div>
        </div>
      </div>

      ${r.failed ? `<h2 class="sec" style="margin-top:0">Dòng bị bỏ qua
          <span class="count">${r.failed}</span></h2>
        <div class="rows">${r.errors.map((e) => `
          <div class="row flag" style="cursor:default">
            <div class="main">
              <div class="title">Dòng ${e.row} trong file Excel</div>
              <div class="meta" style="color:var(--bad);white-space:normal">${esc(e.error)}</div>
            </div>
          </div>`).join('')}</div>` : ''}
      <div style="height:8px"></div>`);

    Sheet.setFoot(`
      <button class="btn ghost" onclick="ImportExcel.open()">Nhập file khác</button>
      <button class="btn" onclick="Sheet.close()">Xong</button>`);

    if (ok) toast(`Đã nhập ${ok} loại thiết bị, sinh ${r.created_units} máy.`);
  },
};
