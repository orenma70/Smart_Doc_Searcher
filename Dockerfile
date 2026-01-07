# Use a slim version to keep the image small and fast
FROM python:3.11-slim-bullseye

# AWS App Runner typically listens on 8080, but we make it flexible
ENV PORT 8080
ENV PYTHONUNBUFFERED True

# 1. Install necessary build tools AND Tesseract OCR
RUN apt-get update && apt-get install -y \
    gcc \
    libc-dev \
    libffi-dev \
    tesseract-ocr \
    tesseract-ocr-heb \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# 2. Set working directory
WORKDIR /app

# 3. Copy requirements and install
# Note: I added the dot (.) after the filename which was missing in your snippet
COPY amazon_requirements.txt .
RUN pip install --no-cache-dir -r amazon_requirements.txt

# 4. Copy your application files
COPY setup.txt .
COPY amazon_search_core.py .
COPY config_reader.py .
COPY document_parsers.py .
COPY amazon_search_utilities.py .

# 5. Start Gunicorn
# We use gthread to handle concurrent requests better in a container
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "amazon_search_core:app"]
