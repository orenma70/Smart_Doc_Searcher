import os
import re
import json
import io
import traceback
from google.cloud import storage
from google import genai
from google.genai import errors

# Flask imports
from flask import Flask, request, jsonify

# Document Processing Libraries
from pdfminer.high_level import extract_text_to_fp
from docx import Document

# --- Configuration & Initialization ---
BUCKET_NAME = "oren-smart-search-docs-1205"
MAX_CHARS_PER_DOC = 10000

def get_storage_client():
    """Initializes and returns the Google Cloud Storage client."""
    try:
        return storage.Client()
    except Exception as e:
        print(f"FATAL: Could not initialize GCS client. Error: {e}")
        return None

#def get_vision_client():
 #   """Initializes and returns the Google Cloud Vision client (unused but kept for completeness)."""
 #   try:
 #       return vision.ImageAnnotatorClient()
 #   except Exception as e:
 #       print(f"FATAL: Could not initialize Vision client. Error: {e}")
 #       return None

def get_gemini_client():
    """Initializes and returns the Gemini client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("FATAL: GEMINI_API_KEY environment variable not set.")
        # If the key is missing, genai.Client() will fail later, but we let it try
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"FATAL: Could not initialize Gemini client. Check API Key. Error: {e}")
        return None

# Global clients (Initialized once at startup)
storage_client = get_storage_client()
#vision_client = get_vision_client() # Kept for consistency, but unused in RAG logic
gemini_client = get_gemini_client()


# --- Utility Functions (RAG Logic) ---

def extract_content(blob_bytes, blob_name):
    """Extracts text content from bytes, handling PDF, DOCX, and others."""
    blob_name_lower = blob_name.lower()

    if blob_name_lower.endswith('.pdf'):
        try:
            file_stream = io.BytesIO(blob_bytes)
            output_string = io.StringIO()
            extract_text_to_fp(file_stream, output_string)
            text = output_string.getvalue()
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        except Exception as e:
            return f"ERROR: Could not read PDF content: {e}"

    elif blob_name_lower.endswith('.docx'):
        text = ""
        try:
            document = Document(io.BytesIO(blob_bytes))
            for paragraph in document.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            return f"ERROR: Could not read DOCX content: {e}"

    # Handle other files as plain text
    try:
        return blob_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        return "ERROR: Could not decode text content."


def get_gcs_files_context(directory_path, bucket_name):
    """Fetches, downloads, processes, and limits content from GCS."""
    if storage_client is None:
        return []

    print(f"🔍 Fetching files from gs://{bucket_name}/{directory_path}/")

    try:
        bucket = storage_client.bucket(bucket_name)
        prefix = f"{directory_path}/"
        blobs = bucket.list_blobs(prefix=prefix)
        file_data = []

        for blob in blobs:
            if blob.name == prefix or blob.size == 0 or not blob.name.lower().endswith(('.docx', '.pdf', '.txt')):
                continue

            file_content_bytes = blob.download_as_bytes()
            content_string = extract_content(file_content_bytes, blob.name)

            if len(content_string) > MAX_CHARS_PER_DOC:
                print(f"⚠️ Truncating file {blob.name} to {MAX_CHARS_PER_DOC} chars.")
                content_string = content_string[:MAX_CHARS_PER_DOC]

            if content_string and not content_string.startswith("ERROR:"):
                file_data.append({
                    "name": blob.name.replace(prefix, ""),
                    "full_path": blob.name,
                    "content": content_string
                })

        print(f"✅ Found {len(file_data)} usable documents in directory '{directory_path}'.")
        return file_data

    except Exception as e:
        print(f"Error listing/downloading files from GCS: {e}")
        return []


def perform_search(query: str, directory_path: str = ""):
    """Performs the RAG search using the globally initialized clients with multi-model fallback."""
    if not gemini_client:
        return {"status": "Fallback", "details": "Gemini client not initialized. Check API Key."}

    # 1. Retrieve and process documents
    documents = get_gcs_files_context(directory_path, BUCKET_NAME)

    if not documents:
        return {"status": "Fallback", "details": f"No usable documents found in '{directory_path}'."}

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
        # Attempt 1: gemini-2.5-flash
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
    return {
        "query": query,
        "status": "Success (RAG)",
        "response": response.text,
        "sources": [doc['name'] for doc in documents]
    }


# --- Flask Application Setup ---

app = Flask(__name__)

@app.route('/search', methods=['POST'])
def search_endpoint():
    # 1. Get JSON data
    data = request.get_json(silent=True)

    if data is None:
        print("LOG: Request failed - Invalid JSON or missing Content-Type header.")
        return jsonify({"error": "Invalid JSON or missing 'Content-Type: application/json' header."}), 400

    # 2. Get parameters
    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()

    # 3. Check for missing query
    if not query:
        print(f"LOG: Request failed - Query missing. Received data: {data}")
        return jsonify({"error": "No search query ('query') provided."}), 400

    # 4. Perform the search (perform_search is now local)
    try:
        results = perform_search(query, directory_path)
        print(f"LOG: Successful search for query: '{query}' in path: '{directory_path}'")
        return jsonify(results), 200

    except Exception as e:
        print(f"--- ERROR IN search_endpoint ---")
        print(traceback.format_exc())
        print(f"-------------------------------")
        return jsonify({"error": "Internal server error during search process. Check server logs for details."}), 500