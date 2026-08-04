import discord
from discord import app_commands
from discord.ext import commands

import config
import database
import embeds
from views import QueueView


class QueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="queue", description="Queue up for a scrim match.")
    @app_commands.describe(
        queue_type="Ranked (elo counts) or Casual (elo doesn't count)",
        role="Which side you want to play",
        scrim_set="Which set to play on",
    )
    @app_commands.choices(
        queue_type=[
            app_commands.Choice(name="Ranked", value="ranked"),
            app_commands.Choice(name="Casual", value="casual"),
        ],
        role=[
            app_commands.Choice(name="Killer", value="killer"),
            app_commands.Choice(name="Survivor", value="survivor"),
        ],
        scrim_set=[app_commands.Choice(name=s, value=s) for s in config.SCRIM_SETS],
    )
    async def queue(
        self,
        interaction: discord.Interaction,
        queue_type: app_commands.Choice[str],
        role: app_commands.Choice[str],
        scrim_set: app_commands.Choice[str],
    ):
        await interaction.response.defer(ephemeral=True)

        is_ranked = queue_type.value == "ranked"
        channel_name = config.RANKED_CHANNEL_NAME if is_ranked else config.CASUAL_CHANNEL_NAME
        ping_role_name = config.RANKED_PING_ROLE if is_ranked else config.CASUAL_PING_ROLE

        target_channel = discord.utils.get(interaction.guild.text_channels, name=channel_name)
        if target_channel is None:
            await interaction.followup.send(
                f"I couldn't find a channel called #{channel_name} in this server. "
                f"Ask an admin to create it, then try again.",
                ephemeral=True,
            )
            return

        killer_id = interaction.user.id if role.value == "killer" else None
        survivor_id = interaction.user.id if role.value == "survivor" else None

        match_id = await database.create_match(
            queue_type.value,
            interaction.guild.id,
            target_channel.id,
            scrim_set.value,
            killer_id=killer_id,
            survivor_id=survivor_id,
        )
        match = await database.get_match(match_id)

        embed = await embeds.build_match_embed(self.bot, match)
        view = QueueView(match_id)

        ping_role = discord.utils.get(interaction.guild.roles, name=ping_role_name)
        content = ping_role.mention if ping_role else None

        msg = await target_channel.send(content=content, embed=embed, view=view)
        await database.set_match_message(match_id, msg.id)

        note = f"Queue posted in {target_channel.mention}."
        if ping_role is None:
            note += f" Heads up: no role named '{ping_role_name}' was found, so nobody got pinged."
        await interaction.followup.send(note, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))
