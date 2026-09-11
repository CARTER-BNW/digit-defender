"""Seeded terrain generation. generate_chunk(seed, cx, cy) is PURE: output
depends only on its arguments, so chunks are identical regardless of visit
order and untouched land regenerates from the seed alone.

Layers, in order:
  1. ground: dark-green checkerboard, shade pair chosen by low-frequency
     simplex noise sampled every NOISE_STEP tiles on a GLOBAL grid and
     bilinear-upsampled (seamless across chunk borders).
  2. deposits: at most one seeded blob of a single digit 1-9 per chunk
     (DEPOSIT_BLOB_CHANCE, random walk), so deposits are spread out. The
     digit is drawn with geometric weights decay**(digit-1): the higher the
     digit the rarer it is, everywhere; the decay eases with distance from
     the origin so 6-9 turn up far out but never outnumber lower digits.
     Never inside the spawn clearing. The four chunks touching the origin
     each carry a forced blob (1, 2, 3 and a random 1-3) so the early game
     always works.
  3. nests: stamped from sim.nests (pure region grid), over everything.

No pygame here. Deposits are infinite, so terrain is never modified in play.
"""
import random
from functools import lru_cache

import numpy as np
from opensimplex import OpenSimplex

from settings import (CHUNK_SIZE, SPAWN_CLEAR_RADIUS, DEPOSIT_BLOB_CHANCE, DEPOSIT_BLOB_SIZE,
                      DEPOSIT_DECAY_NEAR, DEPOSIT_DECAY_PER_CHUNK, DEPOSIT_DECAY_FAR)
from world.tiles import DEPOSIT_BASE, NEST_GROUND, NEST_CORE, GROUND_PAIRS
from sim.nests import nest_in_chunk, NEST_RADIUS

NOISE_STEP = 4                # noise sampled every 4th tile, upsampled between
SHADE_FREQ = 1 / 40.0         # tiles per noise unit; bigger divisor = bigger patches
SHADE_THRESHOLD = 0.18        # |noise| beyond this picks the dark/light pair

# forced early-game deposits: chunk -> digit (None = random 1..3)
FORCED_BLOBS = {(0, 0): 1, (-1, 0): 2, (0, -1): 3, (-1, -1): None}
DIGITS = tuple(range(1, 10))


@lru_cache(maxsize=8)
def _noise(seed):
    return OpenSimplex(seed)


def generate_chunk(seed, cx, cy):
    """Chunk (cx, cy) -> flat row-major list of tile ids (index = ly*16 + lx)."""
    tiles = _ground(seed, cx, cy)
    _deposits(seed, cx, cy, tiles)
    _nests(seed, cx, cy, tiles)
    return tiles


# ---- ground ------------------------------------------------------------------

def _ground(seed, cx, cy):
    base_x, base_y = cx * CHUNK_SIZE, cy * CHUNK_SIZE
    sx = (base_x + np.arange(0, CHUNK_SIZE + 1, NOISE_STEP)).astype(np.float64)
    sy = (base_y + np.arange(0, CHUNK_SIZE + 1, NOISE_STEP)).astype(np.float64)
    coarse = _noise(seed).noise2array(sx * SHADE_FREQ, sy * SHADE_FREQ)
    fine = _upsample(coarse)
    pair = np.where(fine < -SHADE_THRESHOLD, 1,
                    np.where(fine > SHADE_THRESHOLD, 2, 0))
    gx = base_x + np.arange(CHUNK_SIZE)
    gy = base_y + np.arange(CHUNK_SIZE)
    checker = (gx[None, :] + gy[:, None]) & 1          # global parity: seamless
    return (pair * 2 + checker).astype(np.int64).ravel().tolist()


