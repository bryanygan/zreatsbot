import os
import time
import discord
from collections import deque
from discord.errors import HTTPException

ROLE_PING_ID = os.getenv('ROLE_PING_ID', '1352022044614590494')
ORDER_CHANNEL_MENTION = os.getenv('ORDER_CHANNEL_MENTION', '<#1350935337269985334>')

rename_history = deque()

async def change_channel_status(channel: discord.TextChannel, status: str, silent: bool = False):
    """Rename the channel and send open/close/break announcements."""
    if status == "open":
        new_name = "open🟢🟢"
    elif status == "break":
        new_name = "on-hold🟡🟡"
    else:  # close
        new_name = "closed🔴🔴"

    now = time.monotonic()
    while rename_history and now - rename_history[0] > 600:
        rename_history.popleft()

    if len(rename_history) >= 2:
        return False, "Rename limit reached (2 per 10 min). Try again later."

    try:
        await channel.edit(name=new_name)
        rename_history.append(now)

        if status == "open":
            # Only send role ping if not in silent mode
            if not silent:
                await channel.send(f"ZR Eats is now OPEN! <@&{ROLE_PING_ID}>")
            
            embed = discord.Embed(
                title="ZR Eats is now OPEN!",
                description=(
                    f"We are now accepting orders! Click the order button in {ORDER_CHANNEL_MENTION} "
                    "to place an order."
                ),
            )
            await channel.send(embed=embed)
        elif status == "break":
            embed = discord.Embed(
                title="ZR Eats is now on hold!",
                description="Please wait until a Chef is available to take new orders!",
            )
            embed.set_footer(text="Do not open a ticket during this time, you will not get a response.")
            await channel.send(embed=embed)
        else:  # close
            embed = discord.Embed(
                title="ZR Eats is now CLOSED.",
                description=(
                    "We are currently closed. Please come back later when we're open for new orders! "
                    "Do not open a ticket, you will not get a response."
                ),
            )
            await channel.send(embed=embed)
        return True, ""
    except HTTPException as e:
        return False, f"Failed to rename channel: {e.status} {e.text}"