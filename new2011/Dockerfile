FROM python:3.11-bullseye

ENV PORT 8080

# 1. Install necessary build tools (CRITICAL FIX - Cleaned of hidden characters)
RUN apt-get update && apt-get install -y gcc libc-dev libffi-dev && rm -rf /var/lib/apt/lists/*

# 2. BREAK CACHE: Force rebuild every time
RUN echo "Build time: $(date)" > build_time.txt

# 3. Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the single, merged application file
COPY search_core.py .
COPY config_reader.py .
COPY search_utilities.py .
COPY document_parsers.py .


COPY setup.txt .

# 5. Start Gunicorn (Points to app_core:app)
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 search_core:app