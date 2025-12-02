from google import genai
from config_reader import BUCKET_NAME
import os
import io
import time
from google.cloud import storage
from google.cloud import vision_v1 as vision
import traceback
from document_parsers import extract_content3
from config_reader import GCS_OCR_OUTPUT_PATH
import threading
from docx import Document
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple
import json
# --- Global Client Variables (Set to None for Lazy Loading) ---
storage_client = None
vision_client = None
gemini_client = None
gcs_bucket = None     # <-- NEW: Store the GCS Bucket object once

# --- Global Shared State for Caching ---


MAX_CHARS_PER_DOC = 100000

# In search_utilities.py (UPDATED GLOBALS)
# --- Global Shared State for Caching ---
# Key: directory_path (e.g., "my_folder/docs")
# Value: List[Dict] (The document data for that path)
DIRECTORY_CACHE_MAP: Dict[str, List[Dict]] = {}
cache_lock = threading.Lock() # Use this lock for thread-safe access to the map

# The existing get_gcs_files_context function is used below (assuming it's here)

def get_documents_for_path(directory_path: str) -> List[Dict[str, Any]]:
    """
    Retrieves document context for a path. Fetches from GCS only if not in cache.
    The returned list contains objects: [{"name": str, "full_path": str, "content": str, ...}]
    """
    global DIRECTORY_CACHE_MAP, cache_lock

    # Clean the path for consistent key lookup
    cleaned_path = directory_path.strip("/")

    # 1. READ CHECK (FAST PATH)
    with cache_lock:
        if cleaned_path in DIRECTORY_CACHE_MAP:
            print(f"CACHE-HIT: Returning cached documents for '{cleaned_path}'.")
            # Always return a copy for safety
            return list(DIRECTORY_CACHE_MAP[cleaned_path])

    # 2. CACHE MISS (SLOW PATH - Fetch from GCS)
    print(f"CACHE-MISS: Fetching from GCS for '{cleaned_path}'. This may be slow.")

    # Use your existing synchronous GCS fetching function.
    # NOTE: We pass BUCKET_NAME which is defined in this file.
    fetched_documents = get_gcs_files_context(cleaned_path, BUCKET_NAME)

    # 3. WRITE TO CACHE
    with cache_lock:
        DIRECTORY_CACHE_MAP[cleaned_path] = fetched_documents
        print(f"CACHE-WRITE: Stored {len(fetched_documents)} documents for '{cleaned_path}'.")

    return fetched_documents

def initialize_all_clients():
    """
    Initializes clients only if they haven't been initialized yet.
    This runs inside the request context on the first call.
    """
    # CRITICAL: Add gcs_bucket to the global list
    global storage_client, gemini_client, vision_client, gcs_bucket

    # 1. Initialize Storage Client and Bucket
    if storage_client is None:
        storage_client = get_storage_client()

        # --- CRITICAL INSERTION POINT ---
        if storage_client is not None and BUCKET_NAME and gcs_bucket is None:
            try:
                # This line sets the global gcs_bucket variable!
                gcs_bucket = storage_client.bucket(BUCKET_NAME)
                print(f"✅ GCS STEP 2: Successfully connected to Bucket '{BUCKET_NAME}'.")
            except Exception as e:
                print(f"FATAL: GCS STEP 2: FAILED to get Bucket '{BUCKET_NAME}'. Check IAM Permissions. Error: {e}")
                gcs_bucket = None  # Ensure it is None on failure
        # --- END CRITICAL INSERTION POINT ---

    # 2. Initialize other clients
    if vision_client is None:
        vision_client = get_vision_client()

    if gemini_client is None:
        gemini_client = get_gemini_client()

    # Returns True only if all critical clients are initialized
    return (storage_client is not None and gcs_bucket is not None and  # Ensure gcs_bucket is checked!
            gemini_client is not None and vision_client is not None)



def get_storage_client():
    """Initializes and returns the Google Cloud Storage client."""
    try:
        return storage.Client()
    except Exception as e:
        print(f"FATAL: Could not initialize GCS client. Error: {e}")
        return None


def get_vision_client():
    """Initializes and returns the Google Cloud Vision client."""
    try:
        #return vision.V1.ImageAnnotatorClient() #vision.ImageAnnotatorClient()
        return vision.ImageAnnotatorClient()
    except Exception as e:
        print(f"FATAL: Could not initialize Vision client. Error: {e}")
        return None


