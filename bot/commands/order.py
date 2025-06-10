import os
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

from ..views import PaymentView
from ..utils import helpers
from ..utils.helpers import (
    fetch_order_embed,
    fetch_ticket_embed,
    fetch_webhook_embed,
    parse_fields,
    parse_webhook_fields,
    normalize_name,
    normalize_name_for_matching,
    format_name_csv,
    is_valid_field,
    owner_only,
    find_matching_webhook_data,
)
from ..utils.card_validator import CardValidator
from ..utils.channel_status import rename_history  # not used maybe? but not required
from logging_utils import log_command_output

EXP_MONTH = '06'
EXP_YEAR = '30'
ZIP_CODE = '19104'
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'pool.db')


def setup(bot: commands.Bot):
    @bot.tree.command(name='fusion_assist', description='Format a Fusion assist order')
    @app_commands.choices(mode=[
        app_commands.Choice(name='Postmates', value='p'),
        app_commands.Choice(name='UberEats', value='u'),
    ])
    @app_commands.describe(
        email="Optional: Add a custom email to the command",
        card_number="Optional: Use custom card number (bypasses pool)",
        card_cvv="Optional: CVV for custom card (required if card_number provided)",
    )
    async def fusion_assist(interaction: discord.Interaction, mode: app_commands.Choice[str],
                           email: str = None, card_number: str = None, card_cvv: str = None):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

        if card_number and not card_cvv:
            return await interaction.response.send_message("❌ CVV required when using custom card number.", ephemeral=True)
        if card_cvv and not card_number:
            return await interaction.response.send_message("❌ Card number required when using custom CVV.", ephemeral=True)

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)

        was_last_card = False
        if card_number and card_cvv:
            number, cvv = card_number, card_cvv
            card = (number, cvv)
            card_source = "custom"
        else:
            card_result = bot.get_and_remove_card()
            if card_result is None:
                return await interaction.response.send_message("❌ Card pool is empty.", ephemeral=True)
            if len(card_result) == 3:
                number, cvv, was_last_card = card_result
                card = (number, cvv)
            else:
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
        if is_valid_field(raw_name):
            name = normalize_name(raw_name)
            parts.append(f"override_name:{name}")
        if is_valid_field(info['addr2']):
            parts.append(f"override_aptorsuite:{info['addr2']}")
        notes = info['notes'].strip()
        if is_valid_field(notes):
            if notes.lower() == 'meet at door':
                parts.append("override_dropoff:Meet at Door")
            else:
                parts.append(f"override_notes:{notes}")
                if 'leave' in notes.lower():
                    parts.append("override_dropoff:Leave at Door")

        command = ' '.join(parts)

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
                additional_data={"mode": mode.value, "parsed_fields": info, "custom_email": email, "card_source": card_source},
            )

        embed = discord.Embed(title="Fusion Assist", color=0x00ff00)
        embed.add_field(name="", value=f"```{command}```", inline=False)
        if email:
            embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
        embed.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)
        card_count, email_count = bot.get_pool_counts()
        warnings = []
        if was_last_card and card_source == "pool":
            warnings.append("⚠️ Card pool empty!")
        footer_parts = [f"Cards: {card_count}", f"Emails: {email_count}"]
        footer_parts.extend(warnings)
        embed.set_footer(text=" | ".join(footer_parts))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='wool_details', description='Show parsed Wool order details')
    async def wool_details(interaction: discord.Interaction):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)

        details = discord.Embed(title="Wool Order Details", color=0xff6600)
        if is_valid_field(info['link']):
            details.add_field(name="Group Cart Link:", value=f"```{info['link']}```", inline=False)
        if is_valid_field(info['name']):
            formatted = format_name_csv(info['name'])
            details.add_field(name="Name:", value=f"```{formatted}```", inline=False)
        if is_valid_field(info['addr2']):
            details.add_field(name="Apt / Suite / Floor:", value=f"```{info['addr2']}```", inline=False)
        if is_valid_field(info['notes']):
            details.add_field(name="Delivery Notes:", value=f"```{info['notes']}```", inline=False)
        details.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)

        await interaction.response.send_message(embed=details, ephemeral=True)

    @bot.tree.command(name='fusion_order', description='Format a Fusion order with email')
    @app_commands.describe(
        custom_email="Optional: Use custom email (bypasses pool)",
        card_number="Optional: Use custom card number (bypasses pool)",
        card_cvv="Optional: CVV for custom card (required if card_number provided)",
    )
    async def fusion_order(interaction: discord.Interaction, custom_email: str = None,
                          card_number: str = None, card_cvv: str = None):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

        if card_number and not card_cvv:
            return await interaction.response.send_message("❌ CVV required when using custom card number.", ephemeral=True)
        if card_cvv and not card_number:
            return await interaction.response.send_message("❌ Card number required when using custom CVV.", ephemeral=True)

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)

        was_last_card = False
        if card_number and card_cvv:
            number, cvv = card_number, card_cvv
            card = (number, cvv)
            card_source = "custom"
        else:
            card_result = bot.get_and_remove_card()
            if card_result is None:
                return await interaction.response.send_message("❌ Card pool is empty.", ephemeral=True)
            if len(card_result) == 3:
                number, cvv, was_last_card = card_result
                card = (number, cvv)
            else:
                card = card_result
                was_last_card = False
            card_source = "pool"

        was_last_email = False
        if custom_email:
            email = custom_email
            email_source = "custom"
        else:
            email_result = bot.get_and_remove_email()
            if email_result is None:
                return await interaction.response.send_message("❌ Email pool is empty.", ephemeral=True)
            if isinstance(email_result, tuple) and len(email_result) == 2:
                email, was_last_email = email_result
            else:
                email = email_result
                was_last_email = False
            email_source = "pool"

        raw_name = info['name']
        parts = [f"/order uber order_details:{info['link']},{number},{EXP_MONTH},{EXP_YEAR},{cvv},{ZIP_CODE},{email}"]
        if is_valid_field(raw_name):
            name = normalize_name(raw_name)
            parts.append(f"override_name:{name}")
        if is_valid_field(info['addr2']):
            parts.append(f"override_aptorsuite:{info['addr2']}")
        notes = info['notes'].strip()
        if is_valid_field(notes):
            if notes.lower() == 'meet at door':
                parts.append("override_dropoff:Meet at Door")
            else:
                parts.append(f"override_notes:{notes}")
                if 'leave' in notes.lower():
                    parts.append("override_dropoff:Leave at Door")

        command = ' '.join(parts)

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
                additional_data={"parsed_fields": info, "card_source": card_source, "email_source": email_source},
            )

        embed = discord.Embed(title="Fusion Order", color=0x0099ff)
        embed.add_field(name="", value=f"```{command}```", inline=False)
        embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
        embed.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)
        card_count, email_count = bot.get_pool_counts()
        warnings = []
        if was_last_card and card_source == "pool":
            warnings.append("⚠️ Card pool empty!")
        if was_last_email and email_source == "pool":
            warnings.append("⚠️ Email pool empty!")
        footer_parts = [f"Cards: {card_count}", f"Emails: {email_count}"]
        footer_parts.extend(warnings)
        embed.set_footer(text=" | ".join(footer_parts))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='wool_order', description='Format a Wool order')
    @app_commands.describe(
        custom_email="Optional: Use custom email (bypasses pool)",
        card_number="Optional: Use custom card number (bypasses pool)",
        card_cvv="Optional: CVV for custom card (required if card_number provided)",
    )
    async def wool_order(interaction: discord.Interaction, custom_email: str = None,
                        card_number: str = None, card_cvv: str = None):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

        if card_number and not card_cvv:
            return await interaction.response.send_message("❌ CVV required when using custom card number.", ephemeral=True)
        if card_cvv and not card_number:
            return await interaction.response.send_message("❌ Card number required when using custom CVV.", ephemeral=True)

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)

        was_last_card = False
        if card_number and card_cvv:
            number, cvv = card_number, card_cvv
            card = (number, cvv)
            card_source = "custom"
        else:
            card_result = bot.get_and_remove_card()
            if card_result is None:
                return await interaction.response.send_message("❌ Card pool is empty.", ephemeral=True)
            if len(card_result) == 3:
                number, cvv, was_last_card = card_result
                card = (number, cvv)
            else:
                card = card_result
                was_last_card = False
            card_source = "pool"

        was_last_email = False
        if custom_email:
            email = custom_email
            email_source = "custom"
        else:
            email_result = bot.get_and_remove_email()
            if email_result is None:
                return await interaction.response.send_message("❌ Email pool is empty.", ephemeral=True)
            if isinstance(email_result, tuple) and len(email_result) == 2:
                email, was_last_email = email_result
            else:
                email = email_result
                was_last_email = False
            email_source = "pool"

        command = f"{info['link']},{number},{EXP_MONTH}/{EXP_YEAR},{cvv},{ZIP_CODE},{email}"

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
                additional_data={"parsed_fields": info, "card_source": card_source, "email_source": email_source},
            )

        embed = discord.Embed(title="Wool Order", color=0xff6600)
        embed.add_field(name="", value=f"```{command}```", inline=False)
        embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
        if is_valid_field(info['name']):
            formatted = format_name_csv(info['name'])
            embed.add_field(name="Name:", value=f"```{formatted}```", inline=False)
        if is_valid_field(info['addr2']):
            embed.add_field(name="Apt / Suite / Floor:", value=f"```{info['addr2']}```", inline=False)
        if is_valid_field(info['notes']):
            embed.add_field(name="Delivery Notes:", value=f"```{info['notes']}```", inline=False)
        embed.add_field(name="", value=f"Tip: ${info['tip']}", inline=False)
        card_count, email_count = bot.get_pool_counts()
        warnings = []
        if was_last_card and card_source == "pool":
            warnings.append("⚠️ Card pool empty!")
        if was_last_email and email_source == "pool":
            warnings.append("⚠️ Email pool empty!")
        footer_parts = [f"Cards: {card_count}", f"Emails: {email_count}"]
        footer_parts.extend(warnings)
        embed.set_footer(text=" | ".join(footer_parts))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='payments', description='Display payment methods')
    async def payments(interaction: discord.Interaction):
        embed = discord.Embed(
            title="Prin's Payments",
            description="Select which payment method you would like to use!",
            color=0x9932cc,
        )
        view = PaymentView()
        await interaction.response.send_message(embed=embed, view=view)

    @bot.tree.command(name='send_tracking', description='Send order tracking for this ticket')
    async def send_tracking(interaction: discord.Interaction):
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)

        # Use the same ticket embed that order commands use
        ticket_embed = await fetch_ticket_embed(interaction.channel)
        
        if not ticket_embed:
            return await interaction.response.send_message('❌ Could not find ticket embed.', ephemeral=True)
        
        # Parse the ticket embed the same way order commands do
        info = parse_fields(ticket_embed)
        ticket_name = info.get('name', '').strip()
        
        if not ticket_name:
            return await interaction.response.send_message('❌ Could not extract name from ticket.', ephemeral=True)
        
        # Normalize the ticket name for matching
        normalized_ticket_name = normalize_name_for_matching(ticket_name)
        
        # Find matching webhook data using name-only matching
        data = None
        matched_key = None
        
        # Try exact normalized name match first
        for (cached_name, cached_addr), cached_data in helpers.ORDER_WEBHOOK_CACHE.items():
            if normalize_name_for_matching(cached_name) == normalized_ticket_name:
                data = cached_data
                matched_key = (cached_name, cached_addr)
                break
        
        # If no exact match, try partial name matching
        if not data:
            for (cached_name, cached_addr), cached_data in helpers.ORDER_WEBHOOK_CACHE.items():
                cached_normalized = normalize_name_for_matching(cached_name)
                # Check if names contain each other or share significant parts
                if (normalized_ticket_name in cached_normalized or 
                    cached_normalized in normalized_ticket_name or
                    any(part in cached_normalized for part in normalized_ticket_name.split() if len(part) > 2)):
                    data = cached_data
                    matched_key = (cached_name, cached_addr)
                    break
        
        if not data:
            # Show debug info about what was found
            cache_keys = [normalize_name_for_matching(k[0]) for k in helpers.ORDER_WEBHOOK_CACHE.keys()]
            debug_msg = f'❌ No matching webhook found.\n**Ticket name:** `{ticket_name}` → `{normalized_ticket_name}`\n**Cached names:** {", ".join(cache_keys) if cache_keys else "None"}'
            return await interaction.response.send_message(debug_msg, ephemeral=True)

        # Create tracking embed
        e = discord.Embed(title='Order Placed', url=data.get('tracking'), color=0x00ff00)
        e.add_field(name='Store', value=data.get('store'), inline=False)
        e.add_field(name='Estimated Arrival', value=data.get('eta'), inline=False)
        e.add_field(name='Order Items', value=data.get('items'), inline=False)
        e.add_field(name='Name', value=data.get('name'), inline=False)
        e.add_field(name='Delivery Address', value=data.get('address'), inline=False)
        e.set_footer(text='Watch the tracking link for updates!')

        await interaction.response.send_message(embed=e)
        
        # Remove from cache after successful use
        if matched_key:
            helpers.ORDER_WEBHOOK_CACHE.pop(matched_key, None)

    @bot.tree.command(name='debug_tracking', description='Debug webhook lookup')
    async def debug_tracking(
        interaction: discord.Interaction, search_limit: int = 50
    ):
        """Display information about the most recent order embed and cache."""

        if not owner_only(interaction):
            return await interaction.response.send_message(
                '❌ You are not authorized.', ephemeral=True
            )

        debug_channel = interaction.guild.get_channel(1350935337475510297)
        tracking_channel = interaction.guild.get_channel(1352067371006693499)

        if tracking_channel is None:
            msg = '❌ Tracking channel not found.'
            if debug_channel:
                await debug_channel.send(msg)
            return await interaction.response.send_message(msg, ephemeral=True)

        # Try different embed types
        ticket_embed = await fetch_ticket_embed(tracking_channel, search_limit=search_limit)
        webhook_embed = await fetch_webhook_embed(tracking_channel, search_limit=search_limit)
        
        debug = discord.Embed(title='Tracking Debug', color=0xFFFF00)
        
        if ticket_embed:
            info = parse_fields(ticket_embed)
            name = normalize_name_for_matching(info.get('name', ''))
            addr = info.get('address', info.get('addr2', '')).lower().strip()
            debug.add_field(name='Ticket Embed Found', value='✅ Yes', inline=False)
            debug.add_field(name='Ticket Name', value=name or 'None', inline=False)
            debug.add_field(name='Ticket Address', value=addr or 'None', inline=False)
        else:
            debug.add_field(name='Ticket Embed Found', value='❌ No', inline=False)
        
        if webhook_embed:
            webhook_info = parse_webhook_fields(webhook_embed)
            webhook_name = normalize_name_for_matching(webhook_info.get('name', ''))
            webhook_addr = webhook_info.get('address', '').lower().strip()
            debug.add_field(name='Webhook Embed Found', value='✅ Yes', inline=False)
            debug.add_field(name='Webhook Name', value=webhook_name or 'None', inline=False)
            debug.add_field(name='Webhook Address', value=webhook_addr or 'None', inline=False)
        else:
            debug.add_field(name='Webhook Embed Found', value='❌ No', inline=False)
        
        # Use the best available name/address for lookup
        if ticket_embed:
            info = parse_fields(ticket_embed)
            name = normalize_name_for_matching(info.get('name', ''))
            addr = info.get('address', info.get('addr2', '')).lower().strip()
        elif webhook_embed:
            webhook_info = parse_webhook_fields(webhook_embed)
            name = normalize_name_for_matching(webhook_info.get('name', ''))
            addr = webhook_info.get('address', '').lower().strip()
        else:
            msg = '❌ Could not locate any order embed.'
            if debug_channel:
                await debug_channel.send(msg)
            return await interaction.response.send_message(msg, ephemeral=True)

        # Try to find matching data
        data = find_matching_webhook_data(name, addr)
        
        debug.add_field(name='Lookup Key', value=f'{name} | {addr}', inline=False)
        debug.add_field(name='Cache Hit', value='✅ Yes' if data else '❌ No', inline=False)
        
        if not data:
            cache_keys = [f'{k[0]} | {k[1]}' for k in helpers.ORDER_WEBHOOK_CACHE.keys()]
            debug.add_field(
                name='Available Cache Keys', 
                value='; '.join(cache_keys) if cache_keys else 'None', 
                inline=False
            )
        else:
            debug.add_field(name='Matched Data Store', value=data.get('store', 'None'), inline=False)

        status_msg = (
            f'✅ Cache hit for `{name} | {addr}`.'
            if data
            else f'❌ No matching webhook found for `{name} | {addr}`.'
        )
        if debug_channel:
            await debug_channel.send(status_msg)

        await interaction.response.send_message(embed=debug, ephemeral=True)