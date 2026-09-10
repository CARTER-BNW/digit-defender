"""Leveling formulas (docs/PLAN.md section 3.5). Pure functions of the
invested total, so the info panel, the sim and the tests all agree.

invested = total number-value fed into a structure through a feed side.
"""
from bisect import bisect_right

from settings import (LEVEL_THRESHOLDS, RATE_STEP, BASE_HP, BELT_BASE_SPEED,
                      BELT_SPEED_PER_FED, MAX_BELT_SPEED)


def thresholds_passed(invested):
    """How many thresholds invested has reached (>=)."""
    return bisect_right(LEVEL_THRESHOLDS, invested)


def level(invested):
    """Displayed level: 1 at zero invested, 2 at 100, 3 at 200, 4 at 400..."""
    return 1 + thresholds_passed(invested)


def next_threshold(invested):
    n = thresholds_passed(invested)
    return LEVEL_THRESHOLDS[n] if n < len(LEVEL_THRESHOLDS) else None


def belt_speed(invested):
    """Tiles per tick: +0.01 tiles/s per 100 fed, capped."""
    return min(MAX_BELT_SPEED, BELT_BASE_SPEED + invested * BELT_SPEED_PER_FED)


def period(base_period, invested):
    """Ticks per action for miners/machines/towers/spawners."""
    return max(1, int(round(base_period / (1 + thresholds_passed(invested) * RATE_STEP))))


def max_hp(kind, invested):
    return BASE_HP.get(kind, 100) + invested
