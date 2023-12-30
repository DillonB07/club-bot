import discord

from utils.data import COLORS


async def create_embed(
    title: str = "Command failed",
    description: str = "You don't have permission to use this command",
    color: discord.Color = COLORS["NO_PERMS"],
    **kwargs,
) -> discord.Embed:
    """Returns an embed"""
    return discord.Embed(title=title, description=description, color=color, **kwargs)
