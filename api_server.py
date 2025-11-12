from flask import Flask, request, jsonify
from search_core import perform_search # Import the logic you created

app = Flask(__name__)

@app.route('/search', methods=['POST'])
def search_endpoint():
    # Get the search query from the JSON body of the request
    data = request.get_json()
    query = data.get('query', '')

    if not query:
        return jsonify({"error": "No query provided"}), 400

    # Execute the core search logic
    results = perform_search(query)

    # Return the results as JSON
    return jsonify(results)

if __name__ == '__main__':
    # You will use your Dockerfile to run this on Google Cloud,
    # but this allows local testing
    app.run(host='0.0.0.0', port=8080)