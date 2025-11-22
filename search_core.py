import os
import time
import re
import json
import io
import traceback  # Ensure this is imported for logging stack traces
from google.cloud import storage
from google.cloud import vision_v1 as vision
from google import genai
from google.genai import errors
from flask import Flask, request, jsonify
#import  pdfplumber
from docx import Document
from pypdf import PdfReader
from typing import List
import threading


from document_parsers import extract_content3, extract_docx_with_lines, find_all_word_positions_in_pdf, split_into_paragraphs, match_line, highlight_matches_html, find_paragraph_position_in_pages
# ... existing configurations ...

# NEW: Required for Vision API Asynchronous PDF OCR output

MAX_CHARS_PER_DOC = 100000



from config_reader import read_setup
BUCKET_NAME=read_setup("BUCKET_NAME")
#BUCKET_NAME="oren-smart-search-docs-1205"

GCS_OCR_OUTPUT_PATH = "gs://" + BUCKET_NAME + "/vision_ocr_output/"

DOCUMENT_CACHE = {} # <-- NEW: This will store extracted text to prevent re-downloading
gcs_bucket = None     # <-- NEW: Store the GCS Bucket object once

# --- Global Shared State ---

# 3. CACHE_STATUS: Flag to track the readiness of the cache.
# Possible values: "PENDING", "READY", "FAILED".
CACHE_STATUS = "PENDING"  # To track the state
cache_lock = threading.Lock() # To safely manage global state updates
cache_thread: threading.Thread | None = None # To hold the background thread instance


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


# --- Global Client Variables (Set to None for Lazy Loading) ---
storage_client = None
vision_client = None
gemini_client = None


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

# --- Utility Functions (RAG Logic) ---
def detect_text_gcs(bucket_name, file_path):
    """
    Performs OCR on the image file in GCS using the Vision API.
    Returns the extracted text or an error message.
    """
    if vision_client is None:
        return "ERROR: Vision client not initialized."

    print(f"👁️ Starting OCR for gs://{bucket_name}/{file_path}")

    # Use the GCS path for the Vision API to read the image directly
    image = vision.Image()
    image.source.image_uri = f'gs://{bucket_name}/{file_path}'

    try:
        # Use document_text_detection for dense text and accurate layout
        response = vision_client.document_text_detection(image=image)

        if response.full_text_annotation and response.full_text_annotation.text:
            print("✅ OCR successful.")
            return response.full_text_annotation.text
        else:
            print("⚠️ OCR found no text.")
            return "ERROR: OCR detected no text content in the image."

    except Exception as e:
        # ❌ CRITICAL CHANGE: Log the full traceback to help debug IAM/API errors
        print(f"❌ OCR Error for {file_path}: {e}")
        print("--- FULL OCR TRACEBACK START ---")
        # This will print the exact reason for the failure (e.g., PermissionDenied)
        traceback.print_exc()
        print("--- FULL OCR TRACEBACK END ---")
        return f"ERROR: OCR failed, likely due to IAM permissions or file format. Details: {e}"

def detect_text_gcs_async(gcs_uri, gcs_destination_uri):
    """
    Performs asynchronous OCR on a PDF in GCS using the Vision API.
    gcs_uri: Input GCS path of the PDF (e.g. 'gs://bucket/folder/file.pdf').
    gcs_destination_uri: GCS folder prefix where JSON results will be written
                         (e.g. 'gs://bucket/vision_ocr_output/job123/').
    """
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
    storage_cli = get_storage_client()

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


