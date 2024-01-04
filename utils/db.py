import os

from datetime import datetime, timedelta

import discord

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
from utils.data import CHANNELS, COLORS, EMOJIS, NEW_CLUB_MESSAGE, CLUBS_CATEGORY, ROLES

from utils.messages import create_embed

# Set the Stable API version when creating a new client
db_client = AsyncIOMotorClient(os.environ["MONGO_URI"], server_api=ServerApi("1"))
db = db_client.data
clubs = db.clubs
users = db.users


async def create_club(name, topic, reason, interaction):
    guild = interaction.guild
    user = interaction.user

    user_entry = await users.find_one_and_update(
        {"_id": user.id}, {"$set": {"owns_club": True}}, upsert=True
    )
    if user_entry and user_entry.get("owns_club"):
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Creation Error",
                f"{user.display_name}, you already own a club.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )

    club = await clubs.insert_one(
        {
            "owner": user.id,
            "name": name,
            "topic": topic,
            "verified": False,
            "mods": [],
            "mod_perms": [],
            "bubble": None,
        }
    )

    modbed = await create_embed(
        f"Club Request: `{name}`",
        f"{user.mention}(`{user.name}`) has requested to create a club.",
        COLORS["NEW_CLUB"],
    )

    modbed.add_field(name="Topic", value=topic)
    modbed.add_field(name="Reason", value=reason)
    modbed.set_footer(text=f"Club ID: {club.inserted_id}")

    channel = guild.get_channel(CHANNELS["MODS"])

    await channel.send(embed=modbed)

    channel = guild.get_channel(CHANNELS["LOGS"])
    await channel.send(embed=modbed)

    embed = await create_embed(
        "Requested Club Creation",
        f"""
Hi {user.display_name}!
You have requested creation of the `{name}` club with the following information.
The request will be looked at by the mods and I'll let you know if your club is accepted
        """,
        COLORS["NEW_CLUB"],
    )
    embed.add_field(name="Topic", value=topic)
    embed.add_field(name="Reason", value=reason)
    embed.set_footer(text=f"Club ID: {club.inserted_id}")
    await user.send(embed=embed)

    return await interaction.response.send_message(
        embed=await create_embed(
            "Requested Club Creation",
            f"{user.display_name}, your club has been requested.",
            color=COLORS["SUCCESS"],
        ),
        ephemeral=True,
    )


async def verify_club(verify, club_id, interaction):
    guild = interaction.guild
    if guild.get_role(ROLES["MODS"]) not in interaction.user.roles:
        return await interaction.response.send_message(embed=await create_embed())
    club = await clubs.find_one({"_id": ObjectId(club_id)})

    if club:
        if club.get("verified"):
            return await interaction.response.send_message(
                embed=await create_embed(
                    "Club Verification Error",
                    f"{interaction.user.display_name}, this club has already been verified.",  
                    color=COLORS["ERROR"],
                ),
                ephemeral=True,
            )
        owner = guild.get_member(club["owner"])

        if verify:
            role = await guild.create_role(name=f"{club['name']} Member")
            mute = guild.get_role(ROLES["MUTE"])
            channel = await guild.create_text_channel(
                name=club["name"],
                category=guild.get_channel(CLUBS_CATEGORY),
                topic=club["topic"],
                overwrites={
                    # overwrite club owner
                    owner: discord.PermissionOverwrite(
                        manage_messages=True, manage_webhooks=True
                    ),
                    role: discord.PermissionOverwrite(
                        send_messages=True, view_channel=True
                    ),
                    mute: discord.PermissionOverwrite(
                        send_messages=False, send_messages_in_threads=False
                    ),
                    guild.default_role: discord.PermissionOverwrite(
                        send_messages=False, view_channel=False
                    ),
                },
            )

            await clubs.update_one(
                {"_id": ObjectId(club_id)},
                {"$set": {"role": role.id, "verified": True, "channel": channel.id}},
            )
            await users.update_one(
                {"_id": club["owner"]},
                {
                    "$set": {"owns_club": verify},
                    "$addToSet": {"clubs": ObjectId(club_id)},
                },
            )

            await owner.add_roles(role, reason="Club owner")

            # Create club channel
        else:
            # Club rejected, delete from db
            await clubs.delete_one({"_id": club_id})
            await users.update_one(
                {"_id": club["owner"]}, {"$set": {"owns_club": False}}
            )

        word = "approved" if verify else "rejected"
        color = COLORS["SUCCESS"] if verify else COLORS["ERROR"]

        logbed = await create_embed(
            f"Club {word.capitalize()}",
            f"`{club['name']}` has been {word} by {interaction.user.mention}(`{interaction.user.name}`.)",  
            color,
        )
        logbed.set_footer(text=f"Club ID: {club_id}")

        channel = guild.get_channel(CHANNELS["LOGS"])
        await channel.send(embed=logbed)

        embed = await create_embed(
            f"Club {word.capitalize()}",
            f"You have {word} the club: `{club['name']}`",
            color=color,
        )

        await interaction.response.send_message(embed=embed)

        next_embed = await create_embed(
            f"`{club['name']}` Club {word.capitalize()}",
            f"""
bHi {owner.display_name}!
Your club `{club['name']}` has been {word} by the mods.
{NEW_CLUB_MESSAGE if verify else 'You may submit a new club request in the future.'}
            """,
            color=color,
        )

        await owner.send(embed=next_embed)

        return True
    return False


