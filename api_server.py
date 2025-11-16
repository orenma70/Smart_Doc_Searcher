from flask import Flask, request, jsonify
import traceback  # נשאר לטיפול ב-500

app = Flask(__name__)


@app.route('/search', methods=['POST'])
def search_endpoint():
    from search_core import perform_search
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

