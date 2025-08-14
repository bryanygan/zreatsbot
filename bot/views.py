import discord
from discord.ui import View, Button
from discord import ButtonStyle

# Global variable to control CashApp button visibility
CASHAPP_ENABLED = True

def set_cashapp_enabled(enabled: bool):
    """Set the CashApp button visibility"""
    global CASHAPP_ENABLED
    CASHAPP_ENABLED = enabled

def is_cashapp_enabled():
    """Check if CashApp button is enabled"""
    return CASHAPP_ENABLED


class PaymentView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Dynamically add/remove CashApp button based on setting
        if not is_cashapp_enabled():
            # Remove the CashApp button if it exists
            for item in self.children[:]:
                if hasattr(item, 'custom_id') and item.custom_id == 'payment_cashapp':
                    self.remove_item(item)

    @discord.ui.button(label='Zelle', style=ButtonStyle.danger, emoji='🏦', custom_id='payment_zelle')
    async def zelle_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="💳 Zelle Payment",
            color=0x6534D1
        )
        embed.add_field(name="Email:", value="```ganbryanbts@gmail.com```", inline=False)
        embed.add_field(name="📝 Note:", value="Name is **Bryan Gan**", inline=False)
        view = CopyablePaymentView("zelle")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label='Venmo', style=ButtonStyle.primary, emoji='💙', custom_id='payment_venmo')
    async def venmo_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="💙 Venmo Payment", color=0x008CFF)
        embed.add_field(name="Username:", value="```@BGHype```", inline=False)
        embed.add_field(name="📝 Note:", value="Friends & Family, single emoji note only\nLast 4 digits: **0054** (if required)", inline=False)
        view = CopyablePaymentView("venmo")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label='PayPal', style=ButtonStyle.success, emoji='💚', custom_id='payment_paypal')
    async def paypal_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="💚 PayPal Payment", color=0x00CF31)
        embed.add_field(name="Email:", value="```ganbryanbts@gmail.com```", inline=False)
        embed.add_field(name="📝 Note:", value="Friends & Family, no notes", inline=False)
        view = CopyablePaymentView("paypal")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label='CashApp', style=ButtonStyle.success, emoji='💵', custom_id='payment_cashapp')
    async def cashapp_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="💵 CashApp Payment", color=0x00D632)
        embed.add_field(name="CashTag:", value="```$bygan```", inline=False)
        embed.add_field(name="📝 Note:", value="Must be from balance, single emoji note only", inline=False)
        view = CopyablePaymentView("cashapp")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label='Crypto', style=ButtonStyle.secondary, emoji='🪙', custom_id='payment_crypto')
    async def crypto_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="🪙 Crypto Payment", color=0xffa500)
        embed.add_field(name="Available:", value="ETH, LTC, SOL, BTC, USDT, USDC", inline=False)
        embed.add_field(name="📝 Note:", value="Message me for more details and wallet addresses", inline=False)
        view = CopyablePaymentView("crypto")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CopyablePaymentView(View):
    def __init__(self, payment_type: str):
        super().__init__(timeout=300)
        self.payment_type = payment_type

    @discord.ui.button(label='📋 Get Copyable Info', style=ButtonStyle.secondary, emoji='📱')
    async def get_copyable_info(self, interaction: discord.Interaction, button: Button):
        if self.payment_type == "zelle":
            message = """ganbryanbts@gmail.com"""
        elif self.payment_type == "venmo":
            message = """@BGHype"""
        elif self.payment_type == "paypal":
            message = """ganbryanbts@gmail.com"""
        elif self.payment_type == "cashapp":
            message = """$bygan"""
        elif self.payment_type == "crypto":
            message = """**Crypto Payment Info:**\nAvailable: ETH, LTC, SOL, BTC, USDT, USDC\nNote: Message me for wallet addresses"""
        else:
            message = "Payment information not available."
        await interaction.response.send_message(message)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True