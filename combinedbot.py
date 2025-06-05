import os
import time
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from discord.errors import HTTPException
from discord.ui import View, Button
from discord import ButtonStyle
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Dict, Any, Optional, Tuple
import tempfile

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

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None
OPENER_CHANNEL_ID = int(os.getenv('OPENER_CHANNEL_ID')) if os.getenv('OPENER_CHANNEL_ID') else None
ROLE_PING_ID = os.getenv('ROLE_PING_ID', '1352022044614590494')
ORDER_CHANNEL_MENTION = os.getenv('ORDER_CHANNEL_MENTION', '<#1350935337269985334>')

# Constants for card formatting
EXP_MONTH = '06'
EXP_YEAR = '30'
ZIP_CODE = '19104'

# Database paths
DB_PATH = Path(__file__).parent / 'data' / 'pool.db'

# Rate limiting for channel renames
rename_history = deque()

async def change_channel_status(channel: discord.TextChannel, status: str) -> Tuple[bool, str]:
    """Rename the channel and send open/close announcements.

    Returns ``(success, error_message)``.
    ``status`` should be "open" or "close".
    """
    new_name = "open🟢🟢" if status == "open" else "closed🔴🔴"

    now = time.monotonic()
    while rename_history and now - rename_history[0] > 600:
        rename_history.popleft()

    if len(rename_history) >= 2:
        return False, "Rename limit reached (2 per 10 min). Try again later."

    try:
        await channel.edit(name=new_name)
        rename_history.append(now)

        if status == "open":
            await channel.send(f"ZR Eats is now OPEN! <@&{ROLE_PING_ID}>")
            embed = discord.Embed(
                title="ZR Eats is now OPEN!",
                description=(
                    f"We are now accepting orders! Click the order button in {ORDER_CHANNEL_MENTION} "
                    "to place an order."
                ),
            )
            await channel.send(embed=embed)
        else:
            embed = discord.Embed(
                title="ZR Eats is now CLOSED.",
                description=(
                    "We are currently closed. Please come back later when we're open for new orders! "
                    "Do not open a ticket, you will not get a response."
                ),
            )
            await channel.send(embed=embed)
        return True, ""
    except HTTPException as e:
        return False, f"Failed to rename channel: {e.status} {e.text}"

