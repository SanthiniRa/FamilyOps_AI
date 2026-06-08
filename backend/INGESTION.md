Document Ingestion (FamilyOps_AI)

Overview

This module handles uploaded documents and ingests them into the Family Knowledge Hub RAG store.

Features

- Save uploaded files (`document_service.save_upload`) and create `UploadedDocument` DB rows.
- Parse PDFs (pdfminer.six), DOCX (python-docx), TXT/MD, and images via OCR (pytesseract + Pillow).
- Chunk document text and store chunks into `rag_service` with provenance metadata: document id, filename, page, chunk index.
- Background ingestion scheduled on upload; manual trigger available at `POST /api/v1/uploads/{doc_id}/ingest`.

Dependencies

- pdfminer.six (PDF parsing)
- python-docx (DOCX parsing)
- pytesseract + tesseract-ocr system binary (OCR)
- Pillow (image handling)
- aiofiles (async file IO)
- pytest, pytest-asyncio (tests)

Quick start

Install Python deps (in virtualenv):

```sh
pip install -r requirements.txt
# or
pip install .
```

On Debian/Ubuntu install tesseract:

```sh
sudo apt update && sudo apt install -y tesseract-ocr
```

Run server locally:

```sh
cd backend
uvicorn main:app --reload --port 8000
```

Upload a document via `POST /api/v1/uploads/document` (multipart/form-data, field `file`).

Manually trigger ingestion:

```sh
curl -X POST http://localhost:8000/api/v1/uploads/<doc_id>/ingest
```

Testing

```sh
cd backend
pytest -q
```
