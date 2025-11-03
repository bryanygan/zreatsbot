import os
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional, Tuple
import asyncio

try:
    from db import (
        get_and_remove_card as db_get_and_remove_card,
        get_and_remove_email as db_get_and_remove_email,
        get_pool_counts as db_get_pool_counts,
        close_connection,
        init_db,
    )
except ModuleNotFoundError:  # pragma: no cover - fallback for tests
    import importlib.util
    import pathlib
    db_path = pathlib.Path(__file__).resolve().parent / "db.py"
    spec = importlib.util.spec_from_file_location("db", db_path)
    db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(db)
    db_get_and_remove_card = db.get_and_remove_card
    db_get_and_remove_email = db.get_and_remove_email
    db_get_pool_counts = db.get_pool_counts
    close_connection = db.close_connection
    init_db = db.init_db

try:
    from logging_utils import (
        log_command_output,
        get_recent_logs,
        get_full_logs,
        get_log_stats,
    )
except ModuleNotFoundError:  # pragma: no cover - fallback for tests
    import pathlib
    import sys
    sys.path.append(str(pathlib.Path(__file__).resolve().parent))
    from logging_utils import (
        log_command_output,
        get_recent_logs,
        get_full_logs,
        get_log_stats,
    )

# Import status monitoring modules
try:
    from bot_monitor import get_monitor
    from status_server import start_server_thread
    from restart_handler import restart_check_loop
    STATUS_MONITORING_ENABLED = True
except ImportError:
    print("⚠️ Status monitoring modules not found. Install dependencies: pip install flask flask-cors psutil")
    STATUS_MONITORING_ENABLED = False

# optional package imports with fallback
try:
    from bot.views import PaymentView, CopyablePaymentView
except ModuleNotFoundError:  # pragma: no cover - fallback for tests
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parent / "bot" / "views.py"
    spec = importlib.util.spec_from_file_location("bot.views", path)
    views = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(views)
    PaymentView = views.PaymentView
    CopyablePaymentView = views.CopyablePaymentView

try:
    from bot.utils import channel_status, helpers, card_validator
