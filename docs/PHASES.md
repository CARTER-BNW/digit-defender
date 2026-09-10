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

## Phase 2 — Factory core ← CURRENT
Fixed-timestep loop; build mode (toolbar, hotkeys, R rotate, ghost w/ validity+cost tint, X demolish
w/ 50% refund); Belt (chains, merges, turns), Miner, MathMachine (4 ops), 3x3 Hub at origin; balance
HUD; 3 active target numbers with rewards. Every structure ships with to_dict/from_dict.
- [ ] 2a Miner on deposit -> digits ride belts, turns work
- [ ] 2b Two lines into adder -> sums emerge; all 4 ops verified in-game (7//2=3; results<=0 voided)
- [ ] 2c Hub delivery credits face value; target completion pays bonus and rerolls
- [ ] 2d Costs enforced; going broke is possible (log balancing note)
- [ ] 2e Line crossing chunk borders, built 40 chunks away, keeps running off-screen
- [ ] test_belts / test_machines / test_economy green
- [ ] 2000-belt synthetic world >= 60 fps

## Phase 3 — Save/load
persistence + serialize (meta.json, chunks/*.bin, structures.json, enemies.json; atomic tmp+replace),
world-select menu (create/seed/resume, recent-first), autosave 60s + on quit.
- [ ] Quit mid-flow, relaunch, resume: item progress, balance, targets, camera intact
- [ ] Determinism round-trip test green (save@100+load+100 == twin@200)
- [ ] Process kill -> last autosave loads, no corrupt files
- [ ] Two worlds don't cross-contaminate

## Phase 4 — Improvement / leveling
Feed rule live (head-on = feed / side = merge / tail = cargo; machine back = feed), leveling.py
formulas, structure info panel (level, invested, hp bar, next threshold), damage bars, repair action.
- [ ] Feed line visibly speeds a belt; side entry still merges
- [ ] Fed machine measurably faster
- [ ] Panel matches formulas; test_leveling green
- [ ] Side-rule color coding in ghost preview (input green / output red / feed yellow)
- [ ] Design calls confirmed with John: feed-side rules, void-<=0 results

## Phase 5 — Combat
5a Walls + towers (belt-fed ammo, number lasers) + debug enemy -> kill it
5b Waves: timer, budget scaling, spawn ring, greedy+bump pathing, damage, hub death = game over screen
5c Flow-field pathing (shared BFS from hub); enemies route around walls, chew through when enclosed
5d Spawners + units (ranged/melee/heavy; rally point). RANGED/HEAVY SHOTS DEBIT BALANCE by fired value;
   balance too low -> hold fire; melee free
5e Nests: region-gen visuals, aggro raids, destruction bounty, destroyed-set persists
- [ ] Survive 5 waves with walls+towers
- [ ] Lose on purpose -> game over -> reload works
- [ ] Ranged units drain balance while firing; stop at 0
- [ ] Destroy a nest; stays dead after reload
- [ ] Save mid-wave loads sanely (transient units dropped, timer intact)
- [ ] test_combat green

## Phase 6 — Polish (stretch)
Belt-item render interpolation, sounds, minimap, stats graphs, drag-place belts, copy/paste
blueprints, pause/speed controls, balance pass.
