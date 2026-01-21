import os, time, traceback, json
from flask import Flask, request, jsonify
from azure.storage.blob import BlobServiceClient
from azure_search_utilities import azure_provider, search_in_json_content, highlight_matches_html, match_line
import base64
import urllib.parse  # חובה להוסיף בראש הקובץ
#from openai import AzureOpenAI
import requests
import fitz
import config_reader
from document_parsers import extract_text_for_indexing

cloud_provider="Microsoft"
PROVIDER_CONFIG=config_reader.set_provider_config(cloud_provider)

CONTAINER_NAME = PROVIDER_CONFIG["BUCKET_NAME"]


# בתוך ה-Endpoint, וודא שאתה משתמש בזה:
# full_path = decode_azure_path(encoded_path)
app = Flask(__name__)

key_name = "Azuresmartsearch3key1conn" # האות A גדולה כמו בלוג
connection_string = os.getenv(key_name) or os.getenv(key_name.lower()) or os.getenv(key_name.upper())

if connection_string:
    # מדפיסים את האורך ואת 15 התווים הראשונים (שמכילים את שם ה-Account)
    # זה לא חושף את המפתח (Key) שנמצא בסוף
    prefix = connection_string[:30]
    length = len(connection_string)
    print(f"🔍 Found variable '{key_name}'! Length: {length}, Starts with: {prefix}...")

    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        print("✅ Successfully connected to Blob Storage")
    except Exception as e:
        print(f"❌ Failed to initialize Blob Client: {e}")
else:
    print(f"⚠️ Environment variable '{key_name}' is COMPLETELY MISSING!")
    # מדפיס את כל המפתחות שמתחילים ב-A כדי לראות אם יש טעות באותיות
    found_keys = [k for k in os.environ.keys() if k.lower().startswith('a')]
    print(f"🔍 Keys starting with 'A' in system: {found_keys}")


def decode_azure_path(encoded_path):
    try:
        # 1. קודם כל מטפלים בקידוד URL (הופך את %D7 לעברית)
        decoded_url = urllib.parse.unquote(encoded_path)

        # 2. אם זה נראה כמו Base64 (אין http בהתחלה), ננסה לפענח
        if not decoded_url.startswith('http'):
            rem = len(decoded_url) % 4
            if rem > 0: decoded_url += "=" * (4 - rem)
            decoded_bytes = base64.urlsafe_b64decode(decoded_url)
            decoded_url = decoded_bytes.decode('utf-8', errors='ignore')
            # פענוח URL נוסף למקרה שהתוכן בתוך ה-Base64 היה מקודד
            decoded_url = urllib.parse.unquote(decoded_url)

        return decoded_url
    except Exception as e:
        print(f"⚠️ Decode failed: {e}")
        return urllib.parse.unquote(encoded_path)


