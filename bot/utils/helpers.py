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

    The original implementation only looked at the very first message in the
    channel. When other messages appear before the order embed, this fails.
    This revised version scans recent history (newest first) and returns the
    first embed that contains the expected order fields.
    """

    try:
        async for msg in channel.history(limit=search_limit, oldest_first=False):
            if len(msg.embeds) < 2:
                continue
            embed = msg.embeds[1]
            field_names = {f.name for f in embed.fields}
            if {"Group Cart Link", "Name"}.issubset(field_names):
                return embed
        return None
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
