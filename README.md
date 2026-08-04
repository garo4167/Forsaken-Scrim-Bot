# Forsaken Scrim Bot

## Required in your server
- Text channels: `ranked-scrims`, `casual-scrims`
- Roles: `Ranked Scrim`, `Casual Scrim`, `Ladder Moderator`
- Names must match exactly (case-sensitive) — they're set in `config.py`.

## Commands
- `/queue` — pick Ranked/Casual, Killer/Survivor, and a scrim set. Posts a matchmaking
  embed in the right channel and pings the matching role. Buttons let others fill the
  remaining slots or leave.
- Once 1 killer + 4 survivors have joined: the embed locks, a thread (`match-0000`)
  opens with the recap, and a voice channel (`Match 0000`) is created for just those 5.
- `!s w <kills>` / `!s l <kills>` — survivors report the result inside the match thread.
- `!k w <kills>` / `!k l <kills>` — killer reports the result inside the match thread.
  - Killer kills 0-5 → survivors win. Kills 6-12 → killer wins.
  - All 5 players must submit the same kill count before the match finalizes.
- `/cancel` (inside a match thread) — vote to cancel. Needs 3 of 4 survivors plus the
  killer's confirmation.
- `/elo [user]` — view your (or someone else's) killer/survivor elo, rank, and W/L.
- `/leaderboard` — top 10 ranked players, with Killer/Survivor toggle buttons.
- `/forcewin <match_id> <kills>` — **Ladder Moderator only.** Resolves a match directly.
- `/elo <user> <killer_elo> <survivor_elo>` — **Ladder Moderator only.** Overrides a
  player's elo directly (same command as above, extra params require the role).

## Elo rules (config.py)
Everyone starts at 100 elo per side (killer elo and survivor elo are tracked separately).

| Outcome | Killer kills | Elo change |
|---|---|---|
| Survivor win | 0-3 | Survivors +13, Killer −13 |
| Survivor win | 4-5 | Survivors +15, Killer −15 |
| Killer win | 6-9 | Killer +16, Survivors −16 |
| Killer win | 10-12 | Killer +19, Survivors −19 |

Losing-side values weren't specified in the original spec, so they mirror the winner's
tier — change `SURVIVOR_LOSS_*` / `KILLER_LOSS_*` in `config.py` if you want different
numbers.

Ranks: Bronze 0-199, Silver 200-299, Gold 300-399, Platinum 400-499, Diamond 500-599,
Champion 600+.

## Files
- `bot.py` — entry point, intents, cog loading
- `config.py` — every name/number you're likely to want to tweak
- `database.py` — SQLite (aiosqlite) data layer
- `embeds.py` / `views.py` — embed rendering and buttons
- `elo_utils.py` / `match_logic.py` — elo math and match-resolution logic
- `queue_cog.py`, `scoring_cog.py`, `elo_cog.py`, `leaderboard_cog.py`, `moderation_cog.py` — one file per command group

Everything sits flat in one folder on purpose — no subfolders to worry about when uploading from a phone.