async def join_club(club_id: str, interaction):
    club = await clubs.find_one({"_id": ObjectId(club_id)})
    # If the user exists, add the club to their `clubs` array
    if not club:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Join Failed",
                "The club does not exist.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )
    elif not club["verified"]:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Join Failed",
                "This club has not been approved yet.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )
    user = await users.find_one({"_id": interaction.user.id})
    if any(ban.get("club_id") == club["_id"] for ban in user["bans"]):
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Join Failed",
                "You have been banned from this club.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )

    update_result = await users.update_one(
        {"_id": interaction.user.id},
        {"$addToSet": {"clubs": ObjectId(club_id)}},
        upsert=True,
    )
    await interaction.user.add_roles(
        interaction.guild.get_role(club["role"]), reason="Joined club"
    )
    if update_result.modified_count or update_result.upserted_id:
        modbed = await create_embed(
            "Club Joined",
            f"{interaction.user.mention}(`{interaction.user.name}`) has joined `{club['name']}`.",  
            COLORS["JOIN_CLUB"],
        )
        modbed.set_footer(text=f"Club ID: {club['_id']}")

        channel = interaction.guild.get_channel(CHANNELS["LOGS"])
        await channel.send(embed=modbed)

        channel = interaction.guild.get_channel(club["channel"])
        await channel.send(
            f"*{interaction.user.mention} has joined the **{club['name']}** club <:{EMOJIS['REPLJOY']['name']}:{EMOJIS['REPLJOY']['id']}>*"  
        )

        embed = await create_embed(
            "Joined Club",
            f"You have joined the club: `{club['name']}`",
            COLORS["SUCCESS"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return True
    else:
        embed = await create_embed(
            "Already Joined",
            f"You have already joined the club: `{club['name']}`",
            COLORS["ERROR"],
        )
        await interaction.response.send_message(embed=embed)
        return False


async def leave_club(club_id: str, interaction):
    club = await clubs.find_one({"_id": ObjectId(club_id)})
    # If the user exists, add the club to their `clubs` array
    if not club:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Leave Failed",
                "The club does not exist.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )

    update_result = await users.update_one(
        {"_id": interaction.user.id},
        {"$pull": {"clubs": ObjectId(club_id)}},
        upsert=True,
    )
    await interaction.user.remove_roles(
        interaction.guild.get_role(club["role"]), reason="Left club"
    )
    if update_result.modified_count or update_result.upserted_id:
        modbed = await create_embed(
            "Club Left",
            f"{interaction.user.mention}(`{interaction.user.name}`) has left `{club['name']}`.",  
            COLORS["LEAVE_CLUB"],
        )
        modbed.set_footer(text=f"Club ID: {club['_id']}")

        channel = interaction.guild.get_channel(CHANNELS["LOGS"])
        await channel.send(embed=modbed)

        embed = await create_embed(
            "Left Club",
            f"You have left the club: `{club['name']}`",
            COLORS["SUCCESS"],
        )

        channel = interaction.guild.get_channel(club["channel"])
        await channel.send(
            f"*{interaction.user.mention} has left the **{club['name']}** club <:{EMOJIS['REPLSAD']['name']}:{EMOJIS['REPLSAD']['id']}>*"  
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        return True
    else:
        embed = await create_embed(
            "Not in club",
            "You cannot leave a club you're not in!",
            COLORS["ERROR"],
        )
        await interaction.response.send_message(embed=embed)
        return False


async def delete_club(club_id: str, interaction):
    club = await clubs.find_one({"_id": ObjectId(club_id)})
    # If the user exists, add the club to their `clubs` array
    if not club:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Delete Failed",
                "The club does not exist.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )


async def create_join_bubble(interaction: discord.Interaction):
    # Get current channel name

    channel, guild = interaction.channel, interaction.guild
    if not guild or type(channel) != discord.TextChannel:
        return

    club = await get_club_by_channel(channel.id)
    if not club:
        return

    # Get current bubble if it exists, or return None
    bubble = next(
        (c for c in guild.channels if c.name == f"{club['name']} Bubble"), None
    )

    if bubble:
        return await interaction.response.send_message(
            f"{interaction.user.mention} You already have a bubble: {bubble.mention}!"
        )

    role = guild.get_role(club["role"])
    bubble = await guild.create_voice_channel(
        f"{club['name']} Bubble",
        category=guild.get_channel(CLUBS_CATEGORY),
        reason=f'{club["name"]} bubble created by {interaction.user.name}',
        overwrites={
            role: discord.PermissionOverwrite(view_channel=True, stream=None),
            guild.get_role(ROLES["MUTE"]): discord.PermissionOverwrite(
                stream=False, speak=False, send_messages=False
            ),
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
            ),
        },
    )

    await clubs.update_one(
        {"_id": ObjectId(club["_id"])},
        {"$set": {"bubble": bubble.id}},
    )

    modbed = await create_embed(
        "Bubble Created",
        f"{interaction.user.mention}(`{interaction.user.name}`) has created a bubble for `{club['name']}`.",  
        COLORS["NEW_CLUB"],
    )
    modbed.set_footer(text=f"Club ID: {club['_id']}")

    channel = guild.get_channel(CHANNELS["LOGS"])
    await channel.send(embed=modbed)

    embed = await create_embed(
        "Bubble Created",
        f"{interaction.user.mention} has created a bubble! Go hop in at {bubble.mention}! It will be popped shortly if not in use",  
        COLORS["NEW_CLUB"],
    )

    await interaction.response.send_message(embed=embed)


async def mute(interaction: discord.Interaction, user: discord.Member, time: int):
    club = await get_club_by_channel(interaction.channel_id)
    clubber = await users.find_one({"_id": user.id})
    if not club or not clubber:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Mute Failed",
                "The club or member does not exist.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )

    if (
        interaction.user.id not in club["mods"] or "mute" not in club["mod_perms"]
    ) and interaction.user.id != club["owner"]:
        return await interaction.response.send_message(
            embed=await create_embed(
                title="No Permission",
                description="You must be a moderator with permission to mute people",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )

    if (
        user.id in club.get("mods")
        or user.id == club.get("owner")
        or interaction.guild.get_role(ROLES["MODS"]) in user.roles
    ):  
        return await interaction.response.send_message(
            embed=await create_embed(
                "Mute Failed",
                "You cannot mute a club or server moderator.",
                color=COLORS["ERROR"],
            ),
            ephemeral=False,
        )

    expiry = await update_user_mutes(user.id, str(club["_id"]), duration=time)
    channel = interaction.channel
    if type(channel) != discord.TextChannel:
        return await interaction.response.send_message(
            embed=await create_embed(
                description="Whoops, something went wrong :cry:",
                color=COLORS["ERROR"],
            )
        )
    # update channel overrides to mute user
    overwrites = channel.overwrites
    if time > 0:
        overwrites[user] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            speak=False,
            add_reactions=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
        )
        await channel.edit(overwrites=overwrites)
        await interaction.response.send_message(
            embed=await create_embed(
                "Club Mute Success",
                f"{user.mention} has been muted for {time} minutes. It expires <t:{expiry}:R>",  
                color=COLORS["SUCCESS"],
            )
        )
        await user.send(
            f'You have been muted in {club["name"]} club for {time} minutes by {interaction.user.display_name}. This will expire <t:{expiry}:R>'  
        )
        log = await create_embed(
            "Club Mute",
            f"""
    **User:** {user.mention} (`{user.name}`)
    **Moderator:** {interaction.user.mention} (`{interaction.user.name}`)
    **Club:** {club['name']}
    **Duration:** {time} minutes
    **Expiry:** <t:{expiry}:R>
    """,
            COLORS["MUTE"],
        )
    else:
        # remove the users overrides as they're unmuted
        if user in overwrites:
            del overwrites[user]
        await channel.edit(overwrites=overwrites)

        await interaction.response.send_message(
            embed=await create_embed(
                "Club Mute Success",
                f"{user.mention} has been unmuted.",
                color=COLORS["SUCCESS"],
            )
        )
        await user.send(
            f'You have been unmuted in {club["name"]} club by {interaction.user.display_name}'  
        )

        log = await create_embed(
            "Member Unmuted",
            f"""
**User:** {user.mention} (`{user.name}`)
**Moderator:** {interaction.user.mention} (`{interaction.user.name}`)
**Club:** {club['name']}
""",
            COLORS["UNMUTE"],
        )

    channel = interaction.guild.get_channel(CHANNELS["LOGS"])  # type:ignore
    log.set_footer(text=f"Club ID: {club['_id']}")
    await channel.send(embed=log)


async def update_user_mutes(user_id: int, club_id: str, duration: int = 0):
    """Update a user's mute information in the database.

    Args:
        user_id (int): The ID of the user to update.
        club_id (str): The ID of the club the mute applies to.
        duration (int, optional): The duration of the mute in minutes. If 0 or less, the mute is removed.
    Returns:
        int: The Unix time when the mute will expire, or None if the user was unmuted.
    """  
    club_obj_id = ObjectId(club_id)
    if duration > 0:
        mute_expiration = datetime.utcnow() + timedelta(minutes=duration)
        # Check if the mute already exists for this club.
        existing_mute = await users.find_one(
            {"_id": user_id, "mutes.club_id": club_obj_id}
        )
        if existing_mute:
            # If it does, update the existing mute's expiration.
            await users.update_one(
                {"_id": user_id, "mutes.club_id": club_obj_id},
                {"$set": {"mutes.$.expiration": mute_expiration}},
            )
        else:
            # If not, push a new mute onto the mutes array.
            await users.update_one(
                {"_id": user_id},
                {
                    "$push": {
                        "mutes": {"club_id": club_obj_id, "expiration": mute_expiration}
                    }
                },
            )
    else:
        # If duration is 0 or less, remove the mute.
        await users.update_one(
            {"_id": user_id}, {"$pull": {"mutes": {"club_id": club_obj_id}}}
        )
        mute_expiration = None

    # Return the Unix timestamp of when the mute expires or None if unmuting.
    return int(mute_expiration.timestamp()) if mute_expiration else None


async def ban(
    interaction: discord.Interaction, user: discord.Member, duration: int | bool
):
    """Bans or unbans a user from the club based on the duration provided.

    Parameters:
        interaction (discord.Interaction): The interaction object containing the context of the command.
        user (discord.Member): The member object representing the user to be banned or unbanned.
        duration (int | bool): The duration for which the user is to be banned, in minutes. If set to False or a non-positive integer, the ban is lifted. If set to True, the user is banned indefinitely.
    """  
    club = await get_club_by_channel(interaction.channel_id)
    clubber = await users.find_one({"_id": user.id})

    if not club or not clubber:
        return await interaction.response.send_message(
            embed=await create_embed(
                "Club Ban Failed",
                "The club or member does not exist.",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )
    elif (
        interaction.user.id not in club["mods"] or "ban" not in club["mod_perms"]
    ) and interaction.user.id != club["owner"]:
        return await interaction.response.send_message(
            embed=await create_embed(
                title="No Permission",
                description="You must be a moderator with permission to ban people",
                color=COLORS["ERROR"],
            ),
            ephemeral=True,
        )
    elif (
        user.id in club.get("mods")
        or user.id == club.get("owner")
        or interaction.guild.get_role(ROLES["MODS"]) in user.roles
    ):  
        return await interaction.response.send_message(
            embed=await create_embed(
                "Ban Failed",
                "You cannot ban a club or server moderator.",
                color=COLORS["ERROR"],
            ),
            ephemeral=False,
        )
    club_obj_id = ObjectId(club["_id"])

    if {"club_id": club_obj_id} in clubber.get("bans", []):
        return await interaction.response.send_message(
            embed=await create_embed(
                "Ban Failed",
                f"{user.mention} is already banned from this club.",
                color=COLORS["ERROR"],
            )
        )

    role = interaction.guild.get_role(club["role"])

    if isinstance(duration, bool) and duration is True:
        # Permanent ban
        ban_expiration = None

        await users.update_one(
            {"_id": user.id},
            {
                "$push": {
                    "bans": {"club_id": club_obj_id, "expiration": ban_expiration}
                },
                "$pull": {"clubs": club_obj_id},
            },
        )

        await user.remove_roles(role)

        await user.send(
            embed=await create_embed(
                "Permanent Club Ban",
                f"""
Hey {user.display_name},
Unfortunately, you have been permanently banned from {club['name']} club by {interaction.user.mention}(`{interaction.user.name}`).
If a moderator decides to unban you in the future, I'll let you know here!
""",  
                color=COLORS["BAN"],
            )
        )

        await interaction.response.send_message(
            embed=await create_embed(
                f"Permanently Banned {user.mention}",
                f"{user.mention} has been permanently banned by {interaction.user.mention}.",  
                color=COLORS["SUCCESS"],
            )
        )

        logbed = await create_embed(
            "Permanent Club Ban",
            f"""
**User:** {user.mention} (`{user.name}`)
**Moderator:** {interaction.user.mention} (`{interaction.user.name}`)
**Club:** {club['name']}
""",
            color=COLORS["BAN"],
        )
    elif isinstance(duration, int) and duration > 0:
        # Temporary ban with expiration
        ban_expiration = datetime.utcnow() + timedelta(minutes=duration)
        timestamp = int(ban_expiration.timestamp())

        await user.remove_roles(role)

        await users.update_one(
            {"_id": user.id},
            {
                "$push": {
                    "bans": {"club_id": club_obj_id, "expiration": ban_expiration}
                },
                "$pull": {"clubs": club_obj_id},
            },
        )
        await user.send(
            embed=await create_embed(
                "Temporary Club Ban",
                f"""
Hey {user.display_name},
Unfortunately, you have been temporarily banned from {club['name']} club by {interaction.user.mention}(`{interaction.user.name}`).
Your ban will expire <t:{timestamp}:R> or a moderator may decide to unban you.
""",  
                color=COLORS["BAN"],
            )
        )
        logbed = await create_embed(
            "Temporary Club Ban",
            f"""
**User:** {user.mention} (`{user.name}`)
**Moderator:** {interaction.user.mention} (`{interaction.user.name}`)
**Club:** {club['name']}
**Duration:** {duration} minutes
**Expiry:** <t:{timestamp}:R>
""",
            color=COLORS["BAN"],
        )

    else:
        # If duration is 0 or less, remove the ban.
        await users.update_one(
            {"_id": user.id}, {"$pull": {"bans": {"club_id": club_obj_id}}}
        )

        await user.send(
            embed=await create_embed(
                "Unbanned from Club",
                f"You have been unbanned from {club['name']} club by {interaction.user.mention} (`{interaction.user.name}`)",  
                COLORS["UNBAN"],
            )
        )
        logbed = await create_embed(
            "Club Unban",
            f"""
**User:** {user.mention} (`{user.name}`)
**Moderator:** {interaction.user.mention} (`{interaction.user.name}`)
**Club:** {club['name']}
            """,
            color=COLORS["UNBAN"],
        )
        await interaction.response.send_message(
            embed=await create_embed(
                f"Unbanned {user.mention}",
                f"{user.mention} has been unbanned by {interaction.user.mention}",
                color=COLORS["SUCCESS"],
            )
        )

        ban_expiration = None

    logbed.set_footer(text=f"Club ID: {club['_id']}")
    channel = interaction.guild.get_channel(CHANNELS["LOGS"])
    if isinstance(channel, discord.TextChannel):
        await channel.send(embed=logbed)


async def get_club(club_id):
    return await clubs.find_one({"_id": club_id})


async def get_club_by_name(name):
    return await clubs.find_one({"name": name})


async def get_club_by_channel(channel):
    return await clubs.find_one({"channel": channel})


async def edit_club(club_id: str, **kwargs):
    return await clubs.update_one({"_id": ObjectId(club_id)}, {"$set": kwargs})
