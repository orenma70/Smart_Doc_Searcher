import boto3, os
import time
import traceback
from flask import Flask, request, jsonify
from config_reader import BUCKET_NAME
import io
import fitz  # PyMuPDF - כבר נמצא ב-requirements שלך
from docx import Document  # כבר נמצא ב-requirements שלך
import pytesseract
from amazon_search_utilities import match_line, highlight_matches_html, search_in_json_content
from PIL import Image
import shutil
import json

# בדיקה והגדרה של נתיב Tesseract
tesseract_bin = shutil.which("tesseract")
if tesseract_bin:
    pytesseract.pytesseract.tesseract_cmd = tesseract_bin
else:
    # ברירת מחדל בלינוקס אם shutil לא מצא
    pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'




app = Flask(__name__)
s3 = boto3.client('s3')
# --- AWS Configuration ---


def get_documents_for_path(directory_path):
    documents = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        base_prefix = directory_path.strip('/') + '/' if directory_path else ""

        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=base_prefix):
            if 'Contents' not in page: continue

            for obj in page['Contents']:
                key = obj['Key']
                filename = key.split('/')[-1]
                if key.endswith('/') or filename.startswith('~$') or key.startswith('.index/'):
                    continue

                base_path = key.rsplit('.', 1)[0] if '.' in key else key
                index_key = f".index/{base_path}.json".replace("//", "/")

                try:
                    idx_resp = s3.get_object(Bucket=BUCKET_NAME, Key=index_key)
                    index_data = json.loads(idx_resp['Body'].read().decode('utf-8'))

                    # לוקחים רק את העמודים, בלי לבנות full_text
                    pages = index_data.get("pages") or index_data.get("pages_data", [])

                    if not pages: continue

                    documents.append({
                        "name": filename,
                        "full_path": key,
                        "pages": pages  # שומרים את המבנה המקורי לחיפוש
                    })

                except s3.exceptions.NoSuchKey:
                    continue
                except Exception:
                    continue
        return documents
    except Exception as e:
        print(f"🔥 S3 Error: {str(e)}")
        return []


def simple_keyword_search(query, directory_path="", mode="any", match_type="partial", show_mode="paragraph"):
    documents = get_documents_for_path(directory_path)
    if not documents:
        return {"status": "ok", "details": "No documents found", "matches": []}

    words = [w.strip() for w in query.split() if w.strip()]
    results = []

    for doc in documents:
        # אם אנחנו ב-Paragraph Mode, נשתמש בלוגיקה של ה-GUI
        if show_mode == "paragraph":
            matches_html = search_in_json_content(
                doc["full_path"],
                doc.get("pages", []),
                words,
                mode,
                match_type
            )

            if matches_html:
                results.append({
                    "file": doc["name"],
                    "full_path": doc["full_path"],
                    "matches_html": matches_html,  # פסקאות חתוכות עם HTML
                    "match_positions": []  # אופציונלי
                })

        else:  # Line Mode (נשאר כפי שהיה)
            matched_items_html = []
            for page_entry in doc.get("pages", []):
                p_num = page_entry.get("page", 1)
                for idx, line in enumerate(page_entry.get("lines", []), 1):
                    if match_line(line, words, mode, match_type):
                        matched_items_html.append(f"עמוד {p_num}: {highlight_matches_html(line, words, match_type)}")

            if matched_items_html:
                results.append({
                    "file": doc["name"],
                    "full_path": doc["full_path"],
                    "matches_html": matched_items_html
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

@app.route('/version')
def get_version():
    # הוא ימשוך אוטומטית את ה-v21.1.0 מה-App Runner
    return {
        "version": os.getenv("APP_VERSION", "local-dev"),
        "status": "stable",
        "mode": "paragraph"
    }

if __name__ == "__main__":
    if False:
        app.run(host='0.0.0.0', port=8080)
    else:
        #test_docx_parsing("C:\\a\\b.docx")
        file_path = "C:\\a\\b.docx"
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        doc_obj = Document(io.BytesIO(file_bytes))
        all_lines = []
        # יצירת רשימת עמודים אמיתית יותר ל-GUI
        final_pages = []

        # 1. טקסט רגיל (עמודים ראשונים)
        text_lines = []
        for p in doc_obj.paragraphs:
            if p.text.strip():
                text_lines.append(p.text.strip())

        all_lines.extend(text_lines)
        final_pages.append({"page": 1, "lines": text_lines})

        # 2. OCR על תמונות (עמוד 4 ואילך)
        image_counter = 2  # נתייחס לכל תמונה כעמוד חדש לצורך התצוגה
        for rel_id, rel in doc_obj.part.rels.items():
            target_ref_safe = getattr(rel, 'target_ref', '')
            if "image" in target_ref_safe or "/media/" in target_ref_safe:
                try:
                    img = Image.open(io.BytesIO(rel.target_part.blob)).convert("L")
                    ocr_text = pytesseract.image_to_string(img, lang='heb')

                    if ocr_text.strip():
                        lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
                        all_lines.extend(lines)
                        # כאן התיקון! מוסיפים עמוד חדש ל-GUI
                        final_pages.append({"page": image_counter, "lines": lines})
                        image_counter += 1
                        print(f"DEBUG: OCR found text in {rel_id}")
                except:
                    continue

        final_content = "\n\n".join(all_lines)
        a=0