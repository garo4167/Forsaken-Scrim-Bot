"""
Shared logic for ending a match, whether by player consensus, moderator
/forcewin, or a cancel vote. Kept separate from any one cog so both the
scoring cog and the moderation cog can call into it without importing
each other.
"""

import discord

import database
import elo_utils
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


async def _sync_message(bot, match: dict):
    channel = await _get_channel(bot, match["channel_id"])
    if channel is None or not match.get("message_id"):
        return
    try:
        message = await channel.fetch_message(match["message_id"])
    except (discord.NotFound, discord.HTTPException):
        return
    embed = await embeds.build_match_embed(bot, match)
    try:
        await message.edit(embed=embed, view=None)
    except discord.HTTPException:
        pass


async def _cleanup_voice(bot, match: dict):
    vc = await _get_channel(bot, match.get("voice_channel_id"))
    if vc:
        try:
            await vc.delete(reason="Match finished.")
        except discord.HTTPException:
            pass


async def finalize_match_result(bot, match: dict, kills: int) -> str:
    """Applies the result of a completed match: elo (if ranked), embed, cleanup."""
    match_id = match["match_id"]
    ranked = match["queue_type"] == "ranked"
    label = elo_utils.result_label(kills)

    elo_before = {}
    if ranked:
        survivor_delta, killer_delta = elo_utils.elo_deltas(kills)
        survivors_won = elo_utils.survivors_won(kills)

        if match["killer_id"] is not None:
            killer_player = await database.get_or_create_player(match["killer_id"])
            elo_before[match["killer_id"]] = killer_player["killer_elo"]
            await database.apply_match_result(
                match["killer_id"], "killer", killer_delta, won=not survivors_won
            )

        for uid in match["survivor_ids"]:
            p = await database.get_or_create_player(uid)
            elo_before[uid] = p["survivor_elo"]
            await database.apply_match_result(uid, "survivor", survivor_delta, won=survivors_won)

    await database.set_match_status(match_id, "completed", result=label, kills=kills)
    match = await database.get_match(match_id)
    match["_elo_before"] = elo_before

    await _sync_message(bot, match)

    thread = await _get_channel(bot, match.get("thread_id"))
    if thread:
        wrap_up = f"Match complete — {label}."
        if ranked:
            wrap_up += " Elo has been updated — check `/elo`."
        try:
            await thread.send(wrap_up)
        except discord.HTTPException:
            pass

    await _cleanup_voice(bot, match)
    return label


async def cancel_match(bot, match: dict):
    match_id = match["match_id"]
    await database.set_match_status(match_id, "cancelled")
    match = await database.get_match(match_id)

    await _sync_message(bot, match)

    thread = await _get_channel(bot, match.get("thread_id"))
    if thread:
        try:
            await thread.send("This match has been cancelled by vote.")
        except discord.HTTPException:
            pass

    await _cleanup_voice(bot, match)
