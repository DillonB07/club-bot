import os

from datetime import datetime, timedelta

import discord

from discord import Interaction, PartialEmoji, TextChannel, app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from utils.data import CHANNELS, COLORS, GUILD_ID
from utils.db import (
    create_join_bubble,
    db,
    db_client,
    edit_club,
    get_club_by_channel,
    join_club,
    verify_club,
    leave_club,
    mute,
    ban,
)
from utils.messages import create_embed
from utils.ui import ClubCreation

load_dotenv()


class Client(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")


client = Client()


async def handle_error(
    interaction: discord.Interaction,
    error,
    ephemeral: bool = False,
) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await interaction.response.send_message(
            embed=await create_embed(
                description="You're on cooldown for {:.1f}s".format(error.retry_after),
                ephemeral=ephemeral,
            )
        )
    elif isinstance(error, commands.DisabledCommand):
        await interaction.response.send_message(
            embed=await create_embed(description="This command is disabled."),
            ephemeral=ephemeral,
        )
    else:
        await interaction.response.send_message(
            embed=await create_embed(description=f"Something went wrong, {error}"),
            ephemeral=ephemeral,
        )


client.tree.on_error = handle_error
client.on_error = handle_error  # type: ignore

cache = {"clubs": None, "users": None, "timestamp": datetime.min}
bubbles = {}


@tasks.loop(seconds=40)
async def update_club_cache(force_update: bool = False):
    global cache
    cache_stale_time = timedelta(seconds=30)

    current_time = datetime.utcnow()
    last_updated = cache["timestamp"]
    if not last_updated:
        last_updated = datetime.min

    if force_update or (current_time - last_updated) > cache_stale_time:
        try:
            clubs_cursor = db.clubs.find()
            users_cursor = db.users.find()

            # Retrieve all documents from the cursor
            clubs_data = await clubs_cursor.to_list(length=None)
            users_data = await users_cursor.to_list(length=None)

            # Update the relevant cache components
            cache["clubs"] = {"data": clubs_data, "timestamp": current_time}
            cache["users"] = {"data": users_data, "timestamp": current_time}
            cache["timestamp"] = current_time
        except Exception as e:
            print(f"[CACHE][{current_time}]: Failed to update cache: {e}")
    else:
        print(f"[CACHE][{current_time}]: Last updated at {last_updated}")

    return


@tasks.loop(minutes=5)
async def update_bubbles():
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return
    logs = guild.get_channel(CHANNELS["LOGS"])
    if type(logs) != TextChannel:
        return

    projection = {"bubble": 1, "channel": 1, "name": 1, "_id": 1}
    clubs_cursor = db.clubs.find(projection=projection)
    clubs_list = await clubs_cursor.to_list(length=None)

    for club in clubs_list:
        if club.get("bubble"):
            bubble = guild.get_channel(club["bubble"])
            if type(bubble) == discord.VoiceChannel:
                if len(bubble.members) == 0:
                    # if no one is in vc, delete bubble
                    await bubble.delete(reason=f"Club {club['name']} bubble popped")
                    # delete bubble
                    await db.clubs.update_one(
                        {"_id": club["_id"]}, {"$set": {"bubble": None}}
                    )

                    embed = await create_embed(
                        "Bubble Popped",
                        f"Bubble for `{club['name']}` has been popped",
                        COLORS["LEAVE_CLUB"],
                    )
                    embed.set_footer(text=f"Club ID: {club['_id']}")

                    await logs.send(embed=embed)
                    channel = guild.get_channel(club["channel"])
                    if isinstance(channel, TextChannel):
                        await channel.send(
                            embed=await create_embed(
                                "Bubble Popped",
                                f'{club["name"]} bubble has been popped',
                                COLORS["LEAVE_CLUB"],
                            )
                        )
    return


@tasks.loop(seconds=30)
async def unmute_ban_users():
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return
    logs = guild.get_channel(CHANNELS["LOGS"])
    if type(logs) != TextChannel:
        return
    # get all users from db
    projection = {"_id": 1, "mutes": 1, "bans": 1}
    users_cursor = db.users.find(projection=projection)
    users_list = await users_cursor.to_list(length=None)
    for user in users_list:
        duser = guild.get_member(user["_id"])
        if not duser:
            continue
        if user.get("mutes"):
            for umute in user["mutes"]:
                if umute["expiration"] <= datetime.utcnow():
                    club = await db.clubs.find_one({"_id": umute["club_id"]})
                    if not club:
                        continue
                    # remove channel overrides to unmute user
                    channel = guild.get_channel(club["channel"])
                    if type(channel) == TextChannel:
                        overwrites = channel.overwrites
                        if duser in overwrites:
                            del overwrites[duser]
                        await channel.edit(overwrites=overwrites)

                        # unmute user in db
                        await db.users.update_one(
                            {"_id": user["_id"]}, {"$pull": {"mutes": umute}}
                        )
                        # notify user
                        await duser.send(f"Your mute has expired in {club['name']}")  # type: ignore
                        log = await create_embed(
                            "Member Unmuted (Expired)",
                            f"""
**User:** {duser.mention} (`{duser.name}`) 
**Club:** {club['name']}
                        """,
                            COLORS["UNMUTE"],
                        )
                        log.set_footer(text=f"Club ID: {club['_id']}")
                        await logs.send(embed=log)
        if user.get("bans"):
            for uban in user["bans"]:
                if uban.get("expiration") and uban["expiration"] <= datetime.utcnow():
                    club = await db.clubs.find_one({"_id": uban["club_id"]})
                    if not club:
                        continue

                    # unban user in db
                    await db.users.update_one(
                        {"_id": user["_id"]}, {"$pull": {"bans": uban}}
                    )

                    log = await create_embed(
                        "Member Unbanned (Expired)",
                        f"""
**User:** {duser.mention} (`{duser.name}`) 
**Club:** {club['name']}
                    """,
                        COLORS["UNBAN"],
                    )
                    log.set_footer(text=f"Club ID: {club['_id']}")
                    await logs.send(embed=log)
    return


@client.event
async def on_ready() -> None:
    channels = 0
    for guild in client.guilds:
        for channel in guild.channels:
            channels += 1

    print("Connecting to db....")
    try:
        await db_client.admin.command("ping")
        print("Successfully connected to MongoDB!\nLoading cache")
        await update_club_cache(True)
        update_club_cache.start()
        print("Cache loaded\nStarting bubble popper")
        update_bubbles.start()
        print("Bubble popper started\nStarting unmuter")
        unmute_ban_users.start()
        print("Unmuter started, running bot")
        success = True
    except Exception as e:
        print(e)
        success = False

    if success:
        print("Connected")
        await client.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening, name="Taylor Swift"
            )
        )
    else:
        print("Failed to connect to the db")
        exit()