def get_gcs_files_context(directory_path, bucket_name,query=""):
    """Fetches, downloads, processes, and limits content from GCS."""

    if storage_client is None:
        print("⚠️ Storage client is not initialized.")
        return []

    # Normalize directory_path (allow root if empty)
    directory_path = (directory_path or "").strip("/")

    print(f"🔍 Fetching files from gs://{bucket_name}/{directory_path}/")

    SUPPORTED_EXTENSIONS = ('.docx', '.pdf', '.txt')
    prefix = f"{directory_path}/" if directory_path else ""
    file_data = []

    try:
        bucket = storage_client.bucket(bucket_name)

        blobs = bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            blob_name_lower = blob.name.lower()

            # Skip the "folder" itself, empty files, and unsupported extensions
            if (
                blob.name == prefix
                or blob.size == 0
                or not blob_name_lower.endswith(SUPPORTED_EXTENSIONS)
            ):
                continue

            try:
                full_gcs_path = blob.name

                # Download bytes for DOCX/PDF/TXT and let extract_content handle details
                file_content_bytes = blob.download_as_bytes()
                content_string = extract_content(file_content_bytes, blob.name, full_gcs_path)
                # Check for errors before processing
                if isinstance(content_string, str) and content_string.startswith("ERROR:"):
                    print(f"⚠️ Skipping file {blob.name} due to extraction error.")
                    continue

                if not content_string:
                    # nothing extracted – skip file
                    continue

                # Truncate content if too long (this is the SAME logic as before)
                if len(content_string) > MAX_CHARS_PER_DOC:
                    print(f"⚠️ Truncating file {blob.name} to {MAX_CHARS_PER_DOC} chars.")
                    content_string = content_string[:MAX_CHARS_PER_DOC]

                # 1. Relative name (nice for UI and Gemini “File: …”)
                if prefix and blob.name.startswith(prefix):
                    relative_name = blob.name[len(prefix):]  # e.g. "file.pdf" or "sub/file.pdf"
                else:
                    relative_name = blob.name

                # 2. Pages structure for page+line info (NEW), but safe:
                #    if extractors fail, just fall back to a single-page view of content.
                pages = []

                try:
                    if blob_name_lower.endswith('.pdf'):
                        # Expected: [{"page": 1, "lines": [...]}, ...]
                        pages = find_all_word_positions_in_pdf(file_content_bytes, query)
                    elif blob_name_lower.endswith('.docx'):
                        # Expected: [{"page": 1, "lines": [...]}, ...]
                        pages = extract_docx_with_lines(file_content_bytes)

                    else:
                        # TXT: split content into lines as one page
                        text = file_content_bytes.decode("utf-8", errors="ignore")
                        pages = [
                            {"page": 1, "lines": text.split("\n")}
                        ]

                except Exception as pe:
                    print(f"⚠️ Page extraction failed for {blob.name}: {pe}")
                    # Fallback: just one page with `content_string` split into lines
                    pages = [
                        {"page": 1, "lines": content_string.split("\n")}
                    ]

                    # Normalize pages: make sure it's always a list of {"page": int, "lines": list[str]}
                if isinstance(pages, str):
                    # extractor returned "ERROR: ..." or some text
                    if pages.startswith("ERROR:"):
                        print(f"⚠️ Page extractor error for {blob.name}: {pages}")
                        pages = [
                            {"page": 1, "lines": content_string.split("\n")}
                        ]
                    else:
                        pages = [
                            {"page": 1, "lines": pages.split("\n")}
                        ]
                elif not pages:
                    # empty or None -> fallback to content_string
                    pages = [
                        {"page": 1, "lines": content_string.split("\n")}
                    ]
                elif isinstance(pages, list) and pages and isinstance(pages[0], str):
                    # list of strings -> treat as lines of page 1
                    pages = [
                        {"page": 1, "lines": pages}
                    ]
                # Final append – this is what simple_keyword_search expects
                file_data.append({
                    "name": relative_name,     # was effectively blob.name before
                    "full_path": blob.name,
                    "content": content_string,  # SAME field your search uses
                    "pages1": pages              # NEW, but extra only
                })

            except Exception as e:
                print(f"Error processing {blob.name}: {e}")
                continue


        print(f"✅ Found {len(file_data)} usable documents in directory '{directory_path}'.")
        return file_data

    except Exception as e:
        print(f"Error listing/downloading files from GCS: {e}")
        return []


