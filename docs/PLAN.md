# Digit Defender — Implementation Plan

Target: `D:\Claude\projects\games\Digit Defender`
Stack: Python 3.12, pygame-ce, numpy, opensimplex, pytest.
Architecture mirrors Pixel_Worlds' layering (world / render / ui / tests + settings.py) with one
major addition: a **`sim/` package that never imports pygame** — the entire factory and combat
simulation is headless and pytest-testable.

## 0. Governing decisions (read first)

1. **Structures do NOT live in terrain chunks.** `Factory.structures: dict[(tx, ty)] -> Structure`
   at world level. The factory is sparse, must simulate regardless of chunk load state, and must
   persist independently. Terrain chunks handle only ground + deposits + nest tiles. This makes
   chunk-border belts a non-issue and makes "unload vs simulate" trivial: **terrain unloads
   freely; the factory always simulates.**
2. **Fixed timestep**: `TICK_RATE = 20` (dt = 50 ms), accumulator loop in `game.py`, render at
   60 FPS. Sim advances only in whole ticks; rendering may interpolate belt items (Phase 6).
3. **Deposits are infinite** (like Beltmatic). Terrain is essentially never modified → the
   modified-chunk save machinery stays but almost no chunk files get written. Nest destruction
   is recorded in a registry, not by editing chunks.
4. **Deterministic sim**: no `random` inside the factory tick (only combat uses a save-seeded
   `random.Random`). Belt update uses explicit chain ordering, not dict iteration order.
5. **`to_dict()/from_dict()` on every Structure from the day it's written** (Phase 2), so
   Phase 3 save/load is assembly, not surgery.
