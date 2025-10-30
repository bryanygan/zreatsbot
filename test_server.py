"""
Minimal test server to verify Railway can reach our app.
Run this temporarily to test if Railway networking works at all.
"""
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "TEST SERVER WORKING",
        "port": os.getenv('PORT', 'not set'),
        "message": "If you see this, Railway routing works!"
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"🧪 Test server starting on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