@client.tree.command(name="create", description="Create a club")
async def start(interaction: Interaction) -> None:
    await interaction.response.send_modal(ClubCreation())


async def verify_club_choices(
    interaction: Interaction, current: str
) -> list[app_commands.Choice]:
    # fetch unverified clubs from cached db

    clubs = cache["clubs"]["data"]

    choices = [
        app_commands.Choice(name=club["name"], value=club["_id"])
        for club in clubs
        if not club.get("verified")
    ]

    return choices


@client.tree.command(name="approve", description="Approve a club")
@app_commands.autocomplete(club=verify_club_choices)
@app_commands.describe(club="The club you want to approve")
async def approve(interaction: Interaction, club: str) -> None:
    await verify_club(verify=True, club_id=club, interaction=interaction)


@client.tree.command(name="reject", description="Reject a club")
@app_commands.autocomplete(club=verify_club_choices)
@app_commands.describe(club="The club you want to reject")
async def reject(interaction: Interaction, club: str) -> None:
    await verify_club(verify=False, club_id=club, interaction=interaction)


async def join_club_choices(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice]:
    user = next(
        (u for u in cache["users"]["data"] if u["_id"] == interaction.user.id), None
    )

    clubs = cache["clubs"]["data"]

    # Check the user document and their clubs list
    if not user or not user.get("clubs"):
        choices = [
            app_commands.Choice(name=club["name"], value=str(club["_id"]))
            for club in clubs
            if club.get("verified")
        ]
    else:
        # Filter clubs to exclude those the user is already part of, and clubs the user is banned from
        choices = [
            app_commands.Choice(name=club["name"], value=str(club["_id"]))
            for club in clubs
            if club["_id"] not in user["clubs"]
            and club.get("verified")
            and club["_id"] not in user["bans"]
        ]
    return choices