6. **Ranged fire costs balance** (John's rule): long-range and heavy units deduct the fired
   number's value from balance per shot (long-range dmg 1 → 1/shot; heavy 100 → 100/shot);
   balance too low → hold fire. Melee free. **Towers are belt-fed ammo** (no balance cost) —
   the two defense types feel different by design. Armies are an ongoing economic drain.

## 1. Module layout

```
Digit Defender/
├── main.py                 # pygame init, world-select menu, launches Game
├── game.py                 # Game class: event loop, fixed-timestep accumulator,
│                           #   input → build/pan/zoom, autosave timer, game-over
├── settings.py             # all constants (see §4)
├── requirements.txt        # pygame-ce, numpy, opensimplex, pytest
├── run.bat
├── conftest.py             # headless SDL env for the few tests that need pygame
├── docs/                   # idea.txt, PLAN.md (this), PHASES.md, GOTCHAS.md
├── world/                  # terrain only — no gameplay state
│   ├── terrain.py          # Terrain: chunks dict, get_chunk/get_tile,
│   │                       #   update(keep_rect, unload_rect), save_modified()
│   ├── chunk.py            # __slots__ Chunk: flat row-major tile list, dirty flag,
│   │                       #   cached base surface + per-zoom scaled cache (§3.3)
│   ├── generator.py        # pure f(seed, cx, cy): checkered ground shades,
│   │                       #   deposits 1–9, nest region grid (§3.6)
│   └── persistence.py      # save dir layout, meta.json, chunk .bin, atomic writes
├── sim/                    # HEADLESS — imports nothing from pygame/render
│   ├── factory.py          # Factory: structures dict, belt chains, tick(),
│   │                       #   place/remove/rotate, cost checks, feed routing
│   ├── structures.py       # Structure base + Belt, Miner, MathMachine, Hub,
│   │                       #   Wall, Tower, Spawner (each with to_dict/from_dict)
│   ├── economy.py          # balance, build costs, targets (generation + payout)
│   ├── leveling.py         # invested → level / speed / rate / max_hp formulas
│   ├── combat.py           # units, enemies, projectiles, damage, waves
│   ├── nests.py            # deterministic nest registry, raid triggers
│   ├── pathing.py          # hub flow field (BFS), fallback greedy movement
│   └── serialize.py        # structures/enemies ↔ JSON records, versioning
├── render/
│   ├── camera.py           # Pixel_Worlds camera + zoom (§3.3)
│   ├── renderer.py         # chunk blits, structures, belt items, units, fx
│   └── numbers.py          # cached digit text surfaces, 1.2K abbreviation (§3.4)
├── ui/
│   ├── hud.py              # balance, targets panel, wave timer, selected-structure
│   │                       #   info (level/invested/hp), build toolbar, hotbar keys
│   └── menu.py             # world list / create / resume (adapt Pixel_Worlds)
├── tests/                  # test_generator, test_belts, test_machines, test_economy,
│                           #   test_leveling, test_persistence, test_combat
└── saves/                  # gitignored
    └── <world_slug>/
        ├── meta.json
        ├── chunks/{cx}_{cy}.bin
        ├── structures.json
        └── enemies.json
```

## 2. Core data structures

### 2.1 Terrain (adapt Pixel_Worlds nearly verbatim, simplified)

- `Chunk`: `__slots__ = ("cx","cy","tiles","dirty","modified","_surface","_scaled")` — flat
  row-major `tiles` list (16×16), 1 byte per tile. Tile ids: `GROUND_A/GROUND_B` (checker
  shades, plus 2–3 noise-varied dark greens), `DEPOSIT_1..DEPOSIT_9`, `NEST_CORE`, `NEST_GROUND`.
  No depths/floors layers — drop them.
- `Terrain` (rename of Pixel_Worlds `World` to avoid clashing with the game-level object):
  `chunks = {}`, `get_chunk` lazy load-else-generate, `divmod(tx, CHUNK_SIZE)` mapping,
  `update(keep_rect, unload_rect)` hysteresis, `save_modified()`. Structures aren't in chunks,
  so no pinning logic is needed.
- `generator.py` — pure function of `(seed, cx, cy)`:
  - Checker base: `GROUND_A if (tx + ty) % 2 else GROUND_B`, tinted by low-frequency OpenSimplex
    noise bucketed into 2–3 shade pairs. Noise sampled every 4 tiles + bilinear upsample as in
    Pixel_Worlds (seamless borders).
  - Deposits: per-chunk string-seeded rng places at most ONE blob (DEPOSIT_BLOB_CHANCE = 0.45;
    3–7 tiles, single value 1–9), so deposits are spread out (John, 2026-09-11). The digit is
    drawn with geometric weights decay**(digit-1): the higher the digit the rarer, at every
    distance; decay eases from 0.45 near the origin to 0.8 far out so 6–9 become findable but
    never outnumber lower digits. Guarantee: chunks within radius 2 of origin contain at least
    one 1, one 2, one 3 deposit total (early game always works).
  - Spawn area: deposit-free 5×5 tile clearing at the origin for the hub.
  - Nests: region grid (§3.6) stamped into distant chunks.

### 2.2 Structures (`sim/structures.py`)

```python
class Structure:            # __slots__ throughout
    x, y: int               # anchor tile (world coords, any sign)
    direction: int          # 0..3 = N/E/S/W (output side)
    invested: int           # total number-value fed in (drives level AND max_hp)
    hp: float               # current health; max_hp = f(kind, invested)
    # class attrs: KIND, COST, SIZE (1 or (3,3) for hub), BASE_HP
    def tick(self, factory): ...
    def to_dict(self) / from_dict(cls, d): ...

class Belt(Structure):
    items: list[list[value, progress]]   # progress ∈ [0,1), sorted ascending,
                                         # ITEM_SPACING = 0.25 min gap (4/tile)
    # speed (tiles/tick) = BELT_BASE_SPEED + invested * BELT_SPEED_PER_FED
    next: Belt|Structure|None            # resolved link cache (rebuilt on
    prev_count: int                      #   neighbor placement/removal)

class Miner(Structure):
    value: int              # deposit digit cached at placement
    timer: int
    # emits `value` onto the belt it faces every PERIOD(level) ticks, stalls if full

class MathMachine(Structure):
    op: str                 # 'add' | 'sub' | 'mul' | 'div'
    in_a: deque[int]        # left-side input buffer (max 3)
    in_b: deque[int]        # right-side input buffer (max 3)
    out: int|None           # finished result waiting for belt space
    timer: int
    # sides relative to `direction`: output = front; A = left, B = right;
    # back side is feed-only. sub → a-b, div → a//b; results <= 0 are voided
    # (design call — confirm before Phase 4)

class Hub(Structure):       # 3x3, anchored center; all 9 tiles map to it
    # any item pushed in from any side: balance += value; also checked against targets

class Wall(Structure): ...  # blocks enemies; no tick
class Tower(Structure): ... # ammo buffer fed by belts; fires number-lasers, dmg = f(ammo value, level)
class Spawner(Structure):   # kind: 'ranged'|'melee'|'heavy'; spawns Units on a timer
```

Multi-tile handling: `Factory.structures` maps **every occupied tile** to the object; the
object stores its anchor; `origin()` = anchor − SIZE//2, `tiles()` = origin + range(SIZE)²,
`centre()` = origin + SIZE/2 (works for even sizes). Only Hub is multi-tile: 6×6 spanning
−3..2 around its anchor (John, 2026-09-11; was 3×3).

### 2.3 Factory and the tick (`sim/factory.py`)

```python
class Factory:
    structures: dict[(tx,ty), Structure]
    belts_ordered: list[Belt]     # chain-ordered, downstream-first
    miners, machines, towers, spawners: list[...]   # typed lists for the tick
    hub: Hub
    balance: int
    targets: list[Target]         # (value, reward) — economy.py
    tick_count: int
    dirty_links: bool             # neighbor links need re-resolve
    dirty_flowfield: bool         # walls/structures changed → repath (combat)
```

**Tick order (fixed, documented, load-bearing for determinism):**

1. `if dirty_links: rebuild belt links + belts_ordered` (also sets `dirty_flowfield`)
2. **Miners** produce onto facing belt if spacing allows (sorted by (y,x) for determinism)
3. **Machines** finish processing: move `out` onto facing belt if space; start a new op if
   both buffers nonempty
4. **Belts** advance items, iterating `belts_ordered` (downstream first so space frees within
   the same tick). An item crossing 1.0 is offered to `next`:
   - next is Belt → insert if head gap ≥ ITEM_SPACING, else clamp at `1.0 - EPS` (stall,
     natural backpressure)
   - next is MathMachine, arrival side A/B → push to that buffer if not full, else stall
   - next is Hub → consume: `balance += value`, target check
   - next is Tower front → consume into ammo buffer
   - next is any structure on a non-input side (incl. a belt entered head-on against its
     direction) → **consume as feed**: `invested += value`; hp moves only when the level steps
     (max_hp is stepwise, §3.5) — this one rule implements the entire improvement system
   - next is None/terrain → stall at end of belt
5. **Spawners** tick spawn timers (Phase 5)
6. **Combat**: enemy AI (flow field or greedy+bump), unit AI (ranged shots debit balance,
   hold fire if broke), tower target/fire, projectiles, damage, deaths (Phase 5)
7. **Waves/nests**: timers, raid triggers (Phase 5)
8. **Economy**: refresh targets if completed (income is delivery-only)

**Belt chain ordering** (`rebuild`): Kahn's algorithm over cargo links (a belt is ordered after
every belt it outputs into; belts with no belt outputs go first). Belt outputs are the front target
plus belts beside it that point straight away (implicit splitter, even round-robin). Original plan:
follow `next` links; order each chain tail-first (the belt whose `next` is not a belt goes first). Merges make a forest, ordered by DFS from each
sink; merge priority fixed left-first (deterministic). Belt loops are legal: detect, break
ordering at the smallest (y,x) belt, accept one-tick lag inside loops. Rebuild only on
placement/removal/rotation (`dirty_links`), never per tick.

