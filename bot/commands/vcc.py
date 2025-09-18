import discord
from discord import app_commands
from discord.ext import commands
from ..utils.helpers import owner_only
import db

EXP_MONTH = '09'
EXP_YEAR = '30'
ZIP_CODE = '07724'

def setup(bot: commands.Bot):
    @bot.tree.command(name='vcc', description='Pull a card from the pool in order format')
    async def vcc(interaction: discord.Interaction):
        if not owner_only(interaction):
            return await interaction.response.send_message("❌ You are not authorized.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        card_result = db.get_and_remove_card()

        if card_result is None:
            return await interaction.followup.send("❌ Card pool is empty.", ephemeral=True)

        number, cvv = card_result

        card_format = f"{number},{EXP_MONTH}/{EXP_YEAR},{cvv},{ZIP_CODE}"

        await interaction.followup.send(f"```{card_format}```", ephemeral=True)