import os, time, traceback, re
from flask import Flask, request, jsonify
from azure.storage.blob import BlobServiceClient
from azure_search_utilities import azure_provider, search_in_json_content, highlight_matches_html, match_line
import base64
import urllib.parse  # חובה להוסיף בראש הקובץ
from openai import AzureOpenAI
import requests



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


@app.route('/simple_search', methods=['POST'])
def azure_search_endpoint():
    data = request.get_json(silent=True) or {}
    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()
    mode = data.get('mode', 'any')
    match_type = data.get('search_mode', 'partial')
    show_mode = data.get('show_mode', 'paragraph')

    print(f"--- 🚀 New Search Request ---")
    print(f"🔍 Query: '{query}'")

    if not query:
        return jsonify({"results": [], "count": 0}), 200

    words = [w.strip() for w in query.split() if w.strip()]
    results = []

    try:
        # שימוש ב-provider הקיים שלך בדיוק כפי שביקשת
        client = azure_provider.get_search_client()

        if client is None:
            return jsonify({"error": "Search client could not be initialized. Check environment variables."}), 500

        print(f"📡 Calling Azure AI Search for: '{query}'...")

        # ביצוע החיפוש ב-Azure
        azure_docs = client.search(
            search_text=query,
            search_mode="all" if mode == "all" else "any",
            # מוודאים ששולפים את השדות הנכונים מהאינדקס
            select=["content", "metadata_storage_path", "metadata_storage_name"],
            top=100
        )

        doc_count = 0
        for res in azure_docs:
            encoded_path = res.get("metadata_storage_path") or ""
            # כאן הפונקציה decode_azure_path צריכה להיות מוגדרת אצלך בקוד
            full_path = decode_azure_path(encoded_path) if 'decode_azure_path' in globals() else encoded_path
            file_name = res.get("metadata_storage_name") or "Unknown"

            # סינון תיקייה ידני
            if directory_path and directory_path != "/":
                clean_dir = directory_path.strip('/')
                if clean_dir not in full_path:
                    continue

            doc_count += 1
            raw_text = res.get("content") or ""
            if not raw_text:
                continue

            # עיבוד הטקסט לשורות
            lines = [ln.strip() for ln in raw_text.split('\n') if ln.strip()]

            # לוגיקת החיפוש וההדגשה שלך (ללא שינוי)
            if show_mode == "paragraph":
                matches_html = search_in_json_content(
                    full_path, [{"page": 1, "lines": lines}], words, mode, match_type
                )
                if matches_html:
                    results.append({
                        "file": file_name,
                        "full_path": full_path,
                        "matches_html": matches_html
                    })
            else:
                matched_items_html = []
                for line in lines:
                    if match_line(line, words, mode, match_type):
                        matched_items_html.append(highlight_matches_html(line, words, match_type))

                if matched_items_html:
                    results.append({
                        "file": file_name,
                        "full_path": full_path,
                        "matches_html": matched_items_html
                    })

        return jsonify({"status": "ok", "query": query, "matches": results, "count": len(results)})

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
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