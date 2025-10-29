"""
Status API Server - HTTP API for bot monitoring and control
"""
import os
import json
import time
from datetime import datetime
from functools import wraps
from typing import Optional
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import threading
import queue

from bot_monitor import get_monitor
from logging_utils import get_recent_logs, get_full_logs
import db

# Initialize Flask app
app = Flask(__name__)

# Configure CORS
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:4321').split(',')
CORS(app, resources={
    r"/*": {
        "origins": cors_origins,
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-API-Key"],
        "expose_headers": ["Content-Type"]
    }
})

# API key for authentication
API_KEY = os.getenv('STATUS_API_KEY', 'dev-key-change-in-production')

# Event queue for SSE
event_queue = queue.Queue()


def require_api_key(f):
    """Decorator to require API key for protected endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Public endpoints don't need API key for read-only operations
        if request.method == 'GET' and request.endpoint in ['status', 'health', 'pools']:
            return f(*args, **kwargs)

        # Write operations require API key
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != API_KEY:
            return jsonify({"error": "Unauthorized", "message": "Invalid or missing API key"}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/status', methods=['GET'])
def status():
    """Get bot status"""
    monitor = get_monitor()
    return jsonify(monitor.get_full_status())


@app.route('/pools', methods=['GET'])
def pools():
    """Get pool counts"""
    try:
        pool_counts = db.get_pool_counts()
        return jsonify({
            "success": True,
            "pools": pool_counts,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/logs', methods=['GET'])
def logs():
    """Get recent logs"""
    limit = request.args.get('limit', default=50, type=int)
    full_details = request.args.get('full', default='false', type=str).lower() == 'true'

    try:
        if full_details:
            logs_data = get_full_logs(limit)
        else:
            logs_data = get_recent_logs(limit)

        return jsonify({
            "success": True,
            "count": len(logs_data),
            "logs": logs_data,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/restart', methods=['POST'])
@require_api_key
def restart():
    """Request bot restart"""
    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'Remote restart requested')

        monitor = get_monitor()
        monitor.request_restart(reason)

        # Emit restart event
        emit_event('restart_requested', {
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })

        return jsonify({
            "success": True,
            "message": "Restart requested",
            "reason": reason
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/stream', methods=['GET'])
def stream():
    """Server-Sent Events stream for real-time updates"""
    def event_stream():
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

        # Send periodic heartbeat and updates
        while True:
            try:
                # Try to get event from queue (non-blocking with timeout)
                try:
                    event = event_queue.get(timeout=5)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Send heartbeat if no events
                    monitor = get_monitor()
                    yield f"data: {json.dumps({'type': 'heartbeat', 'uptime': monitor.uptime_formatted, 'timestamp': datetime.now().isoformat()})}\n\n"
            except GeneratorExit:
                # Client disconnected
                break

    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@app.route('/last-command', methods=['GET'])
def last_command():
    """Get last command executed"""
    monitor = get_monitor()
    last_cmd = monitor.get_last_command()

    return jsonify({
        "success": True,
        "last_command": last_cmd,
        "timestamp": datetime.now().isoformat()
    })


def emit_event(event_type: str, data: dict):
    """Emit an event to all SSE clients"""
    event = {
        'type': event_type,
        'data': data,
        'timestamp': datetime.now().isoformat()
    }

    # Add to queue (non-blocking)
    try:
        event_queue.put_nowait(event)
    except queue.Full:
        # Queue is full, skip this event
        pass


def run_server(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """Run the Flask server"""
    print(f"[Status Server] Starting on {host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)


def start_server_thread(host: str = None, port: int = None) -> threading.Thread:
    """Start the status server in a background thread"""
    host = host or os.getenv('STATUS_API_HOST', '0.0.0.0')
    # Railway automatically sets PORT - use that first, then fall back to STATUS_API_PORT
    port = port or int(os.getenv('PORT', os.getenv('STATUS_API_PORT', '5000')))

    server_thread = threading.Thread(
        target=run_server,
        args=(host, port, False),
        daemon=True,
        name='StatusServer'
    )
    server_thread.start()
    print(f"[Status Server] Started in background thread")
    return server_thread


if __name__ == '__main__':
    # For testing
    run_server(debug=True)
