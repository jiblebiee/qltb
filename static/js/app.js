/* =============================================================
   Điều hướng và khởi động.
   Thanh dưới chỉ hiện những mục tài khoản có quyền xem.
   ============================================================= */
'use strict';

let currentScreen = 'home';
let navRoot = 'home';

const NAV_ITEMS = [
  { key: 'home', label: 'Tổng quan', perms: null,
    icon: 'M3 11l9-8 9 8v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z' },
  { key: 'loans', label: 'Mượn - Trả', perms: ['loan.loans.view'],
    icon: 'M4 6h16M4 12h10M4 18h7M20 15l-3 3 3 3' },
  { key: 'devices', label: 'Thiết bị', perms: ['loan.devices.view'],
    icon: 'M4 5h16v11H4zM8 20h8M12 16v4' },
  { key: 'stock', label: 'Nhập / Xuất', perms: ['import_export.view'],
    icon: 'M3 8l9-5 9 5v9l-9 5-9-5zM3 8l9 5 9-5M12 13v9' },
  { key: 'more', label: 'Thêm', perms: null, icon: 'M4 7h16M4 12h16M4 17h16' },
];

const SUBPAGES = ['staff', 'depts', 'maint', 'users', 'email'];

/* Cột trái trên máy tính: hiện thẳng mọi mục, không phải chui qua tab "Thêm" */
const SIDE_GROUPS = [
  { title: null, items: [
    { key: 'home', label: 'Tổng quan', perms: null,
      icon: 'M3 11l9-8 9 8v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z' },
    { key: 'loans', label: 'Mượn - Trả', perms: ['loan.loans.view'], badge: true,
      icon: 'M4 6h16M4 12h10M4 18h7M20 15l-3 3 3 3' },
    { key: 'devices', label: 'Thiết bị', perms: ['loan.devices.view'],
      icon: 'M4 5h16v11H4zM8 20h8M12 16v4' },
    { key: 'stock', label: 'Nhập / Xuất', perms: ['import_export.view'],
      icon: 'M3 8l9-5 9 5v9l-9 5-9-5zM3 8l9 5 9-5M12 13v9' },
  ] },
  { title: 'Danh mục', items: [
    { key: 'staff', label: 'Nhân sự', perms: ['loan.staff.view'],
      icon: 'M16 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M9.5 6.5a3 3 0 11-6 0 3 3 0 016 0zM21 20v-2a4 4 0 00-3-3.9M16 3.6a4 4 0 010 7.8' },
    { key: 'depts', label: 'Phòng ban', perms: ['loan.departments.view'],
      icon: 'M3 21h18M5 21V6l7-3 7 3v15M9 10h1M14 10h1M9 14h1M14 14h1M11 21v-4h2v4' },
    { key: 'maint', label: 'Bảo trì & hỏng', perms: ['loan.maintenance.view'],
      icon: 'M14.7 6.3a4 4 0 01-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 015.4-5.4l-2.6 2.6-2-2z' },
  ] },
  { title: 'Hệ thống', items: [
    { key: 'users', label: 'Tài khoản & quyền', perms: ['users.view'],
      icon: 'M12 15a4 4 0 100-8 4 4 0 000 8zM5 21a7 7 0 0114 0M18 4l1.5 1.5M21 8h-2' },
    { key: 'email', label: 'Lịch sử gửi mail', perms: ['loan.loans.view'],
      icon: 'M3 6h18v12H3z M3 7l9 6 9-6' },
  ] },
];

const TITLES = {
  loans: ['Mượn - Trả', 'Phiếu mượn và nhận trả từng máy'],
  devices: ['Thiết bị cho mượn', 'Quản lý theo từng máy có mã riêng'],
  stock: ['Nhập / Xuất kho', 'Hàng hoá kinh doanh — nhập về để bán'],
  more: ['Thêm', 'Danh mục và cấu hình hệ thống'],
  staff: ['Nhân sự', 'Ai đang giữ máy nào'],
  depts: ['Phòng ban', 'Trưởng bộ phận nhận email thông báo'],
  maint: ['Bảo trì & hỏng', 'Máy không sẵn sàng cho mượn'],
  users: ['Tài khoản & phân quyền', 'Người dùng và 28 quyền'],
  email: ['Lịch sử gửi mail', 'Nhật ký thư hệ thống đã gửi'],
};