def initialize_document_cache(directory_path: str):
    """
    Builds the document cache by listing, downloading, and extracting content
    from GCS. This runs ONCE in the background thread.
    """
    global DOCUMENT_CACHE, gcs_bucket, CACHE_STATUS, cache_lock

    if gcs_bucket is None:
        with cache_lock:
            CACHE_STATUS = "FAILED"
            print("CACHE-INIT: Failed to run because gcs_bucket is None.")
        return

    print(f"CACHE-INIT: Starting background cache process for prefix: {directory_path}...")
    cache_start_time = time.time()
    temp_cache = {}

    try:
        prefix = directory_path.strip("/")
        if prefix: prefix += "/"

        # This list_blobs call is a common place for the thread to crash
        blobs = gcs_bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            # We keep the file-level error handling to prevent the loop from aborting
            try:
                if blob.size == 0 or blob.name.endswith('/'): continue

                blob_bytes = blob.download_as_bytes()
                # Assuming extract_content3 is robust enough for your file types
                extracted_text = extract_content3(blob_bytes, blob.name)

                if extracted_text and not extracted_text.startswith("ERROR:"):
                    temp_cache[blob.name] = {
                        "filename": os.path.basename(blob.name),
                        "full_path": blob.name,
                        "content": extracted_text,
                    }

            except Exception as dl_e:
                # Log the error and move to the next file
                print(f"❌ ERROR processing file {blob.name}: {dl_e}")

        # --- CRITICAL SUCCESS BLOCK ---
        with cache_lock:
            DOCUMENT_CACHE = temp_cache
            # Set to READY even if empty, to ensure the state machine moves forward
            CACHE_STATUS = "READY"
            cache_time = round(time.time() - cache_start_time, 2)
            print(f"CACHE-INIT: SUCCESS. Status: READY with {len(temp_cache)} files in {cache_time}s.")

    except Exception as e:
        # --- CRITICAL FAILURE BLOCK ---
        print(f"CACHE-INIT: CATASTROPHIC ERROR (Bucket list failed): {e}")
        traceback.print_exc()
        with cache_lock:
            CACHE_STATUS = "FAILED"


def simple_keyword_search2(query: str,
                          directory_path: str = "",
                          mode="any",
                          match_type="partial",
                          show_mode="line"):
    """
    FAST simple keyword search using the pre-warmed DOCUMENT_CACHE.
    - directory_path is only used to filter the cache, not to hit GCS.
    """
    if not DOCUMENT_CACHE:
        return {
            "status": "error",
            "details": "Document cache is empty or failed to initialize during startup.",
            "matches": []
        }

    # 1. Filter the cache based on the requested directory_path
    # We filter by full_path starting with the prefix (e.g., 'docs-dir/' or '' for root)
    prefix = directory_path.strip("/")
    if prefix:
        prefix += "/"

    # Use the cache instead of hitting GCS
    documents = [
        doc_data for doc_path, doc_data in DOCUMENT_CACHE.items()
        if doc_path.startswith(prefix)
    ]

    if not documents:
        return {
            "status": "ok",
            "details": f"No cached documents found in directory '{directory_path}'.",
            "matches": []
        }

    # Split query into separate words
    words = [w.strip() for w in query.split() if w.strip()]
    if not words:
        return {"status": "ok", "details": "Empty query", "matches": []}

    results = []
    debug_str =""
    # 2. Perform search on cached content (rest of the logic is fast)
    for doc in documents:
        debug_str = doc['full_path']
        matched_items = []
        matched_items_html = []

        # --- Search runs directly on the cached 'content' string ---
        content = doc.get("content", "")

        if show_mode == "line":
            lines = content.split("\n")

            for line in lines:
                if match_line(line, words, mode=mode, match_type=match_type):
                    matched_items.append(line)
                    matched_items_html.append(
                        highlight_matches_html(line, words, match_type=match_type)
                    )

        else:  # paragraph mode
            paragraphs = split_into_paragraphs(content)
            for paragraph in paragraphs:
                if match_line(paragraph, words, mode=mode, match_type=match_type):
                    matched_items.append(paragraph)
                    matched_items_html.append(
                        highlight_matches_html(paragraph, words, match_type=match_type)
                    )

        # NOTE: match_positions (page/line) logic is complex without pages data in the cache.
        # For simple search, we will skip or simplify it here, focusing on speed.

        if matched_items:
            results.append({
                "file": os.path.basename(doc["full_path"]),  # Use base name for file display
                "full_path": doc["full_path"],
                "matches": matched_items,
                "matches_html": matched_items_html,
                "match_positions": []  # Simplified for speed/caching
            })
            debug_str += "match"
        else:
            debug_str += "no match"
    return {
        "debug": debug_str,
        "status": "ok",
        "query": query,
        "directory_path": directory_path,
        "mode": mode,
        "match_type": match_type,
        "show_mode": show_mode,
        "matches": results
    }

def simple_keyword_search(query: str,
                          directory_path: str = "",
                          mode="any",
                          match_type="partial",
                          show_mode="line"):
    """
    Simple non-AI keyword search:
    - mode: 'any' or 'all'
    - match_type: 'partial' or 'full'
    - show_mode: 'line' or 'paragraph'
    """

    documents = get_gcs_files_context(directory_path, BUCKET_NAME, query)


    if not documents:
        return {
            "status": "ok",
            "details": f"No usable documents found in '{directory_path}'.",
            "matches": []
        }

    # Split query into separate words
    words = [w.strip() for w in query.split() if w.strip()]
    if not words:
        return {"status": "ok", "details": "Empty query", "matches": []}

    results = []

    for doc in documents:
        matched_items = []          # text (line or paragraph)
        matched_items_html = []     # highlighted HTML
        match_positions = []        # {"page": p, "line": line_idx}

        # --- Normalize pages defensively (so we don't crash) ---
        raw_pages = doc.get("pages")

        pages = []

        if isinstance(raw_pages, list):
            if raw_pages and isinstance(raw_pages[0], dict) and "lines" in raw_pages[0]:
                pages = raw_pages
            elif raw_pages and isinstance(raw_pages[0], str):
                pages = [{"page": 1, "lines": raw_pages}]
        elif isinstance(raw_pages, str):
            pages = [{"page": 1, "lines": raw_pages.split("\n")}]

        if not pages:
            content = doc.get("content", "")
            pages = [{"page": 1, "lines": content.split("\n")}]

        # =========================
        #   LINE MODE (unchanged)
        # =========================
        if show_mode == "line":

            for page_entry in pages:
                page_num = page_entry.get("page", 1)
                lines = page_entry.get("lines", []) or []

                for line_idx, line in enumerate(lines, start=1):
                    if match_line(line, words, mode=mode, match_type=match_type):
                        matched_items.append(line)
                        matched_items_html.append(
                            highlight_matches_html(line, words, match_type=match_type)
                        )
                        match_positions.append({
                            "page": page_num,
                            "line": line_idx
                        })
        # =========================
        #   PARAGRAPH MODE
        # =========================
        else:
            # Restore ORIGINAL behavior: use your split_into_paragraphs on doc["content"]
            content = doc.get("content", "")
            paragraphs = split_into_paragraphs(content)

            for paragraph in paragraphs:
                if match_line(paragraph, words, mode=mode, match_type=match_type):
                    matched_items.append(paragraph)
                    matched_items_html.append(
                        highlight_matches_html(paragraph, words, match_type=match_type)
                    )

                    # NEW: find (page, line) for this paragraph using pages
                    page_num, line_idx = find_paragraph_position_in_pages(paragraph, pages)
                    match_positions.append({
                        "page": page_num,
                        "line": line_idx
                    })

        if matched_items:
            results.append({
                "file": doc["name"],
                "full_path": doc["full_path"],
                "matches": matched_items,
                "matches_html": matched_items_html,
                "match_positions": match_positions
            })

    return {
        "debug": "",
        "status": "ok",
        "query": query,
        "directory_path": directory_path,
        "mode": mode,
        "match_type": match_type,
        "show_mode": show_mode,
        "matches": results
    }


