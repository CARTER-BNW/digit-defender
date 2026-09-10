# Digit Defender

## Purpose
Infinite borderless grid factory game (Beltmatic-like: mine digits 1-9, math machines, hub
deliveries + target numbers) crossed with base defense (towers, walls, units, enemy nests +
escalating waves). Chunks generate only when first seen. Hub destroyed = game over.
Design is finalized and approved — @docs/PLAN.md is the authority.

## On "start" / "continue" / "go"
1. Read HANDOFF.md, docs/PLAN.md, docs/PHASES.md — in that order.
2. Resume at the first unchecked checkpoint in docs/PHASES.md (the phase marked ← CURRENT).
3. Tick checkboxes and refresh HANDOFF.md as work completes.
4. Stop and demo at each phase boundary before starting the next phase (`/phase-gate`).

## Stack & tooling
- Python 3.12 (Windows / PowerShell), pygame-ce, numpy, opensimplex, pytest
- Reference codebase to ADAPT patterns from (not copy): `D:\Claude\projects\games\Pixel_Worlds`

## Commands
- Deps: `pip install -r requirements.txt`
- Run: `python main.py` (or `run.bat`, once it exists)
- Tests: `python -m pytest`

## Ground rules (non-negotiable — rationale in @docs/PLAN.md)
- `sim/` NEVER imports pygame. All factory/combat logic must be testable headless with pytest.
- Structures live in the world-level dict `Factory.structures[(tx,ty)]`, NEVER inside terrain chunks.
- Always `divmod(t, CHUNK_SIZE)` for tile→chunk coords (negative coords are everywhere).
- Every Structure gets `to_dict()/from_dict()` the moment it is first written.
- Belts update in downstream-first chain order — never dict iteration order (sim determinism).
- Never `font.render` or `transform.scale` chunk surfaces per frame — cache everything.
- Gameplay never writes terrain; nest destruction goes through the registry.

## Architecture map
Add one line per file as files are created, stating what that file owns (layout: @docs/PLAN.md §1).
- `main.py` — entry point: pygame init, window, `--seed/--frames/--fullscreen` flags, launches the loop
- `settings.py` — every tunable (grid, timestep, zoom, economy, belts, leveling, gen, combat, colors); pygame-free
- `conftest.py` — forces SDL dummy drivers so pytest runs headless
- `world/tiles.py` — tile-id registry (ground shades 0-5, DEPOSIT_1..9 = 11..19, NEST_GROUND/CORE) + predicates
- `game.py` — Game: event loop, fixed-timestep accumulator (tick cap 4), pan (WASD/arrows/Shift, middle-drag), wheel zoom at cursor, F3/F11, terrain streaming
- `world/chunk.py` — __slots__ Chunk: flat tile list, dirty/modified flags, opaque render cache (surface, surface_zoom); pygame-free
- `world/terrain.py` — Terrain: chunk dict owner, lazy generate, get_tile/deposit_at via divmod, update(keep, unload) hysteresis, loader/saver hooks
- `world/generator.py` — pure generate_chunk(seed,cx,cy): noise-shaded global checker, per-chunk digit blobs (forced 1/2/3 near origin, spawn clearing), nest stamping
- `sim/nests.py` — pure nest_at(seed,rx,ry) region grid + NestRegistry (destroyed/damage, to_dict/from_dict)
- `render/camera.py` — Camera: world-px centre + discrete zoom index, world<->screen<->tile transforms, cursor-anchored zoom, visible/keep/unload chunk rects
- `render/renderer.py` — chunk surfaces rendered per (chunk, zoom) and cached on the chunk, off-screen eviction, F3 overlay
- `render/numbers.py` — abbrev(n) (1.2K), LRU-cached fonts and outlined text surfaces, reset() after pygame re-init
- `tests/` — test_smoke, test_generator, test_camera, test_terrain, test_game (headless pan/zoom/streaming)

## Project rules
- Discover a trap → log it in @docs/GOTCHAS.md immediately (`/gotcha`).
- Phase gates: don't start the next phase until the current phase's checkpoints are verified (`/phase-gate`).
- End of session: new vN entry in @STATUS.md, refresh HANDOFF.md, commit (`/session-wrap`). Local git only — no push.
- Never commit data dumps, logs, saves/, or secrets — .gitignore covers these; keep it that way.

## Pointers
- @HANDOFF.md — read first in a new session: live state + load-bearing decisions
- @docs/PLAN.md — full approved architecture (module layout, tick order, save format, pitfalls)
- @STATUS.md — reverse-chron session log
- @docs/PHASES.md — roadmap with phase exit gates
- @docs/GOTCHAS.md — known traps
- @idea.txt — John's original concept notes
