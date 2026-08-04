import discord
from discord import app_commands
from discord.ext import commands

import database
import embeds
from views import LeaderboardView


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show the top 10 ranked killers or survivors.")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await database.get_leaderboard("killer", limit=10)
        embed = embeds.build_leaderboard_embed("killer", rows)
        view = LeaderboardView(side="killer")
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
