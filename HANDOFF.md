# HANDOFF — Digit Defender
_Last updated: 2026-09-11 (v3, overnight autonomous run) by Claude_

New-session bootstrap. Read this, then docs/PLAN.md (design authority), docs/PHASES.md (checkpoints), docs/GOTCHAS.md.

## Live state
- **Phases 0-5 are built and verified by script** (tests + real-window runs + screenshots). Phase 6 (polish) is
  in progress. 91+ pytest tests green (`python -m pytest -q`, ~4 s).
- Directory: D:\Claude\projects\games\Digit Defender (local git on `main`, no remote). Saves in `saves/` (gitignored),
  machine prefs in `config.json` (gitignored).
- Run: `python main.py` (menu) or `python main.py --world NAME [--seed N]` (skip menu), `--frames N` auto-quit,
  `--autosave S`, `--fullscreen`. `run.bat` passes args through.
- **John has not played it yet.** Everything visual was checked from screenshots by Claude. Open design checkbox in
  Phase 4: John to confirm feed-side rules and voiding of <= 0 results (implemented per PLAN).

## Health check (what "working" looks like)
1. `python -m pytest -q` -> all green.
2. `python main.py --world smoke --frames 120` -> window opens on a fresh world with the hub, exits 0, `saves/smoke/` written.
3. In game: 1 = belt, 2 = miner (needs a deposit), 3-6 = machines, 7 = wall, 8 = tower, 9/0/- = spawners; R rotate,
   LMB place (drag paints belts that auto-turn), X demolish (hold to sweep), Q pick, H repair, click = select (panel on the
   right), RMB = cancel / set rally on a selected spawner, wheel zoom, MMB drag pan, WASD pan (Shift fast), F3 debug,
   Space pause, [ ] sim speed x1/x2/x4, F1 help overlay, F6 spawn an enemy at the cursor, F7 trigger the next wave,
   F11 fullscreen, Esc = cancel tool / menu. Minimap bottom-right.

## Architecture in one screen (details: CLAUDE.md architecture map, docs/PLAN.md)
- `sim/` is headless (no pygame): `factory.py` (structures dict, fixed tick order, belt chain ordering, economy, damage),
  `structures.py` (Belt/Miner/MathMachine x4/Hub/Wall/Tower/Spawner with side rules + to_dict/from_dict),
  `leveling.py`, `economy.py` (seeded targets), `serialize.py`, `combat.py` (enemies, units, waves, nests, beams),
  `pathing.py` (greedy + hub flow field), `nests.py` (pure region grid + NestRegistry).
- `world/`: `generator.py` (pure), `chunk.py`, `terrain.py` (streaming with a per-frame generation budget), `persistence.py`
  (atomic JSON + .bak, chunk .bin, world registry).
- `render/`: `camera.py` (discrete zoom, screen_origin), `renderer.py` (per-zoom cached chunk surfaces, eviction, F3),
  `structures.py` (cached sprites, batched blits, ghost/selection/health bars), `combat.py`, `numbers.py` (abbrev, fmt, text cache).
- `ui/`: `hud.py` (balance, targets, wave timer, toolbar, hover line, structure panel, messages, game over), `menu.py`.
- `game.py`: Game.load/save, event loop, fixed timestep (20 Hz, cap 4 ticks/frame), build mode, autosave, game over -> [L] reload.

## Load-bearing decisions (do not re-litigate casually; rationale in PLAN.md)
1. Structures live in `Factory.structures[(tx,ty)]` (+ `by_chunk` index for rendering), never in terrain chunks. Terrain
   unloads freely; the factory always simulates (verified: a line 40 chunks away ran while its chunk was unloaded).
2. Fixed timestep 20 ticks/s; render 60 fps; MAX_TICKS_PER_FRAME = 4, leftover time dropped.
3. Deterministic sim: belts update downstream-first (`belts_ordered`, rebuilt only when `dirty_links`), typed lists sorted
   by (y, x), no free-running RNG anywhere (targets/waves/raids are string-seeded by ordinal). Acid test in
   tests/test_persistence.py: save@100 + load + 100 == twin@200.
4. Side rules (`sim/structures.py` docstring): item entering through a non-cargo side is FEED (invested += value, hp += value
   capped). Belt: back/sides cargo, head-on feed. Machine: left = A, right = B, back = feed, front refuses. Hub: all income.
   Tower: front = ammo (arrow points at its supply belt), others feed. Miner/Wall/Spawner: all feed. sub/div <= 0 voided.
5. Leveling: thresholds 100*2^k; belt speed = 0.05 + invested*0.0001 tiles/tick (cap 0.5); periods /(1 + 0.25*levels);
   max_hp = BASE_HP + invested. Repair costs 0.2/hp.
6. Ranged/heavy unit shots debit balance by the fired value; hold fire when broke; melee free; towers eat belt ammo
   (dmg = value * (1 + 0.5*(level-1))). Spawners cap 3 + level units, rally point via RMB.
7. Waves: first at 5 min, interval max(90 s, 240*0.97^n), budget 20*1.25^n, spawn ring = base bbox + 12 tiles (min radius
   30), direction pre-rolled (edge arrow in the last 30 s). Enemies use the hub flow field (walls 40, other structures 15)
   when inside it, greedy otherwise; whatever blocks gets attacked.
8. Nests: region grid 12 chunks, none within 1 region of origin, chance 0.3 per region ring beyond (cap 0.6), tier = ring;
   aggro when a structure is within 48 tiles -> raids every 45 s; core hp 500*tier, bounty 500*tier; destruction lives in
   NestRegistry (enemies.json), never in terrain; renderer draws rubble from the registry.
9. Saves: meta.json (identity + balance/tick/targets/camera/wave), structures.json, enemies.json; write .tmp -> rotate .bak ->
   replace; readers fall back to .bak. Autosave 60 s + on exit; a game-over state is never saved.
10. Rendering: chunk surfaces rendered per (chunk, zoom) at the target tile size and cached on the chunk, evicted off-screen;
    CHUNK_GEN_BUDGET = 24 chunks/frame (visible first). Everything positions from `Camera.screen_origin()` (no seams).

## Known rough edges / ideas (not blockers)
- Balance only probed by a scripted player (STATUS v3): survivable and growing through wave 4 with 2-4 belt-fed towers next to the hub;
  a single 3-miner cannot keep a tower stocked in long fights; towers far from the hub (range 6) never engage.
- Item spacing is half a tile (2 per tile) so numbers do not overlap; belt throughput is 2 items/s at base speed.
- Custom PNG sprites: assets/sprites/<kind>.png, 32x32 per tile (hub 96x96), facing up (see README).
- Player units are not blocked by structures (by design for now); enemies only ever melee.
- Combat stats (kills) are transient; the game-over line shows kills since load.
- Phase 6 left: copy/paste blueprints, sounds, stats graphs, balance pass after a play test. Flow-field rebuild on very large bases
  (60k-tile cap) can cost ~200 ms when structures change during a wave (throttled to every 2 s).

## Next actions
1. John plays a fresh world for 10 minutes and notes feel/balance issues; confirm the Phase 4 design checkbox.
2. Continue Phase 6 polish per docs/PHASES.md; keep `/phase-gate` discipline and the gotchas log.
