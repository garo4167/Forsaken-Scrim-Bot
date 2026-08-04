import discord
from discord import app_commands
from discord.ext import commands

import config
import database
import elo_utils
import match_logic


class ScoringCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _handle_report(self, ctx: commands.Context, side: str, result: str, kills: int):
        result = result.lower()
        cmd_prefix = "k" if side == "killer" else "s"

        if result not in ("w", "l"):
            await ctx.reply(f"Result must be `w` or `l` — e.g. `!{cmd_prefix} w 3`.", mention_author=False)
            return
        if not (0 <= kills <= config.MAX_KILLS):
            await ctx.reply(f"Kills must be between 0 and {config.MAX_KILLS}.", mention_author=False)
            return

        match = await database.get_match_by_thread(ctx.channel.id)
        if not match:
            return  # not a match thread - stay quiet

        if match["status"] != "full":
            await ctx.reply("This match isn't currently awaiting a result.", mention_author=False)
            return

        if side == "killer":
            if ctx.author.id != match["killer_id"]:
                await ctx.reply("Only this match's killer can submit `!k`.", mention_author=False)
                return
        else:
            if ctx.author.id not in match["survivor_ids"]:
                await ctx.reply("Only this match's survivors can submit `!s`.", mention_author=False)
                return

        expected = elo_utils.expected_side_result(side, kills)
        if result != expected:
            await ctx.reply(
                f"With {kills} kills that's a {'killer' if not elo_utils.survivors_won(kills) else 'survivor'} "
                f"win — try `!{cmd_prefix} {expected} {kills}`.",
                mention_author=False,
            )
            return

        existing_reports = await database.get_reports(match["match_id"])
        mismatch = any(r["kills"] != kills for r in existing_reports)

        await database.add_report(match["match_id"], ctx.author.id, side, result, kills)
        reports = await database.get_reports(match["match_id"])

        await ctx.reply(
            f"Submitted your score: `{result.upper()} {kills}`. Reports received: **{len(reports)}/5**.",
            mention_author=False,
        )

        if mismatch:
            await ctx.send(
                "Reported kill counts don't all match yet — whoever's wrong can resubmit. "
                "A Ladder Moderator can also resolve this with `/forcewin`."
            )
            return

        if len(reports) == 5 and len({r["kills"] for r in reports}) == 1:
            await match_logic.finalize_match_result(self.bot, match, kills)

    @commands.command(name="s")
    async def survivor_report(self, ctx: commands.Context, result: str, kills: int):
        await self._handle_report(ctx, "survivor", result, kills)

    @commands.command(name="k")
    async def killer_report(self, ctx: commands.Context, result: str, kills: int):
        await self._handle_report(ctx, "killer", result, kills)

    @app_commands.command(name="cancel", description="Vote to cancel the current match (use inside its thread).")
    async def cancel(self, interaction: discord.Interaction):
        match = await database.get_match_by_thread(interaction.channel.id)
        if not match:
            await interaction.response.send_message(
                "This only works inside a match thread.", ephemeral=True
            )
            return
        if match["status"] != "full":
            await interaction.response.send_message(
                "This match can't be cancelled right now.", ephemeral=True
            )
            return

        uid = interaction.user.id
        if uid != match["killer_id"] and uid not in match["survivor_ids"]:
            await interaction.response.send_message(
                "Only players in this match can vote to cancel.", ephemeral=True
            )
            return

        await database.add_cancel_vote(match["match_id"], uid)
        votes = await database.get_cancel_votes(match["match_id"])
        survivor_votes = len([v for v in votes if v in match["survivor_ids"]])
        killer_voted = match["killer_id"] in votes

        await interaction.response.send_message(
            f"Cancel vote recorded from {interaction.user.mention}. "
            f"Survivors: **{min(survivor_votes, 3)}/3** needed • "
            f"Killer confirmation: **{'yes' if killer_voted else 'no'}**."
        )

        if survivor_votes >= 3 and killer_voted:
            await match_logic.cancel_match(self.bot, match)


async def setup(bot: commands.Bot):
    await bot.add_cog(ScoringCog(bot))
