# Dockerfile for SecureLend backend, built specifically so pytesseract's
# OCR (used for the salary-slip cross-check) actually works on Render.
# Render's default Python buildpack does NOT include the Tesseract binary
# -- pytesseract is just a Python wrapper around it, so without this,
# ids.extract_declared_salary_from_text() silently returns None on every
# upload and the mismatch check never fires (fails open, not loudly).

FROM python:3.12-slim

# Tesseract OCR binary + build tools some Python packages need to compile
# native extensions. (poppler-utils isn't needed -- your PDF text
# extraction uses pdfplumber, which is pure-Python.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (separate layer) so Docker can cache
# this step and skip reinstalling everything on every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code.
COPY . .

# Tesseract's binary is on PATH after apt install, so pytesseract finds it
# automatically -- but set this explicitly too, matching how ids.py reads
# TESSERACT_CMD from the environment (your local .env points this at a
# Windows .exe path, which obviously doesn't exist here; Render's
# environment variables should NOT set TESSERACT_CMD at all, or should
# set it to this Linux path, so ids.py falls back to this default).
ENV TESSERACT_CMD=/usr/bin/tesseract

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]