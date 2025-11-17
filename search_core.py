import os
import re
import json
import io
import traceback  # Ensure this is imported for logging stack traces
from google.cloud import storage
from google.cloud import vision_v1 as vision
from google import genai
from google.genai import errors
from flask import Flask, request, jsonify
from pdfminer.high_level import extract_text_to_fp
from docx import Document
import time  # New import required for polling the async job

# ... existing configurations ...

# NEW: Required for Vision API Asynchronous PDF OCR output
GCS_OCR_OUTPUT_PATH = "gs://oren-smart-search-docs-1205/vision_ocr_output/"

# --- Configuration & Initialization ---
# NOTE: Using a fixed BUCKET_NAME is fine, but typically pulled from environment variables.
BUCKET_NAME = "oren-smart-search-docs-1205"
MAX_CHARS_PER_DOC = 100000


# --- Client Getters ---

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
    """Initializes all global clients (Storage, Gemini, Vision) if they are None."""
    global storage_client, gemini_client, vision_client

    if storage_client is None:
        storage_client = get_storage_client()

    if vision_client is None:
        vision_client = get_vision_client()

    if gemini_client is None:
        gemini_client = get_gemini_client()

    # Return True only if all were successfully initialized
    return storage_client is not None and gemini_client is not None and vision_client is not None


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

def get_gcs_files_context(directory_path, bucket_name):
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
            if blob.name == prefix or blob.size == 0 or not blob_name_lower.endswith(SUPPORTED_EXTENSIONS):
                continue

            try:
                full_gcs_path = blob.name

                # Download bytes for DOCX/PDF/TXT and let extract_content handle details (including OCR for PDFs)
                file_content_bytes = blob.download_as_bytes()
                content_string = extract_content(file_content_bytes, blob.name, full_gcs_path)

                # Check for errors before processing
                if content_string and content_string.startswith("ERROR:"):
                    print(f"⚠️ Skipping file {blob.name} due to extraction error.")
                    continue

                # Truncate content if too long
                if content_string and len(content_string) > MAX_CHARS_PER_DOC:
                    print(f"⚠️ Truncating file {blob.name} to {MAX_CHARS_PER_DOC} chars.")
                    content_string = content_string[:MAX_CHARS_PER_DOC]

                if not content_string:
                    continue

                    # 1. Relative name (nice for UI and Gemini “File: …”)
                if prefix and blob.name.startswith(prefix):
                    relative_name = blob.name[len(prefix):]  # e.g. "file.pdf" or "sub/file.pdf"
                else:
                    relative_name = blob.name

                    # 2. Append document record
                file_data.append({
                    "name": relative_name,  # short/relative name
                    "full_path": blob.name,  # full path in bucket
                    "content": content_string
                })


            except Exception as e:
                print(f"Error processing {blob.name}: {e}")
                continue

        print(f"✅ Found {len(file_data)} usable documents in directory '{directory_path}'.")


        return file_data

    except Exception as e:
        print(f"Error listing/downloading files from GCS: {e}")
        return []



def match_line(line: str, words: list[str], mode="any", match_type="partial"):
    """
    line        = the text line from the document
    words       = user search words (already split)
    mode        = "any" or "all"
    match_type  = "partial" or "full"

    Returns True if the line matches the search rule.
    """

    line_lower = line.lower()

    # full match = whole word
    if match_type == "full":
        def check_word(word):
            return re.search(rf"\b{re.escape(word.lower())}\b", line_lower)

    # partial match = substring
    else:
        def check_word(word):
            return word.lower() in line_lower

    if mode == "all":
        return all(check_word(w) for w in words)

    return any(check_word(w) for w in words)


def simple_keyword_search(query: str, directory_path: str = "",
                          mode="any", match_type="partial"):
    """
    Simple non-AI keyword search:
    - mode: 'any' or 'all'
    - match_type: 'partial' or 'full'
    """

    documents = get_gcs_files_context(directory_path, BUCKET_NAME)

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
        matched_lines = []

        for line in doc["content"].split("\n"):
            if match_line(line, words, mode=mode, match_type=match_type):
                matched_lines.append(line)

        if matched_lines:
            results.append({
                "file": doc["name"],
                "full_path": doc["full_path"],
                "matches": matched_lines
            })

    return {
        "status": "ok",
        "query": query,
        "directory_path": directory_path,
        "mode": mode,
        "match_type": match_type,
        "matches": results
    }

def perform_search(query: str, directory_path: str = ""):
    """Performs the RAG search using the globally initialized clients with multi-model fallback."""
    if not gemini_client:
        return {"status": "Fallback", "details": "Gemini client not initialized. Check API Key."}

    # 1. Retrieve and process documents
    documents = get_gcs_files_context(directory_path, BUCKET_NAME)

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
    # Make sure storage (and friends) are initialized
    if not initialize_all_clients():
        return jsonify({"error": "Service initialization failed. Check BUCKET / GEMINI / VISION settings."}), 500


    data = request.get_json(silent=True) or {}

    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()
    config = data.get("search_config", {})

    # Mapping user config → internal parameters
    mode = config.get("word_logic", "any")       # "any" / "all"
    match_type = config.get("match_type", "partial")  # "partial" / "full"

    if not query or not directory_path:
        return jsonify({"error": "Missing 'query' or 'directory_path' in request."}), 400

    try:
        result = simple_keyword_search(
            query,
            directory_path,
            mode=mode,
            match_type=match_type
        )
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