# HANDOFF — Digit Defender
_Last updated: 2026-09-11 (v5, after John's second play-test feedback) by Claude_

New-session bootstrap. Read this, then docs/PLAN.md (design authority), docs/PHASES.md (checkpoints), docs/GOTCHAS.md.

## Live state
- **Phases 0-5 are built and verified by script** (tests + real-window runs + screenshots). Phase 6 (polish) is
  in progress. 106 pytest tests green (`python -m pytest -q`, ~4 s).
- **John has play-tested three times; every item of his feedback is implemented** (STATUS v4 + v5). Round 3 (v5):
  towers range 10 with a range disc (hover/select/ghost) and a red frame + "0" when out of ammo; spawners train
  only when clicked (units cost 50/50/150 per idea.txt, queue count on the sprite, no M/H/R letter); units gather
  one per tile in a grid beside the hub, walk along grid lines, click/drag-box select + RMB move; belt items
  remember their entry side so corners animate as an L instead of jumping edges; walls join neighbours with
  connector bars and show their level; `[U]` upgrade pays balance up to the next level; hub hp bar sits under
  the HUB label, one tile wide; Esc in the menu resumes the last world; corners/merges never become splitters;
  player units survive save/load.
- John is drawing more sprites (miner, machines, hub...). The loader picks up `assets/sprites/<kind>.png` automatically
  (wall.png, if it arrives, is drawn over the procedural connector bars).
- **Code changes need a game restart** (a running `python main.py` keeps the code it started with).
- Directory: D:\Claude\projects\games\Digit Defender (local git on `main`, no remote). Saves in `saves/` (gitignored),
  machine prefs in `config.json` (gitignored).
- Run: `python main.py` (menu) or `python main.py --world NAME [--seed N]` (skip menu), `--frames N` auto-quit,
  `--autosave S`, `--fullscreen`. `run.bat` passes args through.
- Open design checkbox in Phase 4: John to confirm feed-side rules and voiding of <= 0 results (implemented per PLAN;
  he has now played with them without objection, so likely just tick it).

## Health check (what "working" looks like)
1. `python -m pytest -q` -> all green.
2. `python main.py --world smoke --frames 120` -> window opens on a fresh world with the hub, exits 0, `saves/smoke/` written.
3. In game: 1 = belt, 2 = miner (needs a deposit), 3-6 = machines, 7 = wall, 8 = tower, 9/0/- = spawners; R rotate,
   LMB place (drag paints belts that auto-turn), X demolish (hold to sweep), Q pick, H repair, U upgrade (balance up to
   the next level), click = select (panel on the right), click a spawner = train one unit, click / Shift+click / drag a
   box = select units, RMB = move selected units (grid formation) or set a selected spawner's gather point or cancel,
   wheel zoom, MMB drag pan, WASD pan (Shift fast), F3 debug, Space pause, [ ] sim speed x1/x2/x4, F1 help overlay,
   Home or the HUB button = camera back to the hub, F6 spawn an enemy at the cursor, F7 trigger the next wave,
   F11 fullscreen, Esc = cancel tool / clear selection / menu (Esc in the menu = back into the game). Minimap bottom-right.
4. Belt rules a player sees: drag-paint belts; a belt that starts beside a straight belt and points away becomes a
   branch (T), items alternate between branches; a corner or a merge never branches; numbers cannot be built on
   except by miners; a miner pushes into every adjacent belt.

## Architecture in one screen (details: CLAUDE.md architecture map, docs/PLAN.md)
- `sim/` is headless (no pygame): `factory.py` (structures dict, fixed tick order, belt chain ordering, economy, damage,
  upgrade), `structures.py` (Belt/Miner/MathMachine x4/Hub/Wall/Tower/Spawner with side rules + to_dict/from_dict),
  `leveling.py`, `economy.py` (seeded targets), `serialize.py`, `combat.py` (enemies, units, formations, waves, nests,
  beams), `pathing.py` (greedy + hub flow field), `nests.py` (pure region grid + NestRegistry).
- `world/`: `generator.py` (pure), `chunk.py`, `terrain.py` (streaming with a per-frame generation budget), `persistence.py`
  (atomic JSON + .bak, chunk .bin, world registry).
- `render/`: `camera.py` (discrete zoom, screen_origin), `renderer.py` (per-zoom cached chunk surfaces, eviction, F3),
  `structures.py` (cached sprites, batched blits, ghost/selection/health bars/range discs), `combat.py` (units, beams,
  selection rings, drag box), `numbers.py` (abbrev, fmt, text cache).
- `ui/`: `hud.py` (balance, targets, wave timer, toolbar, hover line, structure panel, messages, game over), `menu.py`.
- `game.py`: Game.load/save, event loop, fixed timestep (20 Hz, cap 4 ticks/frame), build mode, unit commands, autosave,
  game over -> [L] reload.

## Load-bearing decisions (do not re-litigate casually; rationale in PLAN.md)
1. Structures live in `Factory.structures[(tx,ty)]` (+ `by_chunk` index for rendering), never in terrain chunks. Terrain
   unloads freely; the factory always simulates (verified: a line 40 chunks away ran while its chunk was unloaded).
2. Fixed timestep 20 ticks/s; render 60 fps; MAX_TICKS_PER_FRAME = 4, leftover time dropped.
3. Deterministic sim: belts update downstream-first (`belts_ordered`, rebuilt only when `dirty_links`), typed lists sorted
   by (y, x), no free-running RNG anywhere (targets/waves/raids are string-seeded by ordinal). Acid test in
   tests/test_persistence.py: save@100 + load + 100 == twin@200.
4. Side rules (`sim/structures.py` docstring): item entering through a non-cargo side is FEED (invested += value, hp += value
   capped). Belt: back/sides cargo, head-on feed. Machine: left = A, right = B, back = feed, front refuses. Hub: all income.
   Tower: front = ammo (arrow points at its supply belt), others feed. Wall/Spawner: all feed. sub/div <= 0 voided.
   Miners (John, 2026-09-11) push into every adjacent cargo input, never into feed sides, no facing. Belt outputs = the front
   target plus, for a STRAIGHT (back-fed) belt only, belts beside it that point straight away and have no cargo source of
   their own; items alternate evenly over outputs (implicit splitter; `rr` cursor saved). Corners/merges never branch and
   a belt already fed by its own line is never stolen as a branch (John, round 3: parallel lines stay separate). Only
   miners may be built on number tiles. Belt sprites are shape-aware (in_sides | out_sides -> straight/corner/T/cross).
   Belt items are `[value, progress, entry_rel]`; the third field is render-only (corner animation) and the sim never
   reads it; old two-field saves load as BACK.
5. Leveling: thresholds 100*2^k; belt speed = 0.05 + invested*0.0001 tiles/tick (cap 0.5); periods /(1 + 0.25*levels);
   max_hp = BASE_HP + invested. Repair costs 0.2/hp. `[U]` upgrade = pay (next threshold - invested) balance and feed it
   (1 balance = 1 fed, the hub's own exchange rate) — idea.txt: balance is spent to create / improve / repair.
6. Ranged/heavy unit shots debit balance by the fired value; hold fire when broke; melee free; towers eat belt ammo
   (dmg = value * (1 + 0.5*(level-1)), range TOWER_RANGE = 10). Spawners never spawn on their own: a click queues one unit
   (UNIT_COSTS 50/50/150, SPAWNER_QUEUE_MAX 9), one unit walks out per period (timer keeps counting while idle, so the
   first click after a pause trains at once). Units take grid slots: `Combat.slot_near` / `gather` spiral tile centres out
   from the gather point, skipping structure tiles and other units' slots (one unit per tile, compact grid); default gather
   point = GATHER_HUB_OFFSET (3) tiles from the hub centre on the spawner's side; units walk along grid lines (row/column,
   larger axis first, re-centre only to turn) and chase enemies in a straight line. Player units are saved in meta
   `wave.units` (uid, kind, pos, hp, level, owner spawner, slot); enemies still disperse on reload.
7. Waves: first at 5 min, interval max(90 s, 240*0.97^n), budget 20*1.25^n, spawn ring = base bbox + 12 tiles (min radius
   30), direction pre-rolled (edge arrow in the last 60 s). Enemies use the hub flow field (walls 40, other structures 15)
   when inside it, greedy otherwise; whatever blocks gets attacked.
8. Nests: region grid 12 chunks, none within 1 region of origin, chance 0.3 per region ring beyond (cap 0.6), tier = ring;
   aggro when a structure is within 48 tiles -> raids every 45 s; core hp 500*tier, bounty 500*tier; destruction lives in
   NestRegistry (enemies.json), never in terrain; renderer draws rubble from the registry.
9. Saves: meta.json (identity + balance/tick/targets/camera/wave incl. player units), structures.json, enemies.json; write
   .tmp -> rotate .bak -> replace; readers fall back to .bak. Autosave 60 s + on exit; a game-over state is never saved.
10. Rendering: chunk surfaces rendered per (chunk, zoom) at the target tile size and cached on the chunk, evicted off-screen;
    CHUNK_GEN_BUDGET = 24 chunks/frame (visible first). Everything positions from `Camera.screen_origin()` (no seams).
    Walls carry `links` (bitmask of wall neighbours, rebuilt with the links) and draw connector bars + their level;
    a tower with empty ammo gets a red frame; the hub's damage bar sits under its label, one tile wide.

## Known rough edges / ideas (not blockers)
- Towers still level (not stock) when a belt enters a non-arrow side; the placement message, hover line and panel now say
  so. If John still trips on it, the next step is "ammo from any side" (drops the feed sides on towers).
- No way to cancel a queued unit (refund) yet; an accidental click on a spawner costs its unit price.
- Units are picked within 0.6 tile of the click; box select needs a 4 px drag. Selected units are not saved (selection is
  transient); their slots are.
- Four-side miners plus 2-items/tile belts changed the economy since the balance probe (income up, belt throughput 2/s at
  base speed); paid units are a new drain; re-run scratch bot_player.py or just watch John play before touching numbers.
- Sprite label sizes/positions were tuned for the procedural art; check them once John's miner/machine PNGs land.
- Balance only probed by a scripted player (STATUS v3): survivable and growing through wave 4 with 2-4 belt-fed towers next to the hub;
  a single 3-miner cannot keep a tower stocked in long fights.
- Item spacing is half a tile (2 per tile) so numbers do not overlap; belt throughput is 2 items/s at base speed.
- Custom PNG sprites: assets/sprites/<kind>.png, 32x32 per tile (hub 96x96), facing left (see README).
- Player units are not blocked by structures (by design for now); enemies only ever melee.
- Combat stats (kills) are transient; the game-over line shows kills since load.
- Phase 6 left: copy/paste blueprints, sounds, stats graphs, balance pass after a play test. Flow-field rebuild on very large bases
  (60k-tile cap) can cost ~200 ms when structures change during a wave (throttled to every 2 s).

## Next actions
1. Expect more play-test feedback from John (he reports glitches with screenshots); fix, screenshot-verify, commit.
2. When his remaining PNGs arrive: same convention (32x32, hub 96x96, facing left, white transparent); check label overlap.
3. Tick the Phase 4 design checkbox if John confirms; then remaining Phase 6 items (sounds, stats graphs, blueprints,
   balance pass) per docs/PHASES.md; keep `/phase-gate` discipline and the gotchas log.
