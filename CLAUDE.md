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
- Run: `python main.py` (menu) / `python main.py --world NAME` (skip menu) / `run.bat`
- Tests: `python -m pytest`
- Android: `python android\sync.py all` (sync copy -> build APK in the WSL box `dd-android` -> adb install + run + logs); `/android_update_copy` walks it with checks; `android/README.md` has the phone controls

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
- `main.py` — entry point: pygame init, config, menu loop; `--world NAME [--seed]` skips the menu, `--frames N` auto-quit, `--autosave S`, `--fullscreen`
- `build_pc.py` — Windows test build: PyInstaller one-folder app + `dist/DigitDefender-<ver>-win64.zip` (version from android/VERSION; assets bundled; `world/persistence.ROOT` = the exe's folder when frozen)
- `settings.py` — every tunable (grid, timestep, zoom, economy, belts, leveling, gen, combat, colors); pygame-free
- `conftest.py` — forces SDL dummy drivers so pytest runs headless
- `world/tiles.py` — tile-id registry (ground shades 0-5, DEPOSIT_1..9 = 11..19, NEST_GROUND/CORE) + predicates
- `game.py` — Game: Game.load(screen, meta)/save() (autosave every AUTOSAVE_S + on exit; Esc -> menu), event loop, fixed-timestep accumulator (tick cap 4) driving factory.tick, pan (WASD/arrows/Shift, middle-drag), wheel zoom at cursor (with units selected the wheel cycles their formation; Ctrl+wheel zooms), build mode (hotkeys/toolbar, R rotate, LMB place, belt drag = preview path built on release, X = demolish tool (click one / drag a box, removed on release), Del = demolish the selection else the hovered one, Q pick, U upgrade, H repair, RMB/Esc cancel, click select, drag-box multi-select of structures, "occupied by" / "kept its direction" messages on a click), unit commands (click/Shift/drag-box select, RMB move or spawner gather point, middle click = patrol, click a spawner = train), F3/F11, terrain streaming
- `world/chunk.py` — __slots__ Chunk: flat tile list, dirty/modified flags, opaque render cache (surface, surface_zoom); pygame-free
- `world/terrain.py` — Terrain: chunk dict owner, lazy generate, get_tile/deposit_at via divmod, update(keep, unload) hysteresis, loader/saver hooks
- `world/generator.py` — pure generate_chunk(seed,cx,cy): noise-shaded global checker, per-chunk digit blobs (forced 1/2/3 near origin, spawn clearing), nest stamping
- `sim/nests.py` — pure nest_at(seed,rx,ry) region grid + NestRegistry (destroyed/damage, to_dict/from_dict)
- `render/camera.py` — Camera: world-px centre + discrete zoom index, world<->screen<->tile transforms, cursor-anchored zoom, visible/keep/unload chunk rects
- `render/renderer.py` — chunk surfaces rendered per (chunk, zoom) and cached on the chunk, off-screen eviction, F3 overlay
- `render/numbers.py` — abbrev(n) (1.2K), LRU-cached fonts and outlined text surfaces, reset() after pygame re-init
- `sim/structures.py` — Structure base + Belt/Bridge (two-lane crossing)/Miner/MathMachine(4 ops)/Hub/Wall/Tower/Spawner (ranged/melee/heavy/repair): side rules (entry_side, FRONT/RIGHT/BACK/LEFT), feed rule, accept(), tick(), to_dict/from_dict, KINDS registry; belt items [value, progress, entry_rel]; Wall.links; Spawner queue/enqueue (paid units)/rally_point(factory)
- `sim/factory.py` — Factory: structures dict + by_chunk index, typed lists, can_place/place/remove/rotate (a bridge replaces a belt and inherits its items), layout_version, deliver+targets, damage/repair/heal/upgrade (balance -> fed), damaged_structures() (sorted), fixed tick order, rebuild_links (downstream-first belt order, merge priority, loop breaking, splitter rule, wall links), to_dict/from_dict
- `sim/leveling.py` — pure formulas: geometric uncapped level costs (threshold/level_cost/level), belt_speed, period, max_hp
- `sim/economy.py` — Target + seeded make_target, build_cost/demolish_refund
- `sim/serialize.py` — structure records <-> objects (stable (y,x) order)
- `sim/combat.py` — Combat: Unit (enemies + player units), WaveState, seeded waves (budget/ring/angle), nest aggro/raids/bounty, tower+unit attacks (ranged shots debit balance), enemy ranged fire while advancing (nearest_structure_in), beams (incl. HEAL), formations (formation_slots box/line/column/wedge/ring, gather/patrol/set_formation with per-unit anchors), patrol legs, grid walking along cached A* routes (SolidMap: walls/buildings block player units, belts/bridges do not), attack posts off solid tiles, repair-unit AI (heal nearest damaged building/unit, refill at the HQ), unit_at picking, player units in to_dict; ticks from Factory.tick
- `sim/pathing.py` — greedy_step (v1) + FlowField (Dijkstra from the hub over the base bbox, wall/structure costs, throttled rebuild) + route() (bounded A* for player units; a solid goal ends the path beside it)
- `render/combat.py` — enemies/units/beams/gather flag/selection rings + slot markers/drag box/nest hp bars, off-screen enemy + wave-direction edge arrows
- `render/structures.py` — cached sprites per (kind,dir,tile px,label,variant), wall connectors, batched blits of structures + belt items (entry-edge corner paths), ghost/side-role/selection/tower range disc/health-bar (hub bar under label) drawing
- `ui/hud.py` — balance, targets, toolbar (TOOLS/HOTKEYS), hover/selection info line, messages; panels/text follow the text size (`Hud.px`/`Hud.text`), the toolbar the button size
- `ui/prefs.py` — runtime text / button scale from config.json (menu Settings): apply(config), step(), tsize()/tpx(); pygame-free
- `ui/menu.py` — world-select menu (Continue / New World name+seed / Test lab / recent worlds / Settings / Quit; Esc resumes the last world), Settings screen (text size, button size, fullscreen, info hints, enemy waves on/paused: `settings_rows`/`adjust`), blocking loop, max_frames for smoke runs
- `world/persistence.py` — saves/<slug>/{meta,structures,enemies}.json + chunks/*.bin, atomic write_json (.tmp -> .bak rotation), read_json .bak fallback, world registry (slugify/create/list/find_or_create), config.json, save_world/load_world
- `world/testworld.py` — the "Test Lab" layout (every part and junction type around the HQ; `build(factory)`, `is_empty`, `top_up` adds legend parts an older lab save lacks), opened by `--testworld` or the menu entry
- `tests/` — test_smoke, test_generator, test_camera, test_terrain, test_game (headless pan/zoom/streaming/UI), test_belts, test_bridge, test_machines, test_economy, test_leveling, test_combat, test_persistence, test_testworld, test_android_touch (finger events through the mobile layer)
- `android/sync.py` — Windows-side Android tool: `sync` (copy game + mobile/ into android/app, bump VERSION, rewrite buildozer.spec version, draw icon/presplash), `setup` (import the Ubuntu WSL distro `dd-android` to D:\WSL + toolchain), `build`/`clean` (wsl/build.sh: rsync to ~/dd-android, buildozer, APK back to android/bin), `install`/`run`/`logs` (adb), `status`
- `android/mobile/touch.py` — TouchLayer: finger events -> the mouse/key events Game understands (tap = LMB, long press = RMB, one-finger drag = pan or LMB drag with a tool / Box armed, two-finger drag = pan, pinch = discrete zoom, two-finger tap = MMB), on-screen buttons in one row above the toolbar (ACTION_BUTTONS shown only while they apply, SYSTEM_BUTTONS at the right end; sized by the button scale), STATE read by the pygame patches (sticky Shift mods, last finger pos)
- `android/mobile/entry.py` — the APK's main: MobileGame (Game + touch layer, drops SDL's mirrored mouse events, saves on APP_WILLENTERBACKGROUND, F11 no-op) and MobileMenu (soft keyboard on New World), pygame patches (Back key -> Escape in every event loop, key.get_mods, mouse.get_pos), SCALED 720-px-high canvas, saves redirected to the app's private dir; `--desktop` emulates the phone in a window (mouse = finger)
- `android/buildozer.spec`, `android/wsl/*.sh`, `android/README.md`, `android/VERSION` — packaging config (python3, pygame, numpy, opensimplex; arm64; landscape), build-box scripts, phone controls / pipeline docs; `android/app`, `bin`, `build.log` are generated and gitignored

## Project rules
- Discover a trap → log it in @docs/GOTCHAS.md immediately (`/gotcha`).
- Phase gates: don't start the next phase until the current phase's checkpoints are verified (`/phase-gate`).
- End of session: new vN entry in @STATUS.md, refresh HANDOFF.md, commit and push (`/session-wrap`). Remote:
  https://github.com/CARTER-BNW/digit-defender (public since 2026-09-12 so testers can grab the APK; John's call).
- Releases for testers: `python android\sync.py sync build --version X.Y.Z` (APK) and `python build_pc.py` (Windows zip),
  add a section to @docs/RELEASE_NOTES.md, commit, then `gh release create vX.Y.Z android/bin/digitdefender-X.Y.Z-arm64-v8a-debug.apk
  dist/DigitDefender-X.Y.Z-win64.zip --title ... --notes-file ...`.
- Android copy: after desktop changes John wants on the phone, run `/android_update_copy` (the desktop code is the master; only `android/mobile/` is phone-specific).
- Never commit data dumps, logs, saves/, or secrets — .gitignore covers these; keep it that way.

## Pointers
- @HANDOFF.md — read first in a new session: live state + load-bearing decisions
- @docs/PLAN.md — full approved architecture (module layout, tick order, save format, pitfalls)
- @STATUS.md — reverse-chron session log
- @docs/PHASES.md — roadmap with phase exit gates
- @docs/GOTCHAS.md — known traps
- @idea.txt — John's original concept notes
