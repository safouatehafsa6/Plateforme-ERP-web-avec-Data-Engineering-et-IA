FROM python:3.12-slim

WORKDIR /app

# psycopg2-binary compile depuis les sources sur certaines architectures ;
# libpq-dev + gcc évitent un échec de build silencieux.
# tesseract-ocr (+ langues fra/ara/eng) : OCR des PDF numérisés et des images (IDP).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ca-certificates gnupg \
    tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara tesseract-ocr-eng \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
