"""Embed builders. Styled after the reference screenshots, with emojis removed."""

from __future__ import annotations

import discord

import config
import database
import elo_utils

DIVIDER = "─" * 34

RANKED_COLOR = discord.Color.from_rgb(88, 101, 242)
CASUAL_COLOR = discord.Color.from_rgb(87, 165, 111)
CANCELLED_COLOR = discord.Color.from_rgb(153, 45, 45)


def display_id(match_id: int) -> str:
    # DB autoincrement starts at 1; display starts at 0000.
    return f"{max(match_id - 1, 0):04d}"


def internal_id_from_display(display: str) -> int:
    return int(display) + 1


def _status_text(match: dict) -> str:
    return {
        "open": "Open — Waiting For Players",
        "full": "Full — Match In Progress",
        "completed": "Completed",
        "cancelled": "Cancelled",
    }.get(match["status"], match["status"].title())


async def _line_for(bot, side: str, user_id: int | None, ranked: bool, match: dict) -> str:
    if user_id is None:
        return "Open"

    mention = f"<@{user_id}>"
    if not ranked:
        return mention

    player = await database.get_or_create_player(user_id)
    elo_col = f"{side}_elo"

    if match["status"] == "completed" and match.get("_elo_before") and user_id in match["_elo_before"]:
        before = match["_elo_before"][user_id]
        after = player[elo_col]
        delta = after - before
        sign = "+" if delta >= 0 else ""
        return f"{mention} • {before} → {after} ({sign}{delta}) • {elo_utils.get_rank(after)}"

    elo = player[elo_col]
    return f"{mention} • {elo} Elo • {elo_utils.get_rank(elo)}"


async def build_match_embed(bot, match: dict) -> discord.Embed:
    ranked = match["queue_type"] == "ranked"
    disp_id = display_id(match["match_id"])

    title = "RANKED 1V4 MATCHMAKING" if ranked else "CASUAL 1V4 MATCHMAKING"
    color = CASUAL_COLOR if not ranked else RANKED_COLOR
    if match["status"] == "cancelled":
        color = CANCELLED_COLOR

    embed = discord.Embed(title=title, description=f"MATCH ID: {disp_id}\n{DIVIDER}", color=color)

    embed.add_field(name="SET", value=match["scrim_set"], inline=False)
    embed.add_field(name="ROUNDS", value=str(config.ROUNDS_PER_MATCH), inline=False)
    embed.add_field(name="\u200b", value=DIVIDER, inline=False)

    killer_line = await _line_for(bot, "killer", match["killer_id"], ranked, match)
    embed.add_field(name="MATCH KILLER", value=killer_line, inline=False)

    survivor_ids = match["survivor_ids"]
    lines = []
    for i in range(config.SURVIVOR_SLOTS):
        uid = survivor_ids[i] if i < len(survivor_ids) else None
        line = await _line_for(bot, "survivor", uid, ranked, match)
        lines.append(f"{i + 1}. {line}")
    embed.add_field(name="SURVIVORS", value="\n".join(lines), inline=False)

    embed.add_field(name="\u200b", value=DIVIDER, inline=False)
    embed.add_field(name="STATUS", value=_status_text(match), inline=False)

    if match["status"] == "completed" and match.get("result"):
        embed.add_field(name="RESULT", value=match["result"], inline=False)
    elif match["status"] == "cancelled":
        embed.add_field(name="RESULT", value="Match Cancelled By Vote", inline=False)

    embed.set_footer(text=f"Queue ID: {disp_id}")
    return embed


def build_stats_embed(member: discord.abc.User, player: dict) -> discord.Embed:
    embed = discord.Embed(title=f"{member.display_name}'s Ladder Stats", color=RANKED_COLOR)
    embed.set_thumbnail(url=member.display_avatar.url)

    s_elo = player["survivor_elo"]
    embed.add_field(
        name="Survivor Stats",
        value=(
            f"Elo: {s_elo}\n"
            f"Rank: {elo_utils.get_rank(s_elo)}\n"
            f"Wins/Losses: {player['survivor_wins']}/{player['survivor_losses']}"
        ),
        inline=False,
    )

    k_elo = player["killer_elo"]
    embed.add_field(
        name="Killer Stats",
        value=(
            f"Elo: {k_elo}\n"
            f"Rank: {elo_utils.get_rank(k_elo)}\n"
            f"Wins/Losses: {player['killer_wins']}/{player['killer_losses']}"
        ),
        inline=False,
    )
    return embed


def build_leaderboard_embed(side: str, rows: list[dict]) -> discord.Embed:
    embed = discord.Embed(title="Ranked Leaderboard", color=RANKED_COLOR)
    label = "Killer Elo" if side == "killer" else "Survivor Elo"
    elo_col = f"{side}_elo"

    if not rows:
        body = "No ranked matches have been recorded yet."
    else:
        lines = []
        for i, row in enumerate(rows, start=1):
            elo = row[elo_col]
            lines.append(f"{i}. <@{row['user_id']}> • {elo} Elo • {elo_utils.get_rank(elo)}")
        body = "\n".join(lines)

    embed.add_field(name=label, value=body, inline=False)
    embed.set_footer(text=f"Showing top {len(rows)} ranked players" if rows else "No players ranked yet")
    return embed
