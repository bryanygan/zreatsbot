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

    @bot.tree.command(name='bulk_feed', description='Generate feed commands for multiple links')
    @app_commands.describe(
        links='Multiple order links separated by spaces',
        amount='Number of feed commands per link (default: 1, max: 5)'
    )
    async def bulk_feed(interaction: discord.Interaction, links: str, amount: int = 1):
        if not owner_only(interaction):
            return await interaction.response.send_message("You are not authorized.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Parse links (split by space)
        link_list = [link.strip() for link in links.split() if link.strip()]

        if not link_list:
            return await interaction.followup.send("No valid links provided.", ephemeral=True)

        # Validate amount
        if amount < 1:
            amount = 1
        elif amount > 5:
            return await interaction.followup.send("Amount per link cannot exceed 5.", ephemeral=True)

        total_cards_needed = len(link_list) * amount

        # Check if we have enough cards
        pool_counts = db.get_pool_counts()
        if pool_counts['cards'] < total_cards_needed:
            return await interaction.followup.send(
                f"Not enough cards in pool. Needed: {total_cards_needed} ({len(link_list)} links x {amount}), Available: {pool_counts['cards']}",
                ephemeral=True
            )

        # Generate feed commands for each link
        all_commands = []
        for link in link_list:
            for _ in range(amount):
                card_result = db.get_and_remove_card()

                if card_result is None:
                    break

                number, cvv = card_result
                feed_cmd = f"/feed orderinfo: {link},{number},{EXP_MONTH}/{EXP_YEAR},{cvv},{ZIP_CODE}"
                all_commands.append(feed_cmd)

        if not all_commands:
            return await interaction.followup.send("Card pool is empty.", ephemeral=True)

        # Send commands in batches to avoid message length limits
        current_batch = []
        current_length = 0

        for cmd in all_commands:
            cmd_block = f"```{cmd}```"
            # Account for newlines between blocks
            block_length = len(cmd_block) + 2

            if current_length + block_length > 1900:
                # Send current batch
                await interaction.followup.send("\n\n".join(current_batch), ephemeral=True)
                current_batch = [cmd_block]
                current_length = block_length
            else:
                current_batch.append(cmd_block)
                current_length += block_length

        # Send remaining commands
        if current_batch:
            await interaction.followup.send("\n\n".join(current_batch), ephemeral=True)
