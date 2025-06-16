import os
import discord
from typing import Optional
from datetime import datetime
import re

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
    """Parse fields from webhook order embeds (tracking, checkout, and order placement types)"""
    data = {field.name: field.value for field in embed.fields}
    tracking_url = getattr(embed, "url", None) or getattr(getattr(embed, "author", None), "url", "")
    
    # Handle "Order Successfully Placed" format (Pump)
    if (embed.title and "Order Successfully Placed" in embed.title) or \
       any("Order link" in field_name for field_name in data.keys()):
        
        # Extract tracking URL from Order link field or embed URL
        order_link = ""
        for field_name, field_value in data.items():
            if "Order link" in field_name or "order link" in field_name.lower():
                # The field value might contain a clickable link, extract the URL
                import re
                url_match = re.search(r'https://[^\s\)]+', field_value)
                if url_match:
                    order_link = url_match.group(0)
                break
        
        if not order_link and tracking_url:
            order_link = tracking_url.strip()
        
        # Extract store name from Restaurant field or embed description
        store = data.get('Restaurant', '').strip()
        if not store:
            # Try to extract from description if it mentions the store
            if embed.description and "Your order from" in embed.description:
                import re
                store_match = re.search(r'Your order from\s+\*\*([^*]+)\*\*', embed.description)
                if store_match:
                    store = store_match.group(1).strip()
        
        # Extract delivery time from estimated delivery time in description
        eta = 'N/A'
        if embed.description and "Estimated delivery time:" in embed.description:
            import re
            eta_match = re.search(r'Estimated delivery time:\s*\*\*([^*]+)\*\*', embed.description)
            if eta_match:
                eta = eta_match.group(1).strip()
        
        return {
            'store': store or 'Unknown Store',
            'eta': eta,
            'name': data.get('Customer', '').strip(),
            'address': data.get('Delivery Address', '').strip(),
            'items': data.get('Order Items', '').strip(),
            'tracking': order_link,
            'phone': data.get('Phone', '').strip(),
            'payment': data.get('Email', '').strip(),
            'total': data.get('Total', '').strip(),
            'type': 'order_placed'
        }
    
    # Handle tracking webhook format (Store, Name, Delivery Address)
    elif 'Store' in data and 'Estimated Arrival' in data:
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
          ('**Store**:' in embed.description or '**Account Email**:' in embed.description or 
           '**Delivery Information**:' in embed.description or '**Items In Bag**:' in embed.description)):
        
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
        
        # Extract tracking URL from the embed URL or description
        tracking = tracking_url.strip() if tracking_url else ''
        
        # If no tracking URL from embed.url, try to extract from description
        if not tracking and description:
            # Look for tracking URL patterns in the description
            tracking_match = re.search(r'https://(?:www\.)?ubereats\.com/orders/[a-zA-Z0-9-]+', description)
            if tracking_match:
                tracking = tracking_match.group(0)
        
        return {
            'store': store,
            'eta': eta,
            'name': name,
            'address': address,
            'items': items,
            'tracking': tracking,
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
    # Generate multiple normalized variations of the input name
    name_variations = generate_name_variations(name)
    normalized_address = address.lower().strip() if address else ''
    
    matches = []
    
    # Collect all matching webhooks with their timestamps
    for (cached_name, cached_addr), cache_entry in ORDER_WEBHOOK_CACHE.items():
        cached_variations = generate_name_variations(cached_name)
        
        # Try different matching strategies
        is_match = False
        match_type = ""
        
        # Check if any variation of the input name matches any variation of the cached name
        for input_var in name_variations:
            for cached_var in cached_variations:
                # Exact match
                if input_var == cached_var:
                    is_match = True
                    match_type = "exact"
                    break
                # Partial match (one contains the other)
                elif (input_var in cached_var or cached_var in input_var) and len(input_var) > 2 and len(cached_var) > 2:
                    is_match = True
                    match_type = "partial"
                    break
            if is_match and match_type == "exact":
                break
        
        if is_match:
            matches.append({
                'data': cache_entry['data'],
                'timestamp': cache_entry['timestamp'],
                'message_id': cache_entry.get('message_id'),
                'cache_key': (cached_name, cached_addr),
                'match_type': match_type
            })
    
    if not matches:
        return None
    
    # Sort by match quality first, then by recency (most recent first)
    def match_score(match):
        type_scores = {"exact": 3, "partial": 1}
        type_score = type_scores.get(match['match_type'], 0)
        # Use timestamp for recency (newer = higher score)
        timestamp_score = match['timestamp'].timestamp()
        return (type_score, timestamp_score)
    
    # Get the best match (highest score = best type + most recent)
    best_match = max(matches, key=match_score)
    return best_match['data']

def generate_name_variations(name: str) -> list:
    """Generate multiple normalized variations of a name to improve matching"""
    if not name:
        return ['']
    
    variations = set()
    
    # Original name, lowercased and stripped
    base_name = name.lower().strip()
    variations.add(base_name)
    
    # Remove commas and normalize spacing
    no_comma = base_name.replace(',', ' ')
    # Normalize multiple spaces to single space
    no_comma = ' '.join(no_comma.split())
    variations.add(no_comma)
    
    # Remove commas completely (no space replacement)
    no_comma_nospace = base_name.replace(',', '')
    no_comma_nospace = ' '.join(no_comma_nospace.split())
    variations.add(no_comma_nospace)
    
    # Split into parts and take first two meaningful parts
    parts = [p.strip() for p in no_comma.split() if p.strip()]
    
    if len(parts) >= 2:
        # First two parts
        two_parts = f"{parts[0]} {parts[1]}"
        variations.add(two_parts)
        
        # Reversed order (last first)
        reversed_parts = f"{parts[1]} {parts[0]}"
        variations.add(reversed_parts)
        
        # Just first part + first letter of second
        first_plus_initial = f"{parts[0]} {parts[1][0]}" if len(parts[1]) > 0 else parts[0]
        variations.add(first_plus_initial)
    elif len(parts) == 1:
        # Single word variations
        single = parts[0]
        variations.add(single)
        variations.add(f"{single} {single[0]}" if len(single) > 0 else single)
    
    # Remove empty strings and return as list
    return [v for v in variations if v.strip()]

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
    
    # This function is now mainly used for the primary cache key
    # Most matching logic is handled by generate_name_variations
    cleaned = name.lower().strip()
    cleaned = cleaned.replace(',', ' ')
    cleaned = ' '.join(cleaned.split())  # Normalize whitespace
    
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

def cache_webhook_data(data: dict, message_timestamp: datetime = None, message_id: int = None):
    """Cache webhook data with timestamp for recency tracking"""
    name = normalize_name_for_matching(data.get('name', ''))
    addr = data.get('address', '').lower().strip()
    
    if not name:
        return False
    
    cache_key = (name, addr)
    timestamp = message_timestamp or datetime.now()
    
    # Only update cache if this is more recent than existing entry
    if cache_key in ORDER_WEBHOOK_CACHE:
        existing_timestamp = ORDER_WEBHOOK_CACHE[cache_key]['timestamp']
        if timestamp <= existing_timestamp:
            return False  # Don't cache older data
    
    ORDER_WEBHOOK_CACHE[cache_key] = {
        'data': data,
        'timestamp': timestamp,
        'message_id': message_id
    }
    return True

def convert_24h_to_12h(time_text):
    """
    Convert 24-hour time format to 12-hour format in a text string.
    Handles various time formats like "14:30", "2:30 PM", "14:30 - 15:00", etc.
    
    Args:
        time_text (str): Text that may contain time in 24-hour format
        
    Returns:
        str: Text with times converted to 12-hour format
    """
    if not time_text:
        return time_text
    
    def convert_single_time(match):
        """Convert a single time match from 24h to 12h format"""
        hour_str = match.group(1)
        minute_str = match.group(2)
        
        hour = int(hour_str)
        minute = int(minute_str)
        
        # Handle 24-hour conversion
        if hour == 0:
            period = "AM"
            display_hour = 12
        elif hour < 12:
            period = "AM"
            display_hour = hour
        elif hour == 12:
            period = "PM"
            display_hour = 12
        else:
            period = "PM"
            display_hour = hour - 12
        
        return f"{display_hour}:{minute:02d} {period}"
    
    # Pattern to match 24-hour time format (HH:MM)
    pattern = r'\b(\d{1,2}):(\d{2})\b(?!\s*[AaPp][Mm])'
    
    # Replace all 24-hour times with 12-hour format
    converted_text = re.sub(pattern, convert_single_time, time_text)
    
    return converted_text

def detect_webhook_type(embed, field_names):
    """
    Detect the type of webhook embed
    Returns: (is_webhook, webhook_type_name)
    """
    
    # Check for "Order Successfully Placed" format (UberEats order confirmations)
    is_order_placed = (
        (embed.title and "Order Successfully Placed" in embed.title) or
        any("Order link" in field_name or "order link" in field_name.lower() for field_name in field_names) or
        any("Customer" in field_name for field_name in field_names)
    )
    
    # Check for tracking webhook (Store, Name, Delivery Address)
    is_tracking = {"Store", "Name", "Delivery Address"}.issubset(field_names)
    
    # Check for checkout webhook - comprehensive detection
    is_checkout = (
        "Account Email" in field_names or 
        "Delivery Information" in field_names or
        "Items In Bag" in field_names or
        (embed.title and "Checkout Successful" in embed.title) or
        (embed.description and "Checkout Successful" in embed.description) or
        ("Store" in field_names and any(x in field_names for x in ["Account Email", "Account Phone", "Delivery Information", "Items In Bag"])) or
        # Description-based checkout webhooks (like stewardess)
        (len(embed.fields) == 0 and embed.description and 
        any(x in embed.description for x in ['**Store**:', '**Account Email**:', '**Delivery Information**:', '**Items In Bag**:']))
    )
    
    if is_order_placed:
        return True, "order_placed"
    elif is_tracking:
        return True, "tracking"
    elif is_checkout:
        return True, "checkout"
    else:
        return False, "unknown"