import os
import sqlite3
import tempfile
import csv
import io
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from logging_utils import log_command_output, get_recent_logs, get_full_logs, get_log_stats
from ..utils.card_validator import CardValidator
from ..utils.helpers import owner_only
import db

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

        conn = db.acquire_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cards WHERE number = ? AND cvv = ?", (cleaned_number, cleaned_cvv))
        exists = cur.fetchone()[0] > 0

        if exists:
            db.release_connection(conn)
            return await interaction.response.send_message(f"❌ Card ending in {cleaned_number[-4:]} already exists in pool.", ephemeral=True)

        cur.execute("INSERT INTO cards (number, cvv) VALUES (?, ?)", (cleaned_number, cleaned_cvv))
        conn.commit()
        db.release_connection(conn)

        await interaction.response.send_message(f"✅ Card ending in {cleaned_number[-4:]} added successfully.", ephemeral=True)

    @bot.tree.command(name='add_email', description='(Admin) Add an email to the specified pool')
    @app_commands.describe(
        email="Email address to add to the pool",
        pool="Email pool to add to (main, pump_20off25, pump_25off)",
        top="Add this email to the top of the pool so it's used first"
    )
    @app_commands.choices(pool=[
        app_commands.Choice(name='Main Pool', value='main'),
        app_commands.Choice(name='Pump 20off25', value='pump_20off25'),
        app_commands.Choice(name='Pump 25off', value='pump_25off'),
    ])
    async def add_email(interaction: discord.Interaction, email: str, pool: app_commands.Choice[str] = None, top: bool = False):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        pool_type = pool.value if pool else 'main'
        
        try:
            success = db.add_email_to_pool(email, pool_type, top)
            if success:
                position = "top of" if top else "end of"
                await interaction.response.send_message(f"✅ Email `{email}` added to {position} **{pool_type}** pool.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Email `{email}` already exists in **{pool_type}** pool.", ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)

    @bot.tree.command(name='read_cards', description='(Admin) List all cards in the pool')
    async def read_cards(interaction: discord.Interaction):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        conn = db.acquire_connection()
        cur = conn.cursor()
        cur.execute("SELECT number, cvv FROM cards")
        rows = cur.fetchall()
        db.release_connection(conn)

        if not rows:
            return await interaction.response.send_message("✅ No cards in the pool.", ephemeral=True)

        lines = [f"{num},{cvv}" for num, cvv in rows]
        payload = "Cards in pool:\n" + "\n".join(lines)
        
        # Check if the payload is too long
        if len(payload) > 1900:
            # Send as a file instead
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(payload)
                temp_file_path = f.name
            
            try:
                with open(temp_file_path, 'rb') as f:
                    discord_file = discord.File(f, filename="cards_pool.txt")
                    await interaction.response.send_message(
                        f"📄 **Cards in pool** ({len(rows)} cards - sent as file due to length)",
                        file=discord_file,
                        ephemeral=True
                    )
            finally:
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
        else:
            await interaction.response.send_message(f"```{payload}```", ephemeral=True)

    @bot.tree.command(name='read_emails', description='(Admin) List all emails in the specified pool')
    @app_commands.describe(pool="Email pool to read from (leave blank to see all pools)")
    @app_commands.choices(pool=[
        app_commands.Choice(name='Main Pool', value='main'),
        app_commands.Choice(name='Pump 20off25', value='pump_20off25'),
        app_commands.Choice(name='Pump 25off', value='pump_25off'),
    ])
    async def read_emails(interaction: discord.Interaction, pool: app_commands.Choice[str] = None):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if pool:
            # Show specific pool
            pool_type = pool.value
            try:
                emails = db.get_emails_in_pool(pool_type)
                if not emails:
                    return await interaction.response.send_message(f"✅ No emails in **{pool_type}** pool.", ephemeral=True)
                
                payload = f"Emails in **{pool_type}** pool ({len(emails)} total):\n" + "\n".join(emails)
                
                # Check if the payload is too long
                if len(payload) > 1900:
                    # Send as a file instead
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                        f.write(payload)
                        temp_file_path = f.name
                    
                    try:
                        with open(temp_file_path, 'rb') as f:
                            discord_file = discord.File(f, filename=f"{pool_type}_emails.txt")
                            await interaction.response.send_message(
                                f"📄 **{pool_type} pool emails** ({len(emails)} emails - sent as file due to length)",
                                file=discord_file,
                                ephemeral=True
                            )
                    finally:
                        try:
                            os.unlink(temp_file_path)
                        except Exception:
                            pass
                else:
                    await interaction.response.send_message(f"```{payload}```", ephemeral=True)
            except ValueError as e:
                await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        else:
            # Show all pools
            all_emails = db.get_all_emails_with_pools()
            if not all_emails:
                return await interaction.response.send_message("✅ No emails in any pool.", ephemeral=True)
            
            # Group by pool type
            pools = {}
            for email, pool_type in all_emails:
                if pool_type not in pools:
                    pools[pool_type] = []
                pools[pool_type].append(email)
            
            output_lines = []
            for pool_type in db.VALID_EMAIL_POOLS:
                emails = pools.get(pool_type, [])
                output_lines.append(f"**{pool_type}** pool ({len(emails)} emails):")
                if emails:
                    output_lines.extend([f"  {email}" for email in emails[:10]])
                    if len(emails) > 10:
                        output_lines.append(f"  ... and {len(emails) - 10} more")
                else:
                    output_lines.append("  (empty)")
                output_lines.append("")
            
            payload = "\n".join(output_lines)
            
            if len(payload) > 1800:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                    f.write("All Email Pools\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(payload)
                    temp_file_path = f.name
                try:
                    with open(temp_file_path, 'rb') as f:
                        discord_file = discord.File(f, filename="all_email_pools.txt")
                        await interaction.response.send_message(
                            f"📄 **All Email Pools** (sent as file due to length)",
                            file=discord_file,
                            ephemeral=True
                        )
                finally:
                    try:
                        os.unlink(temp_file_path)
                    except Exception:
                        pass
            else:
                await interaction.response.send_message(f"```{payload}```", ephemeral=True)

    @bot.tree.command(name='bulk_cards', description='(Admin) Add multiple cards from a text or CSV file')
    async def bulk_cards(interaction: discord.Interaction, file: discord.Attachment):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        # Check file extension - now supports both .txt and .csv
        if not (file.filename.endswith('.txt') or file.filename.endswith('.csv')):
            return await interaction.response.send_message("❌ Please upload a .txt or .csv file.", ephemeral=True)

        if file.size > 1024 * 1024:
            return await interaction.response.send_message("❌ File too large. Maximum size is 1MB.", ephemeral=True)

        # DEFER THE RESPONSE IMMEDIATELY to prevent timeout
        await interaction.response.defer(ephemeral=True)

        try:
            file_content = await file.read()
            text_content = file_content.decode('utf-8')

            lines = text_content.strip().split('\n')
            cards_to_add = []
            invalid_lines = []
            
            # Detect if it's a CSV file
            is_csv = file.filename.endswith('.csv')

            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Skip header row for CSV files
                if is_csv and i == 1:
                    # Check if it looks like a header row
                    if 'Card Number' in line or 'card number' in line.lower():
                        continue

                if is_csv:
                    # Parse CSV format
                    # Split by comma but handle potential commas within quoted fields
                    reader = csv.reader(io.StringIO(line))
                    try:
                        parts = next(reader)
                    except:
                        invalid_lines.append(f"Line {i}: '{line}' (invalid CSV format)")
                        continue
                    
                    # Expected CSV format has card number at index 5 and CVV at index 8
                    if len(parts) < 9:
                        invalid_lines.append(f"Line {i}: '{line}' (insufficient columns for CSV format)")
                        continue
                    
                    raw_number = parts[5].strip()  # Card Number column
                    raw_cvv = parts[8].strip()     # Card CVV column
                else:
                    # Parse text format (original format: cardnum,cvv)
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
                return await interaction.followup.send(error_msg, ephemeral=True)

            if not cards_to_add:
                return await interaction.followup.send("❌ No valid cards found in the file.", ephemeral=True)

            conn = db.acquire_connection()
            cur = conn.cursor()

            added_count = 0
            duplicate_count = 0
            inserts = []

            for number, cvv in cards_to_add:
                cur.execute("SELECT COUNT(*) FROM cards WHERE number = ? AND cvv = ?", (number, cvv))
                exists = cur.fetchone()[0] > 0

                if exists:
                    duplicate_count += 1
                else:
                    inserts.append((number, cvv))
                    added_count += 1

            if inserts:
                cur.executemany("INSERT INTO cards (number, cvv) VALUES (?, ?)", inserts)

            conn.commit()
            db.release_connection(conn)

            success_msg = f"✅ Successfully added {added_count} cards to the pool."
            if duplicate_count > 0:
                success_msg += f" ({duplicate_count} duplicates skipped)"

            await interaction.followup.send(success_msg, ephemeral=True)

        except UnicodeDecodeError:
            await interaction.followup.send("❌ Could not read file. Please ensure it's a valid UTF-8 text file.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error processing file: {str(e)}", ephemeral=True)

    async def _process_bulk_emails(interaction: discord.Interaction, file: discord.Attachment, pool_type: str):
        """Helper function to process bulk email uploads for any pool"""
        
        if not file.filename.endswith('.txt'):
            return await interaction.response.send_message("❌ Please upload a .txt file.", ephemeral=True)

        if file.size > 1024 * 1024:
            return await interaction.response.send_message("❌ File too large. Maximum size is 1MB.", ephemeral=True)

        # DEFER THE RESPONSE IMMEDIATELY to prevent timeout
        await interaction.response.defer(ephemeral=True)

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
                return await interaction.followup.send(error_msg, ephemeral=True)

            if not emails_to_add:
                return await interaction.followup.send("❌ No valid emails found in the file.", ephemeral=True)

            # Use the database function to add emails with proper pool handling
            added_count = 0
            duplicate_count = 0

            for email in emails_to_add:
                try:
                    success = db.add_email_to_pool(email, pool_type, top=False)
                    if success:
                        added_count += 1
                    else:
                        duplicate_count += 1
                except ValueError as e:
                    return await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)

            success_msg = f"✅ Successfully added {added_count} emails to **{pool_type}** pool."
            if duplicate_count > 0:
                success_msg += f" ({duplicate_count} duplicates skipped)"

            await interaction.followup.send(success_msg, ephemeral=True)

        except UnicodeDecodeError:
            await interaction.followup.send("❌ Could not read file. Please ensure it's a valid UTF-8 text file.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error processing file: {str(e)}", ephemeral=True)

    @bot.tree.command(name='bulk_emails_main', description='(Admin) Add multiple emails to main pool from text file')
    async def bulk_emails_main(interaction: discord.Interaction, file: discord.Attachment):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
        await _process_bulk_emails(interaction, file, 'main')

    @bot.tree.command(name='bulk_emails_pump20', description='(Admin) Add multiple emails to pump_20off25 pool from text file')
    async def bulk_emails_pump20(interaction: discord.Interaction, file: discord.Attachment):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
        await _process_bulk_emails(interaction, file, 'pump_20off25')

    @bot.tree.command(name='bulk_emails_pump25', description='(Admin) Add multiple emails to pump_25off pool from text file')
    async def bulk_emails_pump25(interaction: discord.Interaction, file: discord.Attachment):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
        await _process_bulk_emails(interaction, file, 'pump_25off')

    @bot.tree.command(name='remove_card', description='(Admin) Remove a card from the pool')
    async def remove_card(interaction: discord.Interaction, number: str, cvv: str):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        conn = db.acquire_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM cards WHERE number = ? AND cvv = ?", (number, cvv))
        deleted = cur.rowcount
        conn.commit()
        db.release_connection(conn)

        if deleted:
            await interaction.response.send_message(f"✅ Removed card ending in {number[-4:]}.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No matching card found in the pool.", ephemeral=True)

    @bot.tree.command(name='remove_email', description='(Admin) Remove an email from specified pool')
    @app_commands.describe(
        email="Email address to remove",
        pool="Email pool to remove from (leave blank to remove from all pools)"
    )
    @app_commands.choices(pool=[
        app_commands.Choice(name='Main Pool', value='main'),
        app_commands.Choice(name='Pump 20off25', value='pump_20off25'),
        app_commands.Choice(name='Pump 25off', value='pump_25off'),
    ])
    async def remove_email(interaction: discord.Interaction, email: str, pool: app_commands.Choice[str] = None):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if pool:
            # Remove from specific pool
            pool_type = pool.value
            try:
                success = db.remove_email_from_pool(email, pool_type)
                if success:
                    await interaction.response.send_message(f"✅ Removed email `{email}` from **{pool_type}** pool.", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ Email `{email}` not found in **{pool_type}** pool.", ephemeral=True)
            except ValueError as e:
                await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        else:
            # Remove from all pools (legacy behavior)
            conn = db.acquire_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM emails WHERE email = ?", (email,))
            deleted = cur.rowcount
            conn.commit()
            db.release_connection(conn)

            if deleted:
                await interaction.response.send_message(f"✅ Removed email `{email}` from all pools ({deleted} instances).", ephemeral=True)
            else:
                await interaction.response.send_message("❌ No matching email found in any pool.", ephemeral=True)

    @bot.tree.command(name='remove_bulk_cards', description='(Admin) Remove multiple cards from pool using text file')
    async def remove_bulk_cards(interaction: discord.Interaction, file: discord.Attachment):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if not file.filename.endswith('.txt'):
            return await interaction.response.send_message("❌ Please upload a .txt file.", ephemeral=True)

        if file.size > 1024 * 1024:
            return await interaction.response.send_message("❌ File too large. Maximum size is 1MB.", ephemeral=True)

        # DEFER THE RESPONSE IMMEDIATELY to prevent timeout
        await interaction.response.defer(ephemeral=True)

        try:
            file_content = await file.read()
            text_content = file_content.decode('utf-8')

            lines = text_content.strip().split('\n')
            cards_to_remove = []
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

                # We still validate the format to ensure consistency
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

                cards_to_remove.append((cleaned_number, cleaned_cvv))

            if invalid_lines:
                error_msg = "❌ Found invalid lines:\n" + "\n".join(invalid_lines[:10])
                if len(invalid_lines) > 10:
                    error_msg += f"\n... and {len(invalid_lines) - 10} more errors"
                return await interaction.followup.send(error_msg, ephemeral=True)

            if not cards_to_remove:
                return await interaction.followup.send("❌ No valid cards found in the file.", ephemeral=True)

            conn = db.acquire_connection()
            cur = conn.cursor()

            removed_count = 0
            not_found_count = 0

            for number, cvv in cards_to_remove:
                cur.execute("DELETE FROM cards WHERE number = ? AND cvv = ?", (number, cvv))
                if cur.rowcount > 0:
                    removed_count += 1
                else:
                    not_found_count += 1

            conn.commit()
            db.release_connection(conn)

            success_msg = f"✅ Successfully removed {removed_count} cards from the pool."
            if not_found_count > 0:
                success_msg += f" ({not_found_count} cards not found in pool)"

            await interaction.followup.send(success_msg, ephemeral=True)

        except UnicodeDecodeError:
            await interaction.followup.send("❌ Could not read file. Please ensure it's a valid UTF-8 text file.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error processing file: {str(e)}", ephemeral=True)

    @bot.tree.command(name='remove_bulk_emails', description='(Admin) Remove multiple emails from pool using text file')
    @app_commands.describe(
        file="Text file containing emails to remove (one per line)",
        pool="Email pool to remove from (leave blank to remove from all pools)"
    )
    @app_commands.choices(pool=[
        app_commands.Choice(name='All Pools', value='all'),
        app_commands.Choice(name='Main Pool', value='main'),
        app_commands.Choice(name='Pump 20off25', value='pump_20off25'),
        app_commands.Choice(name='Pump 25off', value='pump_25off'),
    ])
    async def remove_bulk_emails(interaction: discord.Interaction, file: discord.Attachment, 
                                 pool: app_commands.Choice[str] = None):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)

        if not file.filename.endswith('.txt'):
            return await interaction.response.send_message("❌ Please upload a .txt file.", ephemeral=True)

        if file.size > 1024 * 1024:
            return await interaction.response.send_message("❌ File too large. Maximum size is 1MB.", ephemeral=True)

        # DEFER THE RESPONSE IMMEDIATELY to prevent timeout
        await interaction.response.defer(ephemeral=True)

        pool_type = pool.value if pool else 'all'

        try:
            file_content = await file.read()
            text_content = file_content.decode('utf-8')

            lines = text_content.strip().split('\n')
            emails_to_remove = []
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

                emails_to_remove.append(email)

            if invalid_lines:
                error_msg = "❌ Found invalid lines:\n" + "\n".join(invalid_lines[:10])
                if len(invalid_lines) > 10:
                    error_msg += f"\n... and {len(invalid_lines) - 10} more errors"
                return await interaction.followup.send(error_msg, ephemeral=True)

            if not emails_to_remove:
                return await interaction.followup.send("❌ No valid emails found in the file.", ephemeral=True)

            conn = db.acquire_connection()
            cur = conn.cursor()

            removed_count = 0
            not_found_count = 0
            pool_breakdown = {}

            if pool_type == 'all':
                # Remove from all pools
                for email in emails_to_remove:
                    cur.execute("SELECT pool_type FROM emails WHERE email = ?", (email,))
                    found_pools = cur.fetchall()
                    
                    if found_pools:
                        for (found_pool,) in found_pools:
                            if found_pool not in pool_breakdown:
                                pool_breakdown[found_pool] = 0
                            pool_breakdown[found_pool] += 1
                        
                        cur.execute("DELETE FROM emails WHERE email = ?", (email,))
                        removed_count += cur.rowcount
                    else:
                        not_found_count += 1
            else:
                # Remove from specific pool
                for email in emails_to_remove:
                    cur.execute("DELETE FROM emails WHERE email = ? AND pool_type = ?", (email, pool_type))
                    if cur.rowcount > 0:
                        removed_count += 1
                    else:
                        not_found_count += 1

            conn.commit()
            db.release_connection(conn)

            # Build success message
            if pool_type == 'all':
                success_msg = f"✅ Successfully removed {removed_count} emails from all pools."
                if pool_breakdown:
                    breakdown_str = ", ".join([f"{pool}: {count}" for pool, count in pool_breakdown.items()])
                    success_msg += f"\n📊 Breakdown: {breakdown_str}"
            else:
                success_msg = f"✅ Successfully removed {removed_count} emails from **{pool_type}** pool."
            
            if not_found_count > 0:
                if pool_type == 'all':
                    success_msg += f"\n⚠️ {not_found_count} emails not found in any pool"
                else:
                    success_msg += f"\n⚠️ {not_found_count} emails not found in **{pool_type}** pool"

            await interaction.followup.send(success_msg, ephemeral=True)

        except UnicodeDecodeError:
            await interaction.followup.send("❌ Could not read file. Please ensure it's a valid UTF-8 text file.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error processing file: {str(e)}", ephemeral=True)

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

    @bot.tree.command(name='toggle_payment', description='(Admin) Enable or disable any payment method button')
    @app_commands.describe(
        method="The payment method to toggle",
        enabled="True to show the button, False to hide it"
    )
    @app_commands.choices(method=[
        app_commands.Choice(name='Zelle', value='zelle'),
        app_commands.Choice(name='Venmo', value='venmo'),
        app_commands.Choice(name='PayPal', value='paypal'),
        app_commands.Choice(name='CashApp', value='cashapp'),
        app_commands.Choice(name='Crypto', value='crypto'),
    ])
    async def toggle_payment(interaction: discord.Interaction, method: app_commands.Choice[str], enabled: bool):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
        # Import the views module to access the toggle function
        from ..views import set_payment_enabled, is_payment_enabled, get_payment_methods_status
        
        # Set the new state
        success = set_payment_enabled(method.value, enabled)
        
        if not success:
            return await interaction.response.send_message("❌ Invalid payment method.", ephemeral=True)
        
        # Create response embed
        status = "enabled" if enabled else "disabled"
        color = 0x00D632 if enabled else 0xFF0000
        
        # Get emoji for each payment method
        emojis = {
            'zelle': '🏦',
            'venmo': '💙',
            'paypal': '💚',
            'cashapp': '💵',
            'crypto': '🪙'
        }
        
        embed = discord.Embed(
            title=f"{emojis.get(method.value, '💳')} {method.name} Toggle",
            description=f"{method.name} payment button has been **{status}**.",
            color=color
        )
        
        embed.add_field(
            name="Current Status",
            value=f"{'✅ Visible' if enabled else '❌ Hidden'}",
            inline=False
        )
        
        # Show status of all payment methods
        all_status = get_payment_methods_status()
        status_lines = []
        for payment_method, is_enabled in all_status.items():
            method_name = payment_method.capitalize()
            if payment_method == 'cashapp':
                method_name = 'CashApp'
            elif payment_method == 'paypal':
                method_name = 'PayPal'
            status_icon = '✅' if is_enabled else '❌'
            status_lines.append(f"{status_icon} {method_name}")
        
        embed.add_field(
            name="All Payment Methods",
            value="\n".join(status_lines),
            inline=False
        )
        
        embed.add_field(
            name="Effect",
            value="The change will apply to all new `/payments` commands.\nExisting payment messages will not be affected.",
            inline=False
        )
        
        embed.set_footer(text=f"Changed by {interaction.user}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='toggle_cashapp', description='(Admin) Enable or disable the CashApp payment button (legacy)')
    @app_commands.describe(enabled="True to show CashApp button, False to hide it")
    async def toggle_cashapp(interaction: discord.Interaction, enabled: bool):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
        
        # Import the views module to access the toggle function
        from ..views import set_cashapp_enabled, is_cashapp_enabled
        
        # Set the new state
        set_cashapp_enabled(enabled)
        
        # Create response embed
        status = "enabled" if enabled else "disabled"
        color = 0x00D632 if enabled else 0xFF0000
        
        embed = discord.Embed(
            title="💵 CashApp Button Toggle",
            description=f"CashApp payment button has been **{status}**.\n\n⚠️ **Note:** This command is legacy. Use `/toggle_payment` for more control.",
            color=color
        )
        
        embed.add_field(
            name="Current Status",
            value=f"{'✅ Visible' if enabled else '❌ Hidden'}",
            inline=False
        )
        
        embed.add_field(
            name="Effect",
            value="The change will apply to all new `/payments` commands.\nExisting payment messages will not be affected.",
            inline=False
        )
        
        embed.set_footer(text=f"Changed by {interaction.user}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)