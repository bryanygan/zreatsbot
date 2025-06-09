import os
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional, Tuple

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
    from bot.commands import order as order_commands, admin as admin_commands, channel as channel_commands
except ModuleNotFoundError:  # pragma: no cover - fallback for tests
    import importlib.util
    import pathlib
    base = pathlib.Path(__file__).resolve().parent / "bot" / "commands"
    for name in ["order", "admin", "channel"]:
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

EXP_MONTH = '06'
EXP_YEAR = '30'
ZIP_CODE = '19104'

DB_PATH = Path(__file__).parent / 'data' / 'pool.db'


class CombinedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix='!', intents=intents)
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
        card_count, _ = db_get_pool_counts()
        return number, cvv, card_count == 0

    def get_and_remove_email(self) -> Optional[Tuple[str, bool]]:
        result = db_get_and_remove_email()
        if result is None:
            return None
        email = result
        _, email_count = db_get_pool_counts()
        return email, email_count == 0

    def get_pool_counts(self) -> Tuple[int, int]:
        return db_get_pool_counts()

    async def fetch_order_embed(self, channel: discord.TextChannel):
        return await helpers.fetch_order_embed(channel)

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
        print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
        bot.add_view(PaymentView())
        await bot.change_presence(status=discord.Status.invisible)
        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} commands")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

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
            else:
                await bot.process_commands(message)
                return
            success, error = await channel_status.change_channel_status(message.channel, status)
            if success:
                await message.add_reaction("✅")
            else:
                await message.add_reaction("❌")
                await message.channel.send(f"{message.author.mention} ❌ {error}", delete_after=10)
        await bot.process_commands(message)

    channel_commands.setup(bot)
    order_commands.setup(bot)
    admin_commands.setup(bot)

    return bot


if __name__ == "__main__":
    bot = main()
    if not BOT_TOKEN:
        print("❌ Missing BOT_TOKEN in .env file")
        exit(1)
    print("🚀 Starting Discord bot...")
    print(f"🔓 Opener channel: {OPENER_CHANNEL_ID or 'Not configured'}")
    print(f"👑 Owner ID: {OWNER_ID or 'Not configured'}")
    bot.run(BOT_TOKEN)
