from flask import Flask, request, jsonify
# The imported function MUST accept two arguments now: perform_search(query, directory_path)
from search_core import perform_search

app = Flask(__name__)


@app.route('/search', methods=['POST'])
def search_endpoint():
    # Get all JSON data from the request body
    data = request.get_json()

    # 1. Get the search query (STRING)
    query = data.get('query', '')

    # 2. קריטי: קליטת נתיב התיקייה (פרפיקס GCS).
    # אם הלקוח לא שולח את זה, ברירת המחדל היא מחרוזת ריקה, שתחפש בכל הדלי.
    directory_path = data.get('directory_path', '')

    if not query:
        return jsonify({"error": "No query provided"}), 400

    # 3. העברת שני הפרמטרים ללוגיקת החיפוש
    results = perform_search(query, directory_path)

    # Return the results as JSON
    return jsonify(results)


if __name__ == '__main__':
    # Used for local testing only
    app.run(host='0.0.0.0', port=8080)