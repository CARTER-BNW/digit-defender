# PHASES — Digit Defender

Rule: a phase is done only when every checkpoint is checked **and verified by actually running the thing**. Don't start the next phase before that (`/phase-gate`). Details in docs/PLAN.md §6.

## Phase 0 — Scaffold (done 2026-09-11)
requirements.txt (pygame-ce, numpy, opensimplex, pytest), run.bat, settings.py, empty packages,
conftest.py (SDL dummy driver), CLAUDE.md commands updated.
- [x] Folder scaffold: docs, skills, git
- [x] Scope confirmed with John (docs/PLAN.md, idea.txt)
- [x] Stack decided: Python 3.12 + pygame-ce + numpy + opensimplex
- [x] python main.py opens a window and quits cleanly
- [x] pytest passes (placeholder test)

## Phase 1 — Walkable skeleton (done 2026-09-11)
Terrain/Chunk/Generator (dark-green checker + shade noise, deposits 1-9 as digits, spawn clearing),
Camera pan (WASD + middle-drag) and cursor-anchored discrete zoom, per-zoom cached chunk blits,
keep/unload hysteresis, F3 debug overlay.
- [x] Pan forever; chunks appear only when first seen (real-window pan: loaded stays ~270 chunks while 1600+ generated)
- [x] All 6 zoom levels, cursor-anchored, no seams (screenshots at every level; anchor + whole-pixel tests) — John: confirm the feel
- [x] Fly away and return -> identical terrain
- [x] 60 fps fullscreen at zoom 0.25 (1920x1080: 5.6 ms/frame fast pan, 2.6 ms static; worst single frame 19 ms)
- [x] test_generator green (determinism, negative coords, near-spawn deposit guarantee, safe zone)

## Phase 2 — Factory core (done 2026-09-11)
Fixed-timestep loop; build mode (toolbar, hotkeys, R rotate, ghost w/ validity+cost tint, X demolish
w/ 50% refund); Belt (chains, merges, turns), Miner, MathMachine (4 ops), 3x3 Hub at origin; balance
HUD; 3 active target numbers with rewards. Every structure ships with to_dict/from_dict.
- [x] 2a Miner on deposit -> digits ride belts, turns work
- [x] 2b Two lines into adder -> sums emerge; all 4 ops verified in-game (7//2=3; results<=0 voided)
- [x] 2c Hub delivery credits face value; target completion pays bonus and rerolls
- [x] 2d Costs enforced; going broke is possible (balancing note in STATUS v3: adders at 500 vs ~1.5/s income per miner line feels slow; targets start 4-12)
- [x] 2e Line crossing chunk borders, built 40 chunks away, keeps running off-screen (chunk 40 unloaded while its belts carried items)
- [x] test_belts / test_machines / test_economy green (66 tests total)
- [x] 2000-belt synthetic world >= 60 fps (1920x1080 fullscreen, all 2000 belts + 4000 items visible: 10.7 ms/frame at 0.25, 11.0 ms at 1.0; sim tick 1.2 ms)

## Phase 3 — Save/load (done 2026-09-11)
persistence + serialize (meta.json, chunks/*.bin, structures.json, enemies.json; atomic tmp+replace),
world-select menu (create/seed/resume, recent-first), autosave 60s + on quit.
- [x] Quit mid-flow, relaunch, resume: item progress, balance, targets, camera intact (in-process reload identical; real relaunch via main.py --world advanced 124 -> 164 ticks)
- [x] Determinism round-trip test green (save@100+load+100 == twin@200)
- [x] Process kill -> last autosave loads, no corrupt files (taskkill /F at 7.5 s with --autosave 2: loaded tick 119, no .tmp leftovers)
- [x] Two worlds don't cross-contaminate

## Phase 4 — Improvement / leveling (built 2026-09-11; one design checkbox left for John)
Feed rule live (head-on = feed / side = merge / tail = cargo; machine back = feed), leveling.py
formulas, structure info panel (level, invested, hp bar, next threshold), damage bars, repair action.
- [x] Feed line visibly speeds a belt; side entry still merges (head-on 9s: belt fed 765 -> Lv4, 1.0 -> 2.57 tiles/s; side 2s merge)
- [x] Fed machine measurably faster (back-fed 400: period 40 -> 23 ticks, 8 -> 17 outputs per 400 ticks)
- [x] Panel matches formulas; test_leveling green (9 tests)
- [x] Side-rule color coding in ghost preview (input green / output red / feed yellow) — also on the selected structure
- [ ] Design calls confirmed with John: feed-side rules, void-<=0 results (implemented per PLAN; John to confirm or change)

## Phase 5 — Combat (built 2026-09-11, verified by script; John to play-test)
5a Walls + towers (belt-fed ammo, number lasers) + debug enemy -> kill it
5b Waves: timer, budget scaling, spawn ring, greedy+bump pathing, damage, hub death = game over screen
5c Flow-field pathing (shared BFS from hub); enemies route around walls, chew through when enclosed
5d Spawners + units (ranged/melee/heavy; rally point). RANGED/HEAVY SHOTS DEBIT BALANCE by fired value;
   balance too low -> hold fire; melee free
5e Nests: region-gen visuals, aggro raids, destruction bounty, destroyed-set persists
- [x] Survive 5 waves with walls+towers (scripted: wall ring + 4 belt-fed towers, 28 kills, hub untouched, 1 wall lost)
- [x] Lose on purpose -> game over -> reload works (overlay, [L] reloads the last save; dead state never saved)
- [x] Ranged units drain balance while firing; stop at 0
- [x] Destroy a nest; stays dead after reload (bounty paid, rubble rendered, no more raids)
- [x] Save mid-wave loads sanely (transient units dropped, timer intact)
- [x] test_combat green (12 tests; 91 total)

## Phase 6 — Polish (stretch) ← CURRENT
Belt-item render interpolation, sounds, minimap, stats graphs, drag-place belts, copy/paste
blueprints, pause/speed controls, balance pass.
- [x] Belt-item render interpolation (items advance by speed * accumulator fraction; render-only)
- [x] Drag-place belts (paint with LMB held; belts auto-turn along the drag)
- [x] Pause (Space) and sim speed x1/x2/x4 ([ ])
- [x] Minimap (bottom-right, 96 tiles across, structures/enemies/units/nests/camera rect)
- [x] F1 help overlay
- [ ] Sounds
- [ ] Stats graphs
- [ ] Copy/paste blueprints
- [ ] Balance pass (after John's play test)
- [x] Android copy (John, 2026-09-11): `android/` = the desktop game + a touch layer, packaged by
      python-for-android in the WSL box `dd-android`, refreshed with `/android_update_copy`
      (`python android\sync.py all`). 2026-09-12: APK 0.1.0 installed on his Pixel 9a and driven by adb
      (menu, Test Lab running, Pause by touch, swipe pan, Back -> menu, save in the private dir); John to play-test