def _upsample(coarse):
    """Bilinear (n+1, n+1) sample grid -> (CHUNK_SIZE, CHUNK_SIZE) tile grid."""
    w = np.arange(NOISE_STEP) / NOISE_STEP
    rows = coarse[:, :-1, None] * (1 - w) + coarse[:, 1:, None] * w
    rows = rows.reshape(coarse.shape[0], CHUNK_SIZE)
    grid = rows[:-1, None, :] * (1 - w)[:, None] + rows[1:, None, :] * w[:, None]
    return grid.reshape(CHUNK_SIZE, CHUNK_SIZE)


# ---- deposits ----------------------------------------------------------------

def in_spawn_clearing(tx, ty):
    return abs(tx) <= SPAWN_CLEAR_RADIUS and abs(ty) <= SPAWN_CLEAR_RADIUS


def digit_decay(dist):
    """Weight ratio between digit d and d+1 at Chebyshev chunk distance dist."""
    return min(DEPOSIT_DECAY_FAR, DEPOSIT_DECAY_NEAR + DEPOSIT_DECAY_PER_CHUNK * dist)


def _pick_digit(rng, dist):
    """1 is the most common digit and 9 the rarest, at every distance; far
    from the origin the gap narrows so high digits become findable."""
    decay = digit_decay(dist)
    return rng.choices(DIGITS, [decay ** (d - 1) for d in DIGITS])[0]


def _deposits(seed, cx, cy, tiles):
    rng = random.Random(f"{seed}:{cx}:{cy}:dep")
    dist = max(abs(cx), abs(cy))
    blobs = []
    if (cx, cy) in FORCED_BLOBS:
        forced = FORCED_BLOBS[(cx, cy)]
        blobs.append(forced if forced is not None else rng.randint(1, 3))
    if rng.random() < DEPOSIT_BLOB_CHANCE:
        blobs.append(_pick_digit(rng, dist))
    base_x, base_y = cx * CHUNK_SIZE, cy * CHUNK_SIZE
    for digit in blobs:
        size = rng.randint(*DEPOSIT_BLOB_SIZE)
        _stamp_blob(rng, tiles, base_x, base_y, digit, size)


def _stamp_blob(rng, tiles, base_x, base_y, digit, size):
    """Random-walk blob of one digit, kept inside this chunk (purity) and out
    of the spawn clearing. Gives up quietly if it cannot grow."""
    tile_id = DEPOSIT_BASE + digit
    for _ in range(20):   # find a free start tile
        lx, ly = rng.randrange(CHUNK_SIZE), rng.randrange(CHUNK_SIZE)
        if tiles[ly * CHUNK_SIZE + lx] < DEPOSIT_BASE \
                and not in_spawn_clearing(base_x + lx, base_y + ly):
            break
    else:
        return
    placed = {(lx, ly)}
    tiles[ly * CHUNK_SIZE + lx] = tile_id
    frontier = [(lx, ly)]
    attempts = 0
    while len(placed) < size and attempts < size * 8:
        attempts += 1
        px, py = rng.choice(frontier)
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        nx, ny = px + dx, py + dy
        if not (0 <= nx < CHUNK_SIZE and 0 <= ny < CHUNK_SIZE):
            continue
        if (nx, ny) in placed or tiles[ny * CHUNK_SIZE + nx] >= DEPOSIT_BASE:
            continue
        if in_spawn_clearing(base_x + nx, base_y + ny):
            continue
        placed.add((nx, ny))
        frontier.append((nx, ny))
        tiles[ny * CHUNK_SIZE + nx] = tile_id


# ---- nests -------------------------------------------------------------------

def _nests(seed, cx, cy, tiles):
    spec = nest_in_chunk(seed, cx, cy)
    if spec is None:
        return
    lx0, ly0 = spec.tx - cx * CHUNK_SIZE, spec.ty - cy * CHUNK_SIZE
    for dy in range(-NEST_RADIUS, NEST_RADIUS + 1):
        for dx in range(-NEST_RADIUS, NEST_RADIUS + 1):
            tiles[(ly0 + dy) * CHUNK_SIZE + lx0 + dx] = NEST_GROUND
    tiles[ly0 * CHUNK_SIZE + lx0] = NEST_CORE
