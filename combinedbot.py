import os
import time
import json
import csv
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from discord.errors import HTTPException
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Dict, Any, Optional, Tuple
import tempfile

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None
POINTS_CHANNEL_ID = int(os.getenv('POINTS_CHANNEL_ID')) if os.getenv('POINTS_CHANNEL_ID') else None
OPENER_CHANNEL_ID = int(os.getenv('OPENER_CHANNEL_ID')) if os.getenv('OPENER_CHANNEL_ID') else None
ROLE_PING_ID = os.getenv('ROLE_PING_ID', '1352022044614590494')
VIP_ROLE_ID = os.getenv('VIP_ROLE_ID', '1371247728646033550')
ORDER_CHANNEL_MENTION = os.getenv('ORDER_CHANNEL_MENTION', '<#1350935337269985334>')

# Constants for card formatting
EXP_MONTH = '06'
EXP_YEAR = '30'
ZIP_CODE = '19104'

# Database paths
DB_PATH = Path(__file__).parent / 'data' / 'pool.db'
POINTS_DB_PATH = Path(__file__).parent / 'data' / 'points.db'
LOGS_DIR = Path(__file__).parent / 'logs'

# Rate limiting for channel renames
rename_history = deque()

class CombinedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix='!', intents=intents)
        
        # Initialize databases
        self.init_databases()
        
        # Ensure logs directory exists
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def init_databases(self):
        """Initialize both pool and points databases"""
        # Create data directory
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize pool database (cards/emails)
        self.init_pool_db()
        
        # Initialize points database
        self.init_points_db()

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

    def init_points_db(self):
        """Initialize the points database"""
        conn = sqlite3.connect(POINTS_DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS points (
                user_id TEXT PRIMARY KEY,
                points INTEGER DEFAULT 0
            )
        ''')

        conn.commit()
        conn.close()

    # Database helper methods
    def get_and_remove_card(self) -> Optional[Tuple[str, str]]:
        """Fetch the oldest card and remove it from the database"""
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

    def get_and_remove_email(self) -> Optional[str]:
        """Fetch the oldest email and remove it from the database"""
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

    def get_user_points(self, user_id: str) -> int:
        """Get points for a user"""
        conn = sqlite3.connect(POINTS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT points FROM points WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0

    def set_user_points(self, user_id: str, points: int):
        """Set points for a user"""
        conn = sqlite3.connect(POINTS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''INSERT OR REPLACE INTO points (user_id, points) VALUES (?, ?)''', 
                      (user_id, points))
        conn.commit()
        conn.close()

    def add_user_points(self, user_id: str, points: int = 1) -> int:
        """Add points to a user and return new total"""
        current = self.get_user_points(user_id)
        new_total = current + points
        self.set_user_points(user_id, new_total)
        return new_total

    def get_leaderboard(self, limit: int = 10) -> list:
        """Get top users by points"""
        conn = sqlite3.connect(POINTS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, points FROM points ORDER BY points DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def clear_all_points(self):
        """Clear all points"""
        conn = sqlite3.connect(POINTS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM points')
        conn.commit()
        conn.close()

    # Logging functionality
    def log_command_output(self, command_type: str, user_id: int, username: str, 
                          channel_id: int, guild_id: int, command_output: str,
                          tip_amount: str = None, card_used: tuple = None, 
                          email_used: str = None, additional_data: Dict[str, Any] = None):
        """Log command output to multiple formats"""
        timestamp = datetime.now()
        
        # Extract card digits
        card_digits_9_12 = None
        card_digits_9_16 = None
        card_full = None
        if card_used:
            card_number, card_cvv = card_used
            card_full = f"{card_number} CVV:{card_cvv}"
            if len(card_number) >= 12:
                card_digits_9_12 = card_number[8:12]
            if len(card_number) >= 16:
                card_digits_9_16 = card_number[8:16]
        
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "command_type": command_type,
            "command_output": command_output,
            "email_used": email_used,
            "card_full": card_full,
            "card_digits_9_12": card_digits_9_12,
            "card_digits_9_16": card_digits_9_16,
            "additional_data": additional_data or {}
        }
        
        # Log to JSON file
        json_file = LOGS_DIR / f"commands_{timestamp.strftime('%Y%m')}.json"
        self._log_to_json(json_file, log_entry)
        
        # Log to CSV file
        csv_file = LOGS_DIR / f"commands_{timestamp.strftime('%Y%m')}.csv"
        self._log_to_csv(csv_file, log_entry)
        
        # Log to daily text file
        txt_file = LOGS_DIR / f"commands_{timestamp.strftime('%Y%m%d')}.txt"
        self._log_to_txt(txt_file, log_entry, timestamp)

    def _log_to_json(self, filename: Path, log_entry: Dict[str, Any]):
        """Append log entry to JSON file"""
        try:
            if filename.exists():
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = []
            
            data.append(log_entry)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error logging to JSON: {e}")

    def _log_to_csv(self, filename: Path, log_entry: Dict[str, Any]):
        """Append log entry to CSV file"""
        try:
            headers = ["timestamp", "command_type", "command_output", 
                      "email_used", "card_full", "card_digits_9_12"]
            
            file_exists = filename.exists()
            
            row_data = [
                log_entry["timestamp"],
                log_entry["command_type"],
                log_entry["command_output"],
                log_entry["email_used"],
                log_entry["card_full"],
                log_entry["card_digits_9_12"]
            ]
            
            with open(filename, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerow(row_data)
        except Exception as e:
            print(f"Error logging to CSV: {e}")

    def _log_to_txt(self, filename: Path, log_entry: Dict[str, Any], timestamp: datetime):
        """Append log entry to text file"""
        try:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"TIMESTAMP: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"COMMAND TYPE: {log_entry['command_type']}\n")
                if log_entry['email_used']:
                    f.write(f"EMAIL USED: {log_entry['email_used']}\n")
                if log_entry['card_full']:
                    f.write(f"CARD USED: {log_entry['card_full']}\n")
                if log_entry['card_digits_9_12']:
                    f.write(f"CARD DIGITS 9-12: {log_entry['card_digits_9_12']}\n")
                f.write(f"\nCOMMAND OUTPUT:\n{log_entry['command_output']}\n")
                f.write(f"{'='*80}\n")
        except Exception as e:
            print(f"Error logging to TXT: {e}")

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
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Points tracking functionality
    if POINTS_CHANNEL_ID and message.channel.id == POINTS_CHANNEL_ID:
        # Check for image attachments
        image_attachments = message.attachments
        has_images = any(att.content_type and att.content_type.startswith('image/') 
                        for att in image_attachments)
        
        if has_images:
            user_id = str(message.author.id)
            new_points = bot.add_user_points(user_id)
            
            point_word = 'point' if new_points == 1 else 'points'
            try:
                await message.reply(f"🎉 <@{message.author.id}> earned 1 point. They now have **{new_points}** {point_word} total.")
            except Exception as e:
                print(f"Failed to send points reply: {e}")

    # Channel opener functionality
    if OPENER_CHANNEL_ID and message.channel.id == OPENER_CHANNEL_ID:
        content = message.content.lower().strip()
        if content == "open":
            new_name = "open🟢🟢"
        elif content in ("close", "closed"):
            new_name = "closed🔴🔴"
        else:
            await bot.process_commands(message)
            return

        now = time.monotonic()
        # Remove entries older than 600 seconds
        while rename_history and now - rename_history[0] > 600:
            rename_history.popleft()

        if len(rename_history) >= 2:
            await message.channel.send(
                f"{message.author.mention} ⚠️ Rename limit reached (2 per 10 min). Try again later.",
                delete_after=10
            )
        else:
            try:
                await message.channel.edit(name=new_name)
                rename_history.append(now)

                if content == "open":
                    await message.channel.send(f"ZR Eats is now OPEN! <@&{ROLE_PING_ID}>")
                    embed = discord.Embed(
                        title="ZR Eats is now OPEN!",
                        description=f"We are now accepting orders! Click the order button in {ORDER_CHANNEL_MENTION} to place an order."
                    )
                    await message.channel.send(embed=embed)
                elif content in ("close", "closed"):
                    embed = discord.Embed(
                        title="ZR Eats is now CLOSED.",
                        description="We are currently closed. Please come back later when we're open for new orders! Do not open a ticket, you will not get a response."
                    )
                    await message.channel.send(embed=embed)

            except HTTPException as e:
                await message.channel.send(
                    f"{message.author.mention} ❌ Failed to rename channel: {e.status} {e.text}",
                    delete_after=10
                )

    await bot.process_commands(message)

# ORDER COMMANDS
@bot.tree.command(name='fusion_assist', description='Format a Fusion assist order')
@app_commands.choices(mode=[
    app_commands.Choice(name='Postmates', value='p'),
    app_commands.Choice(name='UberEats', value='u'),
])
@app_commands.describe(email="Optional: Add a custom email to the end of the command")
async def fusion_assist(interaction: discord.Interaction, mode: app_commands.Choice[str], email: str = None):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

    embed = await bot.fetch_order_embed(interaction.channel)
    if embed is None:
        return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

    info = bot.parse_fields(embed)
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
    tip_line = f"Tip: ${info['tip']}"

    bot.log_command_output(
        command_type="fusion_assist",
        user_id=interaction.user.id,
        username=str(interaction.user),
        channel_id=interaction.channel.id,
        guild_id=interaction.guild.id if interaction.guild else None,
        command_output=command,
        tip_amount=info['tip'],
        card_used=card,
        email_used=email,
        additional_data={"mode": mode.value, "parsed_fields": info, "custom_email": email}
    )

    # Format output with email if used
    output_message = f"```{command}```\n{tip_line}"
    if email:
        output_message += f"\n**Email used:** `{email}`"
    
    # Add warning if last card was used
    if was_last_card:
        output_message += f"\n⚠️ **Warning: Card pool is now empty! Add more cards with `/add_card` or `/bulk_cards`**"
    
    await interaction.response.send_message(output_message, ephemeral=True)

@bot.tree.command(name='fusion_order', description='Format a Fusion order with email')
async def fusion_order(interaction: discord.Interaction):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

    embed = await bot.fetch_order_embed(interaction.channel)
    if embed is None:
        return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

    info = bot.parse_fields(embed)
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
    tip_line = f"Tip: ${info['tip']}"

    bot.log_command_output(
        command_type="fusion_order",
        user_id=interaction.user.id,
        username=str(interaction.user),
        channel_id=interaction.channel.id,
        guild_id=interaction.guild.id if interaction.guild else None,
        command_output=command,
        tip_amount=info['tip'],
        card_used=card,
        email_used=email,
        additional_data={"parsed_fields": info}
    )

    # Format output with email
    output_message = f"```{command}```\n{tip_line}\n**Email used:** `{email}`"
    
    # Add warnings if pools are empty
    warnings = []
    if was_last_card:
        warnings.append("⚠️ **Card pool is now empty!** Add more cards with `/add_card` or `/bulk_cards`")
    if was_last_email:
        warnings.append("⚠️ **Email pool is now empty!** Add more emails with `/add_email` or `/bulk_emails`")
    
    if warnings:
        output_message += "\n\n" + "\n".join(warnings)
    
    await interaction.response.send_message(output_message, ephemeral=True)

@bot.tree.command(name='wool_order', description='Format a Wool order')
async def wool_order(interaction: discord.Interaction):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

    embed = await bot.fetch_order_embed(interaction.channel)
    if embed is None:
        return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

    info = bot.parse_fields(embed)
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

    command = f"{info['link']},{number},{EXP_MONTH}/{EXP_YEAR},{cvv},{ZIP_CODE},{email}"
    tip_line = f"Tip: ${info['tip']}"

    bot.log_command_output(
        command_type="wool_order",
        user_id=interaction.user.id,
        username=str(interaction.user),
        channel_id=interaction.channel.id,
        guild_id=interaction.guild.id if interaction.guild else None,
        command_output=command,
        tip_amount=info['tip'],
        card_used=card,
        email_used=email,
        additional_data={"parsed_fields": info}
    )

    # Format output with email
    output_message = f"```{command}```\n{tip_line}\n**Email used:** `{email}`"
    
    # Add warnings if pools are empty
    warnings = []
    if was_last_card:
        warnings.append("⚠️ **Card pool is now empty!** Add more cards with `/add_card` or `/bulk_cards`")
    if was_last_email:
        warnings.append("⚠️ **Email pool is now empty!** Add more emails with `/add_email` or `/bulk_emails`")
    
    if warnings:
        output_message += "\n\n" + "\n".join(warnings)
    
    await interaction.response.send_message(output_message, ephemeral=True)

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

# POINTS COMMANDS
@bot.tree.command(name='setpoints', description='(Admin) Set a user\'s points')
@app_commands.describe(user="The user to set points for", points="Number of points to set")
async def setpoints(interaction: discord.Interaction, user: discord.User, points: int):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    
    bot.set_user_points(str(user.id), points)
    await interaction.response.send_message(f"🔧 Set <@{user.id}>'s points to **{points}**.", ephemeral=True)

@bot.tree.command(name='checkpoints', description='Show your current point total')
@app_commands.describe(user="Optional: user to check points for")
async def checkpoints(interaction: discord.Interaction, user: discord.User = None):
    target_user = user or interaction.user
    if target_user.id != interaction.user.id and not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You do not have permission to check others' points.", ephemeral=True)
    
    points = bot.get_user_points(str(target_user.id))
    plural = 'point' if points == 1 else 'points'
    mention = 'You have' if target_user.id == interaction.user.id else f'<@{target_user.id}> has'
    await interaction.response.send_message(f"{mention} **{points}** {plural}.", ephemeral=True)

@bot.tree.command(name='leaderboard', description='Show top point earners')
@app_commands.describe(limit="Number of users to display (default 10)")
async def leaderboard(interaction: discord.Interaction, limit: int = 10):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You do not have permission to view the leaderboard.", ephemeral=True)
    
    entries = bot.get_leaderboard(limit)
    if not entries:
        return await interaction.response.send_message("No points have been recorded yet.", ephemeral=True)
    
    lines = []
    for i, (user_id, points) in enumerate(entries, 1):
        word = 'point' if points == 1 else 'points'
        lines.append(f"{i}. <@{user_id}> — {points} {word}")
    
    await interaction.response.send_message('\n'.join(lines), ephemeral=True)

@bot.tree.command(name='clearpoints', description='(Admin) Clear points for a user or all users')
@app_commands.describe(user="Optional: user to clear points for")
async def clearpoints(interaction: discord.Interaction, user: discord.User = None):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You do not have permission to clear points.", ephemeral=True)
    
    if user:
        bot.set_user_points(str(user.id), 0)
        return await interaction.response.send_message(f"✅ Cleared points for <@{user.id}>.", ephemeral=True)
    else:
        bot.clear_all_points()
        return await interaction.response.send_message("✅ Cleared points for all users.", ephemeral=True)

@bot.tree.command(name='redeem', description='(Admin) Redeem points for a reward')
@app_commands.choices(reward=[
    app_commands.Choice(name='Free Order', value='Free Order'),
    app_commands.Choice(name='Perm Fee', value='Perm Fee'),
])
@app_commands.describe(user="The user to redeem points for", reward="Reward to redeem")
async def redeem(interaction: discord.Interaction, user: discord.User, reward: app_commands.Choice[str]):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    
    user_id = str(user.id)
    current_points = bot.get_user_points(user_id)
    
    if current_points < 10:
        return await interaction.response.send_message(f"❌ <@{user.id}> needs at least 10 points to redeem.", ephemeral=True)
    
    new_points = current_points - 10
    bot.set_user_points(user_id, new_points)

    reply_message = f"✅ Redeemed **{reward.value}** for <@{user.id}>. They now have **{new_points}** points."
    
    if reward.value == 'Perm Fee':
        try:
            guild_member = await interaction.guild.members.fetch(user.id)
            vip_role = interaction.guild.get_role(int(VIP_ROLE_ID))
            if vip_role:
                await guild_member.add_roles(vip_role)
                reply_message += ' They have been granted the VIP role.'
            else:
                reply_message += ' (VIP role not found - check VIP_ROLE_ID)'
        except Exception as e:
            reply_message += f' (Failed to add VIP role: {e})'
    
    return await interaction.response.send_message(reply_message, ephemeral=True)

# BACKFILL COMMAND
@bot.tree.command(name='backfill', description='(Admin) Backfill points from existing messages in the channel')
async def backfill(interaction: discord.Interaction):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
    
    if not POINTS_CHANNEL_ID:
        return await interaction.response.send_message("❌ POINTS_CHANNEL_ID not configured.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    
    channel = bot.get_channel(POINTS_CHANNEL_ID)
    if not channel or not hasattr(channel, 'history'):
        return await interaction.followup.send("❌ Points channel not found or unsupported.", ephemeral=True)
    
    # Check bot permissions
    perms = channel.permissions_for(interaction.guild.me)
    if not perms.view_channel or not perms.read_message_history:
        return await interaction.followup.send("❌ I need View Channel and Read Message History permissions to backfill this channel.", ephemeral=True)
    
    processed = 0
    last_id = None
    
    try:
        while True:
            options = {'limit': 100}
            if last_id:
                options['before'] = discord.Object(last_id)
            
            batch = []
            async for message in channel.history(**options):
                batch.append(message)
            
            if not batch:
                break
            
            for message in batch:
                if message.author.bot:
                    continue
                
                # Check for image attachments
                has_images = any(att.content_type and att.content_type.startswith('image/') 
                               for att in message.attachments)
                
                if has_images:
                    user_id = str(message.author.id)
                    bot.add_user_points(user_id, 1)
            
            processed += len(batch)
            last_id = batch[-1].id
            
            # Rate limiting
            await interaction.edit_original_response(content=f"Processing... {processed} messages checked")
            await asyncio.sleep(0.5)
            
    except Exception as e:
        return await interaction.followup.send(f"❌ Error during backfill: {e}", ephemeral=True)
    
    await interaction.followup.send(f"✅ Processed **{processed}** messages and updated points.", ephemeral=True)

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
@bot.tree.command(name='print_logs', description='(Admin) Print recent command logs with email and card digits 9-16')
@app_commands.describe(count="Number of recent logs to retrieve (default: 10, max: 100)")
async def print_logs(interaction: discord.Interaction, count: int = 10):
    if not bot.owner_only(interaction):
        return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
    
    if count < 1:
        return await interaction.response.send_message("❌ Count must be at least 1.", ephemeral=True)
    if count > 100:
        return await interaction.response.send_message("❌ Maximum count is 100.", ephemeral=True)
    
    # Get recent logs from JSON file
    current_month = datetime.now().strftime('%Y%m')
    json_file = LOGS_DIR / f"commands_{current_month}.json"
    
    if not json_file.exists():
        return await interaction.response.send_message("❌ No logs found.", ephemeral=True)
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sorted_data = sorted(data, key=lambda x: x["timestamp"], reverse=True)
        logs = sorted_data[:count]
    except Exception as e:
        return await interaction.response.send_message(f"❌ Error reading logs: {e}", ephemeral=True)
    
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
    
    json_file = LOGS_DIR / f"commands_{month}.json"
    
    if not json_file.exists():
        return await interaction.response.send_message(f"❌ No log file found for month {month}.", ephemeral=True)
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stats = {
            "total_commands": len(data),
            "command_types": {},
            "emails_used": set(),
            "cards_used": set(),
            "date_range": {"start": None, "end": None}
        }
        
        for entry in data:
            cmd_type = entry["command_type"]
            stats["command_types"][cmd_type] = stats["command_types"].get(cmd_type, 0) + 1
            
            if entry.get("email_used"):
                stats["emails_used"].add(entry["email_used"])
            
            if entry.get("card_digits_9_12"):
                stats["cards_used"].add(entry["card_digits_9_12"])
            
            entry_date = entry["timestamp"]
            if stats["date_range"]["start"] is None or entry_date < stats["date_range"]["start"]:
                stats["date_range"]["start"] = entry_date
            if stats["date_range"]["end"] is None or entry_date > stats["date_range"]["end"]:
                stats["date_range"]["end"] = entry_date
        
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
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error reading log file: {e}", ephemeral=True)

# Import asyncio for backfill
import asyncio

# Run the bot
if __name__ == '__main__':
    if not BOT_TOKEN:
        print("❌ Missing BOT_TOKEN in .env file")
        exit(1)
    
    print("🚀 Starting combined Discord bot...")
    print(f"📍 Points channel: {POINTS_CHANNEL_ID or 'Not configured'}")
    print(f"🔓 Opener channel: {OPENER_CHANNEL_ID or 'Not configured'}")
    print(f"👑 Owner ID: {OWNER_ID or 'Not configured'}")
    
    bot.run(BOT_TOKEN)