**Simulation-while-unloaded policy**: the whole factory ticks always (independent of chunk
state). Stalled belts early-out (head item clamped + next full → skip). Budget check: profile
at Phase 2 exit with a synthetic 2,000-belt world before adding cleverness.

### 2.4 Game loop (`game.py`)

```python
acc = 0.0
while running:
    dt = clock.tick(FPS) / 1000
    acc += dt
    handle_events()                    # build/rotate/demolish/pan/zoom/UI
    n = 0
    while acc >= TICK_DT and n < MAX_TICKS_PER_FRAME:   # cap = 4: no death spiral
        factory.tick(); acc -= TICK_DT; n += 1
    if n == MAX_TICKS_PER_FRAME: acc = 0.0             # drop time, don't snowball
    terrain.update(*camera.keep_unload_rects())
    renderer.draw(...); hud.draw(...)
```

Game over: `hub.hp <= 0` → freeze sim, overlay, offer load-last-save / quit.

## 3. Key design problems — chosen solutions

### 3.1 Belts across chunk borders
Solved structurally: belts live in the world-level dict keyed by world tile coords (negatives
fine — always `divmod`). Chunk borders don't exist for the sim.

### 3.2 Entity representation
As §2.2. Belt items are 2-element lists (mutable progress) inside per-belt lists — no
per-item objects/IDs.

