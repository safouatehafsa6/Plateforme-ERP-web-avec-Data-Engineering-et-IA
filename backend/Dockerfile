FROM python:3.12-slim

WORKDIR /app

# psycopg2-binary compile depuis les sources sur certaines architectures ;
# libpq-dev + gcc évitent un échec de build silencieux.
# tesseract-ocr (+ langues français, arabe, anglais) : OCR des documents
# numérisés et des images pour l'IDP.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
