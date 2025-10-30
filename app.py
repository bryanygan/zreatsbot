"""
Railway entry point - runs Flask as main process with Discord bot in background thread.

This is specifically for Railway deployment where the web server must be the main process.
For local development, continue using: python combinedbot.py
"""
import os
import threading
import time

# Start Discord bot in background before importing Flask app
def start_discord_bot():
    """Start Discord bot in a background thread"""
    # Small delay to let Flask initialize first
    time.sleep(2)

    print("🤖 Starting Discord bot in background thread...")
    import combinedbot

    bot = combinedbot.main()
    BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')

    if not BOT_TOKEN:
        print("❌ Missing BOT_TOKEN in environment")
        return

    # Run bot (this will block this thread, but Flask runs in main thread)
    bot.run(BOT_TOKEN)

# Start bot thread (non-daemon so it keeps running)
print("🚀 Launching Discord bot thread...")
bot_thread = threading.Thread(target=start_discord_bot, daemon=False, name='DiscordBotThread')
bot_thread.start()

# Import Flask app (this must be after bot thread starts)
from status_server import app

# Flask will run in main thread when Railway/gunicorn starts this
if __name__ == '__main__':
    # Get port from Railway environment
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('STATUS_API_HOST', '0.0.0.0')

    print(f"🌐 Starting Flask server on {host}:{port} (main thread)")
    print("📡 Discord bot running in background thread")

    # Run Flask in main thread (not daemon) - Railway can connect to this
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
