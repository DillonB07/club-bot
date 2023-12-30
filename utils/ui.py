import discord

from discord import ui, SelectOption
from utils.data import COLORS

from utils.messages import create_embed

from .db import create_club


class ClubCreation(ui.Modal, title="Create Club"):
    name = ui.TextInput(
        label="Club Name",
        required=True,
        max_length=50,
        style=discord.TextStyle.short,
        min_length=3,
        placeholder="Anime Appreciation",
    )
    topic = ui.TextInput(
        label="Club Description",
        placeholder=f"Chat about anime & waifus here!",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=3,
        max_length=500,
    )
    reason = ui.TextInput(
        label="Club Reason",
        placeholder=f"I'd like this club to be created as anime is hated in #oof-topic so we want a safe space to chat",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
        min_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        return await create_club(
            self.name.value, self.topic.value, self.reason.value, interaction
        )

    async def on_error(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=await create_embed(
                "Club Creation Error",
                f"{interaction.user.display_name}, there was an error while creating your club. Please try again later.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )

    async def on_timeout(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=await create_embed(
                "Club Creation Error",
                f"{interaction.user.display_name}, there was an error while creating your club. Please try again later.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )
