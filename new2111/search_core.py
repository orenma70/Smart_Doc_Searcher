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
from pdfminer.high_level import extract_text_to_fp
from docx import Document
from pypdf import PdfReader
from typing import List

from search_utilities import split_into_paragraphs, match_line, highlight_matches_html, get_gcs_files_context, extract_content3

# ... existing configurations ...

# NEW: Required for Vision API Asynchronous PDF OCR output

MAX_CHARS_PER_DOC = 100000

import os



from config_reader import read_setup
BUCKET_NAME=read_setup("BUCKET_NAME")
#BUCKET_NAME="oren-smart-search-docs-1205"

GCS_OCR_OUTPUT_PATH = "gs://" + BUCKET_NAME + "/vision_ocr_output/"

DOCUMENT_CACHE = {} # <-- NEW: This will store extracted text to prevent re-downloading
gcs_bucket = None     # <-- NEW: Store the GCS Bucket object once



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








def split_into_paragraphs2(text: str, paragraph_mode) -> List[str]:
    """
    Splits text into paragraphs. If the text appears as one block (i.e., few lines
    from the parser), it intelligently attempts to split by sentence endings
    (period, question mark, exclamation mark) to simulate paragraphs.

    If the text has many line breaks, it defaults to splitting based on blank lines.
    """

    # 1. Standard Split (relies on parser-provided \n or blank lines)
    lines = text.split("\n")

    # Heuristic: If we have very few actual line breaks, the parser likely failed
    # to recognize them and returned a giant text block.
    if len(lines) < 10 and len(text) > 500:

        # 2. Advanced Sentence Split (Fallback for "stuck" text)

        # Define sentence termination patterns (., ?, !) followed by space or end of string
        # This regex splits while keeping the punctuation at the end of the sentence
        sentences = re.split(r'([.?!])\s*(?=[A-Zא-ת]|$)', text.strip())

        paragraphs = []
        current_paragraph = ""
        sentence_count = 0

        for part in sentences:
            if not part.strip():
                continue

            # The regex sometimes splits into content and the punctuation mark itself.
            if part in ['.', '?', '!']:
                current_paragraph += part
                if len(current_paragraph.split()) > 5:  # Require at least 5 words for a paragraph segment
                    paragraphs.append(current_paragraph.strip())
                    current_paragraph = ""
                    sentence_count = 0
                continue

            # If the current paragraph is getting long, start a new one
            if sentence_count >= 3:
                if current_paragraph:
                    paragraphs.append(current_paragraph.strip())
                current_paragraph = part.strip()
                sentence_count = 1
            else:
                current_paragraph += (" " + part.strip())
                sentence_count += 1

        # Add the final remaining paragraph segment
        if current_paragraph:
            paragraphs.append(current_paragraph.strip())

        # If the advanced split created significantly more logical units, use it.
        if len(paragraphs) > 1:
            return paragraphs

    # 3. Default Robust Split (Groups lines separated by blank space)
    paragraphs = []
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))

    return paragraphs











def initialize_document_cache(directory_path: str):
    """
    Builds the document cache by listing, downloading, and extracting content
    from GCS. This runs ONCE in the request context.
    """
    global DOCUMENT_CACHE, gcs_bucket

    if DOCUMENT_CACHE: return

    if gcs_bucket is None:
        print("FATAL: gcs_bucket is NULL. Cannot proceed with list_blobs.")
        return

    print(f"INFO: Starting document cache initialization (Expected delay: ~20s)...")
    cache_start_time = time.time()
    temp_cache = {}

    try:
        # 1. Setup prefix
        prefix = directory_path.strip("/")
        if prefix: prefix += "/"

        # 2. List all blobs
        blobs = gcs_bucket.list_blobs(prefix=prefix)

        # NOTE: You MUST ensure your extract_content function is updated
        # to use the new global client variables (vision_client, storage_client)
        # and to return just the extracted text string.

        for blob in blobs:
            # (Your existing file filtering and processing logic goes here)
            # ...
            # 3. Inside the loop, you will call:
            try:
                blob_bytes = blob.download_as_bytes()
                extracted_text = extract_content3(blob_bytes, blob.name)  # Call your existing extractor

                if extracted_text and not extracted_text.startswith("ERROR:"):
                    # 4. Save to the cache using the full path as the key
                    temp_cache[blob.name] = {
                        "filename": os.path.basename(blob.name),
                        "full_path": blob.name,
                        "content": extracted_text,  # The actual text content
                    }
                # ... (error handling)
            except Exception as dl_e:
                print(f"❌ ERROR downloading or processing {blob.name}: {dl_e}")
                traceback.print_exc()

        DOCUMENT_CACHE = temp_cache
        cache_time = round(time.time() - cache_start_time, 2)
        print(f"SUCCESS: Cache populated with {len(DOCUMENT_CACHE)} files in {cache_time} seconds.")

    except Exception as e:
        print(f"ERROR during cache initialization (List or Download phase): {e}")
        traceback.print_exc()


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

def find_paragraph_position_in_pages(paragraph_text: str, pages):
    """
    Try to find the (page, line) where this paragraph starts,
    by matching its first non-empty line inside pages.
    """
    if not pages:
        return 1, 1

    # Take the first non-empty line from the paragraph
    first_line = None
    for raw_line in paragraph_text.split("\n"):
        s = raw_line.strip()
        if s:
            first_line = s
            break

    if not first_line:
        return 1, 1

    first_line_lower = first_line.lower()

    for page_entry in pages:
        page_num = page_entry.get("page", 1)
        lines = page_entry.get("lines", []) or []
        for line_idx, doc_line in enumerate(lines, start=1):
            if doc_line and first_line_lower in doc_line.lower():
                return page_num, line_idx

    # Fallback if not found
    return 1, 1

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


# --- Flask Application Setup ---

app = Flask(__name__)



@app.route('/simple_search', methods=['POST'])
def simple_search_endpoint():
    # --- TIMER 1: Client Initialization (Should be refactored) ---
    timer1 = time.time()
    time_stamp = " "

    # NOTE: Calling this on every request adds overhead. If this takes 14s,
    # it must be moved out of the request handler.
    if not initialize_all_clients():
        print("ERROR: Service initialization failed.")
        return jsonify({"error": "Service initialization failed. Check BUCKET / GEMINI / VISION settings."}), 500


    # --- Setup and Validation ---
    data = request.get_json(silent=True) or {}

    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()

    global DOCUMENT_CACHE
    if not DOCUMENT_CACHE:
        # This function (the slow ~20s part) only runs on the first request
        print("LOG: Cache empty, performing deferred full document cache initialization on this request.")
        initialize_document_cache("")

        # 4. Check for cache success before proceeding
    if not DOCUMENT_CACHE:
        return jsonify({"error": "Cache is empty after attempted initialization. Check GCS permissions/logs."}), 500


    config = data.get("search_config", {})

    mode = config.get("word_logic", "any")
    match_type = config.get("match_type", "partial")
    show_mode = config.get("show_mode", "paragraph")

    if not query or not directory_path:
        return jsonify({"error": "Missing 'query' or 'directory_path' in request."}), 400

    try:


        result = simple_keyword_search2(
            query,
            directory_path,
            mode=mode,
            match_type=match_type,
            show_mode=show_mode
        )

        time_stamp += f"simple_search_endpoint={round(100 * (time.time() - timer1))/100},"

        result["debug"] += time_stamp
        return jsonify(result), 200

    except Exception as e:
        print(f"ERROR in simple_search_endpoint: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

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