def get_documents_for_path_azure(directory_path):
    documents = []
    # השתמשנו במשתנה הגלובלי שהגדרת למעלה
    container_name = CONTAINER_NAME
    container_name = CONTAINER_NAME.strip()  # ניקוי רווחים מיותרים
    print(f"DEBUG: Using Container Name: '{container_name}'")

    try:
        container_client = blob_service_client.get_container_client(container_name)
        print(f"DEBUG2")
        base_prefix = directory_path.strip('/') + '/' if directory_path else ""
        blobs = container_client.list_blobs(name_starts_with=base_prefix)

        for blob in blobs:
            print(f"DEBUG3")
            key = blob.name
            filename = key.split('/')[-1]

            if key.endswith('/') or filename.startswith('~$') or key.startswith('.index/'):
                continue

            base_path = key.rsplit('.', 1)[0] if '.' in key else key
            index_key = f".index/{base_path}.json"

            pages = []
            blob_client_index = container_client.get_blob_client(index_key)

            try:
                # 1. ניסיון טעינה מה-JSON הקיים (ה-Sidecar)
                index_content = blob_client_index.download_blob().readall()
                index_data = json.loads(index_content.decode('utf-8'))
                raw_pages = index_data.get("pages", [])

                # נירמול המבנה כדי ש-search_in_json_content לא יקרוס
                for idx, p in enumerate(raw_pages):
                    if isinstance(p, str):
                        pages.append({"page_number": idx + 1, "lines": [p]})
                    else:
                        # וידוא שקיים מפתח page_number
                        p_num = p.get("page_number") or p.get("page") or (idx + 1)
                        pages.append({"page_number": p_num, "lines": p.get("lines", [])})

            except Exception:
                # 2. אם האינדקס חסר - חילוץ/OCR
                print(f"🔍 Index missing for {filename}. Downloading original...")
                blob_client_file = container_client.get_blob_client(key)
                file_content = blob_client_file.download_blob().readall()
                file_ext = filename.lower()

                if file_ext.endswith('.pdf'):
                    with fitz.open(stream=file_content, filetype="pdf") as pdf:
                        num_pages = len(pdf)
                        full_digital_text = "\n".join([p.get_text() for p in pdf])

                    avg_chars = len(full_digital_text) / max(num_pages, 1)

                    if avg_chars < 200:
                        print(f"🚀 Triggering OCR for {filename} (Scanned Doc detected)")
                        # קריאה לפונקציית ה-OCR שלך
                        raw_pages, _ = extract_text_for_indexing(file_content, '.pdf')
                        pages = [{"page_number": p.get("page", i + 1), "lines": p.get("lines", [])} for i, p in
                                 enumerate(raw_pages)]

                        # שמירת האינדקס ל-Azure כדי שלא נריץ OCR שוב לעולם
                        index_save_data = {"filename": filename, "pages": pages, "timestamp": time.time()}
                        blob_client_index.upload_blob(
                            json.dumps(index_save_data, ensure_ascii=False, indent=4).encode('utf-8'),
                            overwrite=True
                        )
                    else:
                        # חילוץ דיגיטלי מהיר
                        with fitz.open(stream=file_content, filetype="pdf") as pdf:
                            for i, page in enumerate(pdf):
                                pages.append({"page_number": i + 1, "lines": page.get_text().splitlines()})

                # כאן אפשר להוסיף טיפול ב-DOCX במידת הצורך

            documents.append({
                "name": filename,
                "full_path": key,
                "pages": pages
            })

        return documents
    except Exception as e:
        print(f"🔥 Azure Blob Error: {str(e)}")
        traceback.print_exc()
        return []

def azure_simple_keyword_search(query, directory_path="", mode="any", match_type="partial", show_mode="paragraph"):
    # 1. שליפת המסמכים מ-Azure Blob Storage (כולל ה-OCR והאינדוקס)
    # זו הפונקציה שבנינו שבודקת את תיקיית .index בתוך ה-Blob
    documents = get_documents_for_path_azure(directory_path)

    if not documents:
        print(f"⚠️ No documents found in Azure path: {directory_path}")
        return {"status": "ok", "details": "No documents found", "matches": []}

    words = [w.strip() for w in query.split() if w.strip()]
    results = []

    print(f"🔍 Searching for '{query}' across {len(documents)} documents...")

    for doc in documents:
        # בדיקה שהמסמך מכיל דפים/טקסט
        doc_pages = doc.get("pages", [])
        if not doc_pages:
            continue

        if show_mode == "paragraph":
            # שימוש בפונקציית העזר הקיימת שלך לחיפוש בפסקאות
            matches_html = search_in_json_content(
                doc["full_path"], doc_pages, words, mode, match_type
            )
            if matches_html:
                results.append({
                    "file": doc["name"],
                    "full_path": doc["full_path"],
                    "matches_html": matches_html,
                    "match_positions": []
                })
        else:  # Line Mode (מצב שורות עם מספרי עמודים)
            matched_items_html = []
            for page_entry in doc_pages:
                # שים לב: ב-OCR המפתח הוא לעיתים "page_number" ובדיגיטלי "page"
                p_num = page_entry.get("page") or page_entry.get("page_number") or 1

                for line in page_entry.get("lines", []):
                    if match_line(line, words, mode, match_type):
                        highlighted = highlight_matches_html(line, words, match_type)
                        matched_items_html.append(f"עמוד {p_num}: {highlighted}")

            if matched_items_html:
                results.append({
                    "file": doc["name"],
                    "full_path": doc["full_path"],
                    "matches_html": matched_items_html
                })

    return {
        "status": "ok",
        "query": query,
        "matches": results,
        "count": len(results)
    }


@app.route('/simple_search', methods=['POST'])
def azure_simple_search_endpoint():
    timer_start = time.time()

    # 1. הגנה מפני קלט ריק או לא תקין
    data = request.get_json(silent=True)
    if not data:
        print("⚠️ DEBUG: No JSON data received in request")
        return jsonify({"error": "Missing JSON body"}), 400

    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()

    # 2. שליפת הגדרות עם וידוא טיפוסים (Types)
    config = data.get("search_config", {})
    if not isinstance(config, dict): config = {}

    word_logic = config.get("word_logic", "any")
    match_type = config.get("match_type", "partial")
    show_mode = config.get("show_mode", "paragraph")

    print(f"--- 🚀 Azure Search Start ---")
    print(f"🔍 Query: '{query}' | Path: '{directory_path}'")
    print(f"⚙️ Config: Logic={word_logic}, Match={match_type}, Show={show_mode}")

    if not query:
        return jsonify({"status": "ok", "matches": [], "count": 0, "details": "Empty query"}), 200

    try:
        # 3. קריאה למנוע החיפוש (הפונקציה שמשלבת OCR ו-Blob)
        # וודא שהפונקציה הזו מוגדרת לפני ה-Endpoint בקוד
        result = azure_simple_keyword_search(
            query,
            directory_path,
            mode=word_logic,
            match_type=match_type,
            show_mode=show_mode
        )

        # 4. חישוב זמן ביצוע והוספת נתוני אבחון
        execution_time = round(time.time() - timer_start, 2)
        result["debug"] = {
            "execution_time_sec": execution_time,
            "container": "Azure Container Apps",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        print(f"✅ Search completed: {len(result.get('matches', []))} matches in {execution_time}s")
        return jsonify(result), 200

    except Exception as e:
        # 5. פירוט שגיאה מלא לטרמינל (Log Stream) ב-Azure
        error_msg = str(e)
        print(f"🔥 CRITICAL ERROR in /simple_search: {error_msg}")
        traceback.print_exc()

        # החזרת שגיאה מפורטת ללקוח (רק בזמן פיתוח)
        return jsonify({
            "status": "error",
            "error": "Internal Server Error",
            "message": error_msg,
            "trace": traceback.format_exc().splitlines()[-3:]  # מחזיר רק את השורות האחרונות של השגיאה
        }), 500

def perform_azure_ai_search(query):
    try:
        # 1. חיפוש באינדקס (משתמש במפתח החיפוש הייעודי)
        search_key = os.getenv("azure-key-search")
        search_url = "https://smart-search-service3.search.windows.net/indexes/azureblob-index2/docs/search?api-version=2023-11-01"

        print(f"LOG: 1. Searching Index...")
        r = requests.post(search_url,
                          json={"search": query, "top": 3},
                          headers={"api-key": search_key, "Content-Type": "application/json"})
        r.raise_for_status()
        context = "\n".join([f"Content: {d['content']}" for d in r.json().get('value', [])])

        # 2. פנייה ל-OpenAI (כאן התיקון הקריטי!)
        # אנחנו מוותרים על ה-Connection String ומשתמשים במפתח ה-AI שקיים לך
        openai_key = os.getenv("AZURE_OPENAI_KEY")


        print(f"LOG: 2. Initializing AI with AZURE_OPENAI_KEY (starts with {openai_key[:4] if openai_key else 'None'})")

        ai_client = AzureOpenAI(
            api_key=openai_key,
            azure_endpoint="https://smartsearch3-openai.openai.azure.com",
            api_version="2024-02-01"
        )

        print(f"LOG: 3. Sending to GPT...")
        response = ai_client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": f"Context: {context}\nQuestion: {query}"}]
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"❌ AI Error: {str(e)}")
        return f"AI Error: {str(e)}"

@app.route('/search', methods=['POST'])
def search_endpoint():

    data = request.get_json(silent=True)
    query = data.get('query', '').strip()

    try:
        print(f"--- 🚀 New AI start ---")
        answer = perform_azure_ai_search(query)
        print(f"--- 🚀 New AI end ---")
        return jsonify({"answer": answer, "status": "Success"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/version')
def get_version():
    return jsonify({
        "version": os.getenv("APP_VERSION", "v24.7.2"),
        "status": "stable",
        "provider": "Azure Container Apps"
    })


if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)