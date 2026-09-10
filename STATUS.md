# STATUS
_Last updated: 2026-09-11 (v3) by Claude_

## v3 (2026-09-11, overnight autonomous run): Phase 0 + Phase 1 done
- John went to bed with "do all you can"; phases verified by running them (tests + scripted real window + screenshots), not by demo.
- Phase 0: requirements.txt, run.bat, settings.py (all PLAN section 4 tunables), world/tiles.py, conftest.py, main.py, tests/test_smoke.py.
- Phase 1: world/{chunk,terrain,generator}.py, sim/nests.py, render/{camera,renderer,numbers}.py, game.py; 29 tests green.
- Real-window verification (scratch verify_phase1.py): all 6 zooms screenshot; fullscreen 1920x1080 at 0.25 = 5.6 ms/frame fast pan
  (worst single frame 19 ms when a column of chunks generates), 2.6 ms static; fly 300 chunks away and back -> identical tiles.
- Gotchas logged: str-seeded RNG (hash salting), font cache after pygame re-init, Bash heredoc length.
- Tuned: NEST_CHANCE_PER_REGION 0.3 (nests findable at region distance 2-3). Deposit colors per digit; deposits draw as dots below zoom 0.5.
- Phase 2: sim/{structures,factory,leveling,economy,serialize}.py, render/structures.py, ui/hud.py, build mode in game.py
  (hotkeys 1-9/0/-, R rotate, LMB place, drag-paint belts that auto-turn, X demolish (hold to sweep), Q pick, RMB/Esc cancel, click select).
  Side rules: belt back/side = cargo, head-on = feed; machine left = A, right = B, back = feed, front refuses; hub = income; tower front = ammo.
- Phase 2 verification (scratch verify_phase2.py, real window): 3-line to hub with real costs, target 3 paid +35 and rerolled, adder/sub/mul/div
  produce 9/5/12/3 in-game, 3-5 voided, broke -> "need 500" and belt refused at balance 1, paint-place turns [E,E,E,S,S,W,W], far line in chunk 40
  ran while unloaded. 2000 belts + 4000 items fullscreen: 10.7 ms/frame at 0.25, 11.0 ms at 1.0 (uncapped), sim tick 1.2 ms.
- Perf work: batched Surface.blits + convert_alpha sprites (16.6 -> 11 ms/frame), CHUNK_GEN_BUDGET=24 chunks/frame (visible first) removes the zoom-out freeze.
- Balancing note (2d): income is face value only (~1.5/s per miner line of 3s); adders at 500 take minutes. Targets start 4-12 (TARGET_BASE 4, x1.25 per completion,
  reward value*5+20). Feels slow-but-fair on paper; needs a play test.
- **For John to eyeball:** zoom feel, checker contrast, deposit colors, belt/item sprites, HUD layout, early-game pacing.

## v2 (2026-09-11): Design complete — plan approved
- Scope confirmed with John: Beltmatic-like infinite grid factory (mine digits 1-9, math machines,
  hub deliveries + targets) crossed with base defense (towers, walls, units, nests + waves).
  Free pan/zoom camera; chunks generate only when first seen; hub destroyed = game over.
- Stack: Python 3.12 + pygame-ce + numpy + opensimplex; patterns adapted from Pixel_Worlds.
- Wrote docs/PLAN.md (full architecture), docs/PHASES.md (Phases 0-6 with exit gates),
  rewrote HANDOFF.md (new-session bootstrap with 10 load-bearing decisions).
- Design change from John mid-planning: ranged/heavy unit shots debit balance by fired value;
  melee free; towers belt-fed (no balance cost).
- **Open:** Phase 0 build (scaffold + window + pytest), then Phase 1. Empty typo folder
  `..\Digit Denfender` still locked by a session — delete when free.

## v1 (2026-09-10): Project scaffold
- Scaffolded by /create_project: CLAUDE.md, HANDOFF.md, README.md, docs/PHASES.md, docs/GOTCHAS.md
- Project skills: session-wrap, phase-gate, gotcha
- git init on `main`, initial commit
- **Open:** confirm scope (Phase 0), define Phase 1+ checkpoints
