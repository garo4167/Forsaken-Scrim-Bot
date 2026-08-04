import discord
from discord import app_commands
from discord.ext import commands

import database
import embeds
import permissions


class EloCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="elo", description="View ladder stats, or (Ladder Moderator) adjust a player's elo.")
    @app_commands.describe(
        user="Whose stats to view (defaults to you)",
        killer_elo="[Ladder Moderator only] Set this player's killer elo",
        survivor_elo="[Ladder Moderator only] Set this player's survivor elo",
    )
    async def elo(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        killer_elo: int = None,
        survivor_elo: int = None,
    ):
        target = user or interaction.user

        if killer_elo is not None or survivor_elo is not None:
            if not permissions.is_moderator(interaction.user):
                await interaction.response.send_message(
                    "Adjusting elo is restricted to Ladder Moderator.", ephemeral=True
                )
                return
            if killer_elo is not None:
                await database.set_player_elo(target.id, "killer", killer_elo)
            if survivor_elo is not None:
                await database.set_player_elo(target.id, "survivor", survivor_elo)

        player = await database.get_or_create_player(target.id)
        embed = embeds.build_stats_embed(target, player)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EloCog(bot))