### 3.3 Zoomable camera + chunk surfaces
- `Camera` gains `zoom` with **discrete steps**: `ZOOM_LEVELS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)`,
  mouse wheel moves along the tuple, zoom anchored at the cursor (adjust `x,y` so the world
  point under the mouse stays fixed).
- `world_to_screen(wx, wy) = round((wx - x) * zoom + w/2), ...`; `visible_chunk_range` divides
  screen extents by `CHUNK_PX * zoom`.
- Chunks keep their base 1.0 surface (dirty-flag pattern, `TILE_SIZE = 32` for digit
  legibility) plus `_scaled: dict[zoom -> Surface]` filled lazily with `pygame.transform.scale`
  and cleared when dirty; cap `_scaled` to the current zoom only (drop others on zoom change).
- Structures, belt items, units, health bars draw directly every frame at scaled positions
  (sparse); only terrain uses cached surfaces.

### 3.4 Number rendering
`render/numbers.py`: `abbrev(n)` → `"7"`, `"142"`, `"1.2K"`, `"3.4M"`, `"5.1B"`, then
`functools.lru_cache(4096)` on `(text, zoom)` → rendered Surface (white text, 1px black
outline via 4 offset blits). Below `zoom < 0.5`, belt items render as small colored squares
(hue bucketed by magnitude), no text — perf guard AND readability win.

