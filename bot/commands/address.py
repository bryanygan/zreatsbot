"""Context menu command for converting a message's address to shipping CSV."""

import asyncio
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from ..utils.helpers import owner_only
from ..utils.address_parser import (
    parse_address,
    format_address_csv,
    STATE_MAP,
    STATE_ABBREVS,
    _smart_title,
    _extract_state_from_end,
)

# Temporary storage for parsed addresses awaiting modal submission.
# Keyed by modal custom_id → {"parsed": dict, "handle": asyncio.TimerHandle}
_pending_addresses: dict = {}

_TTL_SECONDS = 300  # 5 minutes


def _cleanup(modal_id: str) -> None:
    _pending_addresses.pop(modal_id, None)


def _store_parsed(modal_id: str, parsed: dict) -> None:
    # Cancel any previous timer for the same id (shouldn't happen, but be safe)
    old = _pending_addresses.get(modal_id)
    if old and "handle" in old:
        old["handle"].cancel()

    loop = asyncio.get_event_loop()
    handle = loop.call_later(_TTL_SECONDS, _cleanup, modal_id)
    _pending_addresses[modal_id] = {"parsed": parsed, "handle": handle}


def _pop_parsed(modal_id: str) -> dict | None:
    entry = _pending_addresses.pop(modal_id, None)
    if entry is None:
        return None
    if "handle" in entry:
        entry["handle"].cancel()
    return entry["parsed"]


def _parse_from_csz(text: str) -> dict | None:
    """Parse a 'City, State, ZIP' string into components.

    Accepts formats like:
      "Los Angeles, CA, 90210"
      "Los Angeles, CA 90210"
      "Los Angeles CA 90210"
    """
    import re

    text = text.strip()
    # Extract ZIP (5 or 5+4) from the end
    m = re.search(r'\b(\d{5}(?:-\d{4})?)\s*$', text)
    if not m:
        return None
    zip_code = m.group(1)
    rest = text[:m.start()].strip().rstrip(',').strip()

    # Extract state from end of remaining text
    state, rest = _extract_state_from_end(rest)
    if not state:
        return None

    city = rest.strip().rstrip(',').strip()
    if not city:
        return None

    return {"city": _smart_title(city), "state": state.upper(), "zip": zip_code}


def _escape_csv_field(value: str) -> str:
    if ',' in value:
        return f'"{value}"'
    return value


