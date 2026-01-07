import boto3
import time
import re
import traceback
from flask import Flask, request, jsonify
from config_reader import BUCKET_NAME
import io
import fitz  # PyMuPDF - כבר נמצא ב-requirements שלך
from docx import Document  # כבר נמצא ב-requirements שלך

app = Flask(__name__)

# --- AWS Configuration ---
s3 = boto3.client('s3')

    

# --- Your Original Logic Functions ---

def match_line(text, words, mode="any", match_type="partial"):
    if not words: return False
    # Handle Full vs Partial match
    if match_type == "full":
        patterns = [rf'\b{re.escape(w)}\b' for w in words]
    else:
        patterns = [re.escape(w) for w in words]

    # Handle All vs Any logic
    if mode == "all":
        return all(re.search(p, text, re.IGNORECASE) for p in patterns)
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def highlight_matches_html(text, words, match_type="partial"):
    highlighted = text
    for w in words:
        pattern = rf'\b{re.escape(w)}\b' if match_type == "full" else re.escape(w)
        highlighted = re.sub(pattern, lambda m: f"<mark>{m.group()}</mark>", highlighted, flags=re.IGNORECASE)
    return highlighted


def split_into_paragraphs(text):
    return [p.strip() for p in text.split('\n\n') if p.strip()]


def find_paragraph_position_in_pages(paragraph, pages):
    for page_entry in pages:
        full_page_text = "\n".join(page_entry.get("lines", []))
        if paragraph in full_page_text:
            return page_entry.get("page", 1), 1
    return 1, 1


# --- AWS S3 Data Fetcher ---



def get_documents_for_path(directory_path):
    documents = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        # ניקוי ה-Prefix כדי לוודא שאין סלאשים מיותרים
        prefix = directory_path.strip('/') + '/' if directory_path else ""

        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
            if 'Contents' not in page: continue

            for obj in page['Contents']:
                key = obj['Key']
                if key.endswith('/'): continue

                # הורדת הקובץ כ-Bytes
                resp = s3.get_object(Bucket=BUCKET_NAME, Key=key)
                file_bytes = resp['Body'].read()
                file_ext = key.lower()
                content = ""

                try:
                    # לוגיקת פענוח לפי סוג קובץ (כמו בקוד Google שלך)
                    if file_ext.endswith('.pdf'):
                        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                            content = "".join([page_text.get_text() for page_text in doc])

                    elif file_ext.endswith('.docx'):
                        doc_obj = Document(io.BytesIO(file_bytes))
                        content = "\n".join([p.text for p in doc_obj.paragraphs])

                    else:
                        # קבצי טקסט רגילים
                        content = file_bytes.decode('utf-8', errors='ignore')

                except Exception as parse_error:
                    print(f"Error parsing {key}: {parse_error}")
                    continue

                if content:
                    documents.append({
                        "name": key.split('/')[-1],
                        "full_path": f"s3://{BUCKET_NAME}/{key}",
                        "content": content,
                        "pages": [{"page": 1, "lines": content.split('\n')}]
                    })
        return documents
    except Exception as e:
        print(f"S3 Error: {e}")
        return []

# --- Main Search Logic (Your Google Logic) ---

def simple_keyword_search(query, directory_path="", mode="any", match_type="partial", show_mode="line"):
    documents = get_documents_for_path(directory_path)
    if not documents:
        return {"status": "ok", "details": "No documents found", "matches": []}

    words = [w.strip() for w in query.split() if w.strip()]
    results = []

    for doc in documents:
        matched_items = []
        matched_items_html = []
        match_positions = []
        pages = doc.get("pages", [])

        if show_mode == "line":
            for page_entry in pages:
                p_num = page_entry.get("page", 1)
                for idx, line in enumerate(page_entry.get("lines", []), 1):
                    if match_line(line, words, mode, match_type):
                        matched_items.append(line)
                        matched_items_html.append(highlight_matches_html(line, words, match_type))
                        match_positions.append({"page": p_num, "line": idx})
        else:
            paragraphs = split_into_paragraphs(doc.get("content", ""))
            for para in paragraphs:
                if match_line(para, words, mode, match_type):
                    matched_items.append(para)
                    matched_items_html.append(highlight_matches_html(para, words, match_type))
                    p_num, l_idx = find_paragraph_position_in_pages(para, pages)
                    match_positions.append({"page": p_num, "line": l_idx})

        if matched_items:
            results.append({
                "file": doc["name"],
                "full_path": doc["full_path"],
                "matches": matched_items,
                "matches_html": matched_items_html,
                "match_positions": match_positions
            })

    return {"status": "ok", "query": query, "matches": results}

@app.route('/')
def home():
    return {"status": "searching_api_active"}, 200
# ---------------------

@app.route('/simple_search', methods=['POST'])
def simple_search_endpoint():
    timer_start = time.time()
    data = request.get_json(silent=True) or {}

    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()
    config = data.get("search_config", {})

    try:
        result = simple_keyword_search(
            query, directory_path,
            mode=config.get("word_logic", "any"),
            match_type=config.get("match_type", "partial"),
            show_mode=config.get("show_mode", "paragraph")
        )
        result["debug"] = f"{round(time.time() - timer_start, 2)} sec"
        return jsonify(result), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)