def perform_search(query: str, directory_path: str = ""):
    """Performs the RAG search using the globally initialized clients with multi-model fallback."""
    if not gemini_client:
        return {"status": "Fallback", "details": "Gemini client not initialized. Check API Key."}

    # 1. Retrieve and process documents
    documents = get_gcs_files_context(directory_path, BUCKET_NAME,"")

    if not documents:
        # If no documents were processed successfully (could be due to OCR failure on all files)
        return {"status": "Fallback",
                "details": f"No usable documents found in '{directory_path}'. All files may have failed content extraction."}

    # 2. Prepare Prompt for Gemini
    document_context = "\n\n--- DOCUMENTS CONTEXT ---\n\n"
    for doc in documents:
        document_context += f"File: {doc['name']}\nFull Path: {doc['full_path']}\nContent:\n{doc['content']}\n---\n"

    system_instruction = (
        "You are a helpful assistant. Provide the answer in Hebrew (עברית). "
        "Use ONLY the provided document text as context "
        "to answer the question. If the information is not in the text, reply #$$$#"
    )

    final_prompt = (
        f"DOCUMENT CONTEXT:\n---\n{document_context}\n---\n\n"
        f"QUESTION: {query}"
    )

    # 3. Call Gemini API with Fallback Logic
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=final_prompt,
            config={"system_instruction": system_instruction}
        )
        print("✅ Response received from gemini-2.5-flash.")

    except errors.APIError as e:
        if '503 UNAVAILABLE' not in str(e) and '500' not in str(e):
            print(f"Non-503/500 Gemini API Error: {e}")
            traceback.print_exc()
            return {
                "status": "API Error",
                "details": f"Check your request or API configuration. Error: {e}"
            }

        # Attempt 2: gemini-2.5-pro (Fallback)
        print("⚠️ gemini-2.5-flash overloaded. Falling back to gemini-2.5-pro...")
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=final_prompt,
                config={"system_instruction": system_instruction}
            )
            print("✅ Response received from gemini-2.5-pro (Fallback Success).")
        except Exception as fallback_e:
            print(f"❌ Fallback to gemini-2.5-pro failed: {fallback_e}")
            traceback.print_exc()
            return {
                "status": "API Error",
                "details": f"Both models are unavailable. Error: {fallback_e}"
            }

    except Exception as e:
        print(f"Unhandled non-API error: {e}")
        return {
            "status": "API Error",
            "details": f"An unknown error occurred: {e}"
        }

    # Success: Return the result
    response_text = response.text.replace("#$$$#", "המידע אינו נמצא במסמכים שסופקו.")
    return {
        "query": query,
        "status": "Success (RAG)",
        "response": response_text,
        "sources": [doc['name'] for doc in documents]
    }


def start_cache_thread(directory_path: str):
    """
    Starts the background thread responsible for populating the cache ONLY IF
    it is not already running or finished successfully.
    """
    global cache_thread, CACHE_STATUS

    with cache_lock:
        print(f"START-CACHE: Lock acquired. Current Status: {CACHE_STATUS}. Thread Alive: {cache_thread and cache_thread.is_alive()}")

        # Check if the existing thread is dead (stale)
        is_thread_stale = cache_thread and not cache_thread.is_alive()

        # Condition to start the thread:
        # 1. Status is an initial/failure state (PENDING, FAILED, EMPTY_SUCCESS)
        # 2. OR the thread is stale AND the status is stuck on WARMING_UP (retry needed)
        if CACHE_STATUS in ["PENDING", "FAILED", "EMPTY_SUCCESS"] or (is_thread_stale and CACHE_STATUS == "WARMING_UP"):

            if is_thread_stale and CACHE_STATUS != "READY":
                print("START-CACHE: Previous thread finished with non-READY status or stalled. Retrying initialization.")

            CACHE_STATUS = "WARMING_UP"
            print(f"START-CACHE: Setting Status to WARMING_UP and launching thread...")

            # Directory path is currently ignored in initialize_document_cache as per your setup, but kept for future proofing.
            cache_thread = threading.Thread(
                target=initialize_document_cache,
                args=(directory_path,),
                daemon=True
            )
            cache_thread.start()
            print("START-CACHE: Thread launched successfully.")
            return True
        else:
            print(f"START-CACHE: Cache thread already running or ready (Status: {CACHE_STATUS}). Skipping launch.")
            return False