def setup(bot: commands.Bot):
    # ------------------------------------------------------------------ #
    # Context-menu command: right-click message → Apps → Convert Address
    # ------------------------------------------------------------------ #
    @bot.tree.context_menu(name="Convert Address to CSV")
    async def convert_address_to_csv(
        interaction: discord.Interaction, message: discord.Message
    ):
        if not owner_only(interaction):
            return await interaction.response.send_message(
                "You are not authorized.", ephemeral=True
            )

        content = message.content
        if not content or not content.strip():
            return await interaction.response.send_message(
                "That message has no text content to parse.", ephemeral=True
            )

        parsed = parse_address(content)
        if "error" in parsed:
            return await interaction.response.send_message(
                f"Could not parse address: {parsed['error']}", ephemeral=True
            )

        # Store parsed result keyed by a unique modal id
        modal_id = f"address_csv_modal_{interaction.id}"
        _store_parsed(modal_id, parsed)

        # Build and send the modal
        modal = discord.ui.Modal(title="Generate Shipping CSV", custom_id=modal_id)
        modal.add_item(
            discord.ui.TextInput(
                label="Package Weight (lbs)",
                style=discord.TextStyle.short,
                required=True,
                placeholder="e.g. 2.5",
                custom_id="weight",
            )
        )
        modal.add_item(
            discord.ui.TextInput(
                label="From: Name",
                style=discord.TextStyle.short,
                required=True,
                placeholder="e.g. John Doe",
                custom_id="from_name",
            )
        )
        modal.add_item(
            discord.ui.TextInput(
                label="From: Street Address",
                style=discord.TextStyle.short,
                required=True,
                placeholder="e.g. 123 Main St",
                custom_id="from_street",
            )
        )
        modal.add_item(
            discord.ui.TextInput(
                label="From: Apt/Suite (leave blank if none)",
                style=discord.TextStyle.short,
                required=False,
                placeholder="e.g. Apt 4B",
                custom_id="from_street2",
            )
        )
        modal.add_item(
            discord.ui.TextInput(
                label="From: City, State, ZIP",
                style=discord.TextStyle.short,
                required=True,
                placeholder="e.g. Los Angeles, CA, 90210",
                custom_id="from_csz",
            )
        )

        # We need to attach the on_submit callback
        async def on_modal_submit(modal_interaction: discord.Interaction):
            await _handle_modal_submit(modal_interaction, modal_id)

        modal.on_submit = on_modal_submit

        await interaction.response.send_modal(modal)

    # ------------------------------------------------------------------ #
    # Modal submission handler
    # ------------------------------------------------------------------ #
    async def _handle_modal_submit(
        interaction: discord.Interaction, modal_id: str
    ):
        to_addr = _pop_parsed(modal_id)
        if to_addr is None:
            return await interaction.response.send_message(
                "Session expired. Please try again.", ephemeral=True
            )

        # Extract modal field values by custom_id
        fields = {
            child.custom_id: child.value
            for child in interaction.data.get("components", [])
            for child in child.get("components", [])
        }
        # discord.py v2 exposes components differently depending on version;
        # walk all action-row children to be safe.
        if not fields:
            for row in interaction.data.get("components", []):
                for comp in row.get("components", []):
                    fields[comp["custom_id"]] = comp.get("value", "")

        weight_raw = fields.get("weight", "").strip()
        from_name = fields.get("from_name", "").strip()
        from_street = fields.get("from_street", "").strip()
        from_street2 = fields.get("from_street2", "").strip()
        from_csz_raw = fields.get("from_csz", "").strip()

        # Validate weight
        try:
            weight = float(weight_raw)
            if weight <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return await interaction.response.send_message(
                "Invalid weight. Please enter a positive number (e.g. 2.5).",
                ephemeral=True,
            )

        # Parse from city/state/zip
        from_csz = _parse_from_csz(from_csz_raw)
        if from_csz is None:
            return await interaction.response.send_message(
                f"Could not parse From city/state/ZIP: `{from_csz_raw}`\n"
                "Expected format: `City, ST, 12345` or `City ST 12345`",
                ephemeral=True,
            )

        # Format weight — drop trailing zeros (2.0 → "2", 2.5 → "2.5")
        weight_str = f"{weight:g}"

        # Build CSV fields
        csv_fields = [
            weight_str,
            from_name,
            from_street,
            from_street2,
            from_csz["city"],
            from_csz["state"],
            from_csz["zip"],
            to_addr["name"],
            to_addr["street"],
            to_addr["street2"],
            to_addr["city"],
            to_addr["state"],
            to_addr["zip"],
        ]
        csv_line = ",".join(_escape_csv_field(f) for f in csv_fields)

        # Build formatted addresses for the embed
        from_lines = [from_name, from_street]
        if from_street2:
            from_lines.append(from_street2)
        from_lines.append(
            f"{from_csz['city']}, {from_csz['state']} {from_csz['zip']}"
        )

        to_lines = [to_addr["name"]] if to_addr["name"] else []
        to_lines.append(to_addr["street"])
        if to_addr["street2"]:
            to_lines.append(to_addr["street2"])
        to_lines.append(
            f"{to_addr['city']}, {to_addr['state']} {to_addr['zip']}"
        )

        embed = discord.Embed(
            title="\U0001f4e6 Shipping CSV Generated",
            color=0x57F287,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="From", value="\n".join(from_lines), inline=True)
        embed.add_field(name="To", value="\n".join(to_lines), inline=True)
        embed.add_field(name="Weight", value=f"{weight_str} lbs", inline=True)

        await interaction.response.send_message(
            f"```\n{csv_line}\n```",
            embed=embed,
            ephemeral=True,
        )
