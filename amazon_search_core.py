from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/', methods=['GET'])
def health_check():
    # This is for the Load Balancer
    return "OK", 200


@app.route('/simple_search', methods=['POST'])
def simple_search():
    data = request.json
    return {"results": "found something for " + data['query']}

if __name__ == "__main__":
    # Standard Flask run (though Gunicorn will usually handle this)
    app.run(host='0.0.0.0', port=80)