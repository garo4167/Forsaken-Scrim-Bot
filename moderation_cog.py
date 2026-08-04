import discord
from discord import app_commands
from discord.ext import commands

import database
import embeds
import match_logic
import permissions


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="forcewin", description="[Ladder Moderator] Force-resolve a match's outcome.")
    @app_commands.describe(
        match_id="The 4-digit match ID shown on the embed, e.g. 0007",
        kills="Total killer kills for the match, 0-12",
    )
    async def forcewin(
        self,
        interaction: discord.Interaction,
        match_id: str,
        kills: app_commands.Range[int, 0, 12],
    ):
        if not permissions.is_moderator(interaction.user):
            await interaction.response.send_message(
                "This command is restricted to Ladder Moderator.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            internal_id = embeds.internal_id_from_display(match_id.strip())
        except ValueError:
            await interaction.followup.send("Match ID must be numeric, e.g. `0007`.", ephemeral=True)
            return

        match = await database.get_match(internal_id)
        if not match or match["status"] != "full":
            await interaction.followup.send("That match isn't currently in progress.", ephemeral=True)
            return

        label = await match_logic.finalize_match_result(self.bot, match, kills)
        await interaction.followup.send(f"Match {match_id} force-resolved: {label}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
