FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend

RUN apt-get update && \
    apt-get install -y --no-install-recommends tesseract-ocr poppler-utils && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Use the app entrypoint so Railway can inject HOST/PORT at runtime.
CMD ["python", "run.py"]
