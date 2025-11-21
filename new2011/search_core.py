import os
import time
import re
import json
import traceback
import threading
from typing import List, Dict, Any, Optional
import logging
from google.cloud import storage
from flask import Flask, request, jsonify

# Local Imports from our modular files
# CRITICAL: Ensure these modules and functions are defined in their respective files
from document_parsers import extract_content3
from search_utilities import split_into_paragraphs, match_line, highlight_matches_html, get_gcs_files_context

# Configuration reader
from config_reader import read_setup

BUCKET_NAME = read_setup("BUCKET_NAME")
GCS_DOCUMENT_PATH = "gs://" + BUCKET_NAME + "/vision_ocr_output/"
SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.txt')
MAX_CHARS_PER_DOC = 10000

# --- Global Client & Cache Variables ---
storage_client: Optional[storage.Client] = None
gcs_bucket: Optional[storage.Bucket] = None
DOCUMENT_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_STATUS = "NOT_STARTED"  # "NOT_STARTED", "WARMING_UP", "READY", or "ERROR"
TOTAL_DOC_COUNT = 0
PROCESSED_DOC_COUNT = 0

app = Flask(__name__)


# --- Client and Cache Initialization Logic ---

def initialize_clients() -> bool:
    """Initializes GCS client and bucket connection."""
    global storage_client, gcs_bucket

    if storage_client is None:
        try:
            storage_client = storage.Client()
        except Exception as e:
            print(f"FATAL: Failed to initialize GCS client. Error: {e}")
            return False

    if storage_client is not None and BUCKET_NAME and gcs_bucket is None:
        try:
            gcs_bucket = storage_client.bucket(BUCKET_NAME)
            print(f"✅ GCS Client: Connected to Bucket '{BUCKET_NAME}'.")
        except Exception as e:
            print(f"FATAL: FAILED to get Bucket '{BUCKET_NAME}'. Check IAM Permissions. Error: {e}")
            return False

    return storage_client is not None and gcs_bucket is not None


def initialize_document_cache(directory_path: str = ""):
    """
    Builds the document cache by listing, downloading, and extracting content
    from GCS. This function runs ONCE in the background thread.
    """
    global CACHE_STATUS, DOCUMENT_CACHE, TOTAL_DOC_COUNT, PROCESSED_DOC_COUNT, gcs_bucket

    if CACHE_STATUS == "READY": return

    if gcs_bucket is None:
        print("FATAL: gcs_bucket is NULL. Cannot proceed with list_blobs.")
        CACHE_STATUS = "ERROR"
        return

    print(f"INFO: Starting document cache initialization for path: '{directory_path}'...")
    CACHE_STATUS = "WARMING_UP"
    temp_cache: Dict[str, Any] = {}

    try:
        prefix = directory_path.strip("/")
        if prefix: prefix += "/"

        # 1. List all blobs to set TOTAL_DOC_COUNT
        all_blobs = list(gcs_bucket.list_blobs(prefix=prefix))

        allowed_extensions = ('.pdf', '.docx', '.txt')

        # Filter blobs by extension and set total count
        filtered_blobs = [
            blob for blob in all_blobs
            if blob.name.lower().endswith(allowed_extensions)
        ]
        TOTAL_DOC_COUNT = len(filtered_blobs)
        PROCESSED_DOC_COUNT = 0
        print(f"INFO: Found {TOTAL_DOC_COUNT} documents to process.")

        for blob in filtered_blobs:
            try:
                # 2. Download file bytes
                blob_bytes = blob.download_as_bytes()

                # 3. Extract content (using imported local parsers)
                extracted_text = extract_content3(blob_bytes, blob.name)

                if extracted_text and not extracted_text.startswith("ERROR:"):
                    # 4. Save to the cache
                    temp_cache[blob.name] = {
                        "name": os.path.basename(blob.name),
                        "content": extracted_text,
                    }
                else:
                    print(f"WARNING: Skipping {blob.name} due to empty or error content.")

            except Exception as dl_e:
                print(f"❌ ERROR downloading or processing {blob.name}: {dl_e}")
                traceback.print_exc()
            finally:
                PROCESSED_DOC_COUNT += 1

        DOCUMENT_CACHE = temp_cache
        CACHE_STATUS = "READY"
        print(f"SUCCESS: Cache populated with {len(DOCUMENT_CACHE)} files.")

    except Exception as e:
        print(f"FATAL ERROR during cache initialization: {e}")
        traceback.print_exc()
        CACHE_STATUS = "ERROR"


# --- Search Execution Helper ---

