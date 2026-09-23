FROM python:3.12-slim

WORKDIR /app

# Chỉ cần curl cho HEALTHCHECK. Không cài trình biên dịch: mọi gói trong
# requirements.txt đều có sẵn bản dựng cho Linux x86_64, pip chỉ việc tải về.
# Bỏ build-essential giúp ảnh nhẹ hơn ~250MB và dựng nhanh hơn vài phút.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY static ./static
# Cần cho: docker compose exec web python3 scripts/create-admin.py
COPY scripts ./scripts

# Không chạy bằng root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
