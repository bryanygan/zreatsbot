import os
import discord
from typing import Optional

OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None

# cache for parsed webhook orders keimport os
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
    """Parse fields from webhook order embeds (both tracking and checkout types)"""
    data = {field.name: field.value for field in embed.fields}
    tracking_url = getattr(embed, "url", None) or getattr(getattr(embed, "author", None), "url", "")
    
    # Handle tracking webhook format (Store, Name, Delivery Address)
    if 'Store' in data and 'Estimated Arrival' in data:
        return {
            'store': data.get('Store', '').strip(),
            'eta': data.get('Estimated Arrival', '').strip(),
            'name': data.get('Name', '').strip(),
            'address': data.get('Delivery Address', '').strip(),
            'items': data.get('Order Items', '').strip(),
            'tracking': tracking_url.strip() if tracking_url else '',
            'phone': data.get('Phone', '').strip(),
            'payment': data.get('Payment', '').strip(),
            'type': 'tracking'
        }
    
    # Handle checkout webhook format - check if it's in description instead of fields
    elif (len(embed.fields) == 0 and embed.description and 
          ('Store:' in embed.description or 'Account Email:' in embed.description or 
           'Delivery Information:' in embed.description or 'Items In Bag:' in embed.description)):
        
        description = embed.description
        import re
        
        # Extract store from description
        store_match = re.search(r'\*\*Store\*\*:\s*([^\n]+)', description)
        store = store_match.group(1).strip() if store_match else 'Unknown Store'
        
        # Extract name from Delivery Information section
        name = ''
        name_match = re.search(r'╰・\*\*Name\*\*:\s*([^\n╰]+)', description)
        if name_match:
            name = name_match.group(1).strip()
        
        # Extract address from Delivery Information section
        address = ''
        addr_match = re.search(r'╰・\*\*Address L1\*\*:\s*([^\n╰]+)', description)
        if addr_match:
            address = addr_match.group(1).strip()
        
        # Extract arrival time
        eta = ''
        arrival_match = re.search(r'\*\*Arrival\*\*:\s*([^\n]+)', description)
        if arrival_match:
            eta = arrival_match.group(1).strip()
        
        # Extract items
        items = ''
        items_match = re.search(r'\*\*Items In Bag\*\*:\s*(.*?)(?=\n\*\*|$)', description, re.DOTALL)
        if items_match:
            items = items_match.group(1).strip()
        
        # Extract account email
        email = ''
        email_match = re.search(r'\*\*Account Email\*\*:\s*(?:```)?([^\n`]+)', description)
        if email_match:
            email = email_match.group(1).strip()
        
        # Extract phone
        phone = ''
        phone_match = re.search(r'\*\*Account Phone\*\*:\s*`?([^`\n]+)', description)
        if phone_match:
            phone = phone_match.group(1).strip()
        
        return {
            'store': store,
            'eta': eta,
            'name': name,
            'address': address,
            'items': items,
            'tracking': tracking_url.strip() if tracking_url else '',
            'phone': phone,
            'payment': email,
            'type': 'checkout'
        }
    
    # Handle checkout webhook format (rich text with **bold** and ╰・ formatting in fields)
    elif ('Account Email' in data or 'Delivery Information' in data or 'Items In Bag' in data or
          ('Store' in data and any(x in data for x in ['Account Email', 'Account Phone', 'Delivery Information', 'Items In Bag']))):
        
        # Extract name from Delivery Information
        delivery_info = data.get('Delivery Information', '')
        name = ''
        address = ''
        
        if delivery_info:
            # Handle rich text format like: ╰・Name: Bryan Gan
            import re
            
            # Extract name using regex to handle the formatting
            name_match = re.search(r'(?:╰・)?(?:\*\*)?Name(?:\*\*)?[:\s]+([^╰\n*]+)', delivery_info, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip()
            
            # Extract address using regex
            addr_match = re.search(r'(?:╰・)?(?:\*\*)?Address L1(?:\*\*)?[:\s]+([^╰\n*]+)', delivery_info, re.IGNORECASE)
            if addr_match:
                address = addr_match.group(1).strip()
        
        # Extract store from Store field or title/description
        store = data.get('Store', '').strip()
        if not store:
            store_text = embed.title or embed.description or ''
            if store_text:
                # Handle formats like "🎉 Checkout Successful (ubereats)"
                import re
                paren_match = re.search(r'Checkout Successful[^(]*\(([^)]+)\)', store_text)
                if paren_match:
                    store = paren_match.group(1).strip()
                else:
                    store = 'Unknown Store'
        
        # Extract arrival time from Arrival field or parse from text
        eta = 'N/A'
        if 'Arrival' in data:
            eta = data.get('Arrival', '').strip()
        
        return {
            'store': store,
            'eta': eta,
            'name': name,
            'address': address,
            'items': data.get('Items In Bag', '').strip(),
            'tracking': tracking_url.strip() if tracking_url else '',
            'phone': data.get('Account Phone', '').strip(),
            'payment': data.get('Account Email', '').strip(),
            'type': 'checkout'
        }
    
    # Fallback to original format for compatibility
    else:
        return {
            'store': data.get('Store', '').strip(),
            'eta': data.get('Estimated Arrival', '').strip(),
            'name': data.get('Name', '').strip(),
            'address': data.get('Delivery Address', '').strip(),
            'items': data.get('Order Items', '').strip(),
            'tracking': tracking_url.strip() if tracking_url else '',
            'phone': data.get('Phone', '').strip(),
            'payment': data.get('Payment', '').strip(),
            'type': 'unknown'
        }

def find_latest_matching_webhook_data(name: str, address: str = '') -> dict:
    """Find the most recent matching webhook data using flexible name matching"""
    normalized_name = normalize_name_for_matching(name)
    normalized_address = address.lower().strip() if address else ''
    
    matches = []
    
    # Collect all matching webhooks with their cache keys
    for (cached_name, cached_addr), data in ORDER_WEBHOOK_CACHE.items():
        cached_normalized = normalize_name_for_matching(cached_name)
        
        # Try different matching strategies
        is_match = False
        match_type = ""
        
        # Exact name + address match
        if cached_normalized == normalized_name and cached_addr == normalized_address:
            is_match = True
            match_type = "exact"
        # Exact name match (ignore address)
        elif cached_normalized == normalized_name:
            is_match = True
            match_type = "name_exact"
        # Partial name matching
        elif (normalized_name in cached_normalized or 
              cached_normalized in normalized_name or
              any(part in cached_normalized for part in normalized_name.split() if len(part) > 2)):
            is_match = True
            match_type = "name_partial"
        
        if is_match:
            matches.append({
                'data': data,
                'cache_key': (cached_name, cached_addr),
                'match_type': match_type
            })
    
    if not matches:
        return None
    
    # Sort by match quality (exact > name_exact > name_partial) and then by recency
    # Since ORDER_WEBHOOK_CACHE is ordered by insertion, later entries are more recent
    cache_keys = list(ORDER_WEBHOOK_CACHE.keys())
    
    def match_score(match):
        type_scores = {"exact": 3, "name_exact": 2, "name_partial": 1}
        type_score = type_scores.get(match['match_type'], 0)
        # Get position in cache (later = higher score for recency)
        try:
            recency_score = cache_keys.index(match['cache_key'])
        except ValueError:
            recency_score = 0
        return (type_score, recency_score)
    
    # Get the best match (highest score)
    best_match = max(matches, key=match_score)
    return best_match['data']

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