import os
import discord
from discord import app_commands
from discord.ext import commands

from ..utils.channel_status import change_channel_status

OPENER_CHANNEL_ID = int(os.getenv('OPENER_CHANNEL_ID')) if os.getenv('OPENER_CHANNEL_ID') else None


def setup(bot: commands.Bot):
    @bot.tree.command(name='open', description='Open the channel and send announcements')
    @app_commands.describe(mode="Optional: Set to 'silent' to skip role ping announcement")
    @app_commands.choices(mode=[
        app_commands.Choice(name='Normal', value='normal'),
        app_commands.Choice(name='Silent', value='silent'),
    ])
    async def open_command(interaction: discord.Interaction, mode: app_commands.Choice[str] = None):
        if OPENER_CHANNEL_ID and interaction.channel.id != OPENER_CHANNEL_ID:
            return await interaction.response.send_message(
                "❌ This command can only be used in the opener channel.", ephemeral=True
            )
        
        # Determine if silent mode is requested
        silent_mode = mode and mode.value == 'silent'
        
        success, error = await change_channel_status(interaction.channel, "open", silent=silent_mode)
        if success:
            await interaction.response.send_message("✅ Channel opened.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)

    @bot.tree.command(name='break', description='Put the channel on hold')
    async def break_command(interaction: discord.Interaction):
        if OPENER_CHANNEL_ID and interaction.channel.id != OPENER_CHANNEL_ID:
            return await interaction.response.send_message(
                "❌ This command can only be used in the opener channel.", ephemeral=True
            )
        success, error = await change_channel_status(interaction.channel, "break")
        if success:
            await interaction.response.send_message("✅ Channel put on hold.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)

    @bot.tree.command(name='close', description='Close the channel and send announcements')
    async def close_command(interaction: discord.Interaction):
        if OPENER_CHANNEL_ID and interaction.channel.id != OPENER_CHANNEL_ID:
            return await interaction.response.send_message(
                "❌ This command can only be used in the opener channel.", ephemeral=True
            )
        success, error = await change_channel_status(interaction.channel, "close")
        if success:
            await interaction.response.send_message("✅ Channel closed.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)      