### 3.5 Improvement / leveling (Phase 4)
One rule: **an item consumed through a non-cargo side is feed** — `invested += value`.
Belts: head-on against direction = feed; side entry = merge (cargo); tail entry = cargo.
Machines: left/right = operands A/B, back = whichever buffer is emptier (all three sides are
inputs — John, 2026-09-11; machines have no feed side and level via `[U]`); front = output.
Hub: everything is cargo (income). Towers: every side = ammo, no feed sides (John, 2026-09-11;
towers level through the balance upgrade `[U]` instead).
- `leveling.py` pure functions: `level(invested)` from geometric level costs — level n→n+1
  costs `100·1.25^(n-1)` (100, 125, 156, ...), thresholds are the running sum, no level cap
  (John, 2026-09-11; replaced the `100·2^k` table);
  `belt speed = BASE + invested/10000` (user's +0.01 per 100); miner/machine/tower/spawner
  period `= BASE_PERIOD / (1 + level * RATE_STEP)`; `max_hp = BASE_HP + threshold(level-1)`
  (stepwise: hp only rises when a level-up raises max_hp, by exactly that gain; feeding never
  heals — repair costs balance at `REPAIR_COST_PER_HP`; John, 2026-09-11). `[U]` buys the
  next level at its fixed price `level_cost(level)`; the payment is fed in full, so numbers
  already fed toward the level are not discounted and any excess carries over.
- Spawner level additionally scales spawned-unit stats.
- Confirm before Phase 4: sub/div voiding of ≤0 results; head-on-feed rule.

### 3.6 Enemy nests
- `NEST_REGION = 12` chunks (192 tiles). Per region `(rx, ry)`:
  `rng = random.Random(hash((seed, rx, ry, "nest")))`; nest chance 0 within `SAFE_REGIONS = 1`
  Chebyshev of origin, ramping to ~0.6 far out; strength tier `= f(max(|rx|,|ry|))` scaling
  nest hp, raid size, unit stats.
- Generation stamps `NEST_CORE`/`NEST_GROUND` tiles into terrain (deterministic);
  `sim/nests.py` keeps the authoritative registry: `nest_at(rx, ry) -> NestSpec | None`
  (pure) plus `destroyed: set[(rx,ry)]` (saved). Destroyed nests render rubble via a lookup
  at chunk-render time, so terrain files stay unmodified.
- Behavior: dormant until any player structure is within `NEST_AGGRO_TILES`; then spawns raid
  parties on a timer. Destroying the core pays a bounty and adds to `destroyed`.
- Home camp (John, 2026-09-11): every world also has one tier-1 nest `NEST_HOME_DISTANCE` (100)
  tiles from the origin in a seeded direction (`nests.home_nest`), inside the safe zone, always
  known (minimap + edge arrow) so a player can find a camp early; same aggro rule.

### 3.7 Enemy pathing (pragmatic tiering)
- v1 (Phase 5 start): greedy movement toward target (hub for waves, nearest structure for
  raids); when bumping a blocking structure, attack it. Walls work automatically as
  attack-priority speed bumps. No A*.
- Every enemy also shoots (John, 2026-09-11): while advancing it fires `shot_dmg` at the nearest
  player unit, else the nearest structure, within `shot_range` (3–5 tiles), free, on the same
  cooldown as its melee; contact still lands the bigger melee hit. Walls still block bodies.
- v2 (Phase 5 polish): single BFS **flow field from the hub** over the built-up bounding box
  + margin, costs: empty 1, wall 40, other structures 15; recomputed only when
  `dirty_flowfield` and at most every N ticks. All wave enemies share it. Enemies outside the
  field fall back to v1 greedy.

### 3.8 Waves
`WaveState {number, next_at_tick}`. First wave at 5 min; interval `max(90s, 240s · 0.97^n)`;
budget `= 20 · 1.25^n` spent on a unit mix. Spawn ring: bounding box of all structures
inflated by 12 tiles (min radius 30 from origin), deterministic-per-wave rng angle.
HUD countdown + red edge arrows in the last 30 s.

### 3.9 Save format (`persistence.py` + `sim/serialize.py`)
```
meta.json        {version, name, seed, created, last_played, camera:[x,y,zoom],
                  balance, tick_count, wave:{number,next_at_tick,raids,units,next_uid},
                  targets:[{slot,level,value,amount,delivered,reward}, ...]}
chunks/*.bin     version byte + tiles  (rare — deposits infinite; kept for future)
structures.json  {version, structures:[{kind,x,y,dir,invested,hp, ...kind-specific:
                  op, buffers, out, value, timer, items:[[v,p],...]}]}
enemies.json     {version, nests_destroyed:[[rx,ry],...],
                  nests_damaged:{"rx,ry": hp}, units:[...] or omitted}
```
- JSON is fine to 10k+ structures; upgrade path = bump `version`, switch to compact binary
  if saves exceed ~5 MB.
- Atomic writes everywhere: write `*.tmp`, `os.replace`. Autosave every 60 s and on quit.
  Transient combat units dropped on save ("raids disperse on reload") — avoids serializing
  projectiles.
- Belt items serialize with progress → loading mid-flow resumes exactly; combined with fixed
  tick order this keeps saves deterministic.

## 4. Settings to define up front (`settings.py`)

```python
CHUNK_SIZE = 16; TILE_SIZE = 32; CHUNK_PX = 512
WINDOW_W, WINDOW_H = 1280, 720; FPS = 60
TICK_RATE = 20; TICK_DT = 1/20; MAX_TICKS_PER_FRAME = 4
ZOOM_LEVELS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
PRELOAD_CHUNKS = 1; UNLOAD_MARGIN = 3
CAMERA_SPEED = 600; CAMERA_FAST_MULT = 4          # keys; MMB-drag pans too
# economy
START_BALANCE = 1000
COSTS = {"belt": 2, "wall": 5, "miner": 10, "tower": 20,
         "adder": 500, "subtractor": 500, "multiplier": 1000, "divider": 1000,
         "spawner_ranged": 50, "spawner_melee": 50, "spawner_heavy": 150}
DEMOLISH_REFUND = 0.5; REPAIR_COST_PER_HP = 0.2
# belts/items
BELT_BASE_SPEED = 0.05        # tiles/tick = 1 tile/sec
BELT_SPEED_PER_FED = 0.0001   # +0.01 tiles/s per 100 fed (idea.txt spec)
ITEM_SPACING = 0.25
MINER_BASE_PERIOD = 40        # ticks (2 s); MACHINE_BASE_PERIOD = 40
MACHINE_BUFFER = 3
# leveling
LEVEL_THRESHOLDS = [100 * 2**k for k in range(20)]
BASE_HP = {"belt": 20, "wall": 200, "miner": 60, "tower": 100, "hub": 1000, ...}
# world gen
WORLD_SEED default, DEPOSIT_* densities, NEST_REGION = 12, SAFE_REGIONS = 1
# combat
WAVE_FIRST_S = 300; WAVE_* scaling; UNIT_STATS = {...}; NEST_AGGRO_TILES = 48
# ranged unit fire: shot cost = fired value (long-range starts 1, heavy starts 100)
COLORS = {ground_a/b (+shade variants), grid_line, belt, per-op machine colors, hub, enemy, ...}
```

## 5. Testing approach

- `sim/` and `world/generator.py` import no pygame → plain pytest, fast.
- `conftest.py`: `os.environ["SDL_VIDEODRIVER"] = "dummy"` for the few render tests.
- Harness pattern: `Factory(balance=10**9)` with no terrain, place structures by hand,
  `tick()` N times, assert item positions/balance. Key suites:
  - **test_generator**: determinism (same seed → identical chunks, any visit order), negative
    coords, deposit values ∈ 1–9, near-spawn guarantee, nest-free safe zone.
  - **test_belts**: travel time = 1/speed; spacing under a flooding miner; corners; merge;
    head-on feed vs side merge vs tail cargo; cross-border line at tx 15→16 and −1→0; loop
    doesn't crash or lose items; stall backpressure reaches the miner.
  - **test_machines**: each op incl. `7//2 = 3`, `3-5` voided; buffer-full stalls upstream;
    output stall holds `out`.
  - **test_economy**: costs deducted, insufficient-balance rejected, hub credit, target
    payout + replacement, demolish refund.
  - **test_leveling**: threshold table, belt speed formula, max_hp growth, feed increments hp.
  - **test_persistence**: full round-trip — build, run 100 ticks, save, load, run 100 more vs
    an unsaved twin at 200: **identical state** (determinism acid test). Corrupt-file fallback.
  - **test_combat**: greedy pathing bumps and attacks a wall; flow field reaches hub; wave
    budget scaling; tower kills; ranged shot debits balance / holds fire when broke;
    hub death → game_over flag.

## 6. Phase breakdown (mirrored in docs/PHASES.md)

**Phase 0 — Scaffold** (half a session)
requirements.txt, run.bat, settings.py, docs, empty packages, conftest.py.
✓ `python main.py` opens a window and quits cleanly. ✓ `pytest` passes.

**Phase 1 — Walkable skeleton**
Terrain/Chunk/Generator (checker + deposits + spawn clearing), Camera pan (WASD/arrows +
middle-drag) + cursor-anchored zoom, renderer with per-zoom cached chunk surfaces,
keep/unload via `visible_chunk_range`, deposits rendered as digits, F3 overlay.
✓ Pan indefinitely; chunks appear only when seen. ✓ All 6 zoom levels, cursor anchoring,
no seams. ✓ Revisit → identical terrain. ✓ 60 fps at 0.25 zoom. ✓ generator tests green.

**Phase 2 — Factory core** (the big one; sub-checkpoint aggressively)
Fixed-timestep loop; build mode (toolbar + hotkeys, R rotate, ghost preview with
validity/cost tint, X demolish w/ refund); Belt/Miner/MathMachine/Hub in sim; hub at origin
at world creation; balance HUD; 3 active targets with rewards.
✓ 2a: miner on deposit → digits ride belts, turns work. ✓ 2b: two lines into an adder →
sums emerge; all four ops verified in-game. ✓ 2c: delivery credits face value; target pays
bonus and rerolls. ✓ 2d: costs enforced. ✓ 2e: line crossing chunk borders 40 chunks away
keeps running off-screen. ✓ sim tests green. ✓ 2,000-belt synthetic profile ≥ 60 fps.

**Phase 3 — Save/load**
persistence.py + serialize.py, world-select menu (create/name/seed/resume), autosave 60 s +
on quit, camera/balance/targets/tick in meta.
✓ Quit mid-flow, relaunch, resume exact. ✓ Determinism round-trip test green. ✓ Kill process
→ last autosave loads. ✓ Two worlds don't cross-contaminate.

**Phase 4 — Improvement & leveling**
Feed rule in belt transfer, leveling.py, selected-structure panel (level, invested, hp bar,
next threshold), health bars when damaged, repair action. Rates actually scale.
✓ Head-on feed line visibly speeds a belt. ✓ Fed machine processes faster. ✓ Panel matches
formulas; tests green. ✓ Design confirmations logged (feed rule, void-≤0).

**Phase 5 — Combat**
5a walls + towers (ammo-fed number lasers) + debug-spawned enemy → kill it.
5b waves: timer, budget, spawn ring, greedy+bump pathing, damage, hub death = game over.
5c flow field pathing; enemies route around walls, chew through when enclosed.
5d spawners + player units (ranged/melee/heavy; ranged fire debits balance; attack-move
toward nearest enemy/nest, right-click rally).
5e nests: region-gen visuals, aggro raids, destruction bounty + persistence.
✓ Survive 5 waves. ✓ Lose on purpose → game over → reload works. ✓ Destroy a nest, stays
dead after reload. ✓ Save mid-wave loads sanely. ✓ combat tests green.

**Phase 6 — Polish (stretch)**
Belt item render interpolation, sounds, minimap, stats, belt drag-place, blueprints/copy-paste,
pause/speed controls, balance pass.

## 7. Pitfalls specific to this design

1. **Negative coordinates**: only ever `divmod(t, CHUNK_SIZE)` — test −1/0 and 15/16 borders.
2. **Belt determinism vs dict order**: never iterate `structures.values()` to update; use
   `belts_ordered` and (y,x)-sorted typed lists, or reload silently changes behavior.
3. **Naive belt order** causes one-tick gaps — downstream-first chain order is the fix.
4. **Feed vs input ambiguity**: ghost preview must color-code sides (input green, output red,
   feed yellow) or players upgrade machines by accident.
5. **Unload vs simulate**: structures never go in chunks (Pixel_Worlds mobs despawn on
   unload; the factory must not).
6. **Zoom perf**: never `transform.scale` per frame — cache per discrete zoom; never
   `font.render` per frame — everything through numbers.py LRU; text-off below 0.5 zoom.
7. **Fixed-timestep death spiral**: cap 4 ticks/frame, drop the remainder.
8. **Generator purity**: gameplay never writes terrain (nest death via registry) or saves
   and regeneration diverge.
9. **Multi-tile hub**: all 36 tiles map to the Hub, removed together; belt `next` resolution
   accepts any hub tile. Saves from the 3×3 days: `Factory._drop_hub_overlaps` removes anything
   the bigger HQ now covers.
10. **Huge numbers**: abbreviation from day one; consider scientific display > 1e12.
11. **hp vs invested**: hp and max_hp move only on level-ups (John dropped the original
    "feeding heals" coupling on 2026-09-11); repair is the only heal. Test that a level-up
    adds exactly the max_hp gain and that a trickle of feed never touches hp.

## Reference files (read before starting each phase)

- `D:\Claude\projects\games\Pixel_Worlds\world\world.py` — chunk dict, lazy load, keep/unload hysteresis (→ world/terrain.py)
- `D:\Claude\projects\games\Pixel_Worlds\world\chunk.py` — __slots__ + dirty-flag cached surface (→ world/chunk.py)
- `D:\Claude\projects\games\Pixel_Worlds\world\generator.py` — pure seeded gen, noise upsampling, region-grid stamping (→ world/generator.py, nests)
- `D:\Claude\projects\games\Pixel_Worlds\world\persistence.py` — versioned chunk .bin + meta.json registry (→ world/persistence.py)
- `D:\Claude\projects\games\Pixel_Worlds\render\camera.py` — world-px camera + visible_chunk_range (→ render/camera.py, add zoom)

New files carrying the most design weight: `sim/factory.py` (tick order, belt chains),
`sim/structures.py` (feed/input side rules), `settings.py` (tunables).