def execute_search_logic(document_set: Dict[str, Dict[str, Any]], query: str, search_terms: List[str],
                         success_message: str):
    """Common search logic for both cached (fast) and legacy (slow) modes."""
    all_matches = []

    # 1. Check if any documents were passed in (handles GCS failures in fallback mode)
    if not document_set:
        return jsonify({
            "status": "error",
            "message": "No documents available for search. Check GCS bucket path or permissions.",
            "query": query,
            "matches": []
        }), 500

    # 2. Iterate through documents and perform matching
    for doc_path, doc_data in document_set.items():
        doc_content = doc_data['content']
        # Uses split_into_paragraphs from search_utilities.py
        paragraphs = split_into_paragraphs(doc_content)

        doc_matches = []
        for i, paragraph in enumerate(paragraphs):
            # Uses match_line from search_utilities.py
            if match_line(paragraph, search_terms, mode="any", match_type="partial"):
                # Uses highlight_matches_html from search_utilities.py
                highlighted_text = highlight_matches_html(paragraph, search_terms)

                doc_matches.append({
                    "text": highlighted_text,
                    "index": i,
                })

        if doc_matches:
            all_matches.append({
                "document_name": doc_data.get('name', doc_path),
                "document_path": doc_path,
                "matches": doc_matches,
            })

    # 3. Return Results
    return jsonify({
        "status": "ok",
        "message": success_message,
        "query": query,
        "matches": all_matches
    })


# --- Route Definitions ---

@app.route("/")
def health_check():
    """Simple health check and status endpoint."""
    progress = int((PROCESSED_DOC_COUNT / TOTAL_DOC_COUNT) * 100) if TOTAL_DOC_COUNT > 0 else 0
    return jsonify({
        "status": "ok",
        "cache_status": CACHE_STATUS,
        "document_count": len(DOCUMENT_CACHE),
        "total_files": TOTAL_DOC_COUNT,
        "processed_files": PROCESSED_DOC_COUNT,
        "progress_percent": progress
    }), 200


@app.route("/search", methods=["POST"])
@app.route("/simple_search", methods=["POST"])
def search_documents():
    """
    Endpoint for search with automatic fallback:
    1. If cache is READY: Use fast in-memory search.
    2. If cache is WARMING_UP or ERROR: Use slow synchronous GCS fetch (old way).
    """

    data = request.json or {}
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"status": "error", "message": "Query parameter 'query' is required."}), 400

    # 1. Extract and Prepare Search Terms
    search_terms = re.findall(r'\w+', query)
    search_terms = [term.lower() for term in search_terms]

    # --- CRITICAL FALLBACK LOGIC ---
    '''
    if CACHE_STATUS == "READY" and DOCUMENT_CACHE:
        # 1. FAST MODE: Cache is ready.
        document_set = DOCUMENT_CACHE
        message = f"Search executed against {len(DOCUMENT_CACHE)} cached documents."

    else:
        # 2. SLOW FALLBACK MODE (Handles NOT_STARTED, WARMING_UP, and ERROR):

        # Logging only (the function continues execution)
        if CACHE_STATUS == "ERROR":
            print("WARNING: Cache failed to initialize. Falling back to synchronous GCS search.")
        elif CACHE_STATUS in ["NOT_STARTED", "WARMING_UP"]:
            print("WARNING: Cache warming up. Falling back to slow synchronous GCS search.")

        # *** THIS CALL IS THE "OLD WAY" (Synchronous GCS Fetch) ***
        # Uses the global BUCKET_NAME and GCS_DOCUMENT_PATH from config_reader
        document_set = get_gcs_files_context(GCS_DOCUMENT_PATH, BUCKET_NAME)
        message = f"Legacy fallback search executed against {len(document_set)} live GCS documents. Cache Status: {CACHE_STATUS}"

    # 3. Execute Search against the determined document set using the helper function
    return execute_search_logic(document_set, query, search_terms, message)
    '''
    if CACHE_STATUS == "READY" and document_cache:
        # 🟢 FAST MODE: Cache is ready. Execute search against the in-memory cache.
        document_set = document_cache
        message = f"Search executed against {len(document_cache)} cached documents (Cache: READY)."
        return execute_search_logic(document_set, query, search_terms, message)

    else:
        # 🟡 UNAVAILABLE MODE: Cache is not ready (WARMING_UP or ERROR).
        # We skip the slow GCS call entirely and immediately return an error.
        error_message = f"Cache is unavailable. Status: {CACHE_STATUS}. Please wait or check logs."
        logging.warning(error_message)

        status_code = 503 if CACHE_STATUS == "WARMING_UP" else 500

        return jsonify({
            "query": query,
            "matches": [],
            "status": "unavailable",
            "cache_status": CACHE_STATUS,
            "message": error_message
        }), status_code

# --- RUNTIME EXECUTION (The ONLY place server starts) ---

if __name__ == "__main__":

    # 1. Initialize GCS client and bucket connection
    if initialize_clients():
        # 2. CRITICAL STEP: Start the slow function in a separate daemon thread.
        # This runs ONCE when the server boots.
        print(f"LOG: Starting document cache initialization in background thread for path: '{GCS_DOCUMENT_PATH}'.")
        # Use GCS_DOCUMENT_PATH read from the environment
        cache_thread = threading.Thread(target=initialize_document_cache, args=(GCS_DOCUMENT_PATH,), daemon=True)
        cache_thread.start()

    # 3. Start the Flask server immediately.
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))