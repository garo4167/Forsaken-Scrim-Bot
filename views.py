"""
UI components. QueueView buttons are persistent (custom_id encodes the
match_id) so they keep working across bot restarts once re-registered in
bot.py's on_ready. LeaderboardView is a lighter, session-scoped toggle.
"""

import discord

import config
import database
import embeds


async def _get_channel(bot, channel_id):
    if not channel_id:
        return None
    ch = bot.get_channel(channel_id)
    if ch:
        return ch
    try:
        return await bot.fetch_channel(channel_id)
    except discord.HTTPException:
        return None


class QueueView(discord.ui.View):
    def __init__(self, match_id: int):
        super().__init__(timeout=None)
        self.match_id = match_id

        join_killer = discord.ui.Button(
            label="Join Killer", style=discord.ButtonStyle.danger, custom_id=f"sbq:killer:{match_id}"
        )
        join_survivor = discord.ui.Button(
            label="Join Survivor", style=discord.ButtonStyle.primary, custom_id=f"sbq:survivor:{match_id}"
        )
        leave = discord.ui.Button(
            label="Leave Queue", style=discord.ButtonStyle.secondary, custom_id=f"sbq:leave:{match_id}"
        )

        join_killer.callback = self._on_join_killer
        join_survivor.callback = self._on_join_survivor
        leave.callback = self._on_leave

        self.add_item(join_killer)
        self.add_item(join_survivor)
        self.add_item(leave)

    async def _on_join_killer(self, interaction: discord.Interaction):
        await self._handle_join(interaction, "killer")

    async def _on_join_survivor(self, interaction: discord.Interaction):
        await self._handle_join(interaction, "survivor")

    async def _on_leave(self, interaction: discord.Interaction):
        await self._handle_leave(interaction)

    async def _handle_join(self, interaction: discord.Interaction, side: str):
        match = await database.get_match(self.match_id)
        if not match or match["status"] != "open":
            await interaction.response.send_message("This queue is no longer open.", ephemeral=True)
            return

        uid = interaction.user.id
        if uid == match["killer_id"] or uid in match["survivor_ids"]:
            await interaction.response.send_message("You're already in this queue.", ephemeral=True)
            return

        if side == "killer":
            if match["killer_id"] is not None:
                await interaction.response.send_message("The killer slot is already taken.", ephemeral=True)
                return
            await database.set_killer(self.match_id, uid)
        else:
            if len(match["survivor_ids"]) >= config.SURVIVOR_SLOTS:
                await interaction.response.send_message("All survivor slots are full.", ephemeral=True)
                return
            await database.set_survivors(self.match_id, match["survivor_ids"] + [uid])

        match = await database.get_match(self.match_id)
        is_full = (
            match["killer_id"] is not None and len(match["survivor_ids"]) >= config.SURVIVOR_SLOTS
        )

        if is_full:
            await interaction.response.defer()
            await finalize_full_match(interaction.client, interaction.guild, interaction.channel, match)
        else:
            embed = await embeds.build_match_embed(interaction.client, match)
            await interaction.response.edit_message(embed=embed, view=self)

    async def _handle_leave(self, interaction: discord.Interaction):
        match = await database.get_match(self.match_id)
        if not match or match["status"] != "open":
            await interaction.response.send_message(
                "You can only leave while the queue is still open. Once a match is full, "
                "use `/cancel` inside the match thread instead.",
                ephemeral=True,
            )
            return

        uid = interaction.user.id
        changed = False
        if match["killer_id"] == uid:
            await database.set_killer(self.match_id, None)
            changed = True
        if uid in match["survivor_ids"]:
            await database.set_survivors(
                self.match_id, [x for x in match["survivor_ids"] if x != uid]
            )
            changed = True

        if not changed:
            await interaction.response.send_message("You're not in this queue.", ephemeral=True)
            return

        match = await database.get_match(self.match_id)
        embed = await embeds.build_match_embed(interaction.client, match)
        await interaction.response.edit_message(embed=embed, view=self)


class LeaderboardView(discord.ui.View):
    def __init__(self, side: str = "killer"):
        super().__init__(timeout=300)
        self.side = side
        self._sync_styles()

    def _sync_styles(self):
        self.killer_button.style = (
            discord.ButtonStyle.primary if self.side == "killer" else discord.ButtonStyle.secondary
        )
        self.survivor_button.style = (
            discord.ButtonStyle.primary if self.side == "survivor" else discord.ButtonStyle.secondary
        )

    @discord.ui.button(label="Killer", custom_id="sblb:killer")
    async def killer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.side = "killer"
        await self._refresh(interaction)

    @discord.ui.button(label="Survivor", custom_id="sblb:survivor")
    async def survivor_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.side = "survivor"
        await self._refresh(interaction)

    async def _refresh(self, interaction: discord.Interaction):
        self._sync_styles()
        rows = await database.get_leaderboard(self.side, limit=10)
        embed = embeds.build_leaderboard_embed(self.side, rows)
        await interaction.response.edit_message(embed=embed, view=self)


async def finalize_full_match(bot, guild: discord.Guild, channel: discord.abc.GuildChannel, match: dict):
    """Called the moment a queue reaches 1 killer + 4 survivors: locks the
    queue embed, opens the match thread, posts the recap, and spins up a
    voice channel restricted to the 5 participants."""
    match_id = match["match_id"]
    disp_id = embeds.display_id(match_id)

    embed = await embeds.build_match_embed(bot, match)
    try:
        message = await channel.fetch_message(match["message_id"])
        await message.edit(embed=embed, view=None)
    except discord.HTTPException as e:
        print(f"[finalize_full_match] Couldn't fetch/edit queue message {match['message_id']}: {e}")
        message = None

    if message is None:
        return

    thread = await message.create_thread(name=f"match-{disp_id}", auto_archive_duration=1440)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
    }
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, connect=True)

    for uid in [match["killer_id"], *match["survivor_ids"]]:
        member = guild.get_member(uid)
        if member:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True)

    category = getattr(channel, "category", None)
    voice_channel = await guild.create_voice_channel(
        name=f"Match {disp_id}", category=category, overwrites=overwrites
    )

    survivor_mentions = " ".join(f"<@{u}>" for u in match["survivor_ids"])
    recap = (
        f"# Match ID {disp_id}\n"
        f"**Set:** {match['scrim_set']}\n"
        f"**Killer:** <@{match['killer_id']}>\n"
        f"**Survivors:** {survivor_mentions}\n\n"
        f"You may now join match voice chat {disp_id}: {voice_channel.mention}"
    )
    await thread.send(recap)

    howto = (
        "Report the result here when the match ends:\n"
        "Survivors — `!s w <kills>` if the killer got 0-5 kills, `!s l <kills>` if 6-12.\n"
        "Killer — `!k l <kills>` if you got 0-5 kills, `!k w <kills>` if 6-12.\n"
        "All 5 players need to submit the same kill count.\n"
        "To cancel: 3 of 4 survivors and the killer all need to run `/cancel` in this thread."
    )
    if match["queue_type"] == "casual":
        howto = "This is a casual match — no elo is affected.\n" + howto
    await thread.send(howto)

    await database.set_match_thread_and_voice(match_id, thread.id, voice_channel.id)
