"""
Async SQLite data layer. Uses aiosqlite so DB calls never block the bot's
event loop. One connection is opened at startup and reused everywhere.
"""

from __future__ import annotations

import json
import aiosqlite

import config

_db: aiosqlite.Connection | None = None


async def init_db():
    global _db
    _db = await aiosqlite.connect(config.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            killer_elo INTEGER NOT NULL DEFAULT 100,
            killer_wins INTEGER NOT NULL DEFAULT 0,
            killer_losses INTEGER NOT NULL DEFAULT 0,
            survivor_elo INTEGER NOT NULL DEFAULT 100,
            survivor_wins INTEGER NOT NULL DEFAULT 0,
            survivor_losses INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_type TEXT NOT NULL,      -- 'ranked' or 'casual'
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            thread_id INTEGER,
            voice_channel_id INTEGER,
            scrim_set TEXT NOT NULL,
            killer_id INTEGER,
            survivor_ids TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'open',   -- open, full, completed, cancelled
            result TEXT,
            kills INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reports (
            match_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            side TEXT NOT NULL,     -- 'killer' or 'survivor'
            result TEXT NOT NULL,   -- 'w' or 'l'
            kills INTEGER NOT NULL,
            PRIMARY KEY (match_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS cancel_votes (
            match_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (match_id, user_id)
        );
        """
    )
    await _db.commit()


def _row_to_dict(row):
    return dict(row) if row else None


# ---------------------------------------------------------------- players --
async def get_or_create_player(user_id: int) -> dict:
    async with _db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    if row:
        return _row_to_dict(row)
    await _db.execute(
        "INSERT INTO players (user_id, killer_elo, survivor_elo) VALUES (?, ?, ?)",
        (user_id, config.STARTING_ELO, config.STARTING_ELO),
    )
    await _db.commit()
    async with _db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row)


async def apply_match_result(user_id: int, side: str, elo_delta: int, won: bool):
    """side is 'killer' or 'survivor'. elo_delta may be negative."""
    await get_or_create_player(user_id)
    elo_col = f"{side}_elo"
    win_col = f"{side}_wins"
    loss_col = f"{side}_losses"
    counter_col = win_col if won else loss_col
    await _db.execute(
        f"UPDATE players SET {elo_col} = MAX(0, {elo_col} + ?), {counter_col} = {counter_col} + 1 "
        f"WHERE user_id = ?",
        (elo_delta, user_id),
    )
    await _db.commit()
    return await get_or_create_player(user_id)


async def set_player_elo(user_id: int, side: str, new_elo: int) -> dict:
    await get_or_create_player(user_id)
    elo_col = f"{side}_elo"
    await _db.execute(f"UPDATE players SET {elo_col} = ? WHERE user_id = ?", (max(0, new_elo), user_id))
    await _db.commit()
    return await get_or_create_player(user_id)


async def get_leaderboard(side: str, limit: int = 10):
    elo_col = f"{side}_elo"
    async with _db.execute(
        f"SELECT * FROM players WHERE {elo_col} > 0 ORDER BY {elo_col} DESC, user_id ASC LIMIT ?",
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------- matches --
async def create_match(queue_type, guild_id, channel_id, scrim_set, killer_id=None, survivor_id=None) -> int:
    survivor_ids = [survivor_id] if survivor_id else []
    cur = await _db.execute(
        "INSERT INTO matches (queue_type, guild_id, channel_id, scrim_set, killer_id, survivor_ids) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (queue_type, guild_id, channel_id, scrim_set, killer_id, json.dumps(survivor_ids)),
    )
    await _db.commit()
    return cur.lastrowid


async def get_match(match_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,)) as cur:
        row = await cur.fetchone()
    match = _row_to_dict(row)
    if match:
        match["survivor_ids"] = json.loads(match["survivor_ids"])
    return match


async def get_match_by_message(message_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM matches WHERE message_id = ?", (message_id,)) as cur:
        row = await cur.fetchone()
    match = _row_to_dict(row)
    if match:
        match["survivor_ids"] = json.loads(match["survivor_ids"])
    return match


async def get_match_by_thread(thread_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM matches WHERE thread_id = ?", (thread_id,)) as cur:
        row = await cur.fetchone()
    match = _row_to_dict(row)
    if match:
        match["survivor_ids"] = json.loads(match["survivor_ids"])
    return match


async def get_open_matches(queue_type: str | None = None):
    """Matches still in 'open' or 'full' status - used to re-attach persistent views on boot."""
    if queue_type:
        async with _db.execute(
            "SELECT * FROM matches WHERE status IN ('open','full') AND queue_type = ?", (queue_type,)
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with _db.execute("SELECT * FROM matches WHERE status IN ('open','full')") as cur:
            rows = await cur.fetchall()
    out = []
    for r in rows:
        m = _row_to_dict(r)
        m["survivor_ids"] = json.loads(m["survivor_ids"])
        out.append(m)
    return out


async def set_match_message(match_id: int, message_id: int):
    await _db.execute("UPDATE matches SET message_id = ? WHERE match_id = ?", (message_id, match_id))
    await _db.commit()


async def set_match_thread_and_voice(match_id: int, thread_id: int, voice_channel_id: int):
    await _db.execute(
        "UPDATE matches SET thread_id = ?, voice_channel_id = ?, status = 'full' WHERE match_id = ?",
        (thread_id, voice_channel_id, match_id),
    )
    await _db.commit()


async def set_killer(match_id: int, user_id: int | None):
    await _db.execute("UPDATE matches SET killer_id = ? WHERE match_id = ?", (user_id, match_id))
    await _db.commit()


async def set_survivors(match_id: int, survivor_ids: list):
    await _db.execute(
        "UPDATE matches SET survivor_ids = ? WHERE match_id = ?", (json.dumps(survivor_ids), match_id)
    )
    await _db.commit()


async def set_match_status(match_id: int, status: str, result: str | None = None, kills: int | None = None):
    await _db.execute(
        "UPDATE matches SET status = ?, result = COALESCE(?, result), kills = COALESCE(?, kills) "
        "WHERE match_id = ?",
        (status, result, kills, match_id),
    )
    await _db.commit()


# ---------------------------------------------------------------- reports --
async def add_report(match_id: int, user_id: int, side: str, result: str, kills: int):
    await _db.execute(
        "INSERT INTO reports (match_id, user_id, side, result, kills) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(match_id, user_id) DO UPDATE SET side=excluded.side, result=excluded.result, "
        "kills=excluded.kills",
        (match_id, user_id, side, result, kills),
    )
    await _db.commit()


async def get_reports(match_id: int):
    async with _db.execute("SELECT * FROM reports WHERE match_id = ?", (match_id,)) as cur:
        rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


async def clear_reports(match_id: int):
    await _db.execute("DELETE FROM reports WHERE match_id = ?", (match_id,))
    await _db.commit()


# ---------------------------------------------------------- cancel votes --
async def add_cancel_vote(match_id: int, user_id: int):
    await _db.execute(
        "INSERT OR IGNORE INTO cancel_votes (match_id, user_id) VALUES (?, ?)", (match_id, user_id)
    )
    await _db.commit()


async def get_cancel_votes(match_id: int):
    async with _db.execute("SELECT user_id FROM cancel_votes WHERE match_id = ?", (match_id,)) as cur:
        rows = await cur.fetchall()
    return [r["user_id"] for r in rows]


async def clear_cancel_votes(match_id: int):
    await _db.execute("DELETE FROM cancel_votes WHERE match_id = ?", (match_id,))
    await _db.commit()
