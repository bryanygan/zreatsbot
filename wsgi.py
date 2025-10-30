"""
WSGI entry point for production deployment.
This allows gunicorn to run the Flask app while Discord bot runs in background.
"""
import os
import threading
from status_server import app
from bot_monitor import get_monitor

# Start Discord bot in a background thread when gunicorn loads this module
def start_discord_bot():
    """Start the Discord bot in background"""
    import combinedbot
    bot = combinedbot.main()

    BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    if not BOT_TOKEN:
        print("❌ Missing BOT_TOKEN in environment")
        return

    print("🚀 Starting Discord bot in background thread...")
    bot.run(BOT_TOKEN)

# Start bot in daemon thread
bot_thread = threading.Thread(target=start_discord_bot, daemon=True, name='DiscordBot')
bot_thread.start()
print("✅ Discord bot thread started")

# This is what gunicorn will run
if __name__ == "__main__":
    app.run()
