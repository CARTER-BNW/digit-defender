"""All tunables in one place. IMPORTANT: this module is imported by sim/ and
must stay pygame-free (plain numbers, tuples, dicts only).

Load-bearing constants (world gen and save format depend on them; don't
change casually): CHUNK_SIZE, TILE_SIZE, TICK_RATE, ITEM_SPACING.
"""

# --- grid / display -----------------------------------------------------------
CHUNK_SIZE = 16                     # tiles per chunk side
TILE_SIZE = 32                      # px per tile at zoom 1.0 (digits stay legible)
CHUNK_PX = CHUNK_SIZE * TILE_SIZE   # 512

WINDOW_W, WINDOW_H = 1280, 720
FPS = 60

# --- fixed timestep -----------------------------------------------------------
TICK_RATE = 20                      # sim ticks per second
TICK_DT = 1.0 / TICK_RATE           # 50 ms
MAX_TICKS_PER_FRAME = 4             # cap; leftover time is dropped (no death spiral)

# --- camera -------------------------------------------------------------------
ZOOM_LEVELS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
DEFAULT_ZOOM_INDEX = 3              # -> 1.0
CAMERA_SPEED = 600                  # world px/s (at zoom 1) for keyboard panning
CAMERA_FAST_MULT = 4                # while holding Shift
PRELOAD_CHUNKS = 1                  # ring of chunks kept generated beyond the screen
UNLOAD_MARGIN = 3                   # chunks outside this ring get dropped (hysteresis)
CHUNK_GEN_BUDGET = 24               # max chunks generated per frame (visible ones first)
TEXT_MIN_ZOOM = 0.5                 # below this, items/deposits draw as colored squares

# --- economy ------------------------------------------------------------------
START_BALANCE = 1000
COSTS = {
    "belt": 2, "wall": 5, "miner": 10, "tower": 20,
    "adder": 500, "subtractor": 500, "multiplier": 1000, "divider": 1000,
    "spawner_ranged": 50, "spawner_melee": 50, "spawner_heavy": 150,
}
DEMOLISH_REFUND = 0.5               # fraction of COST returned on demolish
REPAIR_COST_PER_HP = 0.2
TARGET_COUNT = 3                    # active hub target numbers
TARGET_BASE = 4                     # first targets roll in [base, 3*base] ...
TARGET_GROWTH = 1.25                # ... and the base grows by this per completed target
TARGET_REWARD_MULT = 5              # reward = value * mult + flat (sim/economy.py)
TARGET_REWARD_FLAT = 20

# --- belts / items ------------------------------------------------------------
BELT_BASE_SPEED = 0.05              # tiles/tick  (= 1 tile/s at 20 ticks/s)
BELT_SPEED_PER_FED = 0.0001         # tiles/tick per fed value: +0.01 tiles/tick per 100 fed (PLAN 3.5)
MAX_BELT_SPEED = 0.5                # tiles/tick cap so items never skip a belt
ITEM_SPACING = 0.25                 # min gap between items on a belt (4 per tile)
MINER_BASE_PERIOD = 40              # ticks between emissions (2 s)
MACHINE_BASE_PERIOD = 40            # ticks per operation
MACHINE_BUFFER = 3                  # operand buffer depth per side
TOWER_AMMO_MAX = 10                 # numbers a tower can hold

# --- leveling -----------------------------------------------------------------
LEVEL_THRESHOLDS = [100 * 2 ** k for k in range(20)]   # invested >= t -> level up
RATE_STEP = 0.25                    # period = BASE_PERIOD / (1 + level * RATE_STEP)
BASE_HP = {
    "belt": 20, "wall": 200, "miner": 60, "tower": 100, "hub": 1000,
    "adder": 150, "subtractor": 150, "multiplier": 200, "divider": 200,
    "spawner_ranged": 120, "spawner_melee": 120, "spawner_heavy": 200,
}

