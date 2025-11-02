"""
Minimal test file to verify Railway/gunicorn basics work.
Temporarily use this to test if Railway can connect at all.
"""
from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "test": "SUCCESS",
        "message": "Railway can connect!",
        "port": os.getenv('PORT', 'not set')
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
