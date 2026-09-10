from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = Field(alias="DB_URL")

    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    # Địa chỉ MinIO/S3 nhìn từ TRÌNH DUYỆT. Chỉ cần khi máy chủ gọi kho ảnh
    # bằng một tên khác với trình duyệt — ví dụ chạy Docker trọn gói thì máy chủ
    # gọi http://minio:9000 còn trình duyệt phải gọi http://<ip-máy-chủ>:9000.
    # Bỏ trống nếu hai bên dùng chung một địa chỉ.
    s3_public_endpoint_url: str | None = Field(default=None, alias="S3_PUBLIC_ENDPOINT_URL")
    s3_bucket: str = Field(alias="S3_BUCKET")
    s3_region: str = Field(alias="S3_REGION")
    s3_prefix: str = Field(default="images/", alias="S3_PREFIX")
    s3_im_export: str = Field(default="im_export/", alias="S3_IM_EXPORT")

    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")

    presign_expires: int = Field(default=900, alias="PRESIGN_EXPIRES")
    allow_origins: str = Field(default="*", alias="ALLOW_ORIGINS")

    # Login/session
    app_secret_key: str = Field(alias="APP_SECRET_KEY")
    bootstrap_admin_user: str | None = Field(default=None, alias="BOOTSTRAP_ADMIN_USER")
    bootstrap_admin_pass: str | None = Field(default=None, alias="BOOTSTRAP_ADMIN_PASS")

    # Phòng đứng ra cho mượn thiết bị. Phòng này được tạo sẵn lúc khởi động và
    # là nguồn của ô "Người cho mượn" trong phiếu mượn.
    lender_department: str = Field(default="IT", alias="LENDER_DEPARTMENT")

    # Email alerts
    smtp_enabled: bool = Field(default=False, alias="SMTP_ENABLED")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")
    mail_from: str | None = Field(default=None, alias="MAIL_FROM")
    mail_alert_recipients: str = Field(default="", alias="MAIL_ALERT_RECIPIENTS")
    email_manage: str = Field(default="", alias="EMAIL_MANAGE")
    # Không còn dùng: việc nhắc quá hạn hằng ngày của bản cũ đã bị bỏ,
    # thay bằng cảnh báo một lần trong overdue_service.
    loan_reminder_days: int = Field(default=0, alias="LOAN_REMINDER_DAYS")

    # --- Nghiệp vụ mượn ---
    # Phiếu mượn không có hạn trả. Quá số ngày này mà chưa hoàn trả thì phiếu
    # chuyển trạng thái "Quá <n>n" và hệ thống gửi email cho trưởng bộ phận.
    loan_overdue_days: int = Field(default=10, alias="LOAN_OVERDUE_DAYS")

    # --- Bảo mật ---
    # Đặt true khi chạy sau HTTPS để trình duyệt không gửi cookie qua HTTP thường.
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    # Số lần đăng nhập sai liên tiếp trước khi khoá tạm theo IP + tài khoản.
    login_max_attempts: int = Field(default=5, alias="LOGIN_MAX_ATTEMPTS")
    login_lockout_seconds: int = Field(default=300, alias="LOGIN_LOCKOUT_SECONDS")

settings = Settings()