def get_gemini_client():
    """Initializes and returns the Gemini client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("FATAL: GEMINI_API_KEY environment variable not set.")
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"FATAL: Could not initialize Gemini client. Check API Key. Error: {e}")
        return None

# Add this function to search_utilities.py
def get_gcs_bucket():
    """Returns the initialized GCS bucket object, ensuring initialization is attempted."""
    global gcs_bucket
    if gcs_bucket is None:
        initialize_all_clients()
    return gcs_bucket



# Add this function (or just use get_gcs_bucket logic)
def get_storage_client_instance():
    """Returns the initialized Storage client object."""
    global storage_client
    if storage_client is None:
        initialize_all_clients()
    return storage_client

# Add this function
def get_vision_client_instance():
    """Returns the initialized Vision client object."""
    global vision_client
    if vision_client is None:
        initialize_all_clients()
    return vision_client

# Add this function
def get_gemini_client_instance():
    """Returns the initialized Gemini client object."""
    global gemini_client
    if gemini_client is None:
        initialize_all_clients()
    return gemini_client



def detect_text_gcs_async(gcs_uri, gcs_destination_uri):
    """
    Performs asynchronous OCR on a PDF in GCS using the Vision API.
    gcs_uri: Input GCS path of the PDF (e.g. 'gs://bucket/folder/file.pdf').
    gcs_destination_uri: GCS folder prefix where JSON results will be written
                         (e.g. 'gs://bucket/vision_ocr_output/job123/').
    """
    vision_client = get_vision_client_instance()

    if vision_client is None:
        return "ERROR: Vision client not initialized."

    print(f"👁️ Starting ASYNC PDF OCR for {gcs_uri} -> {gcs_destination_uri}")

    # 1) Build Vision request objects
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

    gcs_source = vision.GcsSource(uri=gcs_uri)
    input_config = vision.InputConfig(
        gcs_source=gcs_source,
        mime_type="application/pdf",  # ✅ important
    )

    gcs_destination = vision.GcsDestination(uri=gcs_destination_uri)
    output_config = vision.OutputConfig(
        gcs_destination=gcs_destination,
        batch_size=5,  # pages per JSON file (tune if needed)
    )

    async_request = vision.AsyncAnnotateFileRequest(
        features=[feature],
        input_config=input_config,
        output_config=output_config,
    )

    # 2) Call async_batch_annotate_files (this is the correct method)
    operation = vision_client.async_batch_annotate_files(requests=[async_request])

    try:
        result = operation.result(timeout=300)  # wait up to 5 minutes
        print("✅ ASYNC PDF OCR operation finished.")
    except Exception as e:
        print(f"❌ ASYNC OCR operation failed or timed out: {e}")
        traceback.print_exc()
        return f"ERROR: ASYNC OCR failed or timed out: {e}"

    # 3) Read JSON outputs from the destination bucket
    full_text = ""
    storage_cli = get_storage_client_instance()

    # Parse bucket and prefix from 'gs://bucket/prefix/...'
    parts = gcs_destination_uri.replace("gs://", "").split("/", 1)
    out_bucket_name = parts[0]
    out_prefix = parts[1].rstrip("/") + "/"

    try:
        bucket = storage_cli.bucket(out_bucket_name)
        blobs = bucket.list_blobs(prefix=out_prefix)

        for blob in blobs:
            if not blob.name.endswith(".json"):
                continue

            json_bytes = blob.download_as_bytes()
            json_data = json.loads(json_bytes)

            # Each JSON file corresponds to an AnnotateFileResponse with 'responses'
            for response in json_data.get("responses", []):
                full_annotation = response.get("fullTextAnnotation")
                if full_annotation and full_annotation.get("text"):
                    full_text += full_annotation["text"] + "\n"

            # Optional cleanup: delete JSON result files to avoid clutter
            blob.delete()

        if full_text.strip():
            print("✅ ASYNC PDF OCR successful, text extracted.")
            return full_text
        else:
            print("⚠️ ASYNC PDF OCR executed but found no text.")
            return "ERROR: ASYNC PDF OCR executed but found no text."

    except Exception as e:
        print(f"❌ Error reading OCR results or cleaning up: {e}")
        traceback.print_exc()
        return f"ERROR: Error processing OCR output: {e}"



def extract_content(blob_bytes, blob_name, full_gcs_path):
    """
    Extracts text content from document bytes.

    - PDF files are routed to the asynchronous Vision API OCR (detect_text_gcs_async).
    - DOCX files use the docx library.
    - Other files are treated as plain text.
    """

    blob_name_lower = blob_name.lower()
    prefix = "gs://" + BUCKET_NAME + "/"
    gcs_uri = prefix + full_gcs_path

    # Check for PDF
    if blob_name_lower.endswith('.pdf'):
        # NEW LOGIC: Use ASYNCHRONOUS Vision OCR for all PDFs
        # (This handles both scanned images and selectable text robustly)

        # Create a unique temporary path for this job's output
        job_id = f"ocr_job_{os.path.basename(full_gcs_path)}_{int(time.time())}"
        gcs_destination_uri = GCS_OCR_OUTPUT_PATH + job_id + "/"

        # Call the async OCR function defined in step 2
        try:
            content = detect_text_gcs_async(gcs_uri, gcs_destination_uri)
            return content
        except NameError:
            # Fallback if the function is not defined, useful for debugging
            return "ERROR: detect_text_gcs_async function is not defined."

    # Check for DOCX
    elif blob_name_lower.endswith('.docx'):
        text = ""
        try:
            document = Document(io.BytesIO(blob_bytes))
            for paragraph in document.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            return f"ERROR: Could not read DOCX content: {e}"

    # Handle other files as plain text (TXT, CSV, etc.)
    try:
        # We assume the bytes are UTF-8 encoded text
        return blob_bytes.decode('utf-8', errors='ignore').strip()
    except Exception as e:
        return f"ERROR: Could not decode text content for {blob_name}. {e}"


# Global limit for concurrency to prevent overwhelming the server/GCS
MAX_CONCURRENT_DOWNLOADS = 10


def get_gcs_files_context(directory_path: str, bucket_name: str, query: str = "") -> List[Dict[str, Any]]:
    """
    Fetches, downloads, and processes content from GCS concurrently using a ThreadPoolExecutor.
    This prevents the request from hitting a 504 Gateway Timeout on large directories.
    """
    directory_path = (directory_path or "").strip("/")
    prefix = f"{directory_path}/" if directory_path else ""
    file_data: List[Dict[str, Any]] = []
    storage_client = get_storage_client_instance()
    # 1. Get the list of blobs (metadata only - this is fast)
    try:
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        # Filter for relevant file types immediately
        blobs_to_process = [
            blob for blob in blobs
            if blob.name.endswith(('.docx', '.pdf', '.txt'))
        ]

    except Exception as e:
        print(f"ERROR: Failed to list GCS blobs: {e}")
        return []

    def process_single_blob(blob):
        """Worker function executed by each thread."""
        try:
            # NETWORK I/O: This is the slow part now happening in parallel
            file_content_bytes = blob.download_as_bytes()
            content_string = extract_content(file_content_bytes, blob.name, blob.name)

            if content_string.startswith("ERROR:") or not content_string:
                return None

            # Determine relative name
            relative_name = blob.name[len(prefix):] if prefix and blob.name.startswith(prefix) else blob.name

            return {
                "name": relative_name,
                "full_path": blob.name,
                "content": content_string[:MAX_CHARS_PER_DOC],  # Assuming MAX_CHARS_PER_DOC is global
                # Pages structure is often too complex to compute concurrently,
                # but adding a placeholder for consistency:
                "pages": [{"page": 1, "lines": content_string.split("\n")}],
            }
        except Exception as e:
            print(f"ERROR processing {blob.name}: {e}")
            return None

    # 2. Execute file processing concurrently
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS) as executor:
        # Map the worker function over the list of blobs
        results = executor.map(process_single_blob, blobs_to_process)

        # Collect results, filtering out None (failed/skipped files)
        file_data = [res for res in results if res is not None]

    return file_data

# ==============================================================================
# --- MOCK & PLACEHOLDER FUNCTIONS ---
# NOTE: Replace these with your actual implementations
# ==============================================================================

# ==============================================================================
# --- REVISED SEARCH FUNCTION ---
# ==============================================================================