except ModuleNotFoundError:  # pragma: no cover - fallback for tests
    import importlib.util
    import pathlib
    base = pathlib.Path(__file__).resolve().parent / "bot" / "utils"
    for name in ["channel_status", "helpers", "card_validator"]:
        spec = importlib.util.spec_from_file_location(f"bot.utils.{name}", base / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        globals()[name] = mod

try:
    from bot.commands import order as order_commands, admin as admin_commands, channel as channel_commands, vcc as vcc_commands
except ModuleNotFoundError:  # pragma: no cover - fallback for tests
    import importlib.util
    import pathlib
    base = pathlib.Path(__file__).resolve().parent / "bot" / "commands"
    for name in ["order", "admin", "channel", "vcc"]:
        spec = importlib.util.spec_from_file_location(f"bot.commands.{name}", base / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        globals()[f"{name}_commands"] = mod

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None
OPENER_CHANNEL_ID = int(os.getenv('OPENER_CHANNEL_ID')) if os.getenv('OPENER_CHANNEL_ID') else None
ROLE_PING_ID = os.getenv('ROLE_PING_ID', '1352022044614590494')
ORDER_CHANNEL_MENTION = os.getenv('ORDER_CHANNEL_MENTION', '<#1350935337269985334>')

EXP_MONTH = '11'
EXP_YEAR = '35'
ZIP_CODE = '19104'

# Database path - supports both local development and Railway/production
# Railway will use: /app/data/pool.db via DB_PATH environment variable
DB_PATH = Path(os.getenv('DB_PATH', str(Path(__file__).parent / 'data' / 'pool.db')))


class CombinedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(
            command_prefix='!', 
            intents=intents,
            status=discord.Status.invisible  # Makes bot appear offline
        )
        self.init_database()

    def init_database(self):
        init_db()

    def init_pool_db(self):
        init_db()

    async def close(self):
        close_connection()
        await super().close()

    def get_and_remove_card(self) -> Optional[Tuple[str, str, bool]]:
        result = db_get_and_remove_card()
        if result is None:
            return None
        number, cvv = result
        pool_counts = db_get_pool_counts()
        card_count = pool_counts['cards']
        return number, cvv, card_count == 0

    def get_and_remove_email(self, pool_type: str = 'main', fallback_to_main: bool = False) -> Optional[str]:
        """Get and remove email from specified pool"""
        result = db_get_and_remove_email(pool_type, fallback_to_main=fallback_to_main)
        return result

    def get_pool_counts(self) -> dict:
        """Get pool counts in new format"""
        return db_get_pool_counts()

    async def fetch_order_embed(
        self, channel: discord.TextChannel, search_limit: int = 25
    ):
        return await helpers.fetch_order_embed(channel, search_limit=search_limit)

    def parse_fields(self, embed: discord.Embed) -> dict:
        return helpers.parse_fields(embed)

    def normalize_name(self, name: str) -> str:
        return helpers.normalize_name(name)

    def format_name_csv(self, name: str) -> str:
        return helpers.format_name_csv(name)

    def is_valid_field(self, value: str) -> bool:
        return helpers.is_valid_field(value)

    def owner_only(self, interaction: discord.Interaction) -> bool:
        return helpers.owner_only(interaction)


def main():
    bot = CombinedBot()

    @bot.event
    async def on_ready():
        # Ensure bot stays invisible
        await bot.change_presence(status=discord.Status.invisible)

        print(f'🤖 {bot.user} has connected to Discord (invisible)')

        # Sync slash commands
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")

        # Start restart check loop if status monitoring is enabled
        if STATUS_MONITORING_ENABLED:
            bot.loop.create_task(restart_check_loop(bot))

    # Update your on_message event in combinedbot.py:

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        if OPENER_CHANNEL_ID and message.channel.id == OPENER_CHANNEL_ID:
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

        # Enhanced webhook order processing - detects all order confirmation formats
        if message.webhook_id and message.embeds:
            for embed in message.embeds:
                # Check if this looks like an order confirmation embed
                field_names = {f.name for f in embed.fields}
                
                # Check for tracking webhook (Store, Name, Delivery Address)
                field_names = {f.name for f in embed.fields}
                is_webhook, webhook_type = helpers.detect_webhook_type(embed, field_names)

                
                if is_webhook:
                    try:
                        data = helpers.parse_webhook_fields(embed)
                        
                        # Cache with message timestamp for proper ordering
                        success = helpers.cache_webhook_data(
                            data, 
                            message_timestamp=message.created_at,
                            message_id=message.id
                        )
                        
                        if success:
                            webhook_type = data.get('type', 'unknown')
                            store = data.get('store', 'Unknown')
                            name = data.get('name', 'Unknown')
                            print(f"📦 Cached {webhook_type} webhook: {name} at {store} (Message: {message.id})")
                        else:
                            print(f"⚠️ Skipped older webhook for: {data.get('name', 'Unknown')}")
                    except Exception as e:
                        print(f"❌ Error parsing webhook: {str(e)}")

        await bot.process_commands(message)

    channel_commands.setup(bot)
    order_commands.setup(bot)
    admin_commands.setup(bot)
    vcc_commands.setup(bot)

    return bot


if __name__ == "__main__":
    bot = main()
    if not BOT_TOKEN:
        print("❌ Missing BOT_TOKEN in .env file")
        exit(1)
    print("🚀 Starting Discord bot...")
    print(f"🔓 Opener channel: {OPENER_CHANNEL_ID or 'Not configured'}")
    print(f"👑 Owner ID: {OWNER_ID or 'Not configured'}")

    # Show pool information on startup
    try:
        import db
        pool_counts = db.get_pool_counts()
        print(f"📊 Pool Status:")
        print(f"   Cards: {pool_counts['cards']}")
        for pool_name, count in pool_counts['emails'].items():
            print(f"   {pool_name} emails: {count}")
    except Exception as e:
        print(f"⚠️ Could not get pool status: {e}")

    # Start status monitoring server if enabled
    if STATUS_MONITORING_ENABLED:
        try:
            start_server_thread()
            print("📡 Status monitoring API started")
        except Exception as e:
            print(f"⚠️ Failed to start status server: {e}")

    bot.run(BOT_TOKEN)
