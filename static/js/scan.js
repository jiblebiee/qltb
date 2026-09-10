/* =============================================================
   Quét mã QR / mã vạch dán trên máy.

   Ba đường, tự chọn đường tốt nhất máy hỗ trợ:

   1. BarcodeDetector — có sẵn trong Chrome / Edge / trình duyệt Android.
      Nhanh nhất, đọc được cả QR lẫn mã vạch một chiều.
   2. jsQR — thư viện nằm ngay trong máy chủ, không gọi ra Internet. Chỉ đọc
      QR nhưng chạy được ở mọi trình duyệt.
   3. Chụp một tấm ảnh rồi giải mã — dùng khi trang chạy trên http:// chứ
      không phải https://. Trình duyệt CHẶN camera trực tiếp ở http, nhưng ô
      chọn tệp có capture thì vẫn mở được camera. Chậm hơn một nhịp, đổi lại
      không cần dựng HTTPS cho mạng nội bộ.
   ============================================================= */
'use strict';

const Scan = {
  stream: null,
  raf: null,
  detector: null,
  onFound: null,
  lastText: '',
  lastAt: 0,

  /** Trang có được trình duyệt cho phép mở camera trực tiếp không. */
  canUseCamera() {
    return !!(window.isSecureContext && navigator.mediaDevices
      && navigator.mediaDevices.getUserMedia);
  },

  /**
   * Mở khung quét. `onFound(text)` được gọi mỗi lần đọc được một mã;
   * trả về true nếu muốn đóng khung ngay sau đó.
   */
  async open(onFound, { title = 'Quét mã máy' } = {}) {
    this.onFound = onFound;
    this.lastText = '';

    if (!this.canUseCamera()) { this.openPhotoFallback(); return; }

    const box = $('scanner');
    box.classList.add('on');
    $('scanTitle').textContent = title;
    $('scanHint').textContent = 'Đưa mã vào giữa khung';

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } }, audio: false,
      });
    } catch (err) {
      this.close();
      // Người dùng từ chối, hoặc máy không có camera — vẫn còn đường chụp ảnh
      toast('Không mở được camera. Chụp một tấm ảnh mã thay nhé.', true);
      this.openPhotoFallback();
      return;
    }

    const video = $('scanVideo');
    video.srcObject = this.stream;
    video.setAttribute('playsinline', '');
    await video.play().catch(() => {});

    if ('BarcodeDetector' in window) {
      try {
        const kinds = await window.BarcodeDetector.getSupportedFormats();
        this.detector = new window.BarcodeDetector({
          formats: kinds.filter((f) => ['qr_code', 'code_128', 'code_39', 'ean_13'].includes(f)),
        });
      } catch (_) { this.detector = null; }
    }
    this.loop();
  },

  /** Một vòng đọc khung hình. Dừng lại ngay khi khung quét đã đóng. */
  async loop() {
    const video = $('scanVideo');
    if (!this.stream || !video.videoWidth) {
      this.raf = requestAnimationFrame(() => this.loop());
      return;
    }

    let text = null;
    if (this.detector) {
      try {
        const hits = await this.detector.detect(video);
        if (hits.length) text = hits[0].rawValue;
      } catch (_) { this.detector = null; }
    }
    if (!text && window.jsQR) {
      const cv = $('scanCanvas');
      // Giảm cỡ khung hình xuống còn tối đa 480px: đủ để đọc mã, nhẹ cho máy yếu
      const scale = Math.min(1, 480 / Math.max(video.videoWidth, video.videoHeight));
      cv.width = Math.round(video.videoWidth * scale);
      cv.height = Math.round(video.videoHeight * scale);
      const ctx = cv.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(video, 0, 0, cv.width, cv.height);
      const img = ctx.getImageData(0, 0, cv.width, cv.height);
      const hit = window.jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' });
      if (hit) text = hit.data;
    }

    if (text) this.hit(text);
    if (this.stream) this.raf = requestAnimationFrame(() => this.loop());
  },

  /** Một mã vừa đọc được. Chặn lặp lại trong 1,2 giây để khỏi thêm trùng. */
  hit(text) {
    const now = Date.now();
    if (text === this.lastText && now - this.lastAt < 1200) return;
    this.lastText = text; this.lastAt = now;

    if (navigator.vibrate) navigator.vibrate(35);
    const done = this.onFound && this.onFound(String(text).trim());
    if (done) this.close();
  },

  /** Đổi dòng chữ dưới khung — báo kết quả mà không phải đóng khung lại. */
  say(text) {
    const el = $('scanHint');
    if (el) el.textContent = text;
  },

  close() {
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = null; }
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    const video = $('scanVideo');
    if (video) video.srcObject = null;
    this.detector = null;
    $('scanner').classList.remove('on');
  },

  /* ------------------------------------------------ đường chụp ảnh (http) */

  openPhotoFallback() {
    const picker = $('scanPicker');
    picker.value = '';
    picker.click();
  },

  /** Giải mã một tấm ảnh chụp. Thử vài cỡ vì ảnh điện thoại rất lớn. */
  async decodePhoto(file) {
    if (!file) return;
    if (!window.jsQR) { toast('Thiếu thư viện giải mã QR.', true); return; }

    const bitmap = await createImageBitmap(file).catch(() => null);
    if (!bitmap) { toast('Không đọc được ảnh vừa chụp.', true); return; }

    const cv = $('scanCanvas');
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    for (const side of [1000, 640, 1600]) {
      const scale = Math.min(1, side / Math.max(bitmap.width, bitmap.height));
      cv.width = Math.round(bitmap.width * scale);
      cv.height = Math.round(bitmap.height * scale);
      ctx.drawImage(bitmap, 0, 0, cv.width, cv.height);
      const img = ctx.getImageData(0, 0, cv.width, cv.height);
      const hit = window.jsQR(img.data, img.width, img.height);
      if (hit) {
        bitmap.close && bitmap.close();
        if (this.onFound) this.onFound(String(hit.data).trim());
        return;
      }
    }
    bitmap.close && bitmap.close();
    toast('Không tìm thấy mã QR trong ảnh. Chụp lại gần và rõ hơn nhé.', true);
  },
};

document.addEventListener('DOMContentLoaded', () => {
  const close = $('scanClose');
  if (close) close.addEventListener('click', () => Scan.close());
  const backdrop = $('scanner');
  if (backdrop) {
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) Scan.close(); });
  }
  const picker = $('scanPicker');
  if (picker) {
    picker.addEventListener('change', (e) => Scan.decodePhoto(e.target.files[0]));
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && $('scanner') && $('scanner').classList.contains('on')) {
      e.stopPropagation();
      Scan.close();
    }
  }, true);
});
