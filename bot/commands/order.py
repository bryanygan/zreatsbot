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
    @bot.tree.command(name='debug_embed_details', description='Show detailed embed structure for debugging')
    async def debug_embed_details(interaction: discord.Interaction, message_id: str = None, search_limit: int = 5):
        """Show raw embed structure to debug webhook detection issues"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        embeds_analyzed = []
        
        try:
            if message_id:
                # Analyze specific message
                try:
                    message = await interaction.channel.fetch_message(int(message_id))
                    messages_to_check = [message]
                except:
                    return await interaction.response.send_message('❌ Could not find message with that ID.', ephemeral=True)
            else:
                # Analyze recent messages
                messages_to_check = []
                async for msg in interaction.channel.history(limit=search_limit):
                    messages_to_check.append(msg)
            
            for message in messages_to_check:
                if message.embeds:
                    for i, embed in enumerate(message.embeds):
                        analysis = {
                            'message_id': message.id,
                            'embed_index': i,
                            'is_webhook': bool(message.webhook_id),
                            'webhook_id': message.webhook_id,
                            'author': str(message.author),
                            'title': embed.title,
                            'description': (embed.description or '')[:200] + ('...' if embed.description and len(embed.description) > 200 else ''),
                            'field_count': len(embed.fields),
                            'field_names': [f.name for f in embed.fields],
                            'field_values_preview': {f.name: (f.value or '')[:100] + ('...' if f.value and len(f.value) > 100 else '') for f in embed.fields[:5]},
                            'color': embed.color,
                            'url': embed.url
                        }
                        
                        # Test detection logic
                        field_names = set(f.name for f in embed.fields)
                        analysis['is_tracking'] = {"Store", "Name", "Delivery Address"}.issubset(field_names)
                        analysis['is_checkout'] = (
                            "Account Email" in field_names or 
                            "Delivery Information" in field_names or
                            "Items In Bag" in field_names or
                            (embed.title and "Checkout Successful" in embed.title) or
                            (embed.description and "Checkout Successful" in embed.description) or
                            ("Store" in field_names and any(x in field_names for x in ["Account Email", "Account Phone", "Delivery Information", "Items In Bag"]))
                        )
                        
                        # Test parsing if it's detected as a webhook
                        if analysis['is_tracking'] or analysis['is_checkout']:
                            try:
                                parsed_data = helpers.parse_webhook_fields(embed)
                                analysis['parsed_data'] = parsed_data
                            except Exception as e:
                                analysis['parsing_error'] = str(e)
                        
                        embeds_analyzed.append(analysis)
        
        except Exception as e:
            return await interaction.response.send_message(f'❌ Error analyzing embeds: {str(e)}', ephemeral=True)
        
        if not embeds_analyzed:
            return await interaction.response.send_message('📭 No embeds found in the specified messages.', ephemeral=True)
        
        # Create detailed response
        for analysis in embeds_analyzed[:2]:  # Show detailed info for first 2 embeds
            embed = discord.Embed(title=f'Embed Debug: Message {analysis["message_id"]}', color=0xFF00FF)
            embed.add_field(name='Basic Info', 
                           value=f'**Is Webhook**: {analysis["is_webhook"]}\n**Author**: {analysis["author"]}\n**Title**: {analysis["title"] or "None"}\n**Fields**: {analysis["field_count"]}', 
                           inline=False)
            
            embed.add_field(name='Detection Results',
                           value=f'**Is Tracking**: {analysis["is_tracking"]}\n**Is Checkout**: {analysis["is_checkout"]}',
                           inline=False)
            
            embed.add_field(name='Field Names',
                           value=', '.join(analysis["field_names"]) if analysis["field_names"] else 'None',
                           inline=False)
            
            if analysis["field_values_preview"]:
                field_preview = '\n'.join([f'**{name}**: {value}' for name, value in list(analysis["field_values_preview"].items())[:3]])
                embed.add_field(name='Field Values (first 3)', value=field_preview, inline=False)
            
            if 'parsed_data' in analysis:
                parsed = analysis['parsed_data']
                embed.add_field(name='Parsed Data',
                               value=f'**Name**: {parsed.get("name", "None")}\n**Store**: {parsed.get("store", "None")}\n**Type**: {parsed.get("type", "None")}',
                               inline=False)
            elif 'parsing_error' in analysis:
                embed.add_field(name='Parsing Error', value=analysis['parsing_error'], inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Summary response
        summary = f'📊 **Embed Analysis Summary**\n\n'
        summary += f'**Total Embeds Analyzed**: {len(embeds_analyzed)}\n'
        summary += f'**Webhook Messages**: {sum(1 for a in embeds_analyzed if a["is_webhook"])}\n'
        summary += f'**Detected as Tracking**: {sum(1 for a in embeds_analyzed if a["is_tracking"])}\n'
        summary += f'**Detected as Checkout**: {sum(1 for a in embeds_analyzed if a["is_checkout"])}\n'
        
        if len(embeds_analyzed) > 2:
            summary += f'\n*Showing detailed analysis for first 2 embeds only*'
        
        await interaction.response.send_message(summary, ephemeral=True)

    @bot.tree.command(name='check_specific_message', description='Check if a specific message would be detected as webhook')
    async def check_specific_message(interaction: discord.Interaction, message_id: str):
        """Check detection logic on a specific message ID"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        try:
            message = await interaction.channel.fetch_message(int(message_id))
        except:
            return await interaction.response.send_message('❌ Could not find message with that ID.', ephemeral=True)
        
        results = []
        
        if not message.embeds:
            return await interaction.response.send_message('❌ Message has no embeds.', ephemeral=True)
        
        for i, embed in enumerate(message.embeds):
            field_names = set(f.name for f in embed.fields)
            
            # Manual step-by-step detection
            has_webhook_id = bool(message.webhook_id)
            has_store_name_delivery = {"Store", "Name", "Delivery Address"}.issubset(field_names)
            has_account_email = "Account Email" in field_names
            has_delivery_info = "Delivery Information" in field_names
            has_items_in_bag = "Items In Bag" in field_names
            has_checkout_title = embed.title and "Checkout Successful" in embed.title
            has_checkout_desc = embed.description and "Checkout Successful" in embed.description
            has_store_and_account = "Store" in field_names and any(x in field_names for x in ["Account Email", "Account Phone", "Delivery Information", "Items In Bag"])
            
            is_tracking = has_store_name_delivery
            is_checkout = (has_account_email or has_delivery_info or has_items_in_bag or 
                          has_checkout_title or has_checkout_desc or has_store_and_account)
            
            results.append({
                'embed_index': i,
                'field_names': list(field_names),
                'has_webhook_id': has_webhook_id,
                'detection_checks': {
                    'Store + Name + Delivery Address': has_store_name_delivery,
                    'Account Email': has_account_email,
                    'Delivery Information': has_delivery_info,
                    'Items In Bag': has_items_in_bag,
                    'Checkout in Title': has_checkout_title,
                    'Checkout in Description': has_checkout_desc,
                    'Store + Account Fields': has_store_and_account
                },
                'final_detection': {
                    'is_tracking': is_tracking,
                    'is_checkout': is_checkout,
                    'would_process': has_webhook_id and (is_tracking or is_checkout)
                }
            })
        
        embed_response = discord.Embed(title=f'Message Detection Analysis: {message_id}', color=0x00FFFF)
        embed_response.add_field(name='Message Info', 
                                value=f'**Has Webhook ID**: {bool(message.webhook_id)}\n**Author**: {message.author}\n**Embeds**: {len(message.embeds)}',
                                inline=False)
        
        for result in results:
            checks = '\n'.join([f'• {check}: {"✅" if passed else "❌"}' for check, passed in result['detection_checks'].items()])
            final = result['final_detection']
            
            embed_response.add_field(
                name=f'Embed {result["embed_index"]} Analysis',
                value=f'**Field Names**: {", ".join(result["field_names"][:5])}...\n\n**Detection Checks**:\n{checks}\n\n**Final Results**:\n• Tracking: {"✅" if final["is_tracking"] else "❌"}\n• Checkout: {"✅" if final["is_checkout"] else "❌"}\n• **Would Process**: {"✅" if final["would_process"] else "❌"}',
                inline=False
            )
        
        await interaction.response.send_message(embed=embed_response, ephemeral=True)

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
        
        # Find the latest matching webhook data
        data = helpers.find_latest_matching_webhook_data(ticket_name)
        
        if not data:
            # Show debug info about what was found
            cache_keys = [normalize_name_for_matching(k[0]) for k in helpers.ORDER_WEBHOOK_CACHE.keys()]
            debug_msg = f'❌ No matching webhook found.\n**Ticket name:** `{ticket_name}` → `{normalized_ticket_name}`\n**Cached names:** {", ".join(cache_keys) if cache_keys else "None"}'
            return await interaction.response.send_message(debug_msg, ephemeral=True)

        # Create tracking embed based on webhook type
        webhook_type = data.get('type', 'unknown')
        
        if webhook_type == 'tracking':
            e = discord.Embed(title='Order Placed', url=data.get('tracking'), color=0x00ff00)
            e.add_field(name='Store', value=data.get('store'), inline=False)
            e.add_field(name='Estimated Arrival', value=data.get('eta'), inline=False)
            e.add_field(name='Order Items', value=data.get('items'), inline=False)
            e.add_field(name='Name', value=data.get('name'), inline=False)
            e.add_field(name='Delivery Address', value=data.get('address'), inline=False)
            e.set_footer(text='Watch the tracking link for updates!')
        else:  # checkout or unknown
            e = discord.Embed(title='Checkout Successful', url=data.get('tracking'), color=0x0099ff)
            e.add_field(name='Store', value=data.get('store'), inline=False)
            if data.get('eta') and data.get('eta') != 'N/A':
                e.add_field(name='Estimated Arrival', value=data.get('eta'), inline=False)
            if data.get('items'):
                e.add_field(name='Items Ordered', value=data.get('items'), inline=False)
            e.add_field(name='Name', value=data.get('name'), inline=False)
            if data.get('address'):
                e.add_field(name='Delivery Address', value=data.get('address'), inline=False)
            if data.get('payment'):
                e.add_field(name='Account Email', value=data.get('payment'), inline=False)
            e.set_footer(text=f'Checkout confirmed • Type: {webhook_type}')

        await interaction.response.send_message(embed=e)
        
        # Don't remove from cache anymore - keep for potential future lookups

    @bot.tree.command(name='debug_tracking', description='Debug webhook lookup')
    async def debug_tracking(
        interaction: discord.Interaction, search_limit: int = 50
    ):
        """Display information about the ticket embed and webhook cache for debugging."""

        if not owner_only(interaction):
            return await interaction.response.send_message(
                '❌ You are not authorized.', ephemeral=True
            )

        debug_channel = interaction.guild.get_channel(1350935337475510297)
        
        # Get detailed info about all embeds in the channel
        all_embeds = await helpers.debug_all_embeds(interaction.channel, search_limit=search_limit)
        
        # Use the same ticket embed that order commands use
        ticket_embed = await fetch_ticket_embed(interaction.channel, search_limit=search_limit)
        
        debug = discord.Embed(title='Tracking Debug - Detailed', color=0xFFFF00)
        
        # Show embed analysis
        if all_embeds:
            embed_summary = []
            for info in all_embeds[:5]:  # Show first 5
                if 'error' in info:
                    embed_summary.append(f"Error: {info['error']}")
                else:
                    webhook_text = " (webhook)" if info.get('webhook_id') else ""
                    embed_summary.append(f"**{info['title']}**{webhook_text}: {', '.join(info['field_names'][:3])}...")
            
            debug.add_field(
                name=f'Found {len(all_embeds)} Embeds', 
                value='\n'.join(embed_summary) if embed_summary else 'None',
                inline=False
            )
        else:
            debug.add_field(name='Embeds Found', value='None', inline=False)
        
        if ticket_embed:
            info = parse_fields(ticket_embed)
            ticket_name = info.get('name', '').strip()
            normalized_name = normalize_name_for_matching(ticket_name)
            
            debug.add_field(name='Ticket Embed Found', value='✅ Yes', inline=False)
            debug.add_field(name='Ticket Name (Raw)', value=ticket_name or 'None', inline=False)
            debug.add_field(name='Ticket Name (Normalized)', value=normalized_name or 'None', inline=False)
            
            # Try to find matching data using name-only matching
            matched_data = None
            matched_cache_name = None
            
            for (cached_name, cached_addr), cached_data in helpers.ORDER_WEBHOOK_CACHE.items():
                if normalize_name_for_matching(cached_name) == normalized_name:
                    matched_data = cached_data
                    matched_cache_name = cached_name
                    break
            
            debug.add_field(name='Exact Name Match', value='✅ Yes' if matched_data else '❌ No', inline=False)
            
            if matched_data:
                debug.add_field(name='Matched Cache Name', value=matched_cache_name, inline=False)
                debug.add_field(name='Matched Store', value=matched_data.get('store', 'None'), inline=False)
        else:
            debug.add_field(name='Ticket Embed Found', value='❌ No', inline=False)
            
            # Show what field names we're looking for vs what we found
            debug.add_field(
                name='Looking For Fields', 
                value='Group Cart Link + Name (or Group Link + Name)', 
                inline=False
            )
            
            if all_embeds:
                found_fields = []
                for info in all_embeds[:3]:
                    if 'field_names' in info:
                        found_fields.extend(info['field_names'])
                unique_fields = list(set(found_fields))
                debug.add_field(
                    name='Actually Found Fields', 
                    value=', '.join(unique_fields[:10]) if unique_fields else 'None',
                    inline=False
                )
        
        # Show all cached names for comparison
        if helpers.ORDER_WEBHOOK_CACHE:
            cache_info = []
            for (cached_name, cached_addr), cached_data in helpers.ORDER_WEBHOOK_CACHE.items():
                normalized_cached = normalize_name_for_matching(cached_name)
                cache_info.append(f"{cached_name} → {normalized_cached}")
            
            debug.add_field(
                name='All Cached Names', 
                value='; '.join(cache_info[:3]) + ('...' if len(cache_info) > 3 else ''), 
                inline=False
            )
        else:
            debug.add_field(name='Cache Status', value='Empty', inline=False)

        status_msg = f'Detailed debug for ticket embed search (checked {search_limit} messages)'
        if debug_channel:
            await debug_channel.send(status_msg)

    @bot.tree.command(name='scan_webhooks', description='Scan tracking channel for webhook orders')
    async def scan_webhooks(interaction: discord.Interaction, channel_id: str = None, search_limit: int = 50):
        """Manually scan a channel for webhook order confirmations and cache them"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        # Default to tracking channel if no channel specified
        if channel_id:
            try:
                target_channel = interaction.guild.get_channel(int(channel_id))
            except ValueError:
                return await interaction.response.send_message('❌ Invalid channel ID.', ephemeral=True)
        else:
            target_channel = interaction.guild.get_channel(1352067371006693499)  # Default tracking channel
        
        if not target_channel:
            return await interaction.response.send_message('❌ Channel not found.', ephemeral=True)
        
        found_webhooks = 0
        cached_webhooks = 0
        tracking_webhooks = 0
        checkout_webhooks = 0
        
        try:
            async for message in target_channel.history(limit=search_limit):
                if message.webhook_id and message.embeds:
                    for embed in message.embeds:
                        field_names = {f.name for f in embed.fields}
                        
                        # Check for tracking webhook (Store, Name, Delivery Address)
                        is_tracking = {"Store", "Name", "Delivery Address"}.issubset(field_names)
                        
                        # Check for checkout webhook (Account Email, Delivery Information, etc.)
                        is_checkout = (
                            "Account Email" in field_names or 
                            "Delivery Information" in field_names or
                            "Items In Bag" in field_names or
                            (embed.title and "Checkout Successful" in embed.title) or
                            (embed.description and "Checkout Successful" in embed.description) or
                            ("Store" in field_names and any(x in field_names for x in ["Account Email", "Account Phone", "Delivery Information", "Items In Bag"]))
                        )
                        
                        if is_tracking or is_checkout:
                            found_webhooks += 1
                            
                            if is_tracking:
                                tracking_webhooks += 1
                            elif is_checkout:
                                checkout_webhooks += 1
                            
                            data = helpers.parse_webhook_fields(embed)
                            name = helpers.normalize_name_for_matching(data.get('name', ''))
                            addr = data.get('address', '').lower().strip()
                            
                            if name:  # Only cache if we have a valid name
                                cache_key = (name, addr)
                                if cache_key not in helpers.ORDER_WEBHOOK_CACHE:
                                    helpers.ORDER_WEBHOOK_CACHE[cache_key] = data
                                    cached_webhooks += 1
        except Exception as e:
            return await interaction.response.send_message(f'❌ Error scanning channel: {str(e)}', ephemeral=True)
        
        embed = discord.Embed(title='Webhook Scan Results', color=0x00FF00)
        embed.add_field(name='Channel Scanned', value=target_channel.mention, inline=False)
        embed.add_field(name='Messages Searched', value=str(search_limit), inline=False)
        embed.add_field(name='Total Webhook Orders Found', value=str(found_webhooks), inline=False)
        embed.add_field(name='├─ Tracking Webhooks', value=str(tracking_webhooks), inline=True)
        embed.add_field(name='└─ Checkout Webhooks', value=str(checkout_webhooks), inline=True)
        embed.add_field(name='New Entries Cached', value=str(cached_webhooks), inline=False)
        embed.add_field(name='Total Cache Size', value=str(len(helpers.ORDER_WEBHOOK_CACHE)), inline=False)
        
        if helpers.ORDER_WEBHOOK_CACHE:
            recent_names = []
            for (name, addr), data in list(helpers.ORDER_WEBHOOK_CACHE.items())[-5:]:
                store = data.get('store', 'Unknown')
                webhook_type = data.get('type', 'unknown')
                recent_names.append(f"{name} ({store}) [{webhook_type}]")
            embed.add_field(name='Recent Cached Names', value='\n'.join(recent_names), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='check_cache', description='Show current webhook cache contents')
    async def check_cache(interaction: discord.Interaction):
        """Show what's currently in the webhook cache"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        if not helpers.ORDER_WEBHOOK_CACHE:
            return await interaction.response.send_message('📭 Webhook cache is empty.', ephemeral=True)
        
        embed = discord.Embed(title='Webhook Cache Contents', color=0x0099FF)
        embed.add_field(name='Total Entries', value=str(len(helpers.ORDER_WEBHOOK_CACHE)), inline=False)
        
        # Count by type
        tracking_count = sum(1 for data in helpers.ORDER_WEBHOOK_CACHE.values() if data.get('type') == 'tracking')
        checkout_count = sum(1 for data in helpers.ORDER_WEBHOOK_CACHE.values() if data.get('type') == 'checkout')
        unknown_count = len(helpers.ORDER_WEBHOOK_CACHE) - tracking_count - checkout_count
        
        type_summary = []
        if tracking_count > 0:
            type_summary.append(f"Tracking: {tracking_count}")
        if checkout_count > 0:
            type_summary.append(f"Checkout: {checkout_count}")
        if unknown_count > 0:
            type_summary.append(f"Unknown: {unknown_count}")
        
        if type_summary:
            embed.add_field(name='By Type', value=' | '.join(type_summary), inline=False)
        
        cache_entries = []
        for (name, addr), data in helpers.ORDER_WEBHOOK_CACHE.items():
            store = data.get('store', 'Unknown')
            webhook_type = data.get('type', 'unknown')
            cache_entries.append(f"**{name}** → {store} `[{webhook_type}]`")
        
        # Show up to 10 entries
        if len(cache_entries) <= 10:
            embed.add_field(name='All Cached Orders', value='\n'.join(cache_entries), inline=False)
        else:
            embed.add_field(name='Recent 10 Cached Orders', value='\n'.join(cache_entries[-10:]), inline=False)
            embed.add_field(name='Note', value=f'Showing last 10 of {len(cache_entries)} total entries', inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='find_ticket', description='Search for ticket embed in channel')
    async def find_ticket(interaction: discord.Interaction, search_limit: int = 100):
        """Debug command to specifically look for ticket embeds"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        all_embeds = await helpers.debug_all_embeds(interaction.channel, search_limit=search_limit)
        
        debug = discord.Embed(title=f'Ticket Search Results', color=0x00FFFF)
        debug.add_field(name='Search Limit', value=str(search_limit), inline=False)
        debug.add_field(name='Total Embeds Found', value=str(len(all_embeds)), inline=False)
        
        ticket_candidates = []
        webhook_embeds = []
        
        for info in all_embeds:
            if 'error' in info:
                continue
                
            field_names = info.get('field_names', [])
            
            # Check if this could be a ticket embed
            has_group_link = any('group' in name.lower() and 'link' in name.lower() for name in field_names)
            has_name = any('name' in name.lower() for name in field_names)
            
            if has_group_link and has_name:
                ticket_candidates.append(f"✅ **{info['title']}**: {', '.join(field_names)}")
            elif info.get('webhook_id'):
                webhook_embeds.append(f"🔗 **{info['title']}**: {', '.join(field_names[:3])}")
        
        if ticket_candidates:
            debug.add_field(
                name='Potential Ticket Embeds', 
                value='\n'.join(ticket_candidates[:5]), 
                inline=False
            )
        else:
            debug.add_field(name='Potential Ticket Embeds', value='❌ None found', inline=False)
        
        if webhook_embeds:
            debug.add_field(
                name='Webhook Embeds Found', 
                value='\n'.join(webhook_embeds[:5]), 
                inline=False
            )
        
    @bot.tree.command(name='test_webhook_parsing', description='Test webhook parsing on recent messages')
    async def test_webhook_parsing(interaction: discord.Interaction, search_limit: int = 10):
        """Test webhook parsing to see what data is extracted"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        results = []
        
        try:
            async for message in interaction.channel.history(limit=search_limit):
                if message.webhook_id and message.embeds:
                    for i, embed in enumerate(message.embeds):
                        field_names = [f.name for f in embed.fields]
                        
                        # Test if this could be a webhook we care about
                        is_tracking = {"Store", "Name", "Delivery Address"}.issubset(field_names)
                        is_checkout = (
                            "Account Email" in field_names or 
                            "Delivery Information" in field_names or
                            "Items In Bag" in field_names or
                            (embed.title and "Checkout Successful" in embed.title) or
                            (embed.description and "Checkout Successful" in embed.description) or
                            any("Store" in name and "Account" in str(field_names) for name in field_names)
                        )
                        
                        if is_tracking or is_checkout:
                            # Parse the webhook
                            parsed_data = helpers.parse_webhook_fields(embed)
                            
                            results.append({
                                'message_id': message.id,
                                'embed_index': i,
                                'title': embed.title or 'No Title',
                                'description': (embed.description or '')[:100] + ('...' if embed.description and len(embed.description) > 100 else ''),
                                'field_names': field_names,
                                'parsed_name': parsed_data.get('name', 'None'),
                                'parsed_store': parsed_data.get('store', 'None'),
                                'parsed_type': parsed_data.get('type', 'None'),
                                'parsed_address': parsed_data.get('address', 'None')[:50] + ('...' if parsed_data.get('address', '') and len(parsed_data.get('address', '')) > 50 else '')
                            })
        except Exception as e:
            return await interaction.response.send_message(f'❌ Error testing parsing: {str(e)}', ephemeral=True)
        
        if not results:
            return await interaction.response.send_message('📭 No webhook embeds found in recent messages.', ephemeral=True)
        
        embed = discord.Embed(title='Webhook Parsing Test Results', color=0xFFAA00)
        embed.add_field(name='Messages Searched', value=str(search_limit), inline=False)
        embed.add_field(name='Webhook Embeds Found', value=str(len(results)), inline=False)
        
        for i, result in enumerate(results[:3], 1):  # Show first 3 results
            embed.add_field(
                name=f'Webhook {i}: {result["title"]}',
                value=f'**Type**: {result["parsed_type"]}\n**Name**: {result["parsed_name"]}\n**Store**: {result["parsed_store"]}\n**Address**: {result["parsed_address"]}\n**Fields**: {", ".join(result["field_names"][:3])}...',
                inline=False
            )
        
        if len(results) > 3:
            embed.add_field(name='Note', value=f'Showing first 3 of {len(results)} results', inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)