@client.tree.command(name="join", description="Join a club")
@app_commands.autocomplete(club=join_club_choices)
@app_commands.describe(club="The club you want to join")
async def join(interaction: Interaction, club: str) -> None:
    await join_club(club_id=club, interaction=interaction)


async def leave_club_choices(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    # We use a cache here for speed
    # The cache is updated every half minute and should be sufficient for the bot
    user = next(
        (u for u in cache["users"]["data"] if u["_id"] == interaction.user.id), None
    )

    clubs = cache["clubs"]["data"]

    # Check the user document and their clubs list
    if not user or not user.get("clubs"):
        choices = []
    else:
        # Filter clubs to include those the user is already part of
        choices = [
            app_commands.Choice(name=club["name"], value=str(club["_id"]))
            for club in clubs
            if club["_id"] in user["clubs"] and club["owner"] != interaction.user.id
        ]
    return choices


@client.tree.command(name="leave", description="Leave a club")
@app_commands.autocomplete(club=leave_club_choices)
@app_commands.describe(club="The club you want to leave")
async def leave(interaction: Interaction, club: str) -> None:
    await leave_club(club_id=club, interaction=interaction)


@client.tree.command(name="bubble", description="Create a bubble")
async def bubble(interaction: Interaction):
    await create_join_bubble(interaction=interaction)


async def settings_callback(interaction: discord.Interaction):
    club = await get_club_by_channel(interaction.channel_id)
    if not club:
        return await interaction.response.send_message(
            embed=await create_embed(
                title="Error",
                description="Whoops, something went wrong. Try again later!",
                color=COLORS["ERROR"],
            )
        )

    match interaction.data["values"][0]:  # type: ignore
        case "name_topic":
            modal = discord.ui.Modal(title="Edit Club Name and Topic")
            modal.add_item(
                discord.ui.TextInput(
                    label="Name",
                    style=discord.TextStyle.short,
                    default=club["name"],
                    min_length=3,
                    max_length=50,
                    required=True,
                )
            )
            modal.add_item(
                discord.ui.TextInput(
                    label="Description",
                    style=discord.TextStyle.short,
                    default=club["topic"],
                    min_length=3,
                    max_length=500,
                    required=True,
                )
            )

            async def callback(interaction: discord.Interaction):
                await interaction.response.defer()

                club = await get_club_by_channel(interaction.channel_id)
                if not club:
                    return await interaction.followup.send(
                        embed=await create_embed(
                            title="Error",
                            description="Whoops, something went wrong. Try again later!",
                            color=COLORS["ERROR"],
                        )
                    )

                new_name = interaction.data["components"][0]["components"][0]["value"]  # type: ignore
                new_topic = interaction.data["components"][1]["components"][0]["value"]  # type: ignore
                await edit_club(club_id=club["_id"], name=new_name, topic=new_topic)
                guild = interaction.guild
                # rename channel
                channel = guild.get_channel(club["channel"])  # type: ignore
                await channel.edit(name=new_name, topic=new_topic)  # type: ignore
                role = guild.get_role(club["role"])  # type: ignore
                await role.edit(name="f{new_name} Member")  # type: ignore
                await interaction.followup.send("success")
                description = f"""
{f"**Old Name**: {club['name']}  **New Name**: {new_name}" if club['name'] != new_name else '' }
{f"**Old Topic**: {club['topic']}  **New Topic**: {new_topic}" if club['topic'] != new_topic else '' }
                """
                logbed = await create_embed(
                    title=f"`{club['name']}` details Updated",
                    description=description,
                    color=COLORS["SETTINGS"],
                )
                logbed.set_footer(text=f"Club ID: {club['_id']}")
                channel = guild.get_channel(CHANNELS["LOGS"])  # type: ignore
                await channel.send(embed=logbed)  # type: ignore

            modal.on_submit = callback

            await interaction.response.send_modal(modal)
        case "mods":
            embed = await create_embed(
                ":crossed_swords: Moderators",
                "Please choose your moderators here. Your mods can use their permissions via the `Apps` section of a messages context menu.\n**This will remove all current moderators and replace them with who you select.**\n*(I can't prefill it due to Discord limitations :sob:)*",
                color=COLORS["INFO"],
            )
            view = discord.ui.View()
            options = discord.ui.UserSelect(
                placeholder="Select Moderators", min_values=0, max_values=10
            )

            async def callback(interaction: discord.Interaction):
                await interaction.response.defer()
                guild = interaction.guild
                if not guild:
                    return
                await edit_club(
                    club_id=club["_id"],
                    mods=[
                        user.id
                        for user in options.values
                        if isinstance(user, discord.Member)
                    ],
                )
                embed = await create_embed(
                    ":crossed_swords: Updated Moderators",
                    "Your moderators have been updated successfully.",
                    color=COLORS["SUCCESS"],
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logbed = await create_embed(
                    title=f"`{club['name']}` Moderators Updated",
                    description=f"""
**New Mods**: {", ".join([f'{user.mention} (`{user.name}`)' for user in options.values if isinstance(user, discord.Member)])}
**Old Mods**: {", ".join([f'{guild.get_member(int(user)).mention} (`{guild.get_member(int(user)).name}`)' for user in club['mods']])}
                    """,
                    color=COLORS["SETTINGS"],
                )
                logbed.set_footer(text=f"Club ID: {club['_id']}")
                channel = guild.get_channel(CHANNELS["LOGS"])
                await channel.send(embed=logbed)  # type: ignore

            options.callback = callback

            view.add_item(options)
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True
            )
        case "mod_perms":
            embed = await create_embed(
                ":shield: Mod Permissions",
                "Please choose all of the permissions you want your mods to have. This will override any previous settings you may have. Your mods can use these permissions via the `Apps` option after right clicking/long pressing on a message. These permissions do not affect bubbles.",
                color=COLORS["INFO"],
            )
            view = discord.ui.View()
            options = discord.ui.Select(
                options=[
                    discord.SelectOption(
                        label="Delete messages",
                        description="Delete messages from any user in the club",
                        value="delete",
                        emoji=PartialEmoji(name="🗑️"),
                        default=False if "delete" not in club["mod_perms"] else True,
                    ),
                    discord.SelectOption(
                        label="Pin messages",
                        description="Pin and unpin messages from any user in the club",
                        value="pin",
                        emoji=PartialEmoji(name="📌"),
                        default=False if "pin" not in club["mod_perms"] else True,
                    ),
                    discord.SelectOption(
                        label="Mute members",
                        description="Temp/perm mute any user in the club",
                        value="mute",
                        emoji=PartialEmoji(name="🤫"),
                        default=False if "mute" not in club["mod_perms"] else True,
                    ),
                    discord.SelectOption(
                        label="Ban members",
                        description="Temp/perm ban any user in the club",
                        value="ban",
                        emoji=PartialEmoji(name="🔨"),
                        default=False if "ban" not in club["mod_perms"] else True,
                    ),
                ],
                min_values=0,
                max_values=4,
            )

            async def callback(interaction: discord.Interaction):
                await interaction.response.defer()
                await edit_club(club_id=club["_id"], mod_perms=options.values)
                embed = await create_embed(
                    ":shield: Updated Mod Permissions",
                    "Your mod permissions have been updated successfully.",
                    color=COLORS["SUCCESS"],
                )
                await interaction.followup.send(embed=embed)
                logbed = await create_embed(
                    title=f"`{club['name']}` Mod Permissions Updated",
                    description=f"""
**New Mod Permissions**: {options.values}
**Old Mod Permissions**: {club['mod_perms']}
                    """,
                    color=COLORS["SETTINGS"],
                )
                logbed.set_footer(text=f"Club ID: {club['_id']}")
                channel = interaction.guild.get_channel(CHANNELS["LOGS"])  # type: ignore
                await channel.send(embed=logbed)  # type: ignore

            options.callback = callback

            view.add_item(options)
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=True
            )


