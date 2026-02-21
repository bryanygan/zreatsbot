import os
import time
import discord
from collections import deque
from discord.errors import HTTPException

ROLE_PING_ID = os.getenv('ROLE_PING_ID', '1352022044614590494')
ORDER_CHANNEL_MENTIONS = (
    f"<#1350935337269985334>, <#1473952634439205076>, or <#1473952663526703136>"
)
STATUS_MIRROR_CHANNEL_ID = 1350935337269985334  # Channel to mirror status messages

rename_history = deque()
status_message_id = None  # Track the last status message in mirror channel for deletion
main_status_message_id = None  # Track the last status message in main channel for deletion

async def change_channel_status(channel: discord.TextChannel, status: str, silent: bool = False):
    """Rename the channel and send open/close/break announcements."""
    global status_message_id, main_status_message_id
    if status == "open":
        new_name = "open🟢🟢"
    elif status == "break":
        new_name = "on-hold🟡🟡"
    elif status == "semi-open":
        new_name = "semi-open🟡🟡"
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

        # Get the mirror channel for status updates
        mirror_channel = None
        try:
            mirror_channel = channel.guild.get_channel(STATUS_MIRROR_CHANNEL_ID)
        except:
            pass

        # Delete previous status message from main channel if it exists
        if main_status_message_id:
            try:
                old_message = await channel.fetch_message(main_status_message_id)
                await old_message.delete()
                main_status_message_id = None
            except:
                pass

        # Delete previous status message from mirror channel if it exists
        if status_message_id and mirror_channel:
            try:
                old_message = await mirror_channel.fetch_message(status_message_id)
                await old_message.delete()
                status_message_id = None
            except:
                pass

        if status == "open":
            # Only send role ping if not in silent mode
            if not silent:
                await channel.send(f"Ocky Deli is now OPEN! <@&{ROLE_PING_ID}>")

            embed = discord.Embed(
                title="Ocky Deli is now OPEN!",
                description=(
                    f"We are now accepting orders! Click the order button in {ORDER_CHANNEL_MENTIONS} "
                    "to place an order."
                ),
            )
            message = await channel.send(embed=embed)
            main_status_message_id = message.id
        elif status == "break":
            embed = discord.Embed(
                title="Ocky Deli is now on hold!",
                description="Please wait until a Chef is available to take new orders!",
            )
            embed.set_footer(text="Do not open a ticket during this time, you will not get a response.")
            message = await channel.send(embed=embed)
            main_status_message_id = message.id

            # Send same message to mirror channel
            if mirror_channel:
                try:
                    mirror_message = await mirror_channel.send(embed=embed)
                    status_message_id = mirror_message.id
                except:
                    pass
        elif status == "semi-open":
            embed = discord.Embed(
                title="Ocky Deli is now (semi) open.",
                description=(
                    "We are (semi) open. This means that our chefs will periodically check tickets from time to time. "
                    "Please be patient when waiting for a price quote, and expect some wait time. "
                    "Do NOT constantly ping our chefs, that will not make the process any faster."
                ),
            )
            message = await channel.send(embed=embed)
            main_status_message_id = message.id

            # Send same message to mirror channel
            if mirror_channel:
                try:
                    mirror_message = await mirror_channel.send(embed=embed)
                    status_message_id = mirror_message.id
                except:
                    pass
        else:  # close
            embed = discord.Embed(
                title="Ocky Deli is now CLOSED.",
                description=(
                    "We are currently closed. Please come back later when we're open for new orders! "
                    "Do not open a ticket, you will not get a response."
                ),
            )
            message = await channel.send(embed=embed)
            main_status_message_id = message.id

            # Send same message to mirror channel
            if mirror_channel:
                try:
                    mirror_message = await mirror_channel.send(embed=embed)
                    status_message_id = mirror_message.id
                except:
                    pass
        return True, ""
    except HTTPException as e:
        return False, f"Failed to rename channel: {e.status} {e.text}"