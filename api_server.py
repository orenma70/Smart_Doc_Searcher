from flask import Flask, request, jsonify
from search_core import perform_search
import traceback  # נשאר לטיפול ב-500

app = Flask(__name__)


@app.route('/search', methods=['POST'])
def search_endpoint():
    # 1. קליטת JSON חסינת כשל (silent=True)
    data = request.get_json(silent=True)

    if data is None:
        print("LOG: Request failed - Invalid JSON or missing Content-Type header.")
        return jsonify({"error": "Invalid JSON or missing 'Content-Type: application/json' header."}), 400

    # 2. קליטת הפרמטרים
    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()

    # 🛑 3. בדיקה אם שאילתה חסרה (400) - כולל Log!
    if not query:
        # הדפסת הנתונים הנכנסים המלאים כדי לראות מה לא עבר
        print(f"LOG: Request failed - Query missing. Received data: {data}")
        return jsonify({"error": "No search query ('query') provided."}), 400

    # 4. ביצוע החיפוש והחזרת התוצאות
    try:
        results = perform_search(query, directory_path)

        # הדפסה במקרה של הצלחה
        print(f"LOG: Successful search for query: '{query}' in path: '{directory_path}'")

        return jsonify(results), 200

    except Exception as e:
        # לכידת כל שגיאה פנימית
        print(f"--- ERROR IN perform_search ---")
        print(traceback.format_exc())
        print(f"-------------------------------")
        return jsonify({"error": "Internal server error during search process. Check server logs for details."}), 500

def call_gemini_api(model_name, contents, config):
    # Retry logic (not shown, but recommended before falling back)
    try:
        print(f"Attempting API call with {model_name}...")
        return gemini_client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )
    except Exception as e:
        # Check for 503 or 500 errors specifically
        if '503 UNAVAILABLE' in str(e) or '500' in str(e):
            raise Exception("Service unavailable, fallback needed.")
        raise e  # Re-raise other errors

try:
    # 1. PRIMARY ATTEMPT
    response = call_gemini_api('gemini-2.5-flash', user_prompt, config={"system_instruction": system_instruction})

except Exception as e:
    if "Service unavailable" in str(e):
        # 2. FALLBACK ATTEMPT
        print("Falling back to gemini-2.5-pro due to overload.")
        response = call_gemini_api('gemini-2.5-pro', user_prompt, config={"system_instruction": system_instruction})
    else:
        raise e

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)