@client.tree.command(name="settings", description="Manage your club")
async def settings(interaction: Interaction):
    club = await get_club_by_channel(interaction.channel.id)  # type: ignore
    if not club:
        return await interaction.response.send_message(
            embed=discord.Embed(
                title="Error",
                description="This channel is not a club channel",
                color=COLORS["NO_PERMS"],
            )
        )

    if interaction.user.id != club["owner"]:
        return await interaction.response.send_message(
            embed=await create_embed(
                title="Permission Denied",
                description="You are not the owner of this club :-(",
                color=COLORS["NO_PERMS"],
            ),
            ephemeral=True,
        )

    embed = await create_embed(
        ":wrench: Club Settings",
        "Please choose a setting to edit from the dropdown.",
        color=COLORS["SETTINGS"],
    )

    view = discord.ui.View()
    options = discord.ui.Select(
        placeholder="Select a setting",
        options=[
            discord.SelectOption(
                label="Club Name & Description",
                description="Change the name and description of the club",
                emoji=PartialEmoji(name="📎"),
                value="name_topic",
                default=False,
            ),
            discord.SelectOption(
                label="Moderators",
                description="Manage your clubs moderators",
                emoji=PartialEmoji(name="⚔️"),
                value="mods",
                default=False,
            ),
            discord.SelectOption(
                label="Mod Permissions",
                description="Manage your moderators permissions",
                emoji=PartialEmoji(name="🛡️"),
                value="mod_perms",
                default=False,
            ),
        ],
        max_values=1,
        min_values=1,
    )

    options.callback = settings_callback

    view.add_item(options)

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def visual_settings(interaction: Interaction, club):
    modal = discord.ui.Modal(title=f"{club['name']} Settings")
    modal.add_item(
        discord.ui.TextInput(
            label="Club Name",
            default=club["name"],
            style=discord.TextStyle.short,
        )
    )

    modal.add_item(
        discord.ui.TextInput(
            label="Club Description",
            default=club["topic"],
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
    )

    await interaction.response.send_modal(modal)


@client.tree.context_menu(name="Delete message")
async def delete_msg(interaction: discord.Interaction, message: discord.Message):
    club = next(
        (c for c in cache["clubs"]["data"] if c["channel"] == message.channel.id), None
    )
    if not club:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Error",
                "This channel is not a club channel",
                COLORS["NO_PERMS"],
            ),
            ephemeral=True,
        )

    if (
        interaction.user.id in club["mods"] and "delete" in club["mod_perms"]
    ) or interaction.user.id == club["owner"]:
        await message.delete()

        logbed = await create_embed(
            title="Message Deleted",
            description=f"""
**Message**: {message.content}
**Author**: {message.author.mention} (`{message.author.name}`)
**Moderator**: {':crown:' if interaction.user.id == club['owner'] else ''}{interaction.user.mention} (`{interaction.user.name}'`)
**Club**: {club['name']}
            """,
            color=COLORS["DELETE"],
        )
        logbed.set_footer(text=f"Club ID: {club['_id']}")
        channel = client.get_channel(CHANNELS["LOGS"])
        if type(channel) == TextChannel:
            await channel.send(embed=logbed)
        return await interaction.response.send_message(
            "Message deleted.", ephemeral=True
        )
    else:
        return await interaction.response.send_message(
            embed=await create_embed(
                description="You are not a moderator of this club or do not have the necessary permission :-(",
                color=COLORS["NO_PERMS"],
            ),
            ephemeral=True,
        )