const RENDERERS = {
  home: renderHome,
  loans: renderLoans,
  devices: renderDevices,
  stock: renderStock,
  more: renderMore,
  staff: renderStaffScreen,
  depts: renderDepartments,
  maint: renderMaint,
  users: renderUsers,
  email: renderEmailLogs,
};

const SCREEN_PERMS = {
  loans: ['loan.loans.view'],
  devices: ['loan.devices.view'],
  stock: ['import_export.view'],
  staff: ['loan.staff.view'],
  depts: ['loan.departments.view'],
  maint: ['loan.maintenance.view'],
  users: ['users.view'],
  email: ['loan.loans.view'],
};

const visibleNav = () => NAV_ITEMS.filter((n) => !n.perms || can(...n.perms));

function buildNav() {
  $('nav').innerHTML = visibleNav().map((n) => `
    <button data-k="${n.key}" onclick="openScreen('${n.key}')" aria-label="${esc(n.label)}">
      <span class="wrap">
        <svg viewBox="0 0 24 24"><path d="${n.icon}"/></svg>
        ${n.key === 'loans' ? '<span class="badge" id="navBadge" hidden>0</span>' : ''}
      </span>
      <span>${esc(n.label)}</span>
    </button>`).join('');
  $('nav').style.gridTemplateColumns = `repeat(${visibleNav().length}, 1fr)`;
}

function buildSideNav() {
  $('snav').innerHTML = SIDE_GROUPS.map((g) => {
    const items = g.items.filter((n) => !n.perms || can(...n.perms));
    if (!items.length) return '';
    return (g.title ? `<div class="grp">${esc(g.title)}</div>` : '') + items.map((n) => `
      <button data-k="${n.key}" onclick="openScreen('${n.key}')">
        <svg viewBox="0 0 24 24"><path d="${n.icon}"/></svg>
        <span>${esc(n.label)}</span>
        ${n.badge ? '<span class="sbadge" id="sideBadge" hidden>0</span>' : ''}
      </button>`).join('');
  }).join('');

  $('sideAv').textContent = initials(ME.fullName || ME.username);
  $('sideName').textContent = ME.fullName || ME.username;
  $('sideRole').textContent = IS_ADMIN ? 'Quản trị viên' : ME.username;
}

/**
 * Trên máy tính không có nút tròn nổi ở góc — thao tác chính nằm ngay bên phải
 * thanh tiêu đề, đúng chỗ mắt tìm tới. Cùng một nút, chỉ đổi chỗ đứng.
 */
function placeFab() {
  const fab = $('fab');
  const target = isWide() ? $('barSlot') : $('fab').closest('.phone');
  if (fab.parentElement !== target) target.appendChild(fab);
}

function openScreen(key, fromHistory = false) {
  const needed = SCREEN_PERMS[key];
  if (needed && !can(...needed)) {
    toast('Bạn không có quyền xem mục này.', true);
    return;
  }

  document.querySelectorAll('.screen').forEach((s) => s.classList.remove('on'));
  $('s-' + key).classList.add('on');
  currentScreen = key;
  if (!SUBPAGES.includes(key)) navRoot = key;

  document.querySelectorAll('#nav button')
    .forEach((b) => b.classList.toggle('on', b.dataset.k === navRoot));
  // Cột trái sáng đúng mục đang mở, kể cả các mục con
  document.querySelectorAll('#snav button')
    .forEach((b) => b.classList.toggle('on', b.dataset.k === key));

  // Nút quay lại chỉ có nghĩa khi điều hướng bằng thanh dưới của điện thoại
  const isSub = SUBPAGES.includes(key) && !isWide();
  $('backBtn').hidden = !isSub;
  $('mark').hidden = isSub;

  if (key === 'home') {
    // Gọi đủ họ tên. Cắt còn chữ cuối ("Quản trị viên" thành "viên") nghe rất kỳ.
    $('barTitle').textContent = `${greeting()}, ${ME.fullName || ME.username}`;
    $('barSub').textContent = `${IS_ADMIN ? 'Quản trị viên' : 'Nhân viên'} · ${ME.username}`;
  } else {
    let [title, sub] = TITLES[key] || ['', ''];
    // Trên máy tính, "Thêm" không còn là menu — nó là trang tài khoản
    if (key === 'more' && isWide()) [title, sub] = ['Tài khoản của bạn', 'Thông tin đăng nhập'];
    $('barTitle').textContent = title;
    $('barSub').textContent = sub;
  }

  $('body').scrollTop = 0;
  updateFab(key);
  (RENDERERS[key] || (() => {}))();

  // Ghi vào lịch sử trình duyệt để nút Quay lại đi ngược trong ứng dụng,
  // thay vì nhảy ra màn hình đăng nhập.
  if (!fromHistory) {
    const url = '#' + key;
    if (location.hash !== url) history.pushState({ screen: key }, '', url);
    else history.replaceState({ screen: key }, '', url);
  }
}

