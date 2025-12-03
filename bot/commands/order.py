import os
import sqlite3
import discord
import re
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
    convert_24h_to_12h,
    detect_webhook_type,
)
from ..utils.card_validator import CardValidator
from ..utils.channel_status import rename_history
from logging_utils import log_command_output
import db
from config import EXP_MONTH, EXP_YEAR, ZIP_CODE

# Database path - supports both local development and Railway/production
DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'pool.db'))

def clean_tip_amount(tip_str):
    """Extract numeric tip value, removing all non-numeric characters except decimal point"""
    if not tip_str:
        return ""
    # Extract only numbers and decimal point using regex
    matches = re.findall(r'[\d.]+', tip_str)
    if matches:
        # Join all numeric parts and validate it's a proper number
        cleaned = ''.join(matches)
        try:
            float(cleaned)  # Validate it's a number
            return cleaned
        except ValueError:
            return ""  # Return empty string if not a valid number
    return ""  # Return empty string if no numbers found


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
                return await interaction.followup.send("❌ Card pool is empty.", ephemeral=True)
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
                additional_data={"mode": mode.value, "parsed_fields": info, "custom_email": email, "card_source": card_source, "email_pool": "custom"},
            )

        embed = discord.Embed(title="Fusion Assist", color=0x00ff00)
        # Only show the command in the code block, no pool/source text
        embed.add_field(name="", value=f"```{command}```", inline=False)
        if email:
            embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
        embed.add_field(name="Tip:", value=f"```{clean_tip_amount(info['tip'])}```", inline=False)
        pool_counts = bot.get_pool_counts()
        card_count = pool_counts['cards']
        warnings = []
        if was_last_card and card_source == "pool":
            warnings.append("⚠️ Card pool empty!")
        footer_parts = [f"Cards: {card_count}"]
        for pool_name, email_count in pool_counts['emails'].items():
            footer_parts.append(f"{pool_name}: {email_count}")
        footer_parts.extend(warnings)
        embed.set_footer(text=" | ".join(footer_parts))
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
                        field_names = {f.name for f in embed.fields}
                        is_webhook, webhook_type = detect_webhook_type(embed, field_names)
                        
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
                            'url': embed.url,
                            'detected_webhook': is_webhook,
                            'detected_type': webhook_type
                        }
                        
                        # Test parsing if it's detected as a webhook
                        if is_webhook:
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
                           value=f'**Detected Webhook**: {analysis["detected_webhook"]}\n**Detected Type**: {analysis["detected_type"]}',
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
        summary += f'**Detected Webhooks**: {sum(1 for a in embeds_analyzed if a["detected_webhook"])}\n'
        
        # Count by type
        type_counts = {}
        for a in embeds_analyzed:
            if a["detected_webhook"]:
                webhook_type = a["detected_type"]
                type_counts[webhook_type] = type_counts.get(webhook_type, 0) + 1
        
        if type_counts:
            summary += f'**By Type**: {", ".join([f"{t}: {c}" for t, c in type_counts.items()])}\n'
        
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
            field_names = {f.name for f in embed.fields}
            
            # Use the new detection function
            is_webhook, webhook_type = detect_webhook_type(embed, field_names)
            
            results.append({
                'embed_index': i,
                'field_names': list(field_names),
                'has_webhook_id': bool(message.webhook_id),
                'detected_webhook': is_webhook,
                'detected_type': webhook_type,
                'would_process': bool(message.webhook_id) and is_webhook
            })
        
        embed_response = discord.Embed(title=f'Message Detection Analysis: {message_id}', color=0x00FFFF)
        embed_response.add_field(name='Message Info', 
                                value=f'**Has Webhook ID**: {bool(message.webhook_id)}\n**Author**: {message.author}\n**Embeds**: {len(message.embeds)}',
                                inline=False)
        
        for result in results:
            embed_response.add_field(
                name=f'Embed {result["embed_index"]} Analysis',
                value=f'**Field Names**: {", ".join(result["field_names"][:5])}{"..." if len(result["field_names"]) > 5 else ""}\n\n**Detection Results**:\n• Detected Webhook: {"✅" if result["detected_webhook"] else "❌"}\n• Type: {result["detected_type"]}\n• **Would Process**: {"✅" if result["would_process"] else "❌"}',
                inline=False
            )
        
        await interaction.response.send_message(embed=embed_response, ephemeral=True)

    @bot.tree.command(name='simple_embed_debug', description='Simple embed debugging without fetching messages')
    async def simple_embed_debug(interaction: discord.Interaction, search_limit: int = 10):
        """Simple embed debugging that just looks at message history"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        results = []
        
        try:
            async for message in interaction.channel.history(limit=search_limit):
                if message.embeds:
                    for i, embed in enumerate(message.embeds):
                        try:
                            field_names = {f.name for f in embed.fields}
                            
                            # Safe access to properties
                            title = getattr(embed, 'title', None) or ''
                            description = getattr(embed, 'description', None) or ''
                            
                            # Use the new detection function
                            is_webhook, webhook_type = detect_webhook_type(embed, field_names)
                            
                            results.append({
                                'message_id': message.id,
                                'embed_index': i,
                                'is_webhook': bool(getattr(message, 'webhook_id', None)),
                                'webhook_id': getattr(message, 'webhook_id', None),
                                'author_name': str(message.author),
                                'title': title[:100] + ('...' if len(title) > 100 else ''),
                                'description': description[:100] + ('...' if len(description) > 100 else ''),
                                'field_count': len(embed.fields),
                                'field_names': [f.name for f in embed.fields],
                                'detected_webhook': is_webhook,
                                'detected_type': webhook_type,
                                'would_process': bool(getattr(message, 'webhook_id', None)) and is_webhook
                            })
                        except Exception as e:
                            results.append({
                                'message_id': message.id,
                                'embed_index': i,
                                'error': f'Error processing embed: {str(e)}'
                            })
        
        except Exception as e:
            return await interaction.response.send_message(f'❌ Error scanning messages: {str(e)}', ephemeral=True)
        
        if not results:
            return await interaction.response.send_message('📭 No embeds found in recent messages.', ephemeral=True)
        
        # Create summary
        total_embeds = len(results)
        webhook_embeds = sum(1 for r in results if r.get('is_webhook', False))
        detected_webhooks = sum(1 for r in results if r.get('detected_webhook', False))
        would_process = sum(1 for r in results if r.get('would_process', False))
        
        # Count by type
        type_counts = {}
        for r in results:
            if r.get('detected_webhook', False):
                webhook_type = r.get('detected_type', 'unknown')
                type_counts[webhook_type] = type_counts.get(webhook_type, 0) + 1
        
        summary_embed = discord.Embed(title='Simple Embed Debug Results', color=0x00FF00)
        summary_embed.add_field(name='Summary', 
                               value=f'**Total Embeds**: {total_embeds}\n**Webhook Embeds**: {webhook_embeds}\n**Detected Webhooks**: {detected_webhooks}\n**Would Process**: {would_process}',
                               inline=False)
        
        if type_counts:
            type_summary = ', '.join([f'{t}: {c}' for t, c in type_counts.items()])
            summary_embed.add_field(name='Detected Types', value=type_summary, inline=False)
        
        # Show details for first few embeds
        for result in results[:5]:
            if 'error' in result:
                summary_embed.add_field(name=f'Message {result["message_id"]} (Error)', 
                                       value=result['error'], inline=False)
            else:
                field_names_str = ', '.join(result['field_names'][:5])
                if len(result['field_names']) > 5:
                    field_names_str += '...'
                
                summary_embed.add_field(
                    name=f'Message {result["message_id"]} (Embed {result["embed_index"]})',
                    value=f'**Webhook**: {"✅" if result["is_webhook"] else "❌"}\n**Author**: {result["author_name"]}\n**Title**: {result["title"] or "None"}\n**Fields**: {field_names_str}\n**Detected**: {"✅" if result["detected_webhook"] else "❌"} ({result["detected_type"]})\n**Would Process**: {"✅" if result["would_process"] else "❌"}',
                    inline=False
                )
        
        if len(results) > 5:
            summary_embed.add_field(name='Note', value=f'Showing first 5 of {len(results)} embeds', inline=False)
        
        await interaction.response.send_message(embed=summary_embed, ephemeral=True)

    @bot.tree.command(name='raw_field_debug', description='Show raw field names and values for recent embeds')
    async def raw_field_debug(interaction: discord.Interaction, search_limit: int = 5):
        """Show raw field data to debug field name issues"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        found_embeds = []
        
        try:
            async for message in interaction.channel.history(limit=search_limit):
                if message.embeds:
                    for i, embed in enumerate(message.embeds):
                        embed_data = {
                            'message_id': message.id,
                            'embed_index': i,
                            'is_webhook': bool(getattr(message, 'webhook_id', None)),
                            'title': getattr(embed, 'title', None),
                            'description': getattr(embed, 'description', None),
                            'fields': []
                        }
                        
                        for field in embed.fields:
                            embed_data['fields'].append({
                                'name': repr(field.name),  # Use repr to see exact string
                                'value_preview': (field.value or '')[:150] + ('...' if field.value and len(field.value) > 150 else ''),
                                'inline': field.inline
                            })
                        
                        found_embeds.append(embed_data)
        
        except Exception as e:
            return await interaction.response.send_message(f'❌ Error: {str(e)}', ephemeral=True)
        
        if not found_embeds:
            return await interaction.response.send_message('📭 No embeds found.', ephemeral=True)
        
        # Show detailed field info for each embed
        for embed_data in found_embeds[:3]:  # Show first 3 embeds
            debug_embed = discord.Embed(title=f'Raw Fields: Message {embed_data["message_id"]}', color=0xFF9900)
            debug_embed.add_field(name='Basic Info',
                                 value=f'**Is Webhook**: {embed_data["is_webhook"]}\n**Title**: {embed_data["title"] or "None"}\n**Field Count**: {len(embed_data["fields"])}',
                                 inline=False)
            
            if embed_data['fields']:
                field_list = []
                for j, field in enumerate(embed_data['fields'][:10]):  # Show first 10 fields
                    field_list.append(f'{j+1}. {field["name"]} = "{field["value_preview"]}"')
                
                debug_embed.add_field(name='Field Names & Values',
                                     value='\n'.join(field_list) if field_list else 'No fields',
                                     inline=False)
                
                if len(embed_data['fields']) > 10:
                    debug_embed.add_field(name='Note', value=f'Showing first 10 of {len(embed_data["fields"])} fields', inline=False)
            
            await interaction.followup.send(embed=debug_embed, ephemeral=True)
        
        # Send initial response
        await interaction.response.send_message(f'📊 Found {len(found_embeds)} embeds. Showing detailed field info for first 3.', ephemeral=True)

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
        details.add_field(name="Tip:", value=f"```{clean_tip_amount(info['tip'])}```", inline=False)

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

        # Send initial response to prevent timeout
        await interaction.response.send_message("🔄 Working on your Fusion order...", ephemeral=True)

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.followup.send("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)

        was_last_card = False
        if card_number and card_cvv:
            number, cvv = card_number, card_cvv
            card = (number, cvv)
            card_source = "custom"
        else:
            card_result = bot.get_and_remove_card()
            if card_result is None:
                return await interaction.followup.send("❌ Card pool is empty.", ephemeral=True)
            if len(card_result) == 3:
                number, cvv, was_last_card = card_result
                card = (number, cvv)
            else:
                card = card_result
                was_last_card = False
            card_source = "pool"

        was_last_email = False
        email_pool_used = "fusion"
        if custom_email:
            email = custom_email
            email_source = "custom"
            email_pool_used = "custom"
        else:
            # Check pool counts before pulling to determine which pool will be used
            pool_counts_before = bot.get_pool_counts()
            fusion_count_before = pool_counts_before['emails']['fusion']

            email_result = bot.get_and_remove_email('fusion', fallback_to_main=True)
            if email_result is None:
                return await interaction.followup.send("❌ Fusion and main email pools are empty.", ephemeral=True)
            email = email_result
            email_source = "pool"

            # Determine which pool was actually used
            if fusion_count_before > 0:
                email_pool_used = "fusion"
            else:
                email_pool_used = "main"

            pool_counts = bot.get_pool_counts()
            was_last_email = pool_counts['emails'][email_pool_used] == 0

        raw_name = info['name']
        parts = [f"/order uber order_details:{info['link']},{number},{EXP_MONTH},{EXP_YEAR},{cvv},{ZIP_CODE},{email}"]
        if is_valid_field(raw_name):
            name = normalize_name(raw_name)
            parts.append(f"override_name:{name}")
        if is_valid_field(info['addr2']):
            parts.append(f"override_aptorsuite:{info['addr2']}")
        notes = info['notes'].strip()
        if is_valid_field(notes):
            parts.append(f"override_notes:{notes}")
            if 'leave' in notes.lower():
                parts.append("override_dropoff:Leave at Door")
        # Add tip override if present
        tip_amount = clean_tip_amount(info['tip'])
        if tip_amount:
            parts.append(f"override_tip:{tip_amount}")

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
                additional_data={"parsed_fields": info, "card_source": card_source, "email_source": email_source, "email_pool": email_pool_used},
            )

        embed = discord.Embed(title="Fusion Order", color=0x0099ff)
        embed.add_field(name="", value=f"```{command}```", inline=False)
        embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
        pool_counts = bot.get_pool_counts()
        card_count = pool_counts['cards']
        warnings = []
        if was_last_card and card_source == "pool":
            warnings.append("⚠️ Card pool empty!")
        if was_last_email and email_source == "pool":
            warnings.append(f"⚠️ {email_pool_used} email pool empty!")
        footer_parts = [f"Cards: {card_count}"]
        for pool_name, email_count in pool_counts['emails'].items():
            footer_parts.append(f"{pool_name}: {email_count}")
        footer_parts.extend(warnings)
        embed.set_footer(text=" | ".join(footer_parts))

        # Handle interaction timeout for final response
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            print("Fusion order interaction expired")
            return
        except discord.HTTPException as e:
            print(f"Failed to send fusion order response: {e}")
            return
    
    @bot.tree.command(name='debug_stewardess_webhook', description='Debug the stewardess webhook specifically')
    async def debug_stewardess_webhook(interaction: discord.Interaction):
        """Debug the specific stewardess webhook that's not being detected"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        target_message_id = 1381820637600808960  # The stewardess webhook
        found_message = None
        
        try:
            # Look for the message in recent history
            async for message in interaction.channel.history(limit=50):
                if message.id == target_message_id:
                    found_message = message
                    break
            
            if not found_message:
                return await interaction.response.send_message('❌ Could not find the stewardess webhook message.', ephemeral=True)
            
            if not found_message.embeds:
                return await interaction.response.send_message('❌ Message has no embeds.', ephemeral=True)
            
            embed = found_message.embeds[0]  # First embed
            
            # Get all the raw data
            field_names = {f.name for f in embed.fields}
            
            # Use the new detection function
            is_webhook, webhook_type = detect_webhook_type(embed, field_names)
            
            detection_results = {
                'has_webhook_id': bool(found_message.webhook_id),
                'webhook_id': found_message.webhook_id,
                'author': str(found_message.author),
                'title': embed.title,
                'description': embed.description,
                'description_preview': (embed.description or '')[:500] + ('...' if embed.description and len(embed.description) > 500 else ''),
                'field_count': len(embed.fields),
                'field_names': list(field_names),
                'detected_webhook': is_webhook,
                'detected_type': webhook_type,
                'would_process': bool(found_message.webhook_id) and is_webhook
            }
            
            # Test parsing if detected as webhook
            parsed_data = None
            parsing_error = None
            if is_webhook:
                try:
                    parsed_data = helpers.parse_webhook_fields(embed)
                except Exception as e:
                    parsing_error = str(e)
            
            # Create debug response
            debug_embed = discord.Embed(title='Stewardess Webhook Debug', color=0xFF0000)
            
            # Basic info
            debug_embed.add_field(
                name='Basic Info',
                value=f'**Webhook ID**: {detection_results["webhook_id"]}\n**Author**: {detection_results["author"]}\n**Title**: {detection_results["title"] or "None"}\n**Field Count**: {detection_results["field_count"]}\n**Has Description**: {bool(detection_results["description"])}',
                inline=False
            )
            
            # Description preview
            if detection_results['description_preview']:
                debug_embed.add_field(
                    name='Description Preview',
                    value=f'```{detection_results["description_preview"]}```',
                    inline=False
                )
            
            # All field names
            debug_embed.add_field(
                name='All Field Names',
                value=', '.join(f'"{name}"' for name in detection_results['field_names']) if detection_results['field_names'] else 'None',
                inline=False
            )
            
            # Detection results
            debug_embed.add_field(name='Detection Results', 
                                 value=f'**Detected Webhook**: {"✅" if detection_results["detected_webhook"] else "❌"}\n**Type**: {detection_results["detected_type"]}\n**Would Process**: {"✅" if detection_results["would_process"] else "❌"}',
                                 inline=False)
            
            # Show parsing results
            if parsed_data:
                debug_embed.add_field(
                    name='Parsed Data',
                    value=f'**Name**: "{parsed_data.get("name", "None")}"\n**Store**: "{parsed_data.get("store", "None")}"\n**Type**: "{parsed_data.get("type", "None")}"\n**Address**: "{parsed_data.get("address", "None")}"\n**Email**: "{parsed_data.get("payment", "None")}"',
                    inline=False
                )
            elif parsing_error:
                debug_embed.add_field(name='Parsing Error', value=parsing_error, inline=False)
            elif detection_results['detected_webhook']:
                debug_embed.add_field(name='Parsing', value='Detected as webhook but no parsing attempted', inline=False)
            
            await interaction.response.send_message(embed=debug_embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f'❌ Error debugging message: {str(e)}', ephemeral=True)

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

        # Send initial response to prevent timeout
        try:
            await interaction.response.send_message("Processing wool order...", ephemeral=True)
        except discord.errors.NotFound:
            return
        except discord.HTTPException:
            return

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.followup.send("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)

        was_last_card = False
        if card_number and card_cvv:
            number, cvv = card_number, card_cvv
            card = (number, cvv)
            card_source = "custom"
        else:
            card_result = bot.get_and_remove_card()
            if card_result is None:
                return await interaction.followup.send("❌ Card pool is empty.", ephemeral=True)
            if len(card_result) == 3:
                number, cvv, was_last_card = card_result
                card = (number, cvv)
            else:
                card = card_result
                was_last_card = False
            card_source = "pool"

        was_last_email = False
        email_pool_used = "wool"
        if custom_email:
            email = custom_email
            email_source = "custom"
            email_pool_used = "custom"
        else:
            # Check pool counts before pulling to determine which pool will be used
            pool_counts_before = bot.get_pool_counts()
            wool_count_before = pool_counts_before['emails']['wool']

            email_result = bot.get_and_remove_email('wool', fallback_to_main=True)
            if email_result is None:
                return await interaction.followup.send("❌ Wool and main email pools are empty.", ephemeral=True)
            email = email_result
            email_source = "pool"

            # Determine which pool was actually used
            if wool_count_before > 0:
                email_pool_used = "wool"
            else:
                email_pool_used = "main"

            pool_counts = bot.get_pool_counts()
            was_last_email = pool_counts['emails'][email_pool_used] == 0

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
                additional_data={"parsed_fields": info, "card_source": card_source, "email_source": email_source, "email_pool": email_pool_used},
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
        embed.add_field(name="Tip:", value=f"```{clean_tip_amount(info['tip'])}```", inline=False)
        pool_counts = bot.get_pool_counts()
        card_count = pool_counts['cards']
        warnings = []
        if was_last_card and card_source == "pool":
            warnings.append("⚠️ Card pool empty!")
        if was_last_email and email_source == "pool":
            warnings.append(f"⚠️ {email_pool_used} email pool empty!")
        footer_parts = [f"Cards: {card_count}"]
        for pool_name, email_count in pool_counts['emails'].items():
            footer_parts.append(f"{pool_name}: {email_count}")
        footer_parts.extend(warnings)
        embed.set_footer(text=" | ".join(footer_parts))
        
        # Handle interaction timeout
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            # Interaction expired, try to send as followup if possible
            print("Wool order interaction expired")
            return
        except discord.HTTPException as e:
            print(f"Failed to send wool order response: {e}")
            return

    @bot.tree.command(name='tomato_order', description='Format a Tomato order')
    @app_commands.describe(
        custom_email='Optional: Use a specific email instead of pool',
        card_number='Optional: Use a specific card number instead of pool',
        card_cvv='Optional: CVV for custom card'
    )
    async def tomato_order(interaction: discord.Interaction, custom_email: str = None,
                        card_number: str = None, card_cvv: str = None):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

        if card_number and not card_cvv:
            return await interaction.response.send_message("❌ CVV required when using custom card number.", ephemeral=True)
        if card_cvv and not card_number:
            return await interaction.response.send_message("❌ Card number required when using custom CVV.", ephemeral=True)

        # Send initial response to prevent timeout
        try:
            await interaction.response.send_message("Processing tomato order...", ephemeral=True)
        except discord.errors.NotFound:
            return
        except discord.HTTPException:
            return

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.followup.send("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)

        was_last_card = False
        if card_number and card_cvv:
            number, cvv = card_number, card_cvv
            card = (number, cvv)
            card_source = "custom"
        else:
            card_result = bot.get_and_remove_card()
            if card_result is None:
                return await interaction.followup.send("❌ Card pool is empty.", ephemeral=True)
            if len(card_result) == 3:
                number, cvv, was_last_card = card_result
                card = (number, cvv)
            else:
                card = card_result
                was_last_card = False
            card_source = "pool"

        was_last_email = False
        email_pool_used = "fusion"
        if custom_email:
            email = custom_email
            email_source = "custom"
            email_pool_used = "custom"
        else:
            # Check pool counts before pulling to determine which pool will be used
            pool_counts_before = bot.get_pool_counts()
            fusion_count_before = pool_counts_before['emails']['fusion']

            email_result = bot.get_and_remove_email('fusion', fallback_to_main=True)
            if email_result is None:
                return await interaction.followup.send("❌ Fusion and main email pools are empty.", ephemeral=True)
            email = email_result
            email_source = "pool"

            # Determine which pool was actually used
            if fusion_count_before > 0:
                email_pool_used = "fusion"
            else:
                email_pool_used = "main"

            pool_counts = bot.get_pool_counts()
            was_last_email = pool_counts['emails'][email_pool_used] == 0

        # Format: !otp email,link,cardnum,exp_month,exp_year,cvv,zip
        command = f"!otp {email},{info['link']},{number},{EXP_MONTH},{EXP_YEAR},{cvv},{ZIP_CODE}"

        if card_source == "pool" or email_source == "pool":
            log_command_output(
                command_type="tomato_order",
                user_id=interaction.user.id,
                username=str(interaction.user),
                channel_id=interaction.channel.id,
                guild_id=interaction.guild.id if interaction.guild else None,
                command_output=command,
                tip_amount=info['tip'],
                card_used=card if card_source == "pool" else None,
                email_used=email if email_source == "pool" else None,
                additional_data={"parsed_fields": info, "card_source": card_source, "email_source": email_source, "email_pool": email_pool_used},
            )

        embed = discord.Embed(title="Tomato Order", color=0xFF6347)  # Tomato red color
        embed.add_field(name="", value=f"```{command}```", inline=False)
        embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
        if is_valid_field(info['name']):
            formatted = format_name_csv(info['name'])
            embed.add_field(name="Name:", value=f"```{formatted}```", inline=False)
        if is_valid_field(info['addr2']):
            embed.add_field(name="Apt / Suite / Floor:", value=f"```{info['addr2']}```", inline=False)
        if is_valid_field(info['notes']):
            embed.add_field(name="Delivery Notes:", value=f"```{info['notes']}```", inline=False)
        embed.add_field(name="Tip:", value=f"```{clean_tip_amount(info['tip'])}```", inline=False)
        pool_counts = bot.get_pool_counts()
        card_count = pool_counts['cards']
        warnings = []
        if was_last_card and card_source == "pool":
            warnings.append("⚠️ Card pool empty!")
        if was_last_email and email_source == "pool":
            warnings.append(f"⚠️ {email_pool_used} email pool empty!")
        footer_parts = [f"Cards: {card_count}"]
        for pool_name, email_count in pool_counts['emails'].items():
            footer_parts.append(f"{pool_name}: {email_count}")
        footer_parts.extend(warnings)
        embed.set_footer(text=" | ".join(footer_parts))

        # Handle interaction timeout
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            # Interaction expired, try to send as followup if possible
            print("Tomato order interaction expired")
            return
        except discord.HTTPException as e:
            print(f"Failed to send tomato order response: {e}")
            return

    @bot.tree.command(name='payments', description='Display payment methods')
    async def payments(interaction: discord.Interaction):
        try:
            # Create and send response as quickly as possible
            embed = discord.Embed(
                title="Prin's Payments",
                description="Select which payment method you would like to use! (Zelle/Crypto is preferred)",
                color=0x9932cc,
            )
            
            # Import and create view inline to avoid any import issues
            from ..views import PaymentView as PV
            view = PV()
            
            # Send response within the 3-second window
            await interaction.response.send_message(embed=embed, view=view)
            
        except discord.errors.NotFound:
            # Interaction already expired, nothing we can do
            print("Payment command interaction expired (this is normal if the command was called multiple times)")
        except ImportError as e:
            print(f"Import error in payments command: {e}")
            await interaction.response.send_message("❌ Error loading payment methods. Please contact an admin.", ephemeral=True)
        except Exception as e:
            print(f"Unexpected error in payments command: {type(e).__name__}: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred. Please try again.", ephemeral=True)

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
        
        # Always scan for the latest webhooks to ensure we have fresh data
        await interaction.response.send_message('🔍 Scanning for latest webhooks...', ephemeral=True)
        
        # Get the default tracking channel
        tracking_channel = interaction.guild.get_channel(1352067371006693499)  # Default tracking channel ID
        
        if not tracking_channel:
            return await interaction.followup.send('❌ Could not access tracking channel for scanning.', ephemeral=True)
        
        # Scan recent messages for webhooks (last 25 messages should be enough for recent orders)
        scan_limit = 25
        found_webhooks = 0
        cached_webhooks = 0
        updated_webhooks = 0
        order_placed_webhooks = 0
        tracking_webhooks = 0
        checkout_webhooks = 0
        
        try:
            async for message in tracking_channel.history(limit=scan_limit):
                if message.webhook_id and message.embeds:
                    for embed in message.embeds:
                        field_names = {f.name for f in embed.fields}
                        
                        # Use the new detection function
                        is_webhook, webhook_type = detect_webhook_type(embed, field_names)
                        
                        if is_webhook:
                            found_webhooks += 1
                            
                            if webhook_type == "order_placed":
                                order_placed_webhooks += 1
                            elif webhook_type == "tracking":
                                tracking_webhooks += 1
                            elif webhook_type == "checkout":
                                checkout_webhooks += 1
                            
                            try:
                                webhook_data = helpers.parse_webhook_fields(embed)
                                
                                # Cache with message timestamp for proper ordering
                                success = helpers.cache_webhook_data(
                                    webhook_data, 
                                    message_timestamp=message.created_at,
                                    message_id=message.id
                                )
                                
                                if success:
                                    cached_webhooks += 1
                                else:
                                    updated_webhooks += 1
                            except Exception as e:
                                continue
            
            # Find the latest matching webhook data after scanning
            data = helpers.find_latest_matching_webhook_data(ticket_name)
            
            if data:
                type_summary = f"{order_placed_webhooks} order_placed, {tracking_webhooks} tracking, {checkout_webhooks} checkout"
                await interaction.followup.send(f'✅ Found matching webhook! Scanned {scan_limit} messages, found {found_webhooks} webhooks ({type_summary}). New: {cached_webhooks}, existing: {updated_webhooks}.', ephemeral=True)
            else:
                # No match - show detailed debug info
                cache_keys = []
                for (cached_name, cached_addr), cache_entry in helpers.ORDER_WEBHOOK_CACHE.items():
                    cache_keys.append(cached_name)
                
                debug_msg = f'❌ No matching webhook found after scanning.\n**Ticket name:** `{ticket_name}` → `{normalized_ticket_name}`\n**Scanned:** {scan_limit} messages, found {found_webhooks} webhooks ({cached_webhooks} new, {updated_webhooks} existing)\n**All cached names:** {", ".join(cache_keys[:15])}{"..." if len(cache_keys) > 15 else ""}'
                return await interaction.followup.send(debug_msg, ephemeral=True)
                
        except Exception as e:
            return await interaction.followup.send(f'❌ Error scanning webhooks: {str(e)}', ephemeral=True)

        # Create tracking embed based on webhook type
        webhook_type = data.get('type', 'unknown')
        tracking_url = data.get('tracking', '')

        if webhook_type == 'tracking':
            e = discord.Embed(title='Order Placed!', url=data.get('tracking'), color=0x00ff00)

            if tracking_url:
                tracking_text = f"Here are your order details:\n\n**🔗 Tracking Link**\n[Click here]({tracking_url})"
                e.add_field(name='', value=tracking_text, inline=False)
            
            e.add_field(name='Store', value=data.get('store'), inline=False)
            eta_value = data.get('eta')
            if eta_value:
                eta_value = convert_24h_to_12h(eta_value)
            e.add_field(name='Estimated Arrival', value=eta_value, inline=False)
            e.add_field(name='Order Items', value=data.get('items'), inline=False)
            e.add_field(name='Name', value=data.get('name'), inline=False)
            e.add_field(name='Delivery Address', value=data.get('address'), inline=False)
            e.set_footer(text='Watch the tracking link for updates!')

        elif webhook_type == 'order_placed':
            # Handle "Order Successfully Placed" format
            e = discord.Embed(title='🎉 Order Successfully Placed!', url=data.get('tracking'), color=0x00ff00)
            
            if tracking_url:
                tracking_text = f"Your order has been successfully placed!\n\n**🔗 Order Details**\n[Click here]({tracking_url})"
                e.add_field(name='', value=tracking_text, inline=False)
            
            e.add_field(name='Store', value=data.get('store'), inline=False)
            
            # Add estimated delivery time if available
            eta_value = data.get('eta')
            if eta_value and eta_value != 'N/A':
                e.add_field(name='Estimated Delivery Time', value=eta_value, inline=False)
            
            # Add order items
            if data.get('items'):
                e.add_field(name='Order Items', value=data.get('items'), inline=False)
            
            # Add customer name
            e.add_field(name='Customer', value=data.get('name'), inline=False)
            
            # Add delivery address
            if data.get('address'):
                e.add_field(name='Delivery Address', value=data.get('address'), inline=False)
            
            # Add total if available
            if data.get('total'):
                e.add_field(name='Total', value=data.get('total'), inline=False)
            
            e.set_footer(text='Check the order link for real-time updates!')

        else:  # checkout or unknown
            e = discord.Embed(title='Checkout Successful!', url=data.get('tracking'), color=0x00ff00)
            
            if tracking_url:
                tracking_text = f"Here are your order details:\n\n**🔗 Tracking Link**\n[Click here]({tracking_url})"
                e.add_field(name='', value=tracking_text, inline=False)
            
            e.add_field(name='Store', value=data.get('store'), inline=False)
            if data.get('eta') and data.get('eta') != 'N/A':
                eta_value = convert_24h_to_12h(data.get('eta'))
                e.add_field(name='Estimated Arrival', value=eta_value, inline=False)
            if data.get('items'):
                e.add_field(name='Items Ordered', value=data.get('items'), inline=False)
            e.add_field(name='Name', value=data.get('name'), inline=False)
            if data.get('address'):
                e.add_field(name='Delivery Address', value=data.get('address'), inline=False)
            e.set_footer(text='Watch the tracking link for updates!')

        await interaction.followup.send(embed=e)

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
        
        await interaction.response.send_message(embed=debug, ephemeral=True)

    @bot.tree.command(name='scan_webhooks', description='Scan tracking channel for webhook orders')
    async def scan_webhooks(interaction: discord.Interaction, channel_id: str = None, search_limit: int = 50):
        """Manually scan a channel for webhook order confirmations and cache them"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        # Respond immediately to avoid timeout
        await interaction.response.send_message('🔍 Starting webhook scan...', ephemeral=True)
        
        # Default to tracking channel if no channel specified
        if channel_id:
            try:
                target_channel = interaction.guild.get_channel(int(channel_id))
            except ValueError:
                return await interaction.followup.send('❌ Invalid channel ID.', ephemeral=True)
        else:
            target_channel = interaction.guild.get_channel(1352067371006693499)  # Default tracking channel
        
        if not target_channel:
            return await interaction.followup.send('❌ Channel not found.', ephemeral=True)
        
        found_webhooks = 0
        cached_webhooks = 0
        updated_webhooks = 0
        order_placed_webhooks = 0
        tracking_webhooks = 0
        checkout_webhooks = 0
        processed_messages = 0
        errors = []
        
        try:
            # Send progress updates during scanning
            progress_message = None
            
            async for message in target_channel.history(limit=search_limit):
                processed_messages += 1
                
                # Send progress update every 25 messages
                if processed_messages % 25 == 0:
                    try:
                        if progress_message is None:
                            progress_message = await interaction.followup.send(
                                f'📊 Progress: {processed_messages}/{search_limit} messages scanned...', 
                                ephemeral=True
                            )
                        else:
                            await progress_message.edit(
                                content=f'📊 Progress: {processed_messages}/{search_limit} messages scanned...'
                            )
                    except Exception:
                        # Ignore progress update errors
                        pass
                
                if message.webhook_id and message.embeds:
                    for embed in message.embeds:
                        try:
                            field_names = {f.name for f in embed.fields}
                            
                            # Use the new detection function
                            is_webhook, webhook_type = detect_webhook_type(embed, field_names)
                            
                            if is_webhook:
                                found_webhooks += 1
                                
                                if webhook_type == "order_placed":
                                    order_placed_webhooks += 1
                                elif webhook_type == "tracking":
                                    tracking_webhooks += 1
                                elif webhook_type == "checkout":
                                    checkout_webhooks += 1
                                
                                data = helpers.parse_webhook_fields(embed)
                                
                                # Use new caching function with timestamp
                                success = helpers.cache_webhook_data(
                                    data,
                                    message_timestamp=message.created_at,
                                    message_id=message.id
                                )
                                
                                if success:
                                    cached_webhooks += 1
                                else:
                                    updated_webhooks += 1  # Older entry, didn't update cache
                        
                        except Exception as e:
                            errors.append(f"Error parsing embed in message {message.id}: {str(e)}")
                            continue
                            
        except Exception as e:
            await interaction.followup.send(f'❌ Error scanning channel: {str(e)}', ephemeral=True)
            return
        
        # Send final results
        embed = discord.Embed(title='Webhook Scan Results', color=0x00FF00)
        embed.add_field(name='Channel Scanned', value=target_channel.mention, inline=False)
        embed.add_field(name='Messages Searched', value=str(processed_messages), inline=False)
        embed.add_field(name='Total Webhook Orders Found', value=str(found_webhooks), inline=False)
        embed.add_field(name='├─ Order Placed Webhooks', value=str(order_placed_webhooks), inline=True)
        embed.add_field(name='├─ Tracking Webhooks', value=str(tracking_webhooks), inline=True)
        embed.add_field(name='└─ Checkout Webhooks', value=str(checkout_webhooks), inline=True)
        embed.add_field(name='New Entries Cached', value=str(cached_webhooks), inline=False)
        embed.add_field(name='Older Entries Skipped', value=str(updated_webhooks), inline=False)
        embed.add_field(name='Total Cache Size', value=str(len(helpers.ORDER_WEBHOOK_CACHE)), inline=False)
        
        if errors:
            embed.add_field(name='Errors Encountered', value=f'{len(errors)} parsing errors', inline=False)
        
        if helpers.ORDER_WEBHOOK_CACHE:
            # Show most recent entries by timestamp
            sorted_cache = sorted(
                helpers.ORDER_WEBHOOK_CACHE.items(),
                key=lambda x: x[1]['timestamp'],
                reverse=True
            )
            recent_names = []
            for (name, addr), cache_entry in sorted_cache[:5]:
                data = cache_entry['data']
                store = data.get('store', 'Unknown')
                webhook_type = data.get('type', 'unknown')
                timestamp = cache_entry['timestamp'].strftime('%m/%d %H:%M')
                recent_names.append(f"{name} ({store}) [{webhook_type}] - {timestamp}")
            embed.add_field(name='Most Recent Cached Orders', value='\n'.join(recent_names), inline=False)
        
        # Clean up progress message if it exists
        if progress_message:
            try:
                await progress_message.delete()
            except Exception:
                pass
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # If there were errors, send them in a separate message
        if errors and len(errors) <= 10:
            error_text = '\n'.join(errors[:10])
            await interaction.followup.send(f'⚠️ **Parsing Errors:**\n```\n{error_text}\n```', ephemeral=True)

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
        order_placed_count = sum(1 for cache_entry in helpers.ORDER_WEBHOOK_CACHE.values() if cache_entry['data'].get('type') == 'order_placed')
        tracking_count = sum(1 for cache_entry in helpers.ORDER_WEBHOOK_CACHE.values() if cache_entry['data'].get('type') == 'tracking')
        checkout_count = sum(1 for cache_entry in helpers.ORDER_WEBHOOK_CACHE.values() if cache_entry['data'].get('type') == 'checkout')
        unknown_count = len(helpers.ORDER_WEBHOOK_CACHE) - order_placed_count - tracking_count - checkout_count
        
        type_summary = []
        if order_placed_count > 0:
            type_summary.append(f"Order Placed: {order_placed_count}")
        if tracking_count > 0:
            type_summary.append(f"Tracking: {tracking_count}")
        if checkout_count > 0:
            type_summary.append(f"Checkout: {checkout_count}")
        if unknown_count > 0:
            type_summary.append(f"Unknown: {unknown_count}")
        
        if type_summary:
            embed.add_field(name='By Type', value=' | '.join(type_summary), inline=False)
        
        cache_entries = []
        for (name, addr), cache_entry in helpers.ORDER_WEBHOOK_CACHE.items():
            data = cache_entry['data']
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
        
        await interaction.response.send_message(embed=debug, ephemeral=True)

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
                        field_names = {f.name for f in embed.fields}
                        
                        # Use the new detection function
                        is_webhook, webhook_type = detect_webhook_type(embed, field_names)
                        
                        if is_webhook:
                            # Parse the webhook
                            parsed_data = helpers.parse_webhook_fields(embed)
                            
                            results.append({
                                'message_id': message.id,
                                'embed_index': i,
                                'title': embed.title or 'No Title',
                                'description': (embed.description or '')[:100] + ('...' if embed.description and len(embed.description) > 100 else ''),
                                'field_names': list(field_names),
                                'detected_type': webhook_type,
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
        
        # Count by type
        type_counts = {}
        for result in results:
            webhook_type = result['detected_type']
            type_counts[webhook_type] = type_counts.get(webhook_type, 0) + 1
        
        if type_counts:
            type_summary = ', '.join([f'{t}: {c}' for t, c in type_counts.items()])
            embed.add_field(name='By Type', value=type_summary, inline=False)
        
        for i, result in enumerate(results[:3], 1):  # Show first 3 results
            embed.add_field(
                name=f'Webhook {i}: {result["title"]} ({result["detected_type"]})',
                value=f'**Type**: {result["parsed_type"]}\n**Name**: {result["parsed_name"]}\n**Store**: {result["parsed_store"]}\n**Address**: {result["parsed_address"]}\n**Fields**: {", ".join(result["field_names"][:3])}...',
                inline=False
            )
        
        if len(results) > 3:
            embed.add_field(name='Note', value=f'Showing first 3 of {len(results)} results', inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name='debug_cache_timestamps', description='Show cache entries with timestamps for debugging')
    async def debug_cache_timestamps(interaction: discord.Interaction, name_filter: str = None):
        """Show cache entries with timestamps to debug recency issues"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        if not helpers.ORDER_WEBHOOK_CACHE:
            return await interaction.response.send_message('📭 Webhook cache is empty.', ephemeral=True)
        
        # Filter entries if name provided
        filtered_cache = {}
        if name_filter:
            name_filter_lower = name_filter.lower()
            for key, cache_entry in helpers.ORDER_WEBHOOK_CACHE.items():
                name, addr = key
                if name_filter_lower in name.lower():
                    filtered_cache[key] = cache_entry
        else:
            filtered_cache = helpers.ORDER_WEBHOOK_CACHE
        
        if not filtered_cache:
            return await interaction.response.send_message(f'📭 No cache entries found matching "{name_filter}".', ephemeral=True)
        
        # Sort by timestamp (most recent first)
        sorted_entries = sorted(
            filtered_cache.items(),
            key=lambda x: x[1]['timestamp'],
            reverse=True
        )
        
        embed = discord.Embed(title='Cache Debug - Timestamps', color=0xFF9900)
        if name_filter:
            embed.add_field(name='Filter Applied', value=f'Names containing: "{name_filter}"', inline=False)
        
        embed.add_field(name='Total Entries', value=f'{len(filtered_cache)} (of {len(helpers.ORDER_WEBHOOK_CACHE)} total)', inline=False)
        
        # Show detailed entries with character limit handling
        entries_shown = 0
        current_field_text = ""
        field_number = 1
        
        for i, ((name, addr), cache_entry) in enumerate(sorted_entries[:15], 1):
            data = cache_entry['data']
            timestamp = cache_entry['timestamp']
            message_id = cache_entry.get('message_id', 'Unknown')
            
            store = data.get('store', 'Unknown')[:20] + ('...' if len(data.get('store', 'Unknown')) > 20 else '')
            webhook_type = data.get('type', 'unknown')
            
            # Format timestamp (shorter format)
            time_str = timestamp.strftime('%m/%d %H:%M')
            
            entry_text = (
                f"**{i}. {name[:25]}{'...' if len(name) > 25 else ''}**\n"
                f"   {store} | {webhook_type} | {time_str}\n"
                f"   Msg: {message_id}\n"
            )
            
            # Check if adding this entry would exceed the 1024 limit
            if len(current_field_text + entry_text) > 1000:
                # Add current field and start a new one
                if current_field_text:
                    embed.add_field(
                        name=f'Recent Entries (Part {field_number})',
                        value=current_field_text,
                        inline=False
                    )
                    field_number += 1
                    current_field_text = entry_text
                else:
                    # Single entry is too long, truncate it
                    current_field_text = entry_text[:1000] + "..."
            else:
                current_field_text += entry_text
            
            entries_shown += 1
            
            # Limit to prevent too many fields
            if field_number > 3:
                break
        
        # Add the final field if there's content
        if current_field_text:
            embed.add_field(
                name=f'Recent Entries (Part {field_number})' if field_number > 1 else f'Most Recent {entries_shown} Entries',
                value=current_field_text,
                inline=False
            )
        
        if len(sorted_entries) > entries_shown:
            embed.add_field(name='Note', value=f'Showing {entries_shown} of {len(sorted_entries)} entries (truncated due to Discord limits)', inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name='finished', description='Mark order as finished and move ticket')
    async def finished(interaction: discord.Interaction):
        """Move ticket to finished category and send completion message"""
        
        if not owner_only(interaction):
            return await interaction.response.send_message('❌ You are not authorized.', ephemeral=True)
        
        # Category ID where tickets should be moved
        FINISHED_CATEGORY_ID = 1355010691127447794
        
        # Get the current channel (ticket)
        channel = interaction.channel
        
        # Ensure we're in a text channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message('❌ This command can only be used in a text channel.', ephemeral=True)
        
        # Defer response since moving might take a moment
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get the target category
            target_category = interaction.guild.get_channel(FINISHED_CATEGORY_ID)
            
            if not target_category:
                return await interaction.followup.send('❌ Could not find the finished tickets category.', ephemeral=True)
            
            if not isinstance(target_category, discord.CategoryChannel):
                return await interaction.followup.send('❌ The specified ID is not a category.', ephemeral=True)
            
            # Move the channel to the new category
            await channel.edit(category=target_category)
            
            # Create the completion embed
            embed = discord.Embed(
                title="Your food has been ordered! 🎉",
                description="Watch the tracking link carefully for all updates! Once your food arrives, don't forget to leave a vouch in <#1350935336871792701> and feel free to close the ticket!",
                color=0x00ff00  # Green color
            )
            
            # Send the embed to the channel
            await channel.send(embed=embed)
            
            # Confirm to the user who ran the command
            await interaction.followup.send('✅ Ticket moved to finished category and completion message sent.', ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send('❌ I don\'t have permission to move this channel or send messages.', ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f'❌ Failed to move channel: {str(e)}', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'❌ An unexpected error occurred: {str(e)}', ephemeral=True)
    
    @bot.tree.command(name='reorder', description='Format a reorder command with email only')
    @app_commands.describe(
        email="Email address to use for the reorder"
    )
    async def reorder(interaction: discord.Interaction, email: str):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

        embed = await fetch_ticket_embed(interaction.channel)
        if embed is None:
            return await interaction.response.send_message("❌ Could not find order embed.", ephemeral=True)

        info = parse_fields(embed)
        
        # Build the reorder command
        raw_name = info['name']
        parts = [f"/reorder uber order_details:{info['link']},{email}"]
        
        # Add name override if valid
        if is_valid_field(raw_name):
            name = normalize_name(raw_name)
            parts.append(f"override_name:{name}")
        
        # Add apt/suite/floor override if valid
        if is_valid_field(info['addr2']):
            parts.append(f"override_aptorsuite:{info['addr2']}")
        
        # Handle delivery notes and dropoff preference
        notes = info['notes'].strip()
        if is_valid_field(notes):
            # Always add the notes
            parts.append(f"override_notes:{notes}")
            # If notes contain "leave", also set dropoff preference
            if 'leave' in notes.lower():
                parts.append("override_dropoff:Leave at Door")

        # Add tip override if present
        tip_amount = clean_tip_amount(info['tip'])
        if tip_amount:
            parts.append(f"override_tip:{tip_amount}")

        command = ' '.join(parts)

        # Create response embed
        embed = discord.Embed(title="Reorder Command", color=0xFF1493)
        embed.add_field(name="", value=f"```{command}```", inline=False)
        embed.add_field(name="**Email used:**", value=f"```{email}```", inline=False)
        
        # Log the command
        log_command_output(
            command_type="reorder",
            user_id=interaction.user.id,
            username=str(interaction.user),
            channel_id=interaction.channel.id,
            guild_id=interaction.guild.id if interaction.guild else None,
            command_output=command,
            tip_amount=info['tip'],
            card_used=None,  # No card for reorder
            email_used=email,
            additional_data={"parsed_fields": info},
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name='z', description='Parse order information and display breakdown')
    @app_commands.describe(
        order_text="Paste the order information here",
        vip="Enable VIP pricing ($6 service fee instead of $7)",
        service_fee="Override service fee (default: $7.00, VIP: $6.00)"
    )
    async def z_command(interaction: discord.Interaction, order_text: str, vip: bool = False, service_fee: str = None):
        """Parse order information and display breakdown with payment options"""
        
        # Authorization check
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)
        
        # Input validation
        MAX_ORDER_TEXT_LENGTH = 10000  # Reasonable limit
        
        if len(order_text) > MAX_ORDER_TEXT_LENGTH:
            return await interaction.response.send_message(
                f"❌ Order text is too long (max {MAX_ORDER_TEXT_LENGTH} characters).", 
                ephemeral=True
            )
        
        if len(order_text.strip()) == 0:
            return await interaction.response.send_message(
                "❌ Order text cannot be empty.", 
                ephemeral=True
            )
        
        def parse_money(value_str):
            """Extract numeric value from money string with enhanced error handling"""
            if not value_str:
                return 0.0
            
            # Remove dollar signs, commas, and whitespace
            cleaned = value_str.replace('$', '').replace(',', '').strip()
            
            # Handle parentheses for negative values (like discounts)
            if cleaned.startswith('(') and cleaned.endswith(')'):
                cleaned = '-' + cleaned[1:-1]
            
            # Handle negative values (like -$24.80 or $-24.80)
            cleaned = cleaned.replace('$-', '-').replace('-$', '-')
            
            try:
                value = float(cleaned)
                return value
            except ValueError:
                print(f"Warning: Could not parse money value: {value_str}")
                return 0.0
        
        # Parse the order text to extract values
        # First, ensure each ╰・ is on its own line
        order_text = order_text.replace(' ╰・', '\n╰・')
        order_text = order_text.replace('╰・', '\n╰・')
        
        # Handle both single-line and multi-line formats
        # Split potential single-line entries into separate lines
        text_parts = order_text.replace('FARE BREAKDOWN:', '\nFARE BREAKDOWN:').replace('CART ITEMS:', '\nCART ITEMS:')
        
        # Common patterns that should be on new lines
        # Order matters! Process longer patterns first to avoid partial matches
        patterns_to_split = [
            'Total After Tip:',  # Must come before 'Tip:'
            'Taxes & Other Fees:', 'Taxes and Other Fees:',
            'Tipping Amount:',
            'Final Total:', 'Order Total:',
            'Subtotal:', 'Promotion:', 'Delivery Fee:',
            'Uber Cash:',
            'Total:',  # After 'Total After Tip:' and 'Final Total:'
            '╰・Tip:',  # Only split when Tip has the ╰・ prefix
            # Don't split standalone 'Tip:' as it causes issues with 'Total After Tip:'
        ]
        
        for pattern in patterns_to_split:
            if pattern == 'Total After Tip:':
                # Debug this specific replacement
                if pattern in text_parts:
                    print(f"DEBUG: Found '{pattern}' in text")
                    text_parts = text_parts.replace(pattern, '\n' + pattern)
                    print(f"DEBUG: After replacing '{pattern}', relevant section: ...{text_parts[max(0, text_parts.find('Total After')-20):text_parts.find('Total After')+50]}...")
            else:
                text_parts = text_parts.replace(' ' + pattern, '\n' + pattern)
            # Don't add ╰・ prefix here since we already handled it above
        
        lines = text_parts.split('\n')
        
        # Initialize values
        subtotal = 0.0
        delivery_fee = 0.0
        taxes_fees = 0.0
        final_total = 0.0
        temp_total = 0.0  # For storing "Total:" value temporarily
        cart_items = []  # Store cart items
        tip_from_order = 0.0  # Track tip parsed from order text
        
        # Detect which format and parse accordingly
        is_format_two = ':rice:' in order_text or ':cashmachine:' in order_text
        in_cart_section = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue

            line_lower = line.lower()

            # Debug specific lines
            if 'tipping' in line_lower or ('tip' in line_lower and 'after' not in line_lower):
                print(f"DEBUG: Processing line with tip: '{line}'")
            
            # Check for cart items section
            if 'cart items:' in line_lower or 'items in bag:' in line_lower:
                in_cart_section = True
                # Handle case where cart items are on the same line as the header
                if ':' in line and len(line.split(':', 1)) > 1:
                    items_part = line.split(':', 1)[1].strip()
                    if items_part and '•' in items_part:
                        # Split on bullet points and add each item
                        items = items_part.split('•')
                        for item in items:
                            item = item.strip()
                            if item and ('(' in item and ')' in item) or ('x' in item and '$' in item):
                                cart_items.append('• ' + item)
                continue
            elif 'fare breakdown:' in line_lower or 'order total:' in line_lower:
                in_cart_section = False
                continue
            
            # Collect cart items
            if in_cart_section:
                # Format 1: • Item name (x1) - $price
                # Format 2: ╰・1x: Item name
                if line.startswith('•'):
                    cart_items.append(line)
                elif line.startswith('╰・'):
                    # Check if this is a food item (has quantity pattern like "1x:" or "2x:")
                    # and not a subtotal/pricing line
                    if 'x:' in line and not any(keyword in line_lower for keyword in ['subtotal:', 'promotion:', 'delivery', 'taxes', 'total:', 'uber cash:', 'tip:']):
                        # Clean the line to remove any emoji markers and "Order" text
                        clean_item = re.sub(r'\s*(?:<:.*?:\d+>|:.*?:)\s*Order.*$', '', line)
                        cart_items.append(clean_item.strip())
                    else:
                        # This is a pricing line, exit cart section
                        in_cart_section = False
                elif line and not any(keyword in line_lower for keyword in ['subtotal:', 'promotion:', 'delivery', 'taxes', 'total:', 'fare', 'order']):
                    # Also capture items that might not start with bullets but are in cart section
                    # Handle format: "Al Pastor Taco (x8) - $26.00"
                    if ('(' in line and ')' in line and '$' in line) or ('(x' in line and ')' in line and '-' in line):  # Likely a cart item
                        cart_items.append('• ' + line if not line.startswith('•') else line)
            
            # Parse subtotal (including "Estimated Subtotal")
            if ('subtotal:' in line_lower or 'estimated subtotal:' in line_lower) and 'cart' not in line_lower:  # Avoid cart items line
                if '╰・' in line:
                    # Format 2: ╰・Subtotal: $24.80
                    # Remove the ╰・ prefix and any extra spaces
                    clean_line = line.replace('╰・', '').strip()
                    parts = clean_line.split(':', 1)
                    if len(parts) > 1:
                        subtotal = parse_money(parts[1])
                else:
                    # Format 1: Subtotal: $28.08
                    # Split on the last colon to handle any prefixes
                    colon_idx = line.rfind(':')
                    if colon_idx != -1:
                        subtotal = parse_money(line[colon_idx + 1:])
            
            # Parse delivery fee
            elif 'delivery fee:' in line_lower:
                if '╰・' in line:
                    clean_line = line.replace('╰・', '').strip()
                    parts = clean_line.split(':', 1)
                    if len(parts) > 1:
                        delivery_fee = parse_money(parts[1])
                else:
                    colon_idx = line.rfind(':')
                    if colon_idx != -1:
                        value_str = line[colon_idx + 1:].strip()
                        delivery_fee = parse_money(value_str)
            
            # Parse taxes & fees
            elif 'taxes' in line_lower and ('fees' in line_lower or 'other' in line_lower):
                if '╰・' in line:
                    clean_line = line.replace('╰・', '').strip()
                    parts = clean_line.split(':', 1)
                    if len(parts) > 1:
                        taxes_fees = parse_money(parts[1])
                else:
                    colon_idx = line.rfind(':')
                    if colon_idx != -1:
                        taxes_fees = parse_money(line[colon_idx + 1:])

            # Parse tip from order text
            # Check if this is actually a tip line and not part of "Total After Tip:"
            elif (('tipping amount:' in line_lower) or
                  ((line_lower.startswith('tip:') or line_lower.startswith('╰・tip:')) and
                   'after' not in line_lower and
                   'total' not in line_lower)):
                if '╰・' in line:
                    clean_line = line.replace('╰・', '').strip()
                    parts = clean_line.split(':', 1)
                    if len(parts) > 1:
                        tip_from_order = parse_money(parts[1])
                else:
                    colon_idx = line.rfind(':')
                    if colon_idx != -1:
                        tip_from_order = parse_money(line[colon_idx + 1:])
            
            # Parse final total (format varies)
            elif 'total after tip:' in line_lower:
                # Format 1 - this is the most accurate
                colon_idx = line.rfind(':')
                if colon_idx != -1:
                    final_total = parse_money(line[colon_idx + 1:])
            elif 'final total:' in line_lower:
                # Format 2
                if '╰・' in line:
                    clean_line = line.replace('╰・', '').strip()
                    parts = clean_line.split(':', 1)
                    if len(parts) > 1:
                        value_str = parts[1].strip()
                        parsed_value = parse_money(value_str)
                        if parsed_value > 0:
                            final_total = parsed_value
                else:
                    colon_idx = line.rfind(':')
                    if colon_idx != -1:
                        value_str = line[colon_idx + 1:].strip()
                        parsed_value = parse_money(value_str)
                        if parsed_value > 0:
                            final_total = parsed_value
            elif line_lower.startswith('total:') and 'subtotal' not in line_lower and 'final' not in line_lower:
                # Handle "Total: $3.84" format - store temporarily
                parts = line.split(':', 1)
                if len(parts) > 1:
                    temp_total = parse_money(parts[1])
        
        # If we didn't find "Total After Tip" but found "Total:", use that
        if final_total == 0.0 and temp_total != 0.0:
            final_total = temp_total
        
        # Backup regex parsing for final total if still 0
        if final_total == 0.0:
            # Try to find "Total After Tip" first
            after_tip_match = re.search(r'Total After Tip:\s*\$?([\d,]+\.?\d*)', order_text, re.IGNORECASE)
            if after_tip_match:
                final_total = parse_money(after_tip_match.group(1))
            else:
                # Try "Final Total"
                final_match = re.search(r'Final Total:\s*\$?([\d,]+\.?\d*)', order_text, re.IGNORECASE)
                if final_match:
                    final_total = parse_money(final_match.group(1))
                else:
                    # Last resort - just "Total:" but not "Subtotal:"
                    total_match = re.search(r'(?<!Sub)Total:\s*\$?([\d,]+\.?\d*)', order_text, re.IGNORECASE)
                    if total_match:
                        final_total = parse_money(total_match.group(1))
        
        # Calculate original total
        original_total = subtotal + delivery_fee + taxes_fees + 3.49
        
        # Parse tip amount - check ticket embed first, fall back to order text
        tip_amount = 0.0
        tip_found_in_embed = False

        # First try to get tip from ticket embed
        try:
            ticket_embed = await fetch_ticket_embed(interaction.channel)
            if ticket_embed:
                # Look for Tip Amount field in the ticket embed
                for field in ticket_embed.fields:
                    if field.name and field.name.lower().strip() == 'tip amount':
                        # Extract numeric tip value
                        tip_str = field.value
                        if tip_str and tip_str.strip():
                            # Check if it's N/A or empty
                            if tip_str.strip().upper() in ['N/A', 'NA', 'NONE', '-', '']:
                                tip_amount = 0.0
                                tip_found_in_embed = True
                                break

                            # Remove currency symbols and commas
                            tip_cleaned = tip_str.strip().replace('$', '').replace(',', '').strip()

                            try:
                                parsed_tip = float(tip_cleaned)
                                # Sanity checks to avoid using wrong values
                                # Don't use if it matches the final total (common bug)
                                # Don't use if it's unreasonably large
                                if 0 <= parsed_tip <= 20 and parsed_tip != final_total:
                                    tip_amount = parsed_tip
                                    tip_found_in_embed = True
                                elif parsed_tip == final_total:
                                    # This is likely a bug where tip field contains total
                                    # Fall back to order text
                                    tip_found_in_embed = False
                                else:
                                    # Unreasonable tip, mark as found but use 0
                                    tip_amount = 0.0
                                    tip_found_in_embed = True
                                break
                            except ValueError:
                                # Not a valid number, treat as not found
                                tip_found_in_embed = False
                                break
        except discord.HTTPException as e:
            print(f"Failed to fetch ticket embed: {e}")
        except Exception as e:
            print(f"Unexpected error fetching ticket embed: {e}")

        # If no valid tip found in embed, use tip from order text
        if not tip_found_in_embed:
            tip_amount = tip_from_order

        # Debug what's happening
        print(f"DEBUG: tip_from_order={tip_from_order}, tip_found_in_embed={tip_found_in_embed}, tip_amount={tip_amount}, final_total={final_total}")
        
        # Parse service fee override
        custom_service_fee = None
        if service_fee:
            service_fee = service_fee.strip()
            # Handle different formats: "$7", "7.00", "7", "$7.00"
            service_fee_cleaned = service_fee.replace('$', '').replace(',', '').strip()
            
            try:
                custom_service_fee = float(service_fee_cleaned)
                if custom_service_fee < 0:
                    return await interaction.response.send_message(
                        "❌ Service fee cannot be negative.", 
                        ephemeral=True
                    )
                if custom_service_fee > 20:  # Sanity check
                    return await interaction.response.send_message(
                        f"⚠️ Large service fee detected: ${custom_service_fee:.2f}. Please confirm this is correct by running the command again.",
                        ephemeral=True
                    )
            except ValueError:
                # Send initial response first
                await interaction.response.send_message("Processing order...", ephemeral=True)
                await interaction.followup.send(
                    f"⚠️ Invalid service fee format '{service_fee}'. Using default service fee.",
                    ephemeral=True
                )
        
        # Always require confirmation for all orders
        if True:  # Show confirmation for all orders
            # Create confirmation embed with order breakdown
            confirmation_embed = discord.Embed(
                title="📋 Order Confirmation Required",
                color=discord.Color.blue()
            )
            
            # Calculate service fee and new total for display
            if custom_service_fee is not None:
                service_fee = custom_service_fee
            else:
                service_fee = 4.0 if vip else 5.0
            # If tip from ticket embed differs from tip in order text, we need to adjust
            # final_total includes the original tip, so we subtract it and add the new tip
            if tip_amount != tip_from_order:
                new_total = final_total - tip_from_order + tip_amount + service_fee
            else:
                new_total = final_total + service_fee
            
            # Build the description with breakdown
            conf_description = f"**Order Total: ${original_total:.2f}**\n\n"
            conf_description += f"Subtotal: ${subtotal:.2f}\n"
            conf_description += f"Delivery Fee: ${delivery_fee:.2f}\n"
            conf_description += f"Taxes & Fees: ${taxes_fees:.2f}\n\n"
            conf_description += f"**After Promo & Service Fee Applied:**\n"
            conf_description += f"Tip Amount: ${tip_amount:.2f}\n"
            conf_description += f"Service Fee: ${service_fee:.2f}\n"
            conf_description += f"**Your New Total: ${new_total:.2f}**\n\n"
            conf_description += "Please review the order details and confirm to proceed."
            
            confirmation_embed.description = conf_description
            
            # Create confirmation view with button
            class OrderConfirmationView(discord.ui.View):
                def __init__(self, original_embed_data, tip_amt, new_tot):
                    super().__init__(timeout=300)  # 5 minute timeout
                    self.original_embed_data = original_embed_data
                    self.tip_amount = tip_amt
                    self.new_total = new_tot
                
                @discord.ui.button(label="✅ Confirm Order", style=discord.ButtonStyle.green)
                async def confirm_order(self, interaction: discord.Interaction, button: discord.ui.Button):
                    # Proceed with original logic
                    embed = discord.Embed(
                        title="Order Breakdown:",
                        color=discord.Color.green()
                    )
                    embed.description = self.original_embed_data
                    
                    try:
                        await interaction.channel.send(embed=embed)
                        await interaction.response.send_message("✅ Order confirmed and processed!", ephemeral=True)
                        
                        # Trigger payments functionality
                        from ..views import PaymentView as PV
                        payment_view = PV()
                        payment_embed = discord.Embed(
                            title="Prin's Payments",
                            description="Select which payment method you would like to use! (Zelle/Crypto is preferred)",
                            color=0x00ff00
                        )
                        await interaction.channel.send(embed=payment_embed, view=payment_view)
                        
                        # Send payment instructions
                        instructions_embed = discord.Embed(
                            title="Payment Instructions",
                            description="When paying, **please don't add any notes.** Only **single emojis** or a **period (.)** if necessary. **Always send as Friends and Family if using PayPal, Venmo, or Zelle**. After you pay, please send a screenshot of the payment confirmation and please ping <@745694160002089130>!",
                            color=0x00ff00
                        )
                        await interaction.channel.send(embed=instructions_embed)
                        
                    except discord.HTTPException as e:
                        await interaction.response.send_message(f"❌ Error processing order: {str(e)}", ephemeral=True)
                
                @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
                async def cancel_order(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await interaction.response.send_message("❌ Order cancelled.", ephemeral=True)
                    # Disable all buttons
                    for item in self.children:
                        item.disabled = True
                    await interaction.edit_original_response(view=self)
            
            # Prepare the embed data for confirmation callback (we need to calculate this early)
            embed_description = ""
            if cart_items:
                if len(cart_items) > 50:
                    cart_items = cart_items[:50]
                    cart_items.append("... and more items")
                embed_description += "**Cart Items:**\n"
                for item in cart_items:
                    embed_description += f"{item}\n"
                embed_description += "\n"
            
            # Calculate service fee and new total early for confirmation
            if custom_service_fee is not None:
                service_fee = custom_service_fee
            else:
                service_fee = 6.0 if vip else 7.0
            # If tip from ticket embed differs from tip in order text, we need to adjust
            # final_total includes the original tip, so we subtract it and add the new tip
            if tip_amount != tip_from_order:
                new_total = final_total - tip_from_order + tip_amount + service_fee
            else:
                new_total = final_total + service_fee
            
            embed_description += f"Your original total + taxes + Uber fees: ${original_total:.2f}\n\n"
            embed_description += "**Promo Discount + Service Fee successfully applied!**\n"
            if vip:
                embed_description += "**VIP discount applied!**\n"
            embed_description += "\n"
            embed_description += f"Tip amount: ${tip_amount:.2f}\n\n"
            embed_description += f"Your new total: **${new_total:.2f}**"
            
            confirmation_view = OrderConfirmationView(embed_description, tip_amount, new_total)
            
            # Send confirmation instead of proceeding
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=confirmation_embed, view=confirmation_view, ephemeral=True)
                else:
                    await interaction.followup.send(embed=confirmation_embed, view=confirmation_view, ephemeral=True)
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ Error sending confirmation: {str(e)}", ephemeral=True)
            
            return  # Exit early, don't proceed with normal flow
        
        # Order parsing validation
        if subtotal == 0.0 and delivery_fee == 0.0 and taxes_fees == 0.0:
            return await interaction.response.send_message(
                "❌ Could not parse order information. Please ensure you've copied the complete order details including subtotal, delivery fee, and taxes.",
                ephemeral=True
            )
        
        if final_total == 0.0:
            return await interaction.response.send_message(
                "❌ Could not determine the final total. Please ensure the order includes 'Total After Tip:', 'Final Total:', or 'Total:' with the amount.",
                ephemeral=True
            )
        
        # If no cart items found, try regex approach
        if not cart_items:
            # First check if CART ITEMS section exists
            if 'CART ITEMS:' in order_text:
                # Extract everything between CART ITEMS: and FARE BREAKDOWN:
                # Handle both multiline and single-line formats
                cart_section_match = re.search(r'CART ITEMS:\s*(.*?)(?:\s*FARE BREAKDOWN:|\s*$)', order_text, re.IGNORECASE | re.DOTALL)
                if cart_section_match:
                    cart_text = cart_section_match.group(1).strip()
                    
                    # Handle case where items are all on one line separated by spaces
                    # Look for bullet points followed by item descriptions
                    if '•' in cart_text:
                        # More robust regex to capture items between bullet points
                        items = re.findall(r'•\s*([^•]+?)(?=\s*(?:•|\s*FARE\s+BREAKDOWN:|\s*$))', cart_text, re.IGNORECASE)
                        for item in items:
                            item = item.strip()
                            # Remove any trailing content after FARE BREAKDOWN
                            item = re.sub(r'\s*FARE\s+BREAKDOWN:.*$', '', item, flags=re.IGNORECASE).strip()
                            if item and ('$' in item or '(' in item):  # Has price or quantity
                                cart_items.append('• ' + item)
                    else:
                        # Fallback: try to find items with prices in the cart section
                        # Look for patterns like "Item Name - $X.XX" or "Item Name (xN) - $X.XX"
                        price_items = re.findall(r'([^•\n]+\$[\d,]+\.?\d*)', cart_text)
                        for item in price_items:
                            item = item.strip()
                            # Remove any trailing content after FARE BREAKDOWN
                            item = re.sub(r'\s*FARE\s+BREAKDOWN:.*$', '', item, flags=re.IGNORECASE).strip()
                            if item and not any(keyword in item.lower() for keyword in ['subtotal', 'promotion', 'delivery', 'taxes', 'total']):
                                cart_items.append('• ' + item)
            
            # Also check for format 2 items
            if not cart_items and ('items in bag' in order_text.lower() or '🍚' in order_text):
                # Find all ╰・ items that look like food (have quantity pattern)
                # Match items like "1x: Rice Bowl" or "2x: Five Falafels"
                # Stop when we hit Order Total or another section marker
                food_items = re.findall(r'╰・(\d+x:[^╰<]+?)(?=\s*(?:╰・(?:\d+x:|Subtotal:|Promotion:|Delivery|Taxes|Uber Cash:|Tip:|Final Total:)|<:|Order Total|$))', order_text)
                for item in food_items:
                    item = item.strip()
                    # Remove any emoji markers and "Order" text that might have been captured
                    item = re.sub(r'\s*(?:<:.*?:\d+>|:.*?:)\s*Order.*$', '', item)
                    item = item.strip()
                    if item and not any(keyword in item.lower() for keyword in ['subtotal', 'promotion', 'delivery', 'taxes', 'uber', 'tip', 'total']):
                        cart_items.append(item)
        
        # Debug: If original total is 0, something went wrong with parsing
        if original_total == 0.0 and subtotal == 0.0:
            # Try a more aggressive parsing approach
            
            # Look for subtotal pattern anywhere in the text (including "Estimated Subtotal")
            subtotal_match = re.search(r'(?:Estimated\s+)?Subtotal:\s*\$?([\d,]+\.?\d*)', order_text, re.IGNORECASE)
            if subtotal_match:
                subtotal = parse_money(subtotal_match.group(1))
            
            # Look for delivery fee
            delivery_match = re.search(r'Delivery Fee:\s*\$?([\d,]+\.?\d*)', order_text, re.IGNORECASE)
            if delivery_match:
                delivery_fee = parse_money(delivery_match.group(1))
            
            # Look for taxes
            taxes_match = re.search(r'Taxes (?:&|and) (?:Other )?Fees:\s*\$?([\d,]+\.?\d*)', order_text, re.IGNORECASE)
            if taxes_match:
                taxes_fees = parse_money(taxes_match.group(1))
            
            # Recalculate
            original_total = subtotal + delivery_fee + taxes_fees + 3.49
        
        # Division by zero and negative value protection
        if final_total < 0:
            return await interaction.response.send_message(
                "❌ Invalid order total detected. Please check the order information.", 
                ephemeral=True
            )
        
        # Calculate service fee (custom override, VIP, or default)
        if custom_service_fee is not None:
            service_fee = custom_service_fee
        else:
            service_fee = 6.0 if vip else 7.0
        
        # Validate service fee
        if service_fee < 0:
            service_fee = 7.0  # Default to standard fee
        
        # Calculate new total with service fee, adjusting for tip difference
        if tip_amount != tip_from_order:
            new_total = final_total - tip_from_order + tip_amount + service_fee
        else:
            new_total = final_total + service_fee
        
        # Create the breakdown embed
        embed = discord.Embed(
            title="Order Breakdown:",
            color=discord.Color.green()
        )
        
        # Build the description
        description = ""
        
        # Add cart items if found (with validation)
        if cart_items:
            # Validate cart items
            if len(cart_items) > 50:  # Sanity check
                cart_items = cart_items[:50]  # Truncate to reasonable amount
                cart_items.append("... and more items")
            
            description += "**Cart Items:**\n"
            for item in cart_items:
                description += f"{item}\n"
            description += "\n"
        
        description += f"Your original total + taxes + Uber fees: ${original_total:.2f}\n\n"
        description += "**Promo Discount + Service Fee successfully applied!**\n"
        if vip:
            description += "**VIP discount applied!**\n"
        description += "\n"
        description += f"Tip amount: ${tip_amount:.2f}\n\n"
        description += f"Your new total: **${new_total:.2f}**"
        
        embed.description = description
        
        # Improved response handling with timeout protection
        try:
            # Check if we haven't already sent a response (from tip validation error)
            if not interaction.response.is_done():
                await interaction.response.send_message("Processing order...", ephemeral=True)
        except discord.errors.NotFound:
            # Interaction already expired
            return
        except discord.HTTPException as e:
            print(f"Failed to send initial response: {e}")
            return
        
        # Send the breakdown embed as a regular message in the channel
        try:
            await interaction.channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to send messages in this channel.", 
                ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Failed to send order breakdown: {str(e)}", 
                ephemeral=True
            )
            return
        
        # Now trigger the payments functionality
        # Import PaymentView the same way the payments command does
        from ..views import PaymentView as PV
        payment_view = PV()
        payment_embed = discord.Embed(
            title="Prin's Payments",
            description="Select which payment method you would like to use! (Zelle/Crypto is preferred)",
            color=0x9932cc,
        )
        
        # Send the payment embed as a regular message in the channel
        await interaction.channel.send(embed=payment_embed, view=payment_view)
        
        # Send payment instructions
        instructions_embed = discord.Embed(
            title="Payment Instructions",
            description="When paying, **please don't add any notes.** Only **single emojis** or a **period (.)** if necessary. **Always send as Friends and Family if using PayPal, Venmo, or Zelle**. After you pay, please send a screenshot of the payment confirmation and please ping <@745694160002089130>!",
            color=0x9932cc
        )
        await interaction.channel.send(embed=instructions_embed)