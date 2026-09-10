"""Tile-id registry (data only, no pygame).

Terrain holds ONLY ground shades, deposits and nest tiles. Player structures
never live in terrain (they are in Factory.structures) — see docs/PLAN.md §0.

Ground ids 0..5 encode (shade_pair, checker): id = pair * 2 + checker, so the
renderer picks its color with GROUND_SHADES[id // 2][id % 2].
"""
GROUND_PAIRS = 3                 # number of shade pairs (noise-bucketed)
GROUND_MAX = GROUND_PAIRS * 2 - 1  # 5

DEPOSIT_BASE = 10                # DEPOSIT_n = 10 + n, n in 1..9
DEPOSIT_1, DEPOSIT_9 = DEPOSIT_BASE + 1, DEPOSIT_BASE + 9

NEST_GROUND = 20
NEST_CORE = 21


def is_ground(tile):
    return 0 <= tile <= GROUND_MAX


def deposit_value(tile):
    """Digit 1..9 for deposit tiles, else 0."""
    return tile - DEPOSIT_BASE if DEPOSIT_1 <= tile <= DEPOSIT_9 else 0


def is_nest(tile):
    return tile == NEST_GROUND or tile == NEST_CORE


def is_buildable(tile):
    """Structures can go on ground and deposits (miners need deposits), never
    on nest tiles."""
    return not is_nest(tile)
