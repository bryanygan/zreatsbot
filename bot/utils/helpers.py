import os
import discord
from typing import Optional

OWNER_ID = int(os.getenv('OWNER_ID')) if os.getenv('OWNER_ID') else None
# default channel where webhook orders are posted
WEBHOOK_CHANNEL_ID = int(os.getenv('WEBHOOK_CHANNEL_ID', '1352067371006693499'))

# cache for parsed webhook orders keyed by (name, address)
ORDER_WEBHOOK_CACHE = {}

async def fetch_order_embed(channel: discord.TextChannel) -> Optional[discord.Embed]:
    try:
        msgs = [msg async for msg in channel.history(limit=1, oldest_first=True)]
        if not msgs or len(msgs[0].embeds) < 2:
            return None
        return msgs[0].embeds[1]
    except Exception:
        return None

def parse_fields(embed: discord.Embed) -> dict:
    data = {field.name: field.value for field in embed.fields}
    return {
        'link': data.get('Group Cart Link'),
        'name': data.get('Name', '').strip(),
        'address': data.get('Delivery Address', '').strip(),
        'addr2': data.get('Apt / Suite / Floor:', '').strip(),
        'notes': data.get('Delivery Notes', '').strip(),
        'tip': data.get('Tip Amount', '').strip(),
    }


def parse_webhook_order(embed: discord.Embed) -> dict:
    data = {field.name: field.value for field in embed.fields}
    tracking_url = getattr(embed, "url", None) or getattr(getattr(embed, "author", None), "url", "")
    return {
        'store': data.get('Store', '').strip(),
        'eta': data.get('Estimated Arrival', '').strip(),
        'name': data.get('Name', '').strip(),
        'address': data.get('Delivery Address', '').strip(),
        'items': data.get('Order Items', '').strip(),
        'tracking': tracking_url.strip() if tracking_url else '',
    }

def normalize_name(name: str) -> str:
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