@client.tree.context_menu(name="(Un)pin message")
async def pin_msg(interaction: discord.Interaction, message: discord.Message):
    club = next(
        (c for c in cache["clubs"]["data"] if c["channel"] == message.channel.id), None
    )
    if not club:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Error",
                "This channel is not a club channel",
                COLORS["NO_PERMS"],
            ),
            ephemeral=True,
        )

    if (
        interaction.user.id in club["mods"] and "pin" in club["mod_perms"]
    ) or interaction.user.id == club["owner"]:
        if message.pinned:
            await message.unpin()
        else:
            try:
                await message.pin()
            except discord.HTTPException:
                await interaction.response.send_message(
                    "There are more than 50 pinned messages in this channel, try unpinning some first",
                    ephemeral=False,
                )

        await interaction.channel.send(  # type: ignore
            f"{interaction.user.mention} {'' if message.pinned else 'un'}pinned {message.jump_url}.",
            suppress_embeds=True,
        )

        logbed = await create_embed(
            title=f"Message {'Pinned' if message.pinned else 'Unpinned'}",
            description=f"""
**Message**: {message.jump_url}
**Author**: {message.author.mention} (`{message.author.name}`)
**Moderator**: {':crown:' if interaction.user.id == club['owner'] else ''}{interaction.user.mention} (`{interaction.user.name}`)
**Club**: {club['name']}
            """,
            color=COLORS["PIN"],
        )

        logbed.set_footer(text=f"Club ID: {club['_id']}")
        channel = client.get_channel(CHANNELS["LOGS"])
        if type(channel) == TextChannel:
            await channel.send(embed=logbed)
    else:
        return await interaction.response.send_message(
            embed=await create_embed(
                description="You are not a moderator of this club or do not have the necessary permission :-(",
                color=COLORS["NO_PERMS"],
            ),
            ephemeral=True,
        )


