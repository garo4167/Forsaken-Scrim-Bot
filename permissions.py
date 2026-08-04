import discord

import config


def is_moderator(member: discord.Member) -> bool:
    return any(r.name == config.MODERATOR_ROLE for r in getattr(member, "roles", []))
