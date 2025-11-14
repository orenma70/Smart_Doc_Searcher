
FROM python:3.11-slim
ENV PORT 8080 

COPY requirements.txt . 

COPY search_core.py . 
COPY api_server.py .
RUN pip install --no-cache-dir -r requirements.txt 



CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 search_core:app
