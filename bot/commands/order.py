import os
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

from ..views import PaymentView
from ..utils import helpers
from ..utils.helpers import (
    fetch_order_embed,
    parse_fields,
    normalize_name,
    format_name_csv,
    is_valid_field,
    owner_only,
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

        embed = await fetch_order_embed(interaction.channel)
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

        embed = await fetch_order_embed(interaction.channel)
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

        embed = await fetch_order_embed(interaction.channel)
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

        embed = await fetch_order_embed(interaction.channel)
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

        embed = await fetch_order_embed(interaction.channel)
        if embed is None:
            return await interaction.response.send_message('❌ Could not find order embed.', ephemeral=True)

        info = parse_fields(embed)
        name = info.get('name', '').lower()
        addr = info.get('address', info.get('addr2', '')).lower()
        key = (name, addr)
        data = helpers.ORDER_WEBHOOK_CACHE.get(key)
        if not data:
            cache_keys = ", ".join([f"{n}|{a}" for n, a in helpers.ORDER_WEBHOOK_CACHE.keys()]) or "<empty>"
            await interaction.response.send_message('❌ No matching webhook found.', ephemeral=True)
            print(f"[DEBUG] send_tracking miss for {key}; cache keys: {cache_keys}")
            return

        e = discord.Embed(title='Order Placed', url=data.get('tracking'), color=0x00ff00)
        e.add_field(name='Store', value=data.get('store'), inline=False)
        e.add_field(name='Estimated Arrival', value=data.get('eta'), inline=False)
        e.add_field(name='Order Items', value=data.get('items'), inline=False)
        e.add_field(name='Name', value=data.get('name'), inline=False)
        e.add_field(name='Delivery Address', value=data.get('address'), inline=False)
        e.set_footer(text='Watch the tracking link for updates!')

        await interaction.response.send_message(embed=e)
        helpers.ORDER_WEBHOOK_CACHE.pop((name, addr), None)
        print(f"[DEBUG] send_tracking delivered for {key}")

    @bot.tree.command(name='debug_webhooks', description='List cached webhook orders')
    async def debug_webhooks(interaction: discord.Interaction):
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)

        if not helpers.ORDER_WEBHOOK_CACHE:
            return await interaction.response.send_message('Cache is empty.', ephemeral=True)

        lines = [f"{n} | {a} -> {d.get('store')}" for (n, a), d in helpers.ORDER_WEBHOOK_CACHE.items()]
        message = '\n'.join(lines)
        await interaction.response.send_message(f'```\n{message}\n```', ephemeral=True)

