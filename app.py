"""
Railway entry point - runs Flask as main process with Discord bot in background thread.

This is specifically for Railway deployment where the web server must be the main process.
For local development, continue using: python combinedbot.py
"""
import os
import threading
import time

# Set environment variable to prevent combinedbot from starting its own status server
os.environ['RAILWAY_DEPLOYMENT'] = '1'

# Start Discord bot in background
def start_discord_bot():
    """Start Discord bot in a background thread"""
    # Small delay to let Flask initialize first
    time.sleep(3)

    print("🤖 Starting Discord bot in background thread...")

    # Import and run bot directly without starting status server
    import combinedbot
    bot = combinedbot.CombinedBot()

    BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
    if not BOT_TOKEN:
        print("❌ Missing BOT_TOKEN in environment")
        return

    # Setup event handlers
    @bot.event
    async def on_ready():
        await bot.change_presence(status=discord.Status.invisible)
        print(f'🤖 {bot.user} has connected to Discord (invisible)')
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        OPENER_CHANNEL_ID = int(os.getenv('OPENER_CHANNEL_ID')) if os.getenv('OPENER_CHANNEL_ID') else None
        if OPENER_CHANNEL_ID and message.channel.id == OPENER_CHANNEL_ID:
            from bot.utils import channel_status
            content = message.content.lower().strip()
            if content == "open":
                status = "open"
            elif content in ("close", "closed"):
                status = "close"
            elif content in ("break", "on hold", "hold"):
                status = "break"
            else:
                await bot.process_commands(message)
                return
            success, error = await channel_status.change_channel_status(message.channel, status)
            if success:
                await message.add_reaction("✅")
            else:
                await message.add_reaction("❌")
                await message.channel.send(f"{message.author.mention} ❌ {error}", delete_after=10)

        # Webhook handling
        if message.webhook_id and message.embeds:
            from bot.utils import helpers
            for embed in message.embeds:
                field_names = {f.name for f in embed.fields}
                is_webhook, webhook_type = helpers.detect_webhook_type(embed, field_names)
                if is_webhook:
                    try:
                        data = helpers.parse_webhook_fields(embed)
                        success = helpers.cache_webhook_data(
                            data,
                            message_timestamp=message.created_at,
                            message_id=message.id
                        )
                        if success:
                            print(f"📦 Cached {data.get('type', 'unknown')} webhook")
                    except Exception as e:
                        print(f"❌ Error parsing webhook: {str(e)}")

        await bot.process_commands(message)

    # Setup commands
    from bot.commands import order as order_commands, admin as admin_commands, channel as channel_commands, vcc as vcc_commands
    channel_commands.setup(bot)
    order_commands.setup(bot)
    admin_commands.setup(bot)
    vcc_commands.setup(bot)

    # Run bot (this will block this thread)
    print("🚀 Discord bot starting...")
    bot.run(BOT_TOKEN)

# Import discord here for the event handlers
import discord

# Start bot thread (non-daemon so it keeps running)
print("🚀 Launching Discord bot thread...")
bot_thread = threading.Thread(target=start_discord_bot, daemon=False, name='DiscordBotThread')
bot_thread.start()

# Import Flask app - this is what gunicorn will use
from status_server import app as application
app = application  # gunicorn looks for 'app' object

print(f"✅ Flask app loaded and ready for gunicorn")
print(f"📡 Discord bot running in background thread")

# For local testing only (not used by gunicorn)
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('STATUS_API_HOST', '0.0.0.0')
    print(f"🌐 Starting Flask server on {host}:{port} (development mode)")
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
