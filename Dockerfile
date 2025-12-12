FROM python:3.11-bullseye

ENV PORT 8080

# 1. Install necessary build tools (CRITICAL FIX - Cleaned of hidden characters)
#RUN apt-get update && apt-get install -y gcc libc-dev libffi-dev && rm -rf /var/lib/apt/lists/*
RUN apt-get update && \
    apt-get install -y \
        libxml2-dev \
        libxslt1-dev \
        tesseract-ocr \
        tesseract-ocr-heb \
        libsm6 libxext6 libxrender-dev \
        gcc libc-dev libffi-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. BREAK CACHE: Force rebuild every time
RUN echo "Build time: $(date)" > build_time.txt

# 3. Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the single, merged application file
COPY setup.txt .
COPY search_core.py .
COPY config_reader.py .
COPY document_parsers.py .
COPY search_utilities.py .



# 5. Start Gunicorn (Points to app_core:app)
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 search_core:app