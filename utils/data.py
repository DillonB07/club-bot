import discord

GUILD_ID = 1182070952675266743  # Dev
# GUILD_ID = 437048931827056642 # FoR

CHANNELS = {"MODS": 1182086149515268268, "LOGS": 1182086187612123137}

# COLORS: Used in embeds
COLORS = {
    "NO_PERMS": discord.Color.red(),
    "SUCCESS": discord.Color.green(),
    "ERROR": discord.Color.red(),
    "NEW_CLUB": discord.Color.blue(),
    "JOIN_CLUB": discord.Color.blurple(),
    "LEAVE_CLUB": discord.Color.teal(),
    "SETTINGS": discord.Color.gold(),
    "DELETE": discord.Color.dark_red(),
    "PIN": discord.Color.dark_green(),
    "INFO": discord.Color.from_str("#ffffff"),
    "MUTE": discord.Color.dark_teal(),
    "UNMUTE": discord.Color.dark_gold(),
    "BAN": discord.Color.dark_magenta(),
    "UNBAN": discord.Color.dark_purple(),
}

CLUBS_CATEGORY = 1182384593140195338  # Dev
# CLUBS_CATEGORY = 1038125721287151656 # FoR

ROLES = {
    "MODS": 1182390311994003467,  # Dev
    # "MODS": 438855279363489812 # FoR Mods role
    "MUTE": 1183478733361905694,  # Dev
    # "MUTE": 439823181046611970 # FoR Muted role
    "CADMIN": 1182390311994003467,  # Dev
    "ADMIN": 1062520912726990869,  # FoR Janitors role
}

EMOJIS = {
    "REPLJOY": {
        "name": "repljoy",
        # "id": 829044813911031859 # FoR
        "id": 1183445697991823452,  # Dev
    },
    "REPLSAD": {
        "name": "replsad",
        # "id": 829045222880313385 # FoR
        "id": 1183445635962261524,  # Dev
    },
}

NEW_CLUB_MESSAGE = """
Now that your club has been approved, here's what you need to know:

**Rules**:
1. Do not ping @everyone or @here, this may result in the ownership of your club being transferred to somebody else.
2. The server rules must be followed, with the exceptions of the following rules which are enforced at your discretion.
    - Languages
    - Self-promo
3. You are responsible for your club. Any breaking of the rules, may result in punishments which include (but are not limited to) the following:
    - Server mute
    - Transfer of club ownership
    - Club deletion
    - Server bans

**Moderation**:
You are able to assign moderators to your club. You can change the permissions that moderators have with `/club settings`. Here's what permissions you can give:
- Pin & unpin messages
- Delete messages
- Mute & unmute members
- Ban & unban members

*Club admins cannot be moderated and will have access to all of these*

**Webhooks**:
You can create webhooks to post messages to your club. Webhooks are not allowed to ping @everyone/@here - Doing this **will** result in removal of your club ownership.
"""