# --- Flask Application Setup ---

app = Flask(__name__)

initialize_all_clients()
timer0 = time.time()




@app.route('/simple_search', methods=['POST'])


def simple_search_endpoint():
    # 1. Ensure the cache thread is started non-blocking (if needed)
    start_cache_thread("")

    timer1 = time.time()
    time_stamp = ""

    # --- Setup and Validation ---
    data = request.get_json(silent=True) or {}
    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()
    config = data.get("search_config", {})

    mode = config.get("word_logic", "any")
    match_type = config.get("match_type", "partial")
    show_mode = config.get("show_mode", "paragraph")

    if not query or not directory_path:
        return jsonify({"error": "Missing 'query' or 'directory_path' in request."}), 400

    global CACHE_STATUS

    # 2. Acquire status safely to decide the path
    with cache_lock:
        current_status = CACHE_STATUS
        cache_is_ready = current_status in ["READY", "EMPTY_SUCCESS"]

    # 3. Decision Tree: Fallback (Slow) or Cache (Fast)?

    if not cache_is_ready:

        # --- SLOW FALLBACK PATH (Synchronous GCS Call) ---
        print(f"LOG: Cache Status: '{current_status}'. Executing slow GCS search.")
        try:
            result = simple_keyword_search(
                query,
                directory_path,
                mode=mode,
                match_type=match_type,
                show_mode=show_mode
            )

            time_stamp += f"{round(100 * (time.time() - timer0)) / 100} sec "
            time_stamp += f" new simple_keyword_search={round(100 * (time.time() - timer1)) / 100},"
            time_stamp += CACHE_STATUS
            result["debug"] += time_stamp
            return jsonify(result), 200

        except Exception as e:
            print(f"ERROR in simple_keyword_search fallback: {e}")
            traceback.print_exc()
            return jsonify({"error": f"Fallback search failed: {str(e)}"}), 500

    else:
        # --- FAST CACHED PATH (In-memory Call) ---
        print(f"LOG: Cache Status: '{current_status}'. Executing fast cached search.")
        try:
            result = simple_keyword_search2(
                query,
                directory_path,
                mode=mode,
                match_type=match_type,
                show_mode=show_mode
            )

            time_stamp += f"{round(100 * (time.time() - timer0)) / 100} sec "
            time_stamp += f" new simple_keyword_search={round(100 * (time.time() - timer1)) / 100},"
            time_stamp += CACHE_STATUS
            result["debug"] += time_stamp

            return jsonify(result), 200

        except Exception as e:
            print(f"ERROR in simple_search_endpoint (cached search): {e}")
            traceback.print_exc()
            return jsonify({"error": f"Cached search failed: {str(e)}"}), 500



@app.route('/search', methods=['POST'])
def search_endpoint():
    if not initialize_all_clients():
        print("LOG: Request failed - Service initialization failed. Check server logs for IAM/API Key errors.")
        return jsonify({"error": "Service initialization failed. Check server logs for IAM/API Key errors."}), 500

    data = request.get_json(silent=True)

    if data is None:
        print("LOG: Request failed - Invalid JSON or missing Content-Type header.")
        return jsonify({"error": "Invalid JSON or missing 'Content-Type: application/json' header."}), 400

    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()

    if not query:
        print(f"LOG: Request failed - Query missing. Received data: {data}")
        return jsonify({"error": "No search query ('query') provided."}), 400

    try:
        results = perform_search(query, directory_path)
        print(f"LOG: Successful search for query: '{query}' in path: '{directory_path}'")

        if results.get("status") in ["API Error", "Fallback"]:
            return jsonify(results), 500

        return jsonify(results), 200

    except Exception as e:
        print(f"--- ERROR IN search_endpoint ---")
        print(traceback.format_exc())
        print(f"-------------------------------")
        return jsonify({"error": "Internal server error during search process. Check server logs for details."}), 500