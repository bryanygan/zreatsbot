import os
import sqlite3
import tempfile
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from logging_utils import log_command_output, get_recent_logs, get_full_logs, get_log_stats
from ..utils.card_validator import CardValidator
from ..utils.helpers import owner_only

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'pool.db')


def setup(bot: commands.Bot):
    @bot.tree.command(name='add_card', description='(Admin) Add a card to the pool')
    async def add_card(interaction: discord.Interaction, number: str, cvv: str):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        is_valid_card, card_error = CardValidator.validate_card_number(number)
        if not is_valid_card:
            return await interaction.response.send_message(f"❌ Invalid card number: {card_error}", ephemeral=True)

        is_valid_cvv, cvv_error = CardValidator.validate_cvv(cvv, number)
        if not is_valid_cvv:
            return await interaction.response.send_message(f"❌ Invalid CVV: {cvv_error}", ephemeral=True)

        cleaned_number = CardValidator.format_card_number(number)
        cleaned_cvv = cvv.strip()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cards WHERE number = ? AND cvv = ?", (cleaned_number, cleaned_cvv))
        exists = cur.fetchone()[0] > 0

        if exists:
            conn.close()
            return await interaction.response.send_message(f"❌ Card ending in {cleaned_number[-4:]} already exists in pool.", ephemeral=True)

        cur.execute("INSERT INTO cards (number, cvv) VALUES (?, ?)", (cleaned_number, cleaned_cvv))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"✅ Card ending in {cleaned_number[-4:]} added successfully.", ephemeral=True)

    @bot.tree.command(name='add_email', description='(Admin) Add an email to the pool')
    @app_commands.describe(top="Add this email to the top of the pool so it's used first")
    async def add_email(interaction: discord.Interaction, email: str, top: bool = False):
        if not owner_only(interaction):
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
        if not owner_only(interaction):
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
        if not owner_only(interaction):
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

    @bot.tree.command(name='bulk_cards', description='(Admin) Add multiple cards from a text file')
    async def bulk_cards(interaction: discord.Interaction, file: discord.Attachment):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if not file.filename.endswith('.txt'):
            return await interaction.response.send_message("❌ Please upload a .txt file.", ephemeral=True)

        if file.size > 1024 * 1024:
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

                raw_number, raw_cvv = parts[0].strip(), parts[1].strip()

                if not raw_number or not raw_cvv:
                    invalid_lines.append(f"Line {i}: '{line}' (empty card number or CVV)")
                    continue

                is_valid_card, card_error = CardValidator.validate_card_number(raw_number)
                if not is_valid_card:
                    invalid_lines.append(f"Line {i}: '{line}' - {card_error}")
                    continue

                is_valid_cvv, cvv_error = CardValidator.validate_cvv(raw_cvv, raw_number)
                if not is_valid_cvv:
                    invalid_lines.append(f"Line {i}: '{line}' - {cvv_error}")
                    continue

                cleaned_number = CardValidator.format_card_number(raw_number)
                cleaned_cvv = raw_cvv.strip()

                cards_to_add.append((cleaned_number, cleaned_cvv))

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
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if not file.filename.endswith('.txt'):
            return await interaction.response.send_message("❌ Please upload a .txt file.", ephemeral=True)

        if file.size > 1024 * 1024:
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

    @bot.tree.command(name='remove_card', description='(Admin) Remove a card from the pool')
    async def remove_card(interaction: discord.Interaction, number: str, cvv: str):
        if not owner_only(interaction):
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
        if not owner_only(interaction):
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

    @bot.tree.command(name='full_logs', description='(Admin) Print recent command logs with full email and command output')
    @app_commands.describe(count="Number of recent logs to retrieve (default: 5, max: 50)")
    async def full_logs_cmd(interaction: discord.Interaction, count: int = 5):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if count < 1:
            return await interaction.response.send_message("❌ Count must be at least 1.", ephemeral=True)
        if count > 50:
            return await interaction.response.send_message("❌ Maximum count is 50.", ephemeral=True)

        logs = get_full_logs(count)
        if not logs:
            return await interaction.response.send_message("❌ No logs found.", ephemeral=True)

        output_lines = []
        for i, log in enumerate(logs, 1):
            email = log.get('email_used', 'N/A')
            command = log.get('command_output', 'N/A')

            output_lines.append(f"{i}. email used: {email}")
            output_lines.append(f"   order command: {command}")
            output_lines.append("")

        output_text = "\n".join(output_lines)

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
                except Exception:
                    pass
        else:
            formatted_output = f"📋 **Recent {len(logs)} Full Command Logs**\n```\n{output_text}\n```"
            await interaction.response.send_message(formatted_output, ephemeral=True)

    @bot.tree.command(name='print_logs', description='(Admin) Print recent command logs with email and card digits 9-16')
    @app_commands.describe(count="Number of recent logs to retrieve (default: 10, max: 100)")
    async def print_logs(interaction: discord.Interaction, count: int = 10):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if count < 1:
            return await interaction.response.send_message("❌ Count must be at least 1.", ephemeral=True)
        if count > 100:
            return await interaction.response.send_message("❌ Maximum count is 100.", ephemeral=True)

        logs = get_recent_logs(count)
        if not logs:
            return await interaction.response.send_message("❌ No logs found.", ephemeral=True)

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
                except Exception:
                    pass
        else:
            formatted_output = f"📋 **Recent {len(logs)} Command Logs**\n```\nEmail | Card Digits 9-16\n{'-' * 40}\n{output_text}\n```"
            await interaction.response.send_message(formatted_output, ephemeral=True)

    @bot.tree.command(name='log_stats', description='(Admin) View command logging statistics')
    @app_commands.describe(month="Month in YYYYMM format (e.g., 202405). Leave blank for current month.")
    async def log_stats_cmd(interaction: discord.Interaction, month: str = None):
        if not owner_only(interaction):
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
