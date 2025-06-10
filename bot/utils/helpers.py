import os
import discord
from typing import Optional

OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None

# cache for parsed webhook orders keyed by (name, address)
ORDER_WEBHOOK_CACHE = {}

async def fetch_order_embed(
    channel: discord.TextChannel, search_limit: int = 25
) -> Optional[discord.Embed]:
    """Fetch the most recent order embed in the provided channel.

    First tries to find a ticket embed (Group Cart Link), then falls back to
    looking for webhook order embeds (Order Successfully Placed).
    """
    try:
        async for msg in channel.history(limit=search_limit, oldest_first=False):
            if len(msg.embeds) < 1:
                continue
            
            # First check for ticket embeds (original functionality)
            if len(msg.embeds) >= 2:
                embed = msg.embeds[1]
                field_names = {f.name for f in embed.fields}
                if {"Group Cart Link", "Name"}.issubset(field_names):
                    return embed
            
            # Then check for webhook order embeds as fallback
            for embed in msg.embeds:
                field_names = {f.name for f in embed.fields}
                # Look for webhook order embeds
                if {"Store", "Name", "Delivery Address"}.issubset(field_names):
                    return embed
                    
        return None
    except Exception:
        return None

async def fetch_ticket_embed(
    channel: discord.TextChannel, search_limit: int = 100
) -> Optional[discord.Embed]:
    """Specifically fetch ticket embeds (with Group Cart Link)"""
    try:
        async for msg in channel.history(limit=search_limit, oldest_first=False):
            if len(msg.embeds) < 1:
                continue
            
            # Check all embeds in the message, not just the second one
            for i, embed in enumerate(msg.embeds):
                field_names = {f.name for f in embed.fields}
                # Look for various possible ticket embed patterns
                if ({"Group Cart Link", "Name"}.issubset(field_names) or
                    {"Group Link", "Name"}.issubset(field_names) or
                    any("Group" in name and "Link" in name for name in field_names) and "Name" in field_names):
                    return embed
        return None
    except Exception:
        return None

async def debug_all_embeds(
    channel: discord.TextChannel, search_limit: int = 25
) -> list:
    """Debug function to show all embeds found in channel"""
    embeds_info = []
    try:
        async for msg in channel.history(limit=search_limit, oldest_first=False):
            if msg.embeds:
                for i, embed in enumerate(msg.embeds):
                    field_names = [f.name for f in embed.fields]
                    embeds_info.append({
                        'message_id': msg.id,
                        'embed_index': i,
                        'title': embed.title or 'No Title',
                        'field_names': field_names,
                        'field_count': len(embed.fields),
                        'author': str(msg.author),
                        'webhook_id': msg.webhook_id
                    })
    except Exception as e:
        embeds_info.append({'error': str(e)})
    return embeds_info

async def fetch_webhook_embed(
    channel: discord.TextChannel, search_limit: int = 25
) -> Optional[discord.Embed]:
    """Specifically fetch webhook order embeds (Order Successfully Placed)"""
    try:
        async for msg in channel.history(limit=search_limit, oldest_first=False):
            if len(msg.embeds) < 1:
                continue
            for embed in msg.embeds:
                field_names = {f.name for f in embed.fields}
                # Look for webhook order embeds
                if {"Store", "Name", "Delivery Address"}.issubset(field_names):
                    return embed
        return None
    except Exception:
        return None

def parse_fields(embed: discord.Embed) -> dict:
    """Parse fields from ticket embeds"""
    data = {field.name: field.value for field in embed.fields}
    return {
        'link': data.get('Group Cart Link'),
        'name': data.get('Name', '').strip(),
        'address': data.get('Delivery Address', '').strip(),
        'addr2': data.get('Apt / Suite / Floor:', '').strip(),
        'notes': data.get('Delivery Notes', '').strip(),
        'tip': data.get('Tip Amount', '').strip(),
    }

def parse_webhook_fields(embed: discord.Embed) -> dict:
    """Parse fields from webhook order embeds"""
    data = {field.name: field.value for field in embed.fields}
    tracking_url = getattr(embed, "url", None) or getattr(getattr(embed, "author", None), "url", "")
    return {
        'store': data.get('Store', '').strip(),
        'eta': data.get('Estimated Arrival', '').strip(),
        'name': data.get('Name', '').strip(),
        'address': data.get('Delivery Address', '').strip(),
        'items': data.get('Order Items', '').strip(),
        'tracking': tracking_url.strip() if tracking_url else '',
        'phone': data.get('Phone', '').strip(),
        'payment': data.get('Payment', '').strip(),
    }

def parse_webhook_order(embed: discord.Embed) -> dict:
    """Legacy function - use parse_webhook_fields instead"""
    return parse_webhook_fields(embed)

def normalize_name(name: str) -> str:
    """Normalize name for display purposes"""
    cleaned = name.replace(',', ' ').strip()
    parts = cleaned.split()
    if len(parts) >= 2:
        first = parts[0].strip().title()
        last = parts[1].strip().title()
        return f"{first} {last}"
    if len(parts) == 1:
        w = parts[0].strip().title()
        return f"{w} {w[0].upper()}"
    return ''

def normalize_name_for_matching(name: str) -> str:
    """Normalize name for cache key matching - more aggressive normalization"""
    if not name:
        return ''
    
    # Remove common suffixes and prefixes, normalize case and spacing
    cleaned = name.lower().strip()
    
    # Remove common words that might vary
    cleaned = cleaned.replace(',', ' ')
    
    # Split into parts and take first two meaningful parts
    parts = [p.strip() for p in cleaned.split() if p.strip()]
    
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    elif len(parts) == 1:
        return parts[0]
    
    return cleaned

def format_name_csv(name: str) -> str:
    cleaned = name.replace(',', ' ').strip()
    parts = cleaned.split()
    if len(parts) >= 2:
        first = parts[0].strip().title()
        last = parts[1].strip().title()
        return f"{first},{last}"
    if len(parts) == 1:
        w = parts[0].strip().title()
        return f"{w},{w[0].upper()}"
    return ''

def is_valid_field(value: str) -> bool:
    return bool(value and value.strip().lower() not in ('n/a', 'none'))

def owner_only(interaction: discord.Interaction) -> bool:
    return OWNER_ID and interaction.user.id == OWNER_ID

def find_matching_webhook_data(name: str, address: str = '') -> dict:
    """Find matching webhook data using flexible name matching"""
    normalized_name = normalize_name_for_matching(name)
    normalized_address = address.lower().strip() if address else ''
    
    # First try exact match
    exact_key = (normalized_name, normalized_address)
    if exact_key in ORDER_WEBHOOK_CACHE:
        return ORDER_WEBHOOK_CACHE[exact_key]
    
    # Try name-only match if address doesn't work
    for (cached_name, cached_addr), data in ORDER_WEBHOOK_CACHE.items():
        if normalize_name_for_matching(cached_name) == normalized_name:
            return data
    
    # Try partial name matching as last resort
    for (cached_name, cached_addr), data in ORDER_WEBHOOK_CACHE.items():
        cached_normalized = normalize_name_for_matching(cached_name)
        if (normalized_name in cached_normalized or 
            cached_normalized in normalized_name or
            any(part in cached_normalized for part in normalized_name.split() if len(part) > 2)):
            return data
    
    return None