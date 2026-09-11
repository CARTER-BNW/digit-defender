"""Leveling formulas (docs/PLAN.md section 3.5). Pure functions of the
invested total, so the info panel, the sim and the tests all agree.

invested = total number-value fed into a structure (through a feed side or
the balance upgrade). Level n -> n+1 costs LEVEL_BASE_COST * GROWTH**(n-1)
(100, 125, 156, 195, 244, ...): every level 25% more than the last, and
there is no level cap (John, 2026-09-11).
"""
import math

from settings import (LEVEL_BASE_COST, LEVEL_COST_GROWTH, RATE_STEP, BASE_HP, BELT_BASE_SPEED,
                      BELT_SPEED_PER_FED, MAX_BELT_SPEED)


def threshold(n):
    """Total invested needed to have passed n levels (threshold(1) = 100,
    threshold(2) = 225, ...); the geometric sum of the level costs."""
    if n <= 0:
        return 0
    r = LEVEL_COST_GROWTH
    return int(round(LEVEL_BASE_COST * (r ** n - 1) / (r - 1)))


def level_cost(level):
    """What the step from `level` to `level + 1` costs."""
    return threshold(level) - threshold(level - 1)


def thresholds_passed(invested):
    """How many level steps `invested` has paid for."""
    if invested < LEVEL_BASE_COST:
        return 0
    r = LEVEL_COST_GROWTH
    n = int(math.log(1 + invested * (r - 1) / LEVEL_BASE_COST) / math.log(r))
    while threshold(n + 1) <= invested:          # float drift either way
        n += 1
    while n > 0 and threshold(n) > invested:
        n -= 1
    return n


def level(invested):
    """Displayed level: 1 at zero invested, 2 at 100, 3 at 225, 4 at 381..."""
    return 1 + thresholds_passed(invested)


def next_threshold(invested):
    """Invested total that reaches the next level (never None: no cap)."""
    return threshold(thresholds_passed(invested) + 1)


def belt_speed(invested):
    """Tiles per tick: +0.01 tiles/s per 100 fed, capped."""
    return min(MAX_BELT_SPEED, BELT_BASE_SPEED + invested * BELT_SPEED_PER_FED)


def period(base_period, invested):
    """Ticks per action for miners/machines/towers/spawners."""
    return max(1, int(round(base_period / (1 + thresholds_passed(invested) * RATE_STEP))))


def max_hp(kind, invested):
    return BASE_HP.get(kind, 100) + invested
