import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/version')
def get_version():
    """
    מחזיר את גרסת האפליקציה.
    ב-Azure Container Apps, נגדיר את APP_VERSION כמשתנה סביבה.
    """
    return jsonify({
        "version": os.getenv("APP_VERSION", "v22.3.0-azure"), # ערך ברירת מחדל לבדיקות
        "status": "stable",
        "mode": "paragraph",
        "provider": "Azure Container Apps",
        "region": os.getenv("AZURE_REGION", "eastus")
    })

if __name__ == '__main__':
    # Azure Container Apps מקשיב לרוב לפורט 8080
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)