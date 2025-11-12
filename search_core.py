import os
import re
import json
import io
from flask import Flask, request, jsonify
from google.cloud import storage
from google import genai
from google.generativeai.errors import APIError
from pypdf import PdfReader  # ייבוא חדש לטובת חילוץ טקסט
from concurrent.futures import ThreadPoolExecutor

# --- Configuration ---
# The bucket name where your PDF documents are stored
BUCKET_NAME = "oren-smart-search-docs-1205"

# The Gemini API key is expected to be set as an environment variable in Cloud Run
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Initializations ---
app = Flask(__name__)
storage_client = storage.Client()
gemini_client = None

if GEMINI_API_KEY:
    try:
        # Initialize the Gemini Client using the API Key
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error initializing Gemini client: {e}")
else:
    print("Warning: GEMINI_API_KEY environment variable not set.")


# --- Utility Functions ---

def process_pdf_content(file_bytes):
    """
    Reads raw PDF file bytes (in memory) using pypdf,
    a more robust parser for complex text structures than fitz for certain PDFs.
    """
    text = ""
    try:
        # 1. יצירת אובייקט BytesIO כדי לדמות קובץ בזיכרון
        file_stream = io.BytesIO(file_bytes)

        # 2. פתיחת ה-PDF באמצעות pypdf
        reader = PdfReader(file_stream)

        # 3. חילוץ טקסט מכל עמוד
        for page in reader.pages:
            # שימוש בשיטת extract_text של pypdf
            extracted_text = page.extract_text()
            if extracted_text:
                text += extracted_text + "\n"

        # ניקוי בסיסי: הסרת רווחים כפולים וקפיצות שורה מיותרות
        text = re.sub(r'\s+', ' ', text).strip()

    except Exception as e:
        # Print the error for debugging, but continue
        print(f"Error processing PDF content with pypdf: {e}")
        return ""  # Return empty string on failure

    return text


def download_and_process_file(blob):
    """
    Downloads a single file's content and processes it.
    Returns: a tuple of (filename, text_content).
    """
    try:
        file_bytes = blob.download_as_bytes()
        text_content = process_pdf_content(file_bytes)
        return text_content
    except Exception as e:
        print(f"Error processing file {blob.name}: {e}")
        return ""


def perform_search(query: str, directory_path: str = ""):
    """
    Performs an aggressive RAG search: reads all PDF content in the directory,
    combines it, and sends the unified context to Gemini for analysis.
    """
    if not gemini_client:
        return {"status": "Error", "details": "Gemini client not initialized (API Key issue)."}

    bucket = storage_client.bucket(BUCKET_NAME)

    # List all relevant files in the specified directory_path
    blobs = list(bucket.list_blobs(prefix=directory_path + "/"))
    pdf_blobs = [b for b in blobs if b.name.lower().endswith('.pdf')]

    if not pdf_blobs:
        return {"status": "Error", "details": f"No PDF files found in GCS folder: {directory_path}"}

    # --- AGGRESSIVE RAG: Read ALL documents concurrently ---

    # Use ThreadPoolExecutor to speed up downloading and processing all PDFs
    all_context_text = ""
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Map the download_and_process_file function to all PDF blobs
        future_results = executor.map(download_and_process_file, pdf_blobs)

        # Combine all extracted text into one large context string
        for text_content in future_results:
            if text_content:
                all_context_text += text_content + "\n\n---\n\n"

    if not all_context_text.strip():
        return {"status": "Error", "details": "Could not extract readable text from any PDF in the directory."}

    # --- Gemini Analysis ---

    # System Instruction: Guiding the model's persona and output
    system_instruction = (
        "אתה אנליסט מסמכים מקצועי. התשובה שלך צריכה להיות עברית רהוטה וברורה. "
        "השתמש אך ורק במידע שסופק בתוך 'CONTEXT' כדי לענות על שאלת המשתמש. "
        "אם המידע אינו קיים ב-CONTEXT, ענה: 'המידע לגבי [שאלה ספציפית] אינו נמצא במסמכים שסופקו'."
    )

    # User Prompt: The combined context and the query
    user_prompt = (
        f"CONTEXT:\n\n{all_context_text}"
        f"\n\n---"
        f"\n\nשאלה אנליטית: {query}"
    )

    try:
        # Call Gemini API
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_prompt,
            system_instruction=system_instruction
        )

        # Success: Return the full analytical response
        return {
            "query": query,
            "status": "Success (RAG)",
            "response": response.text,
            "sources": []  # No specific sources tracking in Aggressive RAG
        }

    except APIError as e:
        # Handle API errors (e.g., key expired, invalid request)
        print(f"Gemini API Error: {e}")
        return {"status": "API Error", "details": f"Check your GEMINI_API_KEY and API access. Details: {e}"}
    except Exception as e:
        # Handle other runtime errors
        print(f"An unexpected error occurred: {e}")
        return {"status": "Runtime Error", "details": f"An unexpected error occurred during search: {e}"}


# --- Flask Routes ---

@app.route("/search", methods=["POST"])
def search():
    """Endpoint for performing the RAG search."""
    try:
        data = request.get_json()
        query = data.get("query", "")
        folder = data.get("folder", "")

        if not query or not folder:
            return jsonify({"status": "Error", "details": "Missing 'query' or 'folder' in request."}), 400

        result = perform_search(query, folder)
        return jsonify(result)

    except Exception as e:
        print(f"Request handling error: {e}")
        return jsonify({"status": "Error", "details": f"Internal server error: {e}"}), 500


if __name__ == "__main__":
    # This block is for local testing only
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))