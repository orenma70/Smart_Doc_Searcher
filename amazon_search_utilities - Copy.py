# Placeholder for Hello World test
def initialize_all_clients():
    return True
'''
import boto3
import os
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from docx import Document
from config_reader import BUCKET_NAME

# --- Configuration & Amazon Clients ---
# These are usually passed via environment variables in ECS

# Use 'textract' if you need OCR on PDFs, otherwise skip
textract_client = boto3.client('textract')
s3_client = boto3.client('s3')

# Global Cache for scannability
DIRECTORY_CACHE_MAP = {}
cache_lock = threading.Lock()


def get_documents_for_path(directory_path: str) -> list:
    """Fetches all supported files from S3 under a specific prefix."""
    cleaned_path = directory_path.strip("/").lower()

    # 1. Check Cache first
    with cache_lock:
        if cleaned_path in DIRECTORY_CACHE_MAP:
            return DIRECTORY_CACHE_MAP[cleaned_path]

    # 2. Fetch from S3 (Listing is fast)
    documents = []
    prefix = f"{cleaned_path}/" if cleaned_path else ""

    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        all_objs = []
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
            if 'Contents' in page:
                all_objs.extend(page['Contents'])

        # 3. Process files concurrently (Downloading is the slow part)
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(process_s3_object, all_objs))
            documents = [r for r in results if r is not None]

        # 4. Save to Cache
        with cache_lock:
            DIRECTORY_CACHE_MAP[cleaned_path] = documents

    except Exception as e:
        print(f"S3 Error listing {prefix}: {e}")

    return documents


def process_s3_object(obj):
    """Downloads an object and extracts text for searching."""
    key = obj['Key']
    if not key.lower().endswith(('.pdf', '.docx', '.txt', '.csv')):
        return None

    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        blob_bytes = response['Body'].read()

        content = ""
        ext = key.lower()

        if ext.endswith('.pdf'):
            # Simple PDF text extraction or Textract
            content = extract_pdf_text_amazon(key)
        elif ext.endswith('.docx'):
            doc = Document(io.BytesIO(blob_bytes))
            content = "\n".join([p.text for p in doc.paragraphs])
        else:
            content = blob_bytes.decode('utf-8', errors='ignore')

        return {
            "name": os.path.basename(key),
            "full_path": key,
            "content": content.lower()  # Store lowercase for easier keyword matching
        }
    except Exception as e:
        print(f"Error reading {key}: {e}")
        return None


def extract_pdf_text_amazon(key):
    """Amazon Textract handles Hebrew and scanned documents better than local libraries."""
    try:
        response = textract_client.detect_document_text(
            Document={'S3Object': {'Bucket': BUCKET_NAME, 'Name': key}}
        )
        return "\n".join([b['Text'] for b in response['Blocks'] if b['BlockType'] == 'LINE'])
    except:
        return ""


def keyword_search(documents: list, query: str):
    """Simple keyword filter."""
    query = query.lower()
    results = [doc for doc in documents if query in doc['content']]
    return results


# Add this to keep your core script happy
def initialize_all_clients():
    return True
'''