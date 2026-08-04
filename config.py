"""
Central configuration for the Forsaken Scrim Bot.
Edit names here if your server uses different channel/role names.
"""

import os

# ---- Channel names (must exist in the server, case-sensitive) ----
RANKED_CHANNEL_NAME = "ranked-scrims"
CASUAL_CHANNEL_NAME = "casual-scrims"

# ---- Role names (must exist in the server, case-sensitive) ----
RANKED_PING_ROLE = "Ranked Scrim"
CASUAL_PING_ROLE = "Casual Scrim"
MODERATOR_ROLE = "Ladder Moderator"

# ---- Match structure ----
ROUNDS_PER_MATCH = 3
SURVIVOR_SLOTS = 4
KILLS_TO_WIN = 6      # killer needs >= 6 (out of 12) for a Killer Victory
MAX_KILLS = 12        # 4 survivors x 3 rounds

# ---- Scrim sets (in the order they should appear in the dropdown) ----
SCRIM_SETS = [
    "Slasher — Work At A Pizza Place",
    "Noli — BrandonWorks",
    "Coolkid — Tempest",
    "Guest 666 — Glasshouses",
    "Azure — CoolCarnival",
    "John Doe — BrandonWorks",
    "Nosferatu — BrandonWorks",
    "1x1x1x1 — CoolCarnival",
]

# ---- Elo ----
STARTING_ELO = 100

# Survivor victory (killer kills 0-5 total)
SURVIVOR_WIN_LOW_KILLS = 13    # killer got 0-3 kills -> easier win
SURVIVOR_WIN_HIGH_KILLS = 15   # killer got 4-5 kills -> close win, worth more

# Killer victory (killer kills 6-12 total)
KILLER_WIN_LOW_KILLS = 16      # killer got 6-9 kills
KILLER_WIN_HIGH_KILLS = 19     # killer got 10-12 kills

# Elo lost by the losing side. Not specified in the spec, so this mirrors the
# winning side's gain for that same kill-count tier. Tune freely below.
SURVIVOR_LOSS_LOW_KILLS = 16   # survivors lose this when killer wins w/ 6-9 kills
SURVIVOR_LOSS_HIGH_KILLS = 19  # survivors lose this when killer wins w/ 10-12 kills
KILLER_LOSS_LOW_KILLS = 13     # killer loses this when survivors win w/ 0-3 kills
KILLER_LOSS_HIGH_KILLS = 15    # killer loses this when survivors win w/ 4-5 kills

# ---- Ranks ----
# (min_elo, max_elo, name) - max_elo=None means unbounded
RANKS = [
    (0, 199, "Bronze"),
    (200, 299, "Silver"),
    (300, 399, "Gold"),
    (400, 499, "Platinum"),
    (500, 599, "Diamond"),
    (600, None, "Champion"),
]

DATABASE_URL = os.environ.get("DATABASE_URL")
COMMAND_PREFIX = "!"