class PaymentView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view, no timeout
    
    @discord.ui.button(label='Zelle', style=ButtonStyle.danger, emoji='🏦', custom_id='payment_zelle')
    async def zelle_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="💳 Zelle Payment",
            color=0xff0000  # Red color
        )
        embed.add_field(
            name="Email:",
            value="```ganbryanbts@gmail.com```",
            inline=False
        )
        embed.add_field(
            name="📝 Note:",
            value="Name is **Bryan Gan**",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='Venmo', style=ButtonStyle.primary, emoji='💙', custom_id='payment_venmo')
    async def venmo_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="💙 Venmo Payment",
            color=0x0099ff  # Blue color
        )
        embed.add_field(
            name="Username:",
            value="```@BGHype```",
            inline=False
        )
        embed.add_field(
            name="📝 Note:",
            value="Friends & Family, no notes, emoji is fine\nLast 4 digits: **0054** (if required)",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='PayPal', style=ButtonStyle.success, emoji='💚', custom_id='payment_paypal')
    async def paypal_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="💚 PayPal Payment",
            color=0x00ff00  # Green color
        )
        embed.add_field(
            name="Email:",
            value="```ganbryanbts@gmail.com```",
            inline=False
        )
        embed.add_field(
            name="📝 Note:",
            value="Friends & Family, no notes",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='Crypto', style=ButtonStyle.secondary, emoji='🪙', custom_id='payment_crypto')
    async def crypto_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="🪙 Crypto Payment",
            color=0xffa500  # Orange color
        )
        embed.add_field(
            name="Available:",
            value="ETH, LTC, SOL, BTC, USDT, USDC",
            inline=False
        )
        embed.add_field(
            name="📝 Note:",
            value="Message me for more details and wallet addresses",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CombinedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix='!', intents=intents)
        
        # Initialize database
        self.init_database()
        

    def init_database(self):
        """Initialize the pool database for cards and emails"""
        # Create data directory
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize pool database (cards/emails)
        self.init_pool_db()

    def init_pool_db(self):
        """Initialize the pool database for cards and emails"""
        if DB_PATH.exists():
            try:
                with DB_PATH.open('rb') as f:
                    header = f.read(16)
                if not header.startswith(b"SQLite format 3\x00"):
                    DB_PATH.unlink()
            except Exception:
                try:
                    DB_PATH.unlink()
                except Exception:
                    pass

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT NOT NULL,
                cvv    TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emails (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT    NOT NULL
            )
        ''')

        conn.commit()
        conn.close()

    # Database helper methods
    def get_and_remove_card(self) -> Optional[Tuple[str, str, bool]]:
        """Fetch the oldest card and remove it from the database.

        Returns a tuple of ``(number, cvv, is_last)`` where ``is_last`` is a
        boolean indicating whether the pool is now empty. ``None`` is returned
        if there are no cards left.
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT id, number, cvv FROM cards ORDER BY id LIMIT 1')
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        card_id, number, cvv = row
        cursor.execute('DELETE FROM cards WHERE id = ?', (card_id,))
        
        # Check if this was the last card
        cursor.execute('SELECT COUNT(*) FROM cards')
        remaining_cards = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        # Return the card and whether this was the last one
        return number, cvv, remaining_cards == 0

    def get_and_remove_email(self) -> Optional[Tuple[str, bool]]:
        """Fetch the oldest email and remove it from the database.

        Returns a tuple of ``(email, is_last)`` where ``is_last`` indicates if
        the email pool became empty after this operation. ``None`` is returned
        when the pool has no emails left.
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT id, email FROM emails ORDER BY id LIMIT 1')
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        email_id, email = row
        cursor.execute('DELETE FROM emails WHERE id = ?', (email_id,))
        
        # Check if this was the last email
        cursor.execute('SELECT COUNT(*) FROM emails')
        remaining_emails = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        # Return the email and whether this was the last one
        return email, remaining_emails == 0


    # Utility functions
    async def fetch_order_embed(self, channel: discord.TextChannel) -> Optional[discord.Embed]:
        """Fetch the first message's second embed in channel"""
        try:
            msgs = [msg async for msg in channel.history(limit=1, oldest_first=True)]
            if not msgs or len(msgs[0].embeds) < 2:
                return None
            return msgs[0].embeds[1]
        except Exception:
            return None

    def parse_fields(self, embed: discord.Embed) -> dict:
        """Parse embed fields"""
        data = {field.name: field.value for field in embed.fields}
        return {
            'link': data.get('Group Cart Link'),
            'name': data.get('Name', '').strip(),
            'addr2': data.get('Address Line 2', '').strip(),
            'notes': data.get('Delivery Notes', '').strip(),
            'tip': data.get('Tip Amount', '').strip()
        }

    def normalize_name(self, name: str) -> str:
        """Normalize name into two words"""
        cleaned = name.replace(",", " ").strip()
        parts = cleaned.split()
        if len(parts) >= 2:
            first = parts[0].strip().title()
            last = parts[1].strip().title()
            return f"{first} {last}"
        if len(parts) == 1:
            w = parts[0].strip().title()
            return f"{w} {w[0].upper()}"
        return ''

    def format_name_csv(self, name: str) -> str:
        """Return name in 'Firstname,Lastname' format with no spaces around comma"""
        cleaned = name.replace(",", " ").strip()
        parts = cleaned.split()
        if len(parts) >= 2:
            first = parts[0].strip().title()
            last = parts[1].strip().title()
            return f"{first},{last}"
        if len(parts) == 1:
            w = parts[0].strip().title()
            return f"{w},{w[0].upper()}"
        return ''

    def is_valid_field(self, value: str) -> bool:
        """Check if field value is valid"""
        return bool(value and value.strip().lower() not in ('n/a', 'none'))

    def owner_only(self, interaction: discord.Interaction) -> bool:
        """Check if user is owner"""
        return OWNER_ID and interaction.user.id == OWNER_ID

# Initialize bot
bot = CombinedBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    bot.add_view(PaymentView())
    
    # Set bot status to invisible (appear offline)
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

    # Channel opener functionality
    if OPENER_CHANNEL_ID and message.channel.id == OPENER_CHANNEL_ID:
        content = message.content.lower().strip()
        if content == "open":
            status = "open"
        elif content in ("close", "closed"):
            status = "close"
        else:
            await bot.process_commands(message)
            return

        success, error = await change_channel_status(message.channel, status)
        if success:
            await message.add_reaction("✅")
        else:
            await message.add_reaction("❌")
            await message.channel.send(
                f"{message.author.mention} ❌ {error}",
                delete_after=10
            )

    await bot.process_commands(message)

# CHANNEL STATUS SLASH COMMANDS
@bot.tree.command(name='open', description='Open the channel and send announcements')
async def open_command(interaction: discord.Interaction):
    if OPENER_CHANNEL_ID and interaction.channel.id != OPENER_CHANNEL_ID:
        return await interaction.response.send_message(
            "❌ This command can only be used in the opener channel.", ephemeral=True
        )

    success, error = await change_channel_status(interaction.channel, "open")
    if success:
        await interaction.response.send_message("✅ Channel opened.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)


@bot.tree.command(name='close', description='Close the channel and send notice')
async def close_command(interaction: discord.Interaction):
    if OPENER_CHANNEL_ID and interaction.channel.id != OPENER_CHANNEL_ID:
        return await interaction.response.send_message(
            "❌ This command can only be used in the opener channel.", ephemeral=True
        )

    success, error = await change_channel_status(interaction.channel, "close")
    if success:
        await interaction.response.send_message("✅ Channel closed.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)

# ORDER COMMANDS
@bot.tree.command(name='fusion_assist', description='Format a Fusion assist order')
@app_commands.choices(mode=[
    app_commands.Choice(name='Postmates', value='p'),
    app_commands.Choice(name='UberEats', value='u'),
])
@app_commands.describe(
    email="Optional: Add a custom email to the command",
    card_number="Optional: Use custom card number (bypasses pool)",
    card_cvv="Optional: CVV for custom card (required if card_number provided)"
)
async def fusion_assist(interaction: discord.Interaction, mode: app_commands.Choice[str], 
                       email: str = None, card_number: str = None, card_cvv: str = None):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

    # Validate custom card parameters
    if card_number and not card_cvv:
        return await interaction.response.send_message("❌ CVV required when using custom card number.", ephemeral=True)
    if card_cvv and not card_number:
        return await interaction.response.send_message("❌ Card number required when using custom CVV.", ephemeral=True)

    embed = await bot.fetch_order_embed(interaction.channel)
    if embed is None:
        return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

    info = bot.parse_fields(embed)
    
    # Use custom card or get from pool
    was_last_card = False
    if card_number and card_cvv:
        # Use custom card
        number, cvv = card_number, card_cvv
        card = (number, cvv)
        card_source = "custom"
    else:
        # Get card from pool
        card_result = bot.get_and_remove_card()
        if card_result is None:
            return await interaction.response.send_message("❌ Card pool is empty.", ephemeral=True)
        
        # Unpack card result
        if len(card_result) == 3:
            number, cvv, was_last_card = card_result
            card = (number, cvv)
        else:
            # Fallback for old format
            card = card_result
            was_last_card = False
        card_source = "pool"
    
    raw_name = info['name']
    
    base_command = f"{info['link']},{number},{EXP_MONTH},{EXP_YEAR},{cvv},{ZIP_CODE}"
    if email:
        base_command += f",{email}"
    
    parts = [f"/assist order order_details:{base_command}"]
    
    if mode.value == 'p':
        parts.append('mode:postmates')
    elif mode.value == 'u':
        parts.append('mode:ubereats')
    if bot.is_valid_field(raw_name):
        name = bot.normalize_name(raw_name)
        parts.append(f"override_name:{name}")
    if bot.is_valid_field(info['addr2']):
        parts.append(f"override_aptorsuite:{info['addr2']}")
    notes = info['notes'].strip()
    if bot.is_valid_field(notes):
        if notes.lower() == 'meet at door':
            parts.append("override_dropoff:Meet at Door")
        else:
            parts.append(f"override_notes:{notes}")
            if 'leave' in notes.lower():
                parts.append("override_dropoff:Leave at Door")

    command = ' '.join(parts)

    # Only log if using pool resources
    if card_source == "pool":
        log_command_output(
            command_type="fusion_assist",
            user_id=interaction.user.id,
            username=str(interaction.user),
            channel_id=interaction.channel.id,
            guild_id=interaction.guild.id if interaction.guild else None,
            command_output=command,
            tip_amount=info['tip'],
            card_used=card,
            email_used=email,
            additional_data={"mode": mode.value, "parsed_fields": info, "custom_email": email, "card_source": card_source}
        )

    # Create embed for clean output
    embed = discord.Embed(title="Fusion Assist", color=0x00ff00)
    
    # Add command output
    embed.add_field(name="", value=f"```{command}```", inline=False)
    
    # Add email if used
    if email:
        embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
    
    # Add tip amount
    embed.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)
    
    # Add footer only for warnings
    warnings = []
    if was_last_card and card_source == "pool":
        warnings.append("⚠️ Card pool empty!")
    
    if warnings:
        embed.set_footer(text=" | ".join(warnings))
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='wool_details', description='Show parsed Wool order details')
async def wool_details(interaction: discord.Interaction):
    """Display parsed Wool order details without using pool resources."""
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

    embed = await bot.fetch_order_embed(interaction.channel)
    if embed is None:
        return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

    info = bot.parse_fields(embed)

    details = discord.Embed(title="Wool Order Details", color=0xff6600)
    if bot.is_valid_field(info['link']):
        details.add_field(name="Group Cart Link:", value=f"```{info['link']}```", inline=False)
    if bot.is_valid_field(info['name']):
        formatted = bot.format_name_csv(info['name'])
        details.add_field(name="Name:", value=f"```{formatted}```", inline=False)
    if bot.is_valid_field(info['addr2']):
        details.add_field(name="Address Line 2:", value=f"```{info['addr2']}```", inline=False)
    if bot.is_valid_field(info['notes']):
        details.add_field(name="Delivery Notes:", value=f"```{info['notes']}```", inline=False)
    details.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)

    await interaction.response.send_message(embed=details, ephemeral=True)

@bot.tree.command(name='fusion_order', description='Format a Fusion order with email')
@app_commands.describe(
    custom_email="Optional: Use custom email (bypasses pool)",
    card_number="Optional: Use custom card number (bypasses pool)",
    card_cvv="Optional: CVV for custom card (required if card_number provided)"
)
async def fusion_order(interaction: discord.Interaction, custom_email: str = None, 
                      card_number: str = None, card_cvv: str = None):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

    # Validate custom card parameters
    if card_number and not card_cvv:
        return await interaction.response.send_message("❌ CVV required when using custom card number.", ephemeral=True)
    if card_cvv and not card_number:
        return await interaction.response.send_message("❌ Card number required when using custom CVV.", ephemeral=True)

    embed = await bot.fetch_order_embed(interaction.channel)
    if embed is None:
        return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

    info = bot.parse_fields(embed)
    
    # Use custom card or get from pool
    was_last_card = False
    if card_number and card_cvv:
        # Use custom card
        number, cvv = card_number, card_cvv
        card = (number, cvv)
        card_source = "custom"
    else:
        # Get card from pool
        card_result = bot.get_and_remove_card()
        if card_result is None:
            return await interaction.response.send_message("❌ Card pool is empty.", ephemeral=True)
        
        # Unpack card result
        if len(card_result) == 3:
            number, cvv, was_last_card = card_result
            card = (number, cvv)
        else:
            # Fallback for old format
            card = card_result
            was_last_card = False
        card_source = "pool"
    
    # Use custom email or get from pool
    was_last_email = False
    if custom_email:
        # Use custom email
        email = custom_email
        email_source = "custom"
    else:
        # Get email from pool
        email_result = bot.get_and_remove_email()
        if email_result is None:
            return await interaction.response.send_message("❌ Email pool is empty.", ephemeral=True)
        
        # Unpack email result
        if isinstance(email_result, tuple) and len(email_result) == 2:
            email, was_last_email = email_result
        else:
            # Fallback for old format
            email = email_result
            was_last_email = False
        email_source = "pool"

    raw_name = info['name']
    parts = [f"/order uber order_details:{info['link']},{number},{EXP_MONTH},{EXP_YEAR},{cvv},{ZIP_CODE},{email}"]
    if bot.is_valid_field(raw_name):
        name = bot.normalize_name(raw_name)
        parts.append(f"override_name:{name}")
    if bot.is_valid_field(info['addr2']):
        parts.append(f"override_aptorsuite:{info['addr2']}")
    notes = info['notes'].strip()
    if bot.is_valid_field(notes):
        if notes.lower() == 'meet at door':
            parts.append("override_dropoff:Meet at Door")
        else:
            parts.append(f"override_notes:{notes}")
            if 'leave' in notes.lower():
                parts.append("override_dropoff:Leave at Door")

    command = ' '.join(parts)

    # Only log if using pool resources
    if card_source == "pool" or email_source == "pool":
        log_command_output(
            command_type="fusion_order",
            user_id=interaction.user.id,
            username=str(interaction.user),
            channel_id=interaction.channel.id,
            guild_id=interaction.guild.id if interaction.guild else None,
            command_output=command,
            tip_amount=info['tip'],
            card_used=card if card_source == "pool" else None,
            email_used=email if email_source == "pool" else None,
            additional_data={"parsed_fields": info, "card_source": card_source, "email_source": email_source}
        )

    # Create embed for clean output
    embed = discord.Embed(title="Fusion Order", color=0x0099ff)
    
    # Add command output
    embed.add_field(name="", value=f"```{command}```", inline=False)
    
    # Add email
    embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
    
    # Add tip amount
    embed.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)
    
    # Add footer only for warnings
    warnings = []
    if was_last_card and card_source == "pool":
        warnings.append("⚠️ Card pool empty!")
    if was_last_email and email_source == "pool":
        warnings.append("⚠️ Email pool empty!")
    
    if warnings:
        embed.set_footer(text=" | ".join(warnings))
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='wool_order', description='Format a Wool order')
@app_commands.describe(
    custom_email="Optional: Use custom email (bypasses pool)",
    card_number="Optional: Use custom card number (bypasses pool)",
    card_cvv="Optional: CVV for custom card (required if card_number provided)"
)
async def wool_order(interaction: discord.Interaction, custom_email: str = None,
                    card_number: str = None, card_cvv: str = None):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

    # Validate custom card parameters
    if card_number and not card_cvv:
        return await interaction.response.send_message("❌ CVV required when using custom card number.", ephemeral=True)
    if card_cvv and not card_number:
        return await interaction.response.send_message("❌ Card number required when using custom CVV.", ephemeral=True)

    embed = await bot.fetch_order_embed(interaction.channel)
    if embed is None:
        return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

    info = bot.parse_fields(embed)
    
    # Use custom card or get from pool
    was_last_card = False
    if card_number and card_cvv:
        # Use custom card
        number, cvv = card_number, card_cvv
        card = (number, cvv)
        card_source = "custom"
    else:
        # Get card from pool
        card_result = bot.get_and_remove_card()
        if card_result is None:
            return await interaction.response.send_message("❌ Card pool is empty.", ephemeral=True)
        
        # Unpack card result
        if len(card_result) == 3:
            number, cvv, was_last_card = card_result
            card = (number, cvv)
        else:
            # Fallback for old format
            card = card_result
            was_last_card = False
        card_source = "pool"
    
    # Use custom email or get from pool
    was_last_email = False
    if custom_email:
        # Use custom email
        email = custom_email
        email_source = "custom"
    else:
        # Get email from pool
        email_result = bot.get_and_remove_email()
        if email_result is None:
            return await interaction.response.send_message("❌ Email pool is empty.", ephemeral=True)
        
        # Unpack email result
        if isinstance(email_result, tuple) and len(email_result) == 2:
            email, was_last_email = email_result
        else:
            # Fallback for old format
            email = email_result
            was_last_email = False
        email_source = "pool"

    command = f"{info['link']},{number},{EXP_MONTH}/{EXP_YEAR},{cvv},{ZIP_CODE},{email}"

    # Only log if using pool resources
    if card_source == "pool" or email_source == "pool":
        log_command_output(
            command_type="wool_order",
            user_id=interaction.user.id,
            username=str(interaction.user),
            channel_id=interaction.channel.id,
            guild_id=interaction.guild.id if interaction.guild else None,
            command_output=command,
            tip_amount=info['tip'],
            card_used=card if card_source == "pool" else None,
            email_used=email if email_source == "pool" else None,
            additional_data={"parsed_fields": info, "card_source": card_source, "email_source": email_source}
        )

    # Create embed for clean output
    embed = discord.Embed(title="Wool Order", color=0xff6600)

    # Add command output
    embed.add_field(name="", value=f"```{command}```", inline=False)

    # Add email
    embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)

    # Add parsed fields above tip if present
    if bot.is_valid_field(info['name']):
        formatted = bot.format_name_csv(info['name'])
        embed.add_field(name="Name:", value=f"```{formatted}```", inline=False)
    if bot.is_valid_field(info['addr2']):
        embed.add_field(name="Address Line 2:", value=f"```{info['addr2']}```", inline=False)
    if bot.is_valid_field(info['notes']):
        embed.add_field(name="Delivery Notes:", value=f"```{info['notes']}```", inline=False)

    # Add tip amount
    embed.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)
    
    # Add footer only for warnings
    warnings = []
    if was_last_card and card_source == "pool":
        warnings.append("⚠️ Card pool empty!")
    if was_last_email and email_source == "pool":
        warnings.append("⚠️ Email pool empty!")
    
    if warnings:
        embed.set_footer(text=" | ".join(warnings))
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ADMIN COMMANDS FOR POOLS
@bot.tree.command(name='add_card', description='(Admin) Add a card to the pool')
async def add_card(interaction: discord.Interaction, number: str, cvv: str):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO cards (number, cvv) VALUES (?, ?)", (number, cvv))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ Card ending in {number[-4:]} added.", ephemeral=True)

@bot.tree.command(name='add_email', description='(Admin) Add an email to the pool')
@app_commands.describe(top="Add this email to the top of the pool so it's used first")
async def add_email(interaction: discord.Interaction, email: str, top: bool = False):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if top:
        cur.execute("SELECT MIN(id) FROM emails")
        row = cur.fetchone()
        min_id = row[0] if row and row[0] is not None else None
        if min_id is None:
            cur.execute("INSERT INTO emails (email) VALUES (?)", (email,))
        else:
            new_id = min_id - 1
            cur.execute("INSERT INTO emails (id, email) VALUES (?, ?)", (new_id, email))
    else:
        cur.execute("INSERT INTO emails (email) VALUES (?)", (email,))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ Email `{email}` added.", ephemeral=True)

@bot.tree.command(name='read_cards', description='(Admin) List all cards in the pool')
async def read_cards(interaction: discord.Interaction):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT number, cvv FROM cards")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return await interaction.response.send_message("✅ No cards in the pool.", ephemeral=True)

    lines = [f"{num},{cvv}" for num, cvv in rows]
    payload = "Cards in pool:\n" + "\n".join(lines)
    await interaction.response.send_message(f"```{payload}```", ephemeral=True)

@bot.tree.command(name='read_emails', description='(Admin) List all emails in the pool')
async def read_emails(interaction: discord.Interaction):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT email FROM emails")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return await interaction.response.send_message("✅ No emails in the pool.", ephemeral=True)

    lines = [email for (email,) in rows]
    payload = "Emails in pool:\n" + "\n".join(lines)
    await interaction.response.send_message(f"```{payload}```", ephemeral=True)

# BULK UPLOAD COMMANDS
@bot.tree.command(name='bulk_cards', description='(Admin) Add multiple cards from a text file')
async def bulk_cards(interaction: discord.Interaction, file: discord.Attachment):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    if not file.filename.endswith('.txt'):
        return await interaction.response.send_message("❌ Please upload a .txt file.", ephemeral=True)
    
    if file.size > 1024 * 1024:  # 1MB
        return await interaction.response.send_message("❌ File too large. Maximum size is 1MB.", ephemeral=True)
    
    try:
        file_content = await file.read()
        text_content = file_content.decode('utf-8')
        
        lines = text_content.strip().split('\n')
        cards_to_add = []
        invalid_lines = []
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
                
            parts = line.split(',')
            if len(parts) != 2:
                invalid_lines.append(f"Line {i}: '{line}' (expected format: cardnum,cvv)")
                continue
            
            number, cvv = parts[0].strip(), parts[1].strip()
            
            if not number or not cvv:
                invalid_lines.append(f"Line {i}: '{line}' (empty card number or CVV)")
                continue
            
            if not number.isdigit() or len(number) < 13 or len(number) > 19:
                invalid_lines.append(f"Line {i}: '{line}' (invalid card number format)")
                continue
            
            if not cvv.isdigit() or len(cvv) < 3 or len(cvv) > 4:
                invalid_lines.append(f"Line {i}: '{line}' (invalid CVV format)")
                continue
            
            cards_to_add.append((number, cvv))
        
        if invalid_lines:
            error_msg = "❌ Found invalid lines:\n" + "\n".join(invalid_lines[:10])
            if len(invalid_lines) > 10:
                error_msg += f"\n... and {len(invalid_lines) - 10} more errors"
            return await interaction.response.send_message(error_msg, ephemeral=True)
        
        if not cards_to_add:
            return await interaction.response.send_message("❌ No valid cards found in the file.", ephemeral=True)
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        added_count = 0
        duplicate_count = 0
        
        for number, cvv in cards_to_add:
            cur.execute("SELECT COUNT(*) FROM cards WHERE number = ? AND cvv = ?", (number, cvv))
            exists = cur.fetchone()[0] > 0
            
            if exists:
                duplicate_count += 1
            else:
                cur.execute("INSERT INTO cards (number, cvv) VALUES (?, ?)", (number, cvv))
                added_count += 1
        
        conn.commit()
        conn.close()
        
        success_msg = f"✅ Successfully added {added_count} cards to the pool."
        if duplicate_count > 0:
            success_msg += f" ({duplicate_count} duplicates skipped)"
        
        await interaction.response.send_message(success_msg, ephemeral=True)
        
    except UnicodeDecodeError:
        await interaction.response.send_message("❌ Could not read file. Please ensure it's a valid UTF-8 text file.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error processing file: {str(e)}", ephemeral=True)

@bot.tree.command(name='bulk_emails', description='(Admin) Add multiple emails from a text file')
async def bulk_emails(interaction: discord.Interaction, file: discord.Attachment):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    if not file.filename.endswith('.txt'):
        return await interaction.response.send_message("❌ Please upload a .txt file.", ephemeral=True)
    
    if file.size > 1024 * 1024:  # 1MB
        return await interaction.response.send_message("❌ File too large. Maximum size is 1MB.", ephemeral=True)
    
    try:
        file_content = await file.read()
        text_content = file_content.decode('utf-8')
        
        lines = text_content.strip().split('\n')
        emails_to_add = []
        invalid_lines = []
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            email = line.strip()
            
            if not email:
                invalid_lines.append(f"Line {i}: empty email")
                continue
            
            if '@' not in email or len(email) < 5:
                invalid_lines.append(f"Line {i}: '{email}' (invalid email format)")
                continue
            
            parts = email.split('@')
            if len(parts) != 2 or not parts[0] or not parts[1] or '.' not in parts[1]:
                invalid_lines.append(f"Line {i}: '{email}' (invalid email format)")
                continue
            
            emails_to_add.append(email)
        
        if invalid_lines:
            error_msg = "❌ Found invalid lines:\n" + "\n".join(invalid_lines[:10])
            if len(invalid_lines) > 10:
                error_msg += f"\n... and {len(invalid_lines) - 10} more errors"
            return await interaction.response.send_message(error_msg, ephemeral=True)
        
        if not emails_to_add:
            return await interaction.response.send_message("❌ No valid emails found in the file.", ephemeral=True)
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        added_count = 0
        duplicate_count = 0
        
        for email in emails_to_add:
            cur.execute("SELECT COUNT(*) FROM emails WHERE email = ?", (email,))
            exists = cur.fetchone()[0] > 0
            
            if exists:
                duplicate_count += 1
            else:
                cur.execute("INSERT INTO emails (email) VALUES (?)", (email,))
                added_count += 1
        
        conn.commit()
        conn.close()
        
        success_msg = f"✅ Successfully added {added_count} emails to the pool."
        if duplicate_count > 0:
            success_msg += f" ({duplicate_count} duplicates skipped)"
        
        await interaction.response.send_message(success_msg, ephemeral=True)
        
    except UnicodeDecodeError:
        await interaction.response.send_message("❌ Could not read file. Please ensure it's a valid UTF-8 text file.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error processing file: {str(e)}", ephemeral=True)

# REMOVE COMMANDS
@bot.tree.command(name='remove_card', description='(Admin) Remove a card from the pool')
async def remove_card(interaction: discord.Interaction, number: str, cvv: str):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM cards WHERE number = ? AND cvv = ?", (number, cvv))
    deleted = cur.rowcount
    conn.commit()
    conn.close()

    if deleted:
        await interaction.response.send_message(f"✅ Removed card ending in {number[-4:]}.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No matching card found in the pool.", ephemeral=True)

@bot.tree.command(name='remove_email', description='(Admin) Remove an email from the pool')
async def remove_email(interaction: discord.Interaction, email: str):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM emails WHERE email = ?", (email,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()

    if deleted:
        await interaction.response.send_message(f"✅ Removed email `{email}` from the pool.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No matching email found in the pool.", ephemeral=True)

# LOGGING COMMANDS
@bot.tree.command(name='full_logs', description='(Admin) Print recent command logs with full email and command output')
@app_commands.describe(count="Number of recent logs to retrieve (default: 5, max: 50)")
async def full_logs(interaction: discord.Interaction, count: int = 5):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    if count < 1:
        return await interaction.response.send_message("❌ Count must be at least 1.", ephemeral=True)
    if count > 50:
        return await interaction.response.send_message("❌ Maximum count is 50.", ephemeral=True)
    
    logs = get_full_logs(count)
    if not logs:
        return await interaction.response.send_message("❌ No logs found.", ephemeral=True)
    
    # Format the output
    output_lines = []
    for i, log in enumerate(logs, 1):
        email = log.get('email_used', 'N/A')
        command = log.get('command_output', 'N/A')
        
        output_lines.append(f"{i}. email used: {email}")
        output_lines.append(f"   order command: {command}")
        output_lines.append("")  # Empty line for spacing
    
    output_text = "\n".join(output_lines)
    
    # Check if output is too long for Discord message
    if len(output_text) > 1800:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(f"Recent {len(logs)} Full Command Logs\n")
            f.write("=" * 50 + "\n\n")
            f.write(output_text)
            temp_file_path = f.name
        
        try:
            with open(temp_file_path, 'rb') as f:
                discord_file = discord.File(f, filename=f"full_logs_{count}.txt")
                await interaction.response.send_message(
                    f"📄 **Recent {len(logs)} Full Command Logs** (sent as file due to length)",
                    file=discord_file,
                    ephemeral=True
                )
        finally:
            try:
                os.unlink(temp_file_path)
            except:
                pass
    else:
        formatted_output = f"📋 **Recent {len(logs)} Full Command Logs**\n```\n{output_text}\n```"
        await interaction.response.send_message(formatted_output, ephemeral=True)

@bot.tree.command(name='print_logs', description='(Admin) Print recent command logs with email and card digits 9-16')
@app_commands.describe(count="Number of recent logs to retrieve (default: 10, max: 100)")
async def print_logs(interaction: discord.Interaction, count: int = 10):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    if count < 1:
        return await interaction.response.send_message("❌ Count must be at least 1.", ephemeral=True)
    if count > 100:
        return await interaction.response.send_message("❌ Maximum count is 100.", ephemeral=True)
    
    # Retrieve recent logs
    logs = get_recent_logs(count)
    if not logs:
        return await interaction.response.send_message("❌ No logs found.", ephemeral=True)
    
    # Format the output
    output_lines = []
    for log in logs:
        email = log.get('email_used', 'N/A')
        
        digits_9_16 = log.get('card_digits_9_16')
        if digits_9_16 and len(digits_9_16) == 8:
            formatted_digits = f"{digits_9_16[:4]}-{digits_9_16[4:]}"
        else:
            formatted_digits = "N/A"
        
        output_lines.append(f"{email} | {formatted_digits}")
    
    output_text = "\n".join(output_lines)
    
    # Check if output is too long for Discord message
    if len(output_text) > 1800:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(f"Recent {len(logs)} Command Logs\n")
            f.write("=" * 40 + "\n\n")
            f.write("Email | Card Digits 9-16\n")
            f.write("-" * 40 + "\n")
            f.write(output_text)
            temp_file_path = f.name
        
        try:
            with open(temp_file_path, 'rb') as f:
                discord_file = discord.File(f, filename=f"recent_logs_{count}.txt")
                await interaction.response.send_message(
                    f"📄 **Recent {len(logs)} Command Logs** (sent as file due to length)",
                    file=discord_file,
                    ephemeral=True
                )
        finally:
            try:
                os.unlink(temp_file_path)
            except:
                pass
    else:
        formatted_output = f"📋 **Recent {len(logs)} Command Logs**\n```\nEmail | Card Digits 9-16\n{'-' * 40}\n{output_text}\n```"
        await interaction.response.send_message(formatted_output, ephemeral=True)

@bot.tree.command(name='log_stats', description='(Admin) View command logging statistics')
@app_commands.describe(month="Month in YYYYMM format (e.g., 202405). Leave blank for current month.")
async def log_stats(interaction: discord.Interaction, month: str = None):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    if month is None:
        month = datetime.now().strftime('%Y%m')

    stats = get_log_stats(month)
    if "error" in stats:
        return await interaction.response.send_message(f"❌ {stats['error']}", ephemeral=True)

    stats_text = f"""📊 **Command Statistics for {month}**

**Total Commands:** {stats['total_commands']}
**Unique Emails Used:** {len(stats['emails_used'])}
**Unique Cards Used:** {len(stats['cards_used'])}

**Commands by Type:**"""
    for cmd_type, count in stats['command_types'].items():
        stats_text += f"\n  • {cmd_type}: {count}"

    stats_text += f"\n\n**Emails Used:** {', '.join(list(stats['emails_used']))}"
    stats_text += f"\n**Card Digits 9-12 Used:** {', '.join(list(stats['cards_used']))}"

    if stats['date_range']['start']:
        stats_text += f"\n**Date Range:** {stats['date_range']['start'][:10]} to {stats['date_range']['end'][:10]}"

    await interaction.response.send_message(stats_text, ephemeral=True)

@bot.tree.command(name='payments', description='Display payment methods')
async def payments(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Prin's Payments",
        description="Select which payment method you would like to use!",
        color=0x9932cc  # Purple color for the main embed
    )
    
    view = PaymentView()
    await interaction.response.send_message(embed=embed, view=view)

# Run the bot
if __name__ == '__main__':
    if not BOT_TOKEN:
        print("❌ Missing BOT_TOKEN in .env file")
        exit(1)
    
    print("🚀 Starting Discord bot...")
    print(f"🔓 Opener channel: {OPENER_CHANNEL_ID or 'Not configured'}")
    print(f"👑 Owner ID: {OWNER_ID or 'Not configured'}")
    
    bot.run(BOT_TOKEN)
