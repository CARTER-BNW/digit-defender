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

# --- saves --------------------------------------------------------------------
SAVE_VERSION = 1
AUTOSAVE_S = 60                     # seconds between autosaves (also saves on quit)

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
SPRITE_DIR = "assets/sprites"       # optional <kind>.png overrides: 32x32 per tile (hub 96x96), facing up
MINER_PULSE_TICKS = 8               # white border flash after each extraction

# --- economy ------------------------------------------------------------------
START_BALANCE = 1000
COSTS = {
    "belt": 2, "bridge": 10, "wall": 5, "miner": 10, "tower": 20,
    "adder": 500, "subtractor": 500, "multiplier": 1000, "divider": 1000,
    "spawner_ranged": 50, "spawner_melee": 50, "spawner_heavy": 150, "spawner_repair": 100,
}
DEMOLISH_REFUND = 0.5               # fraction of COST returned on demolish
REPAIR_COST_PER_HP = 0.2
TARGET_COUNT = 4                    # hub target slots, each with its own level (John: 4 types)
TARGET_LEVEL1_RANGE = (5, 9)        # level-1 target numbers: distinct picks from this range
TARGET_BASE_AMOUNT = 5              # deliveries of its number a level-1 target wants
TARGET_GROWTH = (0.25, 0.75)        # per level, the number and the amount each grow by a random share in this range
TARGET_REWARD_MULT = (10, 20)       # bonus = number * amount * a seeded roll in this range (John: 5 x 7 pays 350-700)
TARGET_REWARD_FLAT = 0

# --- belts / items ------------------------------------------------------------
BELT_BASE_SPEED = 0.05              # tiles/tick  (= 1 tile/s at 20 ticks/s)
BELT_SPEED_PER_FED = 0.0001         # tiles/tick per fed value: +0.01 tiles/tick per 100 fed (PLAN 3.5)
MAX_BELT_SPEED = 0.5                # tiles/tick cap so items never skip a belt
ITEM_SPACING = 0.5                  # min gap between items on a belt (2 per tile; numbers must not overlap)
MINER_BASE_PERIOD = 40              # ticks between emissions (2 s)
MACHINE_BASE_PERIOD = 40            # ticks per operation
MACHINE_BUFFER = 3                  # operand buffer depth per side
TOWER_AMMO_BASE = 20                # numbers a level-1 tower can hold (John)...
TOWER_AMMO_PER_LEVEL = 10           # ...plus this many per level above 1

# --- leveling -----------------------------------------------------------------
LEVEL_BASE_COST = 100               # fed (or balance) to reach level 2
LEVEL_COST_GROWTH = 1.25            # every further level costs 25% more than the last (John); no level cap
RATE_STEP = 0.25                    # period = BASE_PERIOD / (1 + level * RATE_STEP)
BASE_HP = {
    "belt": 20, "bridge": 40, "wall": 200, "miner": 60, "tower": 100, "hub": 1000,
    "adder": 150, "subtractor": 150, "multiplier": 200, "divider": 200,
    "spawner_ranged": 120, "spawner_melee": 120, "spawner_heavy": 200, "spawner_repair": 120,
}

