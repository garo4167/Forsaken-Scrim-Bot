"""Rank lookup and win/loss elo-tier calculations."""

import config


def get_rank(elo: int) -> str:
    for lo, hi, name in config.RANKS:
        if hi is None:
            if elo >= lo:
                return name
        elif lo <= elo <= hi:
            return name
    return config.RANKS[0][2]


def survivors_won(kills: int) -> bool:
    """Killer needs KILLS_TO_WIN (6) or more to win. Below that, survivors win."""
    return kills < config.KILLS_TO_WIN


def elo_deltas(kills: int) -> tuple[int, int]:
    """
    Returns (survivor_elo_delta, killer_elo_delta) for a completed match with
    the given total killer kill count (0-12). One side's delta is positive,
    the other negative, depending on who won.
    """
    if survivors_won(kills):
        if kills <= 3:
            return config.SURVIVOR_WIN_LOW_KILLS, -config.KILLER_LOSS_LOW_KILLS
        else:  # 4-5
            return config.SURVIVOR_WIN_HIGH_KILLS, -config.KILLER_LOSS_HIGH_KILLS
    else:
        if kills <= 9:
            return -config.SURVIVOR_LOSS_LOW_KILLS, config.KILLER_WIN_LOW_KILLS
        else:  # 10-12
            return -config.SURVIVOR_LOSS_HIGH_KILLS, config.KILLER_WIN_HIGH_KILLS


def result_label(kills: int) -> str:
    if survivors_won(kills):
        return f"Survivor Victory • {kills} Kill{'s' if kills != 1 else ''}"
    return f"Killer Victory • {kills} Kills"


def expected_side_result(side: str, kills: int) -> str:
    """What result ('w' or 'l') a given side SHOULD report for this kill count."""
    won = survivors_won(kills) if side == "survivor" else not survivors_won(kills)
    return "w" if won else "l"
