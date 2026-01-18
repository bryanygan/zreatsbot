import discord
from discord import app_commands
from discord.ext import commands
from ..utils.helpers import owner_only
import db
from config import EXP_MONTH, EXP_YEAR, ZIP_CODE

def setup(bot: commands.Bot):
    @bot.tree.command(name='feed', description='Generate feed command(s) with VCC from pool')
    @app_commands.describe(
        link='The order link (e.g., Uber Eats group order link)',
        amount='Number of feed commands to generate (default: 1, max: 10)'
    )
    async def feed(interaction: discord.Interaction, link: str, amount: int = 1):
        if not owner_only(interaction):
            return await interaction.response.send_message("You are not authorized.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Validate amount
        if amount < 1:
            amount = 1
        elif amount > 10:
            return await interaction.followup.send("Amount cannot exceed 10.", ephemeral=True)

        # Check if we have enough cards
        pool_counts = db.get_pool_counts()
        if pool_counts['cards'] < amount:
            return await interaction.followup.send(
                f"Not enough cards in pool. Requested: {amount}, Available: {pool_counts['cards']}",
                ephemeral=True
            )

        # Generate feed commands
        feed_commands = []
        for _ in range(amount):
            card_result = db.get_and_remove_card()

            if card_result is None:
                break

            number, cvv = card_result
            # Format: /feed orderinfo: link,card_number,exp_month/exp_year,cvv,zip_code
            feed_cmd = f"/feed orderinfo: {link},{number},{EXP_MONTH}/{EXP_YEAR},{cvv},{ZIP_CODE}"
            feed_commands.append(feed_cmd)

        if not feed_commands:
            return await interaction.followup.send("Card pool is empty.", ephemeral=True)

        # Send each command in its own code block for easy copying
        response = "\n\n".join([f"```{cmd}```" for cmd in feed_commands])

        # Check if response is too long
        if len(response) > 2000:
            # Split into multiple messages
            for cmd in feed_commands:
                await interaction.followup.send(f"```{cmd}```", ephemeral=True)
        else:
            await interaction.followup.send(response, ephemeral=True)