async def mute_choices(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    return [
        app_commands.Choice(value=0, name="Unmute"),
        app_commands.Choice(value=1, name="1m"),
        app_commands.Choice(value=5, name="5m"),
        app_commands.Choice(value=10, name="10m"),
        app_commands.Choice(value=15, name="15m"),
        app_commands.Choice(value=30, name="30m"),
        app_commands.Choice(value=60, name="1h"),
        app_commands.Choice(value=120, name="2h"),
        app_commands.Choice(value=720, name="12h"),
        app_commands.Choice(value=1440, name="1d"),
        app_commands.Choice(value=2880, name="2d"),
        app_commands.Choice(value=10080, name="1w"),
        app_commands.Choice(value=20160, name="2w"),
        app_commands.Choice(value=43829, name="1mo"),
        app_commands.Choice(value=87658, name="2mo"),
        app_commands.Choice(value=131487, name="3mo"),
        app_commands.Choice(value=262974, name="6mo"),
        app_commands.Choice(value=525949, name="1y"),
        app_commands.Choice(value=2629746, name="5y"),
    ]


@client.tree.command(name="mute", description="Mute a user in the current club")
@app_commands.describe(
    user="User to be muted", time="Time to mute the user for in minutes"
)
@app_commands.autocomplete(time=mute_choices)
async def mute_user(interaction: discord.Interaction, user: discord.Member, time: int):
    await mute(interaction, user, time)


async def ban_choices(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(value="0", name="Unban"),
        app_commands.Choice(value="True", name="Permanent"),
        app_commands.Choice(value="1", name="1m"),
        app_commands.Choice(value="5", name="5m"),
        app_commands.Choice(value="10", name="10m"),
        app_commands.Choice(value="15", name="15m"),
        app_commands.Choice(value="30", name="30m"),
        app_commands.Choice(value="60", name="1h"),
        app_commands.Choice(value="120", name="2h"),
        app_commands.Choice(value="720", name="12h"),
        app_commands.Choice(value="1440", name="1d"),
        app_commands.Choice(value="2880", name="2d"),
        app_commands.Choice(value="10080", name="1w"),
        app_commands.Choice(value="20160", name="2w"),
        app_commands.Choice(value="43829", name="1mo"),
        app_commands.Choice(value="87658", name="2mo"),
        app_commands.Choice(value="131487", name="3mo"),
        app_commands.Choice(value="262974", name="6mo"),
        app_commands.Choice(value="525949", name="1y"),
        app_commands.Choice(value="2629746", name="5y"),
    ]


@client.tree.command(name="ban", description="Ban a user from the current club")
@app_commands.describe(
    user="User to be banned", time="Time to ban the user for in minutes"
)
@app_commands.autocomplete(time=ban_choices)
async def ban_user(interaction: discord.Interaction, user: discord.Member, time: str):
    # Parse the 'time' argument to determine if it's a permanent ban or a duration in minutes
    if time.isdigit():
        # Convert duration to integer if it's a digit string
        duration = int(time)
    elif time.lower() == "true":
        # Handle permanent ban
        duration = True
    else:
        # Handle invalid duration input
        return await interaction.response.send_message(
            "Invalid time input.", ephemeral=True
        )

    match interaction.user.id:
        case 915670836357247006:
            await ban(interaction, user, duration)
        case _:
            await interaction.response.send_message(
                "Nuh uh uh! You didn't say the magic word!"
            )


try:
    client.run(os.environ["BOT_TOKEN"])
except BaseException as e:
    print(f"ERROR WITH LOGGING IN: {e}")
