import os
import re
import json
import io
import traceback
from flask import Flask, request, jsonify
from google.cloud import storage
from google import genai
from pypdf import PdfReader
import docx

# --- Configuration ---
BUCKET_NAME = "oren-smart-search-docs-1205"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MAX_CHARS_PER_DOC = 10000

# --- Initializations (Eager, Global Initialization Fix) ---
app = Flask(__name__)
storage_client = None
gemini_client = None

try:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    # Initialize clients ONCE at application startup
    storage_client = storage.Client()
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini and Storage clients initialized successfully on startup.")

except Exception as e:
    # If this fails, the server will not start, preventing the 503 loop.
    print(f"FATAL ERROR during client initialization: {e}")
    traceback.print_exc()
    raise


# --- Utility Functions ---

def extract_content(blob_bytes, blob_name):
    """Extracts text content from bytes, handling only PDF for now."""

    if blob_name.lower().endswith('.pdf'):
        text = ""
        try:
            # 1. Use BytesIO to process the file in memory
            file_stream = io.BytesIO(blob_bytes)
            reader = PdfReader(file_stream)

            # 2. Extract text from all pages
            for page in reader.pages:
                text += page.extract_text() or ""

            # Basic cleanup
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        except Exception as e:
            print(f"Error reading PDF {blob_name} with pypdf: {e}")
            return "ERROR: Could not read PDF content."


    elif blob_name.lower().endswith('.docx'):
        text = ""
        try:
            document = docx.Document(io.BytesIO(blob_bytes))
            for paragraph in document.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            print(f"Error reading DOCX {blob_name}: {e}")
            return "ERROR: Could not read DOCX content."

    # Handle other files as plain text
    try:
        return blob_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error decoding text file {blob_name}: {e}")
        return "ERROR: Could not decode text content."


def get_gcs_files_context(directory_path, bucket_name):
    """
    Fetches, downloads, processes, and limits content from GCS.

    This function consolidates the processing to avoid running the same logic twice.
    It uses the global storage_client.
    """
    print(f"🔍 Fetching files from gs://{bucket_name}/{directory_path}/")

    bucket = storage_client.bucket(bucket_name)
    prefix = f"{directory_path}/"
    blobs = bucket.list_blobs(prefix=prefix)

    file_data = []

    # Process files sequentially for simplicity and reduced resource contention,
    # or use ThreadPoolExecutor if document count is very high.
    for blob in blobs:
        # Filter: Skip the folder itself and empty files
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
                    "name": blob.name.replace(prefix, ""),  # Keep just the filename
                    "content": content_string
                })
        except Exception as e:
            print(f"Error downloading/processing {blob.name}: {e}")
            continue

    print(f"✅ Found {len(file_data)} usable documents in directory '{directory_path}'.")
    return file_data


def perform_search(query: str, directory_path: str = ""):
    """
    Performs the RAG search using the globally initialized clients.
    """

    # 1. Retrieve and process documents (consolidated logic)
    documents = get_gcs_files_context(directory_path, BUCKET_NAME)

    if not documents:
        return {"status": "Fallback", "details": f"No usable documents found in '{directory_path}'."}

    # 2. Prepare Prompt for Gemini
    document_context = "\n\n--- DOCUMENTS CONTEXT ---\n\n"
    for doc in documents:
        # Use the filename as a clear boundary for the model
        document_context += f"File: {doc['name']}\nContent:\n{doc['content']}\n---\n"

    #system_instruction2 = (
    #    "אתה אנליסט מסמכים מקצועי. התשובה שלך צריכה להיות עברית רהוטה וברורה. "
    #    "השתמש אך ורק במידע שסופק בתוך 'DOCUMENTS CONTEXT' כדי לענות על שאלת המשתמש. "
    #    "אם המידע אינו קיים ב-CONTEXT, ענה: 'המידע לגבי [שאלה ספציפית] אינו נמצא במסמכים שסופקו'."
    #)

    system_instruction = (
        "YYou are a helpful assistant. Use ONLY the provided document text as document_context "
        "to answer the question. If the information is not in the text, reply #$$$# "
        # "the answer cannot be found in the provided document."
    )

    user_prompt = (
        f"{document_context}\n\n"
        f"\n\n---"
        f"\n\nשאלה אנליטית: {query}"
    )
    final_prompt = (
        f"DOCUMENT CONTEXT:\n---\n{document_context}\n---\n\n"
        f"QUESTION: {query}"
    )

    try:
        # 3. Call Gemini API (using the global client)
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=final_prompt,
            config={"system_instruction": system_instruction}
        )

        # Success: Return the full analytical response
        return {
            "query": query,
            "status": "Success (RAG)",
            "response": response.text,
            "sources": [doc['name'] for doc in documents]  # Optionally return the source filenames
        }

    except Exception as e:
        # Handle API errors (e.g., key expired, invalid request, token overflow)
        print(f"Gemini API Error or runtime error: {e}")
        traceback.print_exc()
        return {
            "status": "API Error",
            "details": f"Check your request size or API configuration. Details: {e}"
        }


# --- Flask Routes ---

@app.route("/search", methods=["POST"])
def search():
    """Endpoint for performing the RAG search."""
    try:
        data = request.get_json()
        query = data.get("query", "")
        directory_path = data.get("directory_path", "")

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