function goBack() { history.back(); }

/** Màn hình ứng với địa chỉ hiện tại, nếu địa chỉ đó hợp lệ. */
function screenFromHash() {
  const key = (location.hash || '').replace(/^#/, '');
  return $('s-' + key) ? key : null;
}

/* ---------------------------------------------------------------- nút tròn */

const FAB_ACTIONS = {
  loans: { label: 'Tạo phiếu mượn', perms: ['loan.loans.create'], run: () => Borrow.open() },
  devices: { label: 'Thêm máy mới', perms: ['loan.devices.create'], run: () => AddDevice.open() },
  stock: { label: 'Lập phiếu', perms: ['import_export.create'], run: () => openStockChoice() },
  staff: { label: 'Thêm nhân sự', perms: ['loan.staff.create'], run: () => StaffForm.open() },
  depts: { label: 'Thêm phòng ban', perms: ['loan.departments.create'], run: () => DeptForm.open() },
  users: { label: 'Tạo tài khoản', perms: ['users.create'], run: () => NewUser.open() },
};

function updateFab(key) {
  const action = FAB_ACTIONS[key];
  const fab = $('fab');
  if (!action || !can(...action.perms)) {
    fab.hidden = true;
    return;
  }
  fab.hidden = false;
  $('fabLabel').textContent = action.label;
}

function fabAction() {
  const action = FAB_ACTIONS[currentScreen];
  if (action && can(...action.perms)) action.run();
}

/* ---------------------------------------------------------------- làm mới ngầm */

/**
 * Sau mỗi thao tác ghi, cập nhật lại huy hiệu quá hạn và màn hình Tổng quan
 * nếu nó đã từng được vẽ — người dùng quay lại là thấy số đúng ngay.
 */
async function refreshBackground() {
  try {
    const data = await apiGet('dashboard');
    updateBadge(data.tickets.overdue);
    if (currentScreen === 'home') renderHome();
    else $('s-home').dataset.loaded = '';
  } catch (_) {
    // Làm mới ngầm thất bại thì bỏ qua, không làm phiền người dùng
  }
}

function updateBadge(count) {
  ['navBadge', 'sideBadge'].forEach((id) => {
    const badge = $(id);
    if (!badge) return;
    badge.textContent = count;
    badge.hidden = !count;
  });
}

/* ---------------------------------------------------------------- khởi động */

async function boot() {
  buildNav();
  buildSideNav();
  placeFab();
  // Đổi kích thước cửa sổ hay xoay màn hình thì vẽ lại theo bố cục mới:
  // danh sách chuyển giữa dạng bảng và dạng thẻ, nút chính đổi chỗ.
  WIDE.addEventListener('change', () => {
    placeFab();
    openScreen(currentScreen);
  });

  $('mark').textContent = initials(ME.fullName || ME.username);
  $('backBtn').addEventListener('click', goBack);
  $('fab').addEventListener('click', fabAction);
  paintThemeButton();
  $('themeBtn').addEventListener('click', toggleTheme);
  // Chưa tự chọn thì đi theo cài đặt của máy, đổi tới đâu vẽ lại tới đó
  window.matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', paintThemeButton);

  $('mailBtn').addEventListener('click', () => {
    if (can('loan.loans.view')) openScreen('email');
    else toast('Bạn không có quyền xem lịch sử gửi mail.', true);
  });
  $('mailBtn').hidden = !can('loan.loans.view');

  // Màn hình đầu tiên: Tổng quan nếu xem được thiết bị, ngược lại vào mục Thêm
  const first = can('loan.devices.view', 'loan.loans.view') ? 'home' : 'more';
  window.addEventListener('popstate', (e) => {
    const key = (e.state && e.state.screen) || screenFromHash() || first;
    openScreen(key, true);
  });
  // Mở lại đúng tab đang xem khi người dùng tải lại trang
  openScreen(screenFromHash() || first);

  try {
    const data = await apiGet('dashboard');
    updateBadge(data.tickets.overdue);
  } catch (_) {
    // Không có quyền xem tổng quan thì bỏ qua huy hiệu
  }
}

document.addEventListener('DOMContentLoaded', boot);