# --- world gen ----------------------------------------------------------------
WORLD_SEED = 1337
SPAWN_CLEAR_RADIUS = 4              # deposit-free (2r+1)^2 clearing around the origin: the 6x6 HQ (-3..2) plus a ring
DEPOSIT_BLOB_CHANCE = 0.45          # chance a chunk holds one deposit blob (spread out; John)
DEPOSIT_BLOB_SIZE = (3, 7)          # tiles per blob, inclusive
DEPOSIT_DECAY_NEAR = 0.45           # digit weight = decay ** (digit - 1): the higher the digit the rarer...
DEPOSIT_DECAY_PER_CHUNK = 0.02      # ...the decay eases with Chebyshev chunk distance from the origin...
DEPOSIT_DECAY_FAR = 0.8             # ...up to this cap (a 9 stays the rarest everywhere)
NEST_REGION = 12                    # chunks per nest-region side (192 tiles)
SAFE_REGIONS = 1                    # no nests within this Chebyshev region distance of origin
NEST_CHANCE_PER_REGION = 0.3        # nest chance grows by this per region beyond SAFE_REGIONS
NEST_CHANCE_MAX = 0.6
NEST_HOME_DISTANCE = 100            # one camp always sits this many tiles from the HQ (seeded direction; John)
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
WAVE_WARNING_S = 60                 # edge arrow shows the coming wave direction this early
HUB_ALERT_S = 3                     # red pulsing hub border + screen frame this long after a hub hit
TOWER_RANGE = 10                    # tiles (John: towers cover a radius of 10)
TOWER_BASE_PERIOD = 20              # ticks between shots (level shortens it)
TOWER_DMG_LEVEL_MULT = 0.5          # dmg = ammo value * (1 + mult * (level - 1))
SPAWNER_BASE_PERIOD = 200           # ticks to train one queued unit (10 s)
SPAWNER_QUEUE_MAX = 9               # units a spawner can hold in its queue
UNIT_COSTS = {"ranged": 50, "melee": 50, "heavy": 150, "repair": 100}   # balance per queued unit (idea.txt)
UNIT_LEVEL_MULT = 0.25              # unit hp/dmg * (1 + mult * (spawner level - 1))
UNIT_AGGRO_TILES = 12               # units chase enemies this close
GATHER_HUB_GAP = 2                  # default gather point: this many tiles clear of the HQ edge
GATHER_MAX_RING = 24                # formation slots spiral out at most this far
FORMATIONS = ("box", "line", "column", "wedge", "ring")   # [wheel] with units selected cycles these
POST_MAX_SHIFT = 3.0                # attackers spread to a free tile at most this far from where they stand
UNIT_PASSABLE_KINDS = ("belt", "bridge")   # player units walk over these; every other structure blocks them (John)
UNIT_PATH_BUDGET = 4000             # A* expansions per route before a unit gives up and holds
REPAIR_UNIT_CAPACITY = 500          # numbers a repair unit carries (John); refills at the HQ from the balance
REPAIR_UNIT_SEARCH = 16             # tiles around a repair unit it looks for damage in
REPAIR_HP_PER_NUMBER = 5            # = 1 / REPAIR_COST_PER_HP: a repair unit fixes hp at the same price as [H]
ENEMY_ATTACK_RANGE = 1.5            # tiles (melee contact, diagonals included so 8 attackers fit around a tile)
FLOW_COST_WALL = 40
FLOW_COST_STRUCT = 15
FLOW_MARGIN = 12                    # tiles around the structure bounding box
FLOW_REFRESH_TICKS = 40             # recompute at most this often
NEST_RAID_PERIOD_S = 45
NEST_RAID_SIZE = 3                  # enemies per raid per tier
NEST_BOUNTY = 500                   # balance per tier when a core dies
WAVE_MIX = {"grunt": 60, "runner": 25, "brute": 15}   # weights; brutes from wave 3
# Player units. Ranged/heavy shots debit balance by "shot" value per shot;
# melee is free (docs/PLAN.md section 0, rule 6).
UNIT_STATS = {
    "ranged": {"hp": 30, "speed": 0.15, "range": 6, "period": 20, "shot": 1},
    "melee":  {"hp": 60, "speed": 0.2,  "range": 1.5, "period": 15, "dmg": 3},
    "heavy":  {"hp": 120, "speed": 0.1, "range": 8, "period": 40, "shot": 100},
    # repair (John): never fights; heals `heal` hp per action on damaged buildings and units next to
    # it, spending carried numbers (REPAIR_HP_PER_NUMBER hp each); empty -> walks to the HQ to refill
    "repair": {"hp": 40, "speed": 0.18, "range": 1.5, "period": 10, "heal": 25},
}
# Enemies both shoot and melee (John): dmg = melee in contact; shot_dmg at up to
# shot_range tiles, fired while advancing (nearest unit first, else nearest structure).
ENEMY_STATS = {
    "grunt":  {"hp": 20, "speed": 0.12, "dmg": 2, "period": 15, "cost": 5, "shot_dmg": 1, "shot_range": 4},
    "brute":  {"hp": 80, "speed": 0.08, "dmg": 8, "period": 25, "cost": 20, "shot_dmg": 3, "shot_range": 3},
    "runner": {"hp": 10, "speed": 0.25, "dmg": 1, "period": 10, "cost": 4, "shot_dmg": 1, "shot_range": 5},
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
    "belt": (92, 92, 104),
    "bridge": (150, 128, 90),
    "belt_arrow": (52, 52, 62),
    "belt_edge": (60, 60, 70),
    "miner": (120, 120, 60),
    "hub": (60, 110, 200),
    "wall": (110, 110, 110),
    "tower": (90, 60, 130),
    "adder": (40, 140, 60), "subtractor": (170, 80, 40),
    "multiplier": (60, 90, 190), "divider": (160, 60, 160),
    "spawner_ranged": (150, 120, 40), "spawner_melee": (150, 70, 40),
    "spawner_heavy": (90, 90, 40),
    "spawner_repair": (170, 40, 40),
    "demolish": (150, 55, 55),
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
