"""
Async Postgres data layer. Uses asyncpg with a connection pool (created
once at startup, reused everywhere) so DB calls never block the bot's
event loop.

survivor_ids is a native Postgres BIGINT[] column - asyncpg converts it
to/from a plain Python list automatically, no JSON encoding needed.
"""

from __future__ import annotations

import asyncpg

import config

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    user_id BIGINT PRIMARY KEY,
    killer_elo INTEGER NOT NULL DEFAULT 100,
    killer_wins INTEGER NOT NULL DEFAULT 0,
    killer_losses INTEGER NOT NULL DEFAULT 0,
    survivor_elo INTEGER NOT NULL DEFAULT 100,
    survivor_wins INTEGER NOT NULL DEFAULT 0,
    survivor_losses INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS matches (
    match_id SERIAL PRIMARY KEY,
    queue_type TEXT NOT NULL,          -- 'ranked' or 'casual'
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    thread_id BIGINT,
    voice_channel_id BIGINT,
    scrim_set TEXT NOT NULL,
    killer_id BIGINT,
    survivor_ids BIGINT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'open',   -- open, full, completed, cancelled
    result TEXT,
    kills INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reports (
    match_id INTEGER NOT NULL,
    user_id BIGINT NOT NULL,
    side TEXT NOT NULL,     -- 'killer' or 'survivor'
    result TEXT NOT NULL,   -- 'w' or 'l'
    kills INTEGER NOT NULL,
    PRIMARY KEY (match_id, user_id)
);

CREATE TABLE IF NOT EXISTS cancel_votes (
    match_id INTEGER NOT NULL,
    user_id BIGINT NOT NULL,
    PRIMARY KEY (match_id, user_id)
);
"""


async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(dsn=config.DATABASE_URL)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


async def close_db():
    if _pool:
        await _pool.close()


# ---------------------------------------------------------------- players --
async def get_or_create_player(user_id: int) -> dict:
    row = await _pool.fetchrow(
        "INSERT INTO players (user_id, killer_elo, survivor_elo) VALUES ($1, $2, $2) "
        "ON CONFLICT (user_id) DO NOTHING RETURNING *",
        user_id, config.STARTING_ELO,
    )
    if row:
        return dict(row)
    row = await _pool.fetchrow("SELECT * FROM players WHERE user_id = $1", user_id)
    return dict(row)


async def apply_match_result(user_id: int, side: str, elo_delta: int, won: bool) -> dict:
    """side is 'killer' or 'survivor'. elo_delta may be negative."""
    await get_or_create_player(user_id)
    elo_col = f"{side}_elo"
    counter_col = f"{side}_wins" if won else f"{side}_losses"
    row = await _pool.fetchrow(
        f"UPDATE players SET {elo_col} = GREATEST(0, {elo_col} + $1), "
        f"{counter_col} = {counter_col} + 1 WHERE user_id = $2 RETURNING *",
        elo_delta, user_id,
    )
    return dict(row)


async def set_player_elo(user_id: int, side: str, new_elo: int) -> dict:
    await get_or_create_player(user_id)
    elo_col = f"{side}_elo"
    row = await _pool.fetchrow(
        f"UPDATE players SET {elo_col} = $1 WHERE user_id = $2 RETURNING *",
        max(0, new_elo), user_id,
    )
    return dict(row)


async def get_leaderboard(side: str, limit: int = 10) -> list[dict]:
    elo_col = f"{side}_elo"
    rows = await _pool.fetch(
        f"SELECT * FROM players WHERE {elo_col} > 0 ORDER BY {elo_col} DESC, user_id ASC LIMIT $1",
        limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- matches --
async def create_match(queue_type, guild_id, channel_id, scrim_set, killer_id=None, survivor_id=None) -> int:
    survivor_ids = [survivor_id] if survivor_id else []
    row = await _pool.fetchrow(
        "INSERT INTO matches (queue_type, guild_id, channel_id, scrim_set, killer_id, survivor_ids) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING match_id",
        queue_type, guild_id, channel_id, scrim_set, killer_id, survivor_ids,
    )
    return row["match_id"]


async def get_match(match_id: int) -> dict | None:
    row = await _pool.fetchrow("SELECT * FROM matches WHERE match_id = $1", match_id)
    return dict(row) if row else None


async def get_match_by_message(message_id: int) -> dict | None:
    row = await _pool.fetchrow("SELECT * FROM matches WHERE message_id = $1", message_id)
    return dict(row) if row else None


async def get_match_by_thread(thread_id: int) -> dict | None:
    row = await _pool.fetchrow("SELECT * FROM matches WHERE thread_id = $1", thread_id)
    return dict(row) if row else None


async def get_open_matches(queue_type: str | None = None) -> list[dict]:
    """Matches still in 'open' or 'full' status - used to re-attach persistent views on boot."""
    if queue_type:
        rows = await _pool.fetch(
            "SELECT * FROM matches WHERE status IN ('open','full') AND queue_type = $1", queue_type
        )
    else:
        rows = await _pool.fetch("SELECT * FROM matches WHERE status IN ('open','full')")
    return [dict(r) for r in rows]


async def set_match_message(match_id: int, message_id: int):
    await _pool.execute("UPDATE matches SET message_id = $1 WHERE match_id = $2", message_id, match_id)


async def set_match_thread_and_voice(match_id: int, thread_id: int, voice_channel_id: int):
    await _pool.execute(
        "UPDATE matches SET thread_id = $1, voice_channel_id = $2, status = 'full' WHERE match_id = $3",
        thread_id, voice_channel_id, match_id,
    )


async def set_killer(match_id: int, user_id: int | None):
    await _pool.execute("UPDATE matches SET killer_id = $1 WHERE match_id = $2", user_id, match_id)


async def set_survivors(match_id: int, survivor_ids: list):
    await _pool.execute("UPDATE matches SET survivor_ids = $1 WHERE match_id = $2", survivor_ids, match_id)


async def set_match_status(match_id: int, status: str, result: str | None = None, kills: int | None = None):
    await _pool.execute(
        "UPDATE matches SET status = $1, result = COALESCE($2, result), kills = COALESCE($3, kills) "
        "WHERE match_id = $4",
        status, result, kills, match_id,
    )


# ---------------------------------------------------------------- reports --
async def add_report(match_id: int, user_id: int, side: str, result: str, kills: int):
    await _pool.execute(
        "INSERT INTO reports (match_id, user_id, side, result, kills) VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (match_id, user_id) DO UPDATE SET side = EXCLUDED.side, "
        "result = EXCLUDED.result, kills = EXCLUDED.kills",
        match_id, user_id, side, result, kills,
    )


async def get_reports(match_id: int) -> list[dict]:
    rows = await _pool.fetch("SELECT * FROM reports WHERE match_id = $1", match_id)
    return [dict(r) for r in rows]


async def clear_reports(match_id: int):
    await _pool.execute("DELETE FROM reports WHERE match_id = $1", match_id)


# ---------------------------------------------------------- cancel votes --
async def add_cancel_vote(match_id: int, user_id: int):
    await _pool.execute(
        "INSERT INTO cancel_votes (match_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        match_id, user_id,
    )


async def get_cancel_votes(match_id: int) -> list[int]:
    rows = await _pool.fetch("SELECT user_id FROM cancel_votes WHERE match_id = $1", match_id)
    return [r["user_id"] for r in rows]


async def clear_cancel_votes(match_id: int):
    await _pool.execute("DELETE FROM cancel_votes WHERE match_id = $1", match_id)
