import asyncio
import os

import discord
from discord.ext import commands

import config
import database
from views import QueueView

intents = discord.Intents.default()
intents.members = True          # needed to look up members for voice-channel permissions
intents.message_content = True  # needed to read !s / !k command arguments

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)

EXTENSIONS = (
    "cogs.queue_cog",
    "cogs.scoring_cog",
    "cogs.elo_cog",
    "cogs.leaderboard_cog",
    "cogs.moderation_cog",
)


@bot.event
async def on_ready():
    # Re-attach button handlers for any match still open/full from before a restart.
    for match in await database.get_open_matches():
        bot.add_view(QueueView(match["match_id"]))

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except discord.HTTPException as e:
        print(f"Slash command sync failed: {e}")

    print(f"Logged in as {bot.user} ({bot.user.id})")


async def main():
    await database.init_db()

    for ext in EXTENSIONS:
        await bot.load_extension(ext)

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