# --- world gen ----------------------------------------------------------------
WORLD_SEED = 1337
SPAWN_CLEAR_RADIUS = 2              # deposit-free (2r+1)^2 clearing around the origin hub
DEPOSIT_BLOBS_PER_CHUNK = (0, 2)    # inclusive range rolled per chunk
DEPOSIT_BLOB_SIZE = (3, 7)          # tiles per blob, inclusive
DEPOSIT_HIGH_BASE = 0.05            # chance a blob is 6-9 next to the origin...
DEPOSIT_HIGH_PER_CHUNK = 0.02       # ...growing per chunk of Chebyshev distance...
DEPOSIT_HIGH_MAX = 0.6              # ...up to this cap
NEST_REGION = 12                    # chunks per nest-region side (192 tiles)
SAFE_REGIONS = 1                    # no nests within this Chebyshev region distance of origin
NEST_CHANCE_PER_REGION = 0.3        # nest chance grows by this per region beyond SAFE_REGIONS
NEST_CHANCE_MAX = 0.6
NEST_AGGRO_TILES = 48

# --- combat -------------------------------------------------------------------
WAVE_FIRST_S = 300
WAVE_INTERVAL_BASE_S = 240
WAVE_INTERVAL_MIN_S = 90
WAVE_INTERVAL_DECAY = 0.97          # interval = max(MIN, BASE * DECAY**n)
WAVE_BUDGET_BASE = 20
WAVE_BUDGET_GROWTH = 1.25           # budget = BASE * GROWTH**n
WAVE_SPAWN_MARGIN = 12              # tiles beyond the structure bounding box
WAVE_MIN_RADIUS = 30                # tiles from origin, minimum
# Player units. Ranged/heavy shots debit balance by "shot" value per shot;
# melee is free (docs/PLAN.md section 0, rule 6).
UNIT_STATS = {
    "ranged": {"hp": 30, "speed": 0.15, "range": 6, "period": 20, "shot": 1},
    "melee":  {"hp": 60, "speed": 0.2,  "range": 1, "period": 15, "dmg": 3},
    "heavy":  {"hp": 120, "speed": 0.1, "range": 8, "period": 40, "shot": 100},
}
ENEMY_STATS = {
    "grunt":  {"hp": 20, "speed": 0.12, "dmg": 2, "period": 15, "cost": 5},
    "brute":  {"hp": 80, "speed": 0.08, "dmg": 8, "period": 25, "cost": 20},
    "runner": {"hp": 10, "speed": 0.25, "dmg": 1, "period": 10, "cost": 4},
}

# --- colors (RGB) -------------------------------------------------------------
GROUND_SHADES = (                   # per shade pair: (checker A, checker B)
    ((30, 62, 30), (36, 72, 36)),
    ((25, 52, 27), (31, 62, 33)),
    ((37, 76, 35), (44, 87, 41)),
)
DEPOSIT_COLORS = {                  # digit -> text/marker color
    1: (225, 225, 225), 2: (120, 200, 255), 3: (120, 255, 120),
    4: (255, 230, 90), 5: (255, 170, 60), 6: (255, 100, 100),
    7: (230, 120, 255), 8: (140, 140, 255), 9: (255, 215, 0),
}
COLORS = {
    "bg": (12, 24, 12),
    "deposit_bg": (18, 36, 20),
    "nest_ground": (70, 30, 30),
    "nest_core": (160, 40, 40),
    "grid_line": (0, 0, 0),
    "belt": (90, 90, 100),
    "belt_arrow": (200, 200, 210),
    "miner": (120, 120, 60),
    "hub": (60, 110, 200),
    "wall": (110, 110, 110),
    "tower": (90, 60, 130),
    "adder": (40, 140, 60), "subtractor": (170, 80, 40),
    "multiplier": (60, 90, 190), "divider": (160, 60, 160),
    "spawner_ranged": (150, 120, 40), "spawner_melee": (150, 70, 40),
    "spawner_heavy": (90, 90, 40),
    "enemy": (220, 40, 40),
    "unit": (60, 200, 220),
    "text": (240, 240, 240),
    "text_shadow": (0, 0, 0),
    "ghost_ok": (80, 255, 80),
    "ghost_bad": (255, 80, 80),
    "side_input": (80, 255, 80),
    "side_output": (255, 80, 80),
    "side_feed": (255, 230, 60),
    "hp_bar": (60, 220, 60),
    "hp_bar_bg": (40, 40, 40),
    "panel": (20, 28, 20),
    "panel_border": (90, 120, 90),
}
