import os
import re
import json
import io
import traceback
from flask import Flask, request, jsonify
from google.cloud import storage, vision
from google import genai
from google.genai import errors
# Document Processing Libraries
from pdfminer.high_level import extract_text_to_fp  # For the 99% of searchable PDFs
from docx import Document  # For DOCX files (using the class)

# Removed unused imports: pypdf, docx (as module)

# --- Configuration ---
# NOTE: BUCKET_NAME and GEMINI_API_KEY should be set as ENV variables in Cloud Run
BUCKET_NAME = os.environ.get("BUCKET_NAME", "default-bucket-name")  # Fallback for local testing
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")  # Fetched from ENV by the get_gemini_client function
MAX_CHARS_PER_DOC = 10000


# --- Initializations (Eager, Global Initialization Fix) ---

def get_storage_client():
    """Initializes and returns the Google Cloud Storage client, returns None on failure."""
    try:
        return storage.Client()
    except Exception as e:
        print(f"FATAL: Could not initialize Google Cloud Storage client. Check IAM/Permissions. Error: {e}")
        return None


def get_vision_client():
    """Initializes and returns the Google Cloud Vision client, returns None on failure."""
    try:
        # Note: Requires the 'google-cloud-vision' library and IAM permission 'Cloud Vision API Service Agent'
        return vision.ImageAnnotatorClient()
    except Exception as e:
        print(f"FATAL: Could not initialize Google Cloud Vision client. Check IAM/Permissions. Error: {e}")
        return None


def get_gemini_client():
    """Initializes and returns the Gemini client, returns None on failure."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("FATAL: GEMINI_API_KEY environment variable not set.")
        return None
    try:
        # Initialize using the API key provided in the environment variable
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"FATAL: Could not initialize Gemini client. Check API Key. Error: {e}")
        return None


# Global clients (initialized once, will be None if initialization failed but the app WILL start)
storage_client = get_storage_client()
vision_client = get_vision_client()
gemini_client = get_gemini_client()

app = Flask(__name__)


# --- Utility Functions ---

def extract_content(blob_bytes, blob_name):
    """Extracts text content from bytes, handling PDF, DOCX, and others."""
    blob_name_lower = blob_name.lower()

    if blob_name_lower.endswith('.pdf'):
        try:
            # Use BytesIO to process the file in memory
            file_stream = io.BytesIO(blob_bytes)

            # Use pdfminer.six for robust text extraction
            output_string = io.StringIO()
            extract_text_to_fp(file_stream, output_string)
            text = output_string.getvalue()

            # Basic cleanup
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        except Exception as e:
            print(f"Error reading PDF {blob_name} with pdfminer.six: {e}")
            # OCR Fallback is removed for simplicity, leaving only text extraction
            return "ERROR: Could not read PDF content."


    elif blob_name_lower.endswith('.docx'):
        text = ""
        try:
            # Use Document class from python-docx
            document = Document(io.BytesIO(blob_bytes))
            for paragraph in document.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            print(f"Error reading DOCX {blob_name}: {e}")
            return "ERROR: Could not read DOCX content."

    # Handle other files as plain text (e.g., .txt)
    try:
        return blob_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error decoding text file {blob_name}: {e}")
        return "ERROR: Could not decode text content."


def get_gcs_files_context(directory_path, bucket_name):
    """
    Fetches, downloads, processes, and limits content from GCS.
    Uses the global storage_client.
    """
    if storage_client is None:
        print("ERROR: Storage client not initialized.")
        return []

    print(f"🔍 Fetching files from gs://{bucket_name}/{directory_path}/")

    bucket = storage_client.bucket(bucket_name)
    prefix = f"{directory_path}/"
    blobs = bucket.list_blobs(prefix=prefix)

    file_data = []

    for blob in blobs:
        # Filter: Skip the folder itself and process only allowed file types
        if blob.name == prefix or blob.size == 0 or not blob.name.lower().endswith(('.docx', '.pdf', '.txt')):
            continue

        try:
            file_content_bytes = blob.download_as_bytes()
            content_string = extract_content(file_content_bytes, blob.name)

            # Truncate text to prevent Gemini token limit errors
            if len(content_string) > MAX_CHARS_PER_DOC:
                print(f"⚠️ Truncating file {blob.name} to {MAX_CHARS_PER_DOC} chars.")
                content_string = content_string[:MAX_CHARS_PER_DOC]

            if content_string and not content_string.startswith("ERROR:"):
                file_data.append({
                    "name": blob.name.replace(prefix, ""),  # Filename only
                    "full_path": blob.name,  # CRITICAL FIX: Add full path for reference
                    "content": content_string
                })
        except Exception as e:
            print(f"Error downloading/processing {blob.name}: {e}")
            continue

    print(f"✅ Found {len(file_data)} usable documents in directory '{directory_path}'.")
    return file_data


def perform_search(query: str, directory_path: str = ""):
    """
    Performs the RAG search using the globally initialized clients with multi-model fallback.
    """
    # בדיקת אתחול קליינט, כדי למנוע קריסה
    if not gemini_client:
        return {"status": "Fallback", "details": "Gemini client not initialized. Check API Key."}

    # 1. Retrieve and process documents (consolidated logic)
    documents = get_gcs_files_context(directory_path, BUCKET_NAME)

    if not documents:
        return {"status": "Fallback", "details": f"No usable documents found in '{directory_path}'."}

    # 2. Prepare Prompt for Gemini
    document_context = "\n\n--- DOCUMENTS CONTEXT ---\n\n"
    for doc in documents:
        # Use the full path and name for the LLM context
        document_context += f"File: {doc['name']}\nFull Path: {doc['full_path']}\nContent:\n{doc['content']}\n---\n"

    # NOTE: Reverting to the successful Hebrew-aware system instruction
    system_instruction = (
        "You are a helpful assistant. Provide the answer in Hebrew (עברית). "
        "Use ONLY the provided document text as context "
        "to answer the question. If the information is not in the text, reply #$$$#"
    )

    final_prompt = (
        f"DOCUMENT CONTEXT:\n---\n{document_context}\n---\n\n"
        f"QUESTION: {query}"
    )

    # --- 3. קריאה ל-Gemini API עם לוגיקת Fallback ---

    # --- ניסיון 1: מודל ראשי (Flash) ---
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=final_prompt,
            config={"system_instruction": system_instruction}
        )
        print("✅ Response received from gemini-2.5-flash.")

    except errors.APIError as e:  # Use specific APIError for better handling
        # בדיקה אם השגיאה היא עומס יתר זמני (503 UNAVAILABLE)
        if '503 UNAVAILABLE' not in str(e) and '500' not in str(e):
            # אם זו שגיאה אחרת (כגון מפתח שגוי), מחזירים אותה מיד
            print(f"Non-503/500 Gemini API Error: {e}")
            traceback.print_exc()
            return {
                "status": "API Error",
                "details": f"Check your request or API configuration. Error: {e}"
            }

        # --- ניסיון 2: מודל Fallback (Pro) ---
        print("⚠️ gemini-2.5-flash overloaded (503/500). Falling back to gemini-2.5-pro...")
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=final_prompt,
                config={"system_instruction": system_instruction}
            )
            print("✅ Response received from gemini-2.5-pro (Fallback Success).")
        except Exception as fallback_e:
            # אם ה-fallback נכשל, מחזירים סטטוס כשל
            print(f"❌ Fallback to gemini-2.5-pro failed as well: {fallback_e}")
            traceback.print_exc()
            return {
                "status": "API Error",
                "details": f"Both gemini-2.5-flash and gemini-2.5-pro are unavailable. Error: {fallback_e}"
            }

    except Exception as e:
        # Catch any other unexpected non-API errors (e.g., network)
        print(f"Unhandled non-API error: {e}")
        return {
            "status": "API Error",
            "details": f"An unknown error occurred during Gemini call: {e}"
        }

    # הצלחה: מחזירים את התשובה מהמודל שהצליח (Flash או Pro)
    return {
        "query": query,
        "status": "Success (RAG)",
        "response": response.text,
        "sources": [doc['name'] for doc in documents]
    }


# --- Flask Routes ---

@app.route("/search", methods=["POST"])
def search():
    """Endpoint for performing the RAG search."""
    try:
        data = request.get_json()
        query = data.get("query", "")
        directory_path = data.get("directory_path", "")

        # Initial client check for immediate 500
        if storage_client is None or gemini_client is None:
            return jsonify({"status": "Error",
                            "details": "Server failed critical client initialization. Check BUCKET_NAME and GEMINI_API_KEY environment variables."}), 500

        if not query or not directory_path:
            return jsonify({"status": "Error", "details": "Missing 'query' or 'directory_path' in request."}), 400

        result = perform_search(query, directory_path)

        # Return 500 for internal errors, 200 for successful RAG or expected fallback
        if result.get("status", "").endswith("Error"):
            return jsonify(result), 500

        return jsonify(result), 200

    except Exception as e:
        print(f"Request handling error: {e}")
        traceback.print_exc()
        return jsonify({"status": "Error", "details": f"Internal server error: {e}"}), 500


# Run the app locally (for debugging)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)