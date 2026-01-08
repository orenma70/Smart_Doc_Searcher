import boto3
import time
import re, os
import traceback
from flask import Flask, request, jsonify
from config_reader import BUCKET_NAME
import io
import fitz  # PyMuPDF - כבר נמצא ב-requirements שלך
from docx import Document  # כבר נמצא ב-requirements שלך
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import shutil


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
    # ניקוי רווחים מיותרים מהפסקה לחיפוש גמיש יותר
    clean_para = re.sub(r'\s+', ' ', paragraph).strip()

    for page_entry in pages:
        full_page_text = " ".join(page_entry.get("lines", []))
        clean_page = re.sub(r'\s+', ' ', full_page_text)

        if clean_para in clean_page:
            return page_entry.get("page", 1), 1
    return 1, 1


# --- AWS S3 Data Fetcher ---


def get_documents_for_path(directory_path):
    documents = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        prefix = directory_path.strip('/') + '/' if directory_path else ""

        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
            if 'Contents' not in page: continue

            for obj in page['Contents']:
                key = obj['Key']
                filename = key.split('/')[-1]

                if key.endswith('/') or filename.startswith('~$'):
                    continue

                resp = s3.get_object(Bucket=BUCKET_NAME, Key=key)
                file_bytes = resp['Body'].read()
                file_ext = key.lower()

                final_content = ""
                final_pages = []

                try:
                    if file_ext.endswith('.pdf'):
                        with fitz.open(stream=file_bytes, filetype="pdf") as pdf_doc:
                            for i, page in enumerate(pdf_doc):
                                # שימוש ב-blocks כדי לחבר מילים למשפטים תקינים
                                blocks = page.get_text("blocks")
                                page_lines = [b[4].strip() for b in blocks if b[4].strip()]

                                # If the page has almost no text but it's a valid page, it's likely a scan
                                if len("".join(page_lines)) < 10:
                                    print(f"Page {i + 1} looks like a scan. Running OCR...")
                                    # We can OCR just this specific page
                                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Zoom for better OCR
                                    img_data = pix.tobytes("png")
                                    ocr_text = pytesseract.image_to_string(io.BytesIO(img_data), lang='heb+eng')
                                    page_lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]

                                page_text = "\n".join(page_lines)
                                final_pages.append({
                                    "page": i + 1,
                                    "lines": page_lines
                                })
                                final_content += page_text + "\n\n"


                    elif file_ext.endswith('.docx'):

                        doc_obj = Document(io.BytesIO(file_bytes))

                        all_lines = []

                        final_pages = []

                        # 1. טקסט רגיל - נכנס כעמוד 1

                        text_lines = [p.text.strip() for p in doc_obj.paragraphs if p.text.strip()]

                        all_lines.extend(text_lines)

                        if text_lines:
                            final_pages.append({"page": 1, "lines": text_lines})

                        # 2. OCR על תמונות - מתחיל מעמוד 2

                        current_page = 2

                        for rel_id, rel in doc_obj.part.rels.items():

                            target_ref_safe = getattr(rel, 'target_ref', '')

                            # הדפסת ה-DEBUG שביקשת

                            print(f"DEBUG: rel_id # {rel_id}")

                            if "image" in target_ref_safe or "/media/" in target_ref_safe:

                                try:

                                    img = Image.open(io.BytesIO(rel.target_part.blob))

                                    ocr_text = pytesseract.image_to_string(img, lang='heb')

                                    if ocr_text.strip():
                                        img_lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]

                                        all_lines.extend(img_lines)

                                        # הוספת עמוד ייחודי לכל תמונה

                                        final_pages.append({

                                            "page": current_page,

                                            "lines": img_lines

                                        })

                                        print(f"DEBUG: OCR found text in {rel_id} (Assigned to page {current_page})")

                                        current_page += 1

                                except Exception as e:

                                    print(f"DEBUG: Failed OCR on {rel_id}: {e}")

                                    continue

                        final_content = "\n\n".join(all_lines)

                    else:
                        text_content = file_bytes.decode('utf-8', errors='ignore')
                        final_content = text_content
                        final_pages = [{"page": 1, "lines": text_content.split('\n')}]

                except Exception as parse_error:
                    print(f"Error parsing {key}: {parse_error}")
                    continue

                if final_content:
                    documents.append({
                        "name": key.split('/')[-1],
                        "full_path": f"s3://{BUCKET_NAME}/{key}",
                        "content": final_content,
                        "pages": final_pages  # כאן נכנסת הרשימה המפורטת שבנינו
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

        # שליחת רשימת העמודים ששמרנו ב-get_documents_for_path
        pages = doc.get("pages", [])

        if show_mode == "line":
            # אנחנו רצים עמוד-עמוד כדי לשמור על p_num תקין
            for page_entry in pages:
                p_num = page_entry.get("page", 1)
                lines = page_entry.get("lines", [])

                for idx, line in enumerate(lines, 1):
                    if match_line(line, words, mode, match_type):
                        matched_items.append(line)
                        matched_items_html.append(highlight_matches_html(line, words, match_type))
                        # עכשיו ה-p_num וה-idx מדויקים!
                        match_positions.append({"page": p_num, "line": idx})

        else:  # Paragraph Mode
            # כאן אנחנו מחברים את כל הטקסט אבל שומרים על הפרדה ברורה
            paragraphs = split_into_paragraphs(doc.get("content", ""))
            for para in paragraphs:
                if match_line(para, words, mode, match_type):
                    matched_items.append(para)
                    matched_items_html.append(highlight_matches_html(para, words, match_type))
                    # פונקציית העזר שלך תמצא את העמוד הנכון לפי תוכן הפסקה
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
                    img = Image.open(io.BytesIO(rel.target_part.blob)).convert("RGB")
                    ocr_text = pytesseract.image_to_string(img, lang='heb+eng')

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