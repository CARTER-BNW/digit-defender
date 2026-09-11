# STATUS
_Last updated: 2026-09-11 (v6) by Claude_

## v6 (2026-09-11, evening): John's fourth round - demolish tool, group select, belt preview
- X is a toggle tool ("Demolish", last toolbar button, 50% refund): click removes one structure, click-and-drag sweeps;
  a fast drag walks every tile between mouse samples (`Game._tiles_between`, also used for wall/tower drag-placing, so
  no more gaps). Red frame + refund over the hovered target. Del stays a one-shot. Holding X no longer sweeps.
- Drag a box (no tool) over buildings: every structure inside joins `selected_structures` (Shift adds); U upgrades them
  all in (y, x) order (skips the unaffordable, message says how many), H repairs them all; group panel with counts per
  kind, level range, total upgrade/repair cost; thin yellow frames. A box around exactly one structure selects it for
  the normal panel. Units and structures in the same box both get selected. Destroyed members drop out each frame.
- Belt drag = preview: LMB down starts `belt_path`, dragging extends it (auto-turn, gap-filling, drag back to undo),
  drawn as transparent shape-aware belt sprites tinted green (will build / turn an existing belt) or red (blocked),
  with "N belts = cost" at the end; release builds it (`_commit_belt_path`: place new, turn existing belts on the path,
  skip the rest; first blocking reason shown). A plain click still places one belt. Esc/tool change discards the path.
- Tests 107 -> 110 (demolish tool click+drag+toggle, belt preview/undo/turn-existing, group select/upgrade/repair/prune).
- Round 5 (same evening): (1) leveling is geometric and uncapped - level n -> n+1 costs 100 * 1.25^(n-1)
  (100, 125, 156, 196, 244...), `leveling.threshold/level_cost/thresholds_passed` (closed form + drift fix), settings
  LEVEL_BASE_COST / LEVEL_COST_GROWTH replace the 100*2^k table; (2) deposits spread out: at most one blob per chunk
  (DEPOSIT_BLOB_CHANCE 0.45) and the digit is drawn with weights decay**(digit-1), decay 0.45 near the origin -> 0.8
  far out, so 1 is always the most common and 9 the rarest (DEPOSIT_DECAY_*; the old 0-2 blobs + 6-9 ramp is gone);
  (3) every enemy shoots AND melees: ENEMY_STATS shot_dmg/shot_range (grunt 1/4, brute 3/3, runner 1/5), fired while
  advancing at the nearest unit else the nearest structure (`Combat.nearest_structure_in`, bounded scan), free, same
  cooldown as melee; beams drawn in enemy orange with the number. Tests 110 -> 113.
- Round 6 (same evening): (1) hp only moves on a level-up: max_hp = BASE_HP + threshold(level-1) (stepwise), `feed()`
  adds exactly the max_hp gain when a level steps and never heals otherwise (repair does); the [U] price is the FIXED
  level price `leveling.level_cost(level)` (100, 125, 156...) so it no longer drifts while numbers trickle in; the
  payment is fed in full and any excess carries over. (2) Units chase enemies/nests along the grid (`_walk_grid`) like
  they walk to rally. (3) Hub under attack: `Factory.hub_hit_tick` + `hub_under_attack()` (3 s) -> pulsing red double
  frame around the hub, red screen frame + "HUB UNDER ATTACK". (4) John: dragging from a belt only opened its panel ->
  clicks are decided on release: a tiny box selects the structure under it (spawner trains; Shift adds it to the group),
  a real drag boxes an area even when it starts on a building. Tests 113 -> 117.
- Round 7 (same evening): (1) belt drag with Shift = one straight run from the anchor along the axis of the first move
  plus one square corner (`Game._straight_belt_path`, axis locked per drag); R during a drag = `belt_turn`, a quarter
  turn applied to every belt on release (twice = the whole line runs backwards), shown in the preview. (2) Menu: Del on
  a world entry -> confirm screen -> `persistence.delete_world` removes the folder (last_world forgotten). (3) T-junction
  fix: a belt already on a drag path is turned only at a line's end (nothing in front) or to reverse it; a belt in the
  middle of a line keeps flowing, so dragging off it leaves a branch beside the line = T. (4) Machines take operands
  from all three non-output sides: back tops up the emptier buffer (A on a tie), so a single line from behind pairs its
  own numbers; machines have no feed side and level via [U]. Tests 117 -> 122.
- Round 8 (same evening): targets redesigned - 4 slots with levels. Level 1: distinct numbers 5..9, amount 5; a
  delivery of the number counts toward the amount; done -> bonus value*amount*1.5+20 and the slot's next level grows
  number and amount each by a seeded random 25-75% (`sim/economy.py`: initial_targets / next_level / top_up; Target has
  slot/level/value/amount/delivered/reward). Panel shows "amount x number  delivered/amount  Lv  +bonus". Old saves
  ({value,reward}, 3 slots) still load. Tests 122 -> 123.
- Round 9 (same evening): RMB with a boxed group of spawners sets one gather point for all of them (their units regroup
  there); a gather flag is drawn for every selected spawner; group panel / hover line say so. Tests 123 -> 124.
- Round 10 (same evening): (1) a guaranteed enemy camp: `nests.home_nest(seed)` puts a tier-1 nest NEST_HOME_DISTANCE
  (100) tiles from the origin in a seeded direction (footprint kept inside one chunk); `nest_at` returns it for its
  region even inside the safe zone; combat always lists it in known_nests (minimap, new dark-red off-screen edge
  arrows toward known camps), aggro/raids unchanged (needs a structure within 48 tiles). (2) "hub" -> "HQ" in every
  player-facing string (sprite label, button, alerts, game over, help, menu tagline, panel names via DISPLAY_NAMES);
  code/saves keep `hub`. Tests 124 -> 126.
- Round 11 (same evening): HUD layout per John - right column (balance centred, targets, HQ button, hints panel with
  word-wrapped lines and a menu toggle "Info hints" saved in config), structure/group info panel top left, minimap
  2x (440x300, 128 tiles across, click to recentre), toolbar centred left of the minimap, off-screen arrows drawn by
  the HUD on top of panels (the camp arrow was hidden under the old minimap), `over_ui` covers every panel. Tower ammo
  buffer 20 + 10 per level (`Tower.ammo_max`), panel shows ammo n/max. Tests adjusted for the new UI rects.


## v5 (2026-09-11, afternoon): John's third round of play-test feedback, all implemented
- Towers: TOWER_RANGE 6 -> 10; translucent range disc on hover/select and on the build ghost; red frame + "0" label when
  the ammo buffer is empty; placement message / hover line / panel explain "belt numbers into the green arrow side".
- Spawners: no auto-spawn. Clicking a spawner (which also selects it) queues one unit and pays UNIT_COSTS (50/50/150,
  idea.txt); one queued unit per period (200 ticks at Lv1, faster with level); queue count replaces the M/H/R letter;
  SPAWNER_QUEUE_MAX 9; `queue` saved.
- Units: grid formations - `spiral_slots` / `Combat.slot_near` / `Combat.gather` hand out tile-centre slots spiralling
  out from the gather point, skipping structure tiles and other units' slots; default gather point 3 tiles from the hub
  centre on the spawner's side; units walk along grid lines (larger axis first, re-centre only to turn, exact arrival);
  click / Shift+click / drag box selects units (yellow rings, slot markers), RMB moves them, RMB on a selected spawner
  moves its gather point (and its idle units). Player units are now saved (meta wave.units) since they cost balance.
- Belt corners: items are `[value, progress, entry_rel]`; the renderer draws the first half of a belt from the entry
  edge to the centre, so a side entry curves through the corner instead of jumping from one edge to another. Old
  two-field saves load as BACK. Tests index items instead of unpacking pairs (docs/GOTCHAS.md).
- Walls: `Wall.links` bitmask rebuilt with the links; sprite = block + connector bars to each wall neighbour (wall.png,
  if it arrives, is drawn on top) + the level number in the middle (no corner badge for walls).
- Upgrades: `[U]` (Factory.upgrade) pays balance = next threshold - invested and feeds it (1:1, heals too); panel and
  help explain both paths (feed a yellow side, or pay). Answer to "how do I upgrade belts/spawners/walls".
- Hub hp bar: one tile wide, just under the HUB label (1x1 structures keep the bar above them).
- Menu: Esc resumes the last world instead of quitting (footer says so); with no world Esc is ignored.
- Splitter rule tightened: only a straight (back-fed) belt branches, and only into a side belt with no cargo source of
  its own - a corner in one of two parallel lines no longer T-joins them, and a turned belt does not split into its old
  tail.
- Verification: 106 tests (9 new/rewritten); scratch verify_feedback2.py real-window screenshots (range disc, red
  no-ammo frame, wall connectors with levels 1/2/3, unit grids beside the hub, hub bar, spawner queue "4", corner
  item motion) and a save/load round trip that kept a trained heavy unit, its owner link and the queue.
- Follow-up (John): towers take ammo from EVERY side - no facing, no feed sides, no intake arrow; a full buffer refuses
  so the supply belt stalls; towers level only via [U]. PLAN 3.5 / HANDOFF decision 4 updated.
- **Open:** no dequeue/refund; balance re-probe with paid units; Phase 4 design checkbox; Phase 6 leftovers (sounds,
  stats, blueprints).

## v4 (2026-09-11, morning): John's first play-test feedback, two rounds, all implemented
- Round 1 (commit 0b652c5): belts drawn as strips with a much smaller, darker arrow; belt numbers plain (no circle) and
  ink-centred (render/numbers.glyph); numbers on miners/machines/deposits centred too; ITEM_SPACING 0.25 -> 0.5 so numbers
  never overlap (item font 0.44 tile); stalled/T-junction jitter fixed (render interpolation obeys the spacing rule);
  miners push their digit into every adjacent cargo input (never feed sides, so miners cannot level each other), no arrow,
  white border pulse on each extraction (MINER_PULSE_TICKS); HUB button + Home key; PNG sprite overrides in assets/sprites.
- Round 2 (2df4160, 1e1c19b, ea04ecd, 27937ef): sprites are drawn facing LEFT (John's convention), pure white and magenta
  are transparent; connection-aware belt shapes (straight/corner/T/cross, rotated to match openings) using John's four
  belt PNGs; links (belt shapes, miner outputs) rebuild immediately even while paused; no facing/rotate for miners+walls;
  implicit splitters: belt outputs = front target + belts beside it pointing straight away, items alternate evenly
  (round-robin cursor saved), Kahn downstream-first ordering; only miners may be placed on number tiles.
- Tests 92 -> 97 (four-side miners, connection sides, splitter split/shape/order, deposit rule, build-while-paused).
- **Open:** John keeps play-testing and drawing sprites; Phase 4 design checkbox; Phase 6 leftovers (sounds, stats,
  blueprints, balance pass). Economy shifted (4-side miners, 2 items/tile) - re-probe before tuning.

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
- Phase 3: world/persistence.py (atomic .tmp -> .bak -> replace, .bak fallback on corrupt/missing, chunk .bin, world registry, config.json),
  ui/menu.py (Continue / New World / recent list / Fullscreen / Quit), main.py menu loop + --world/--autosave flags, Game.load/save,
  autosave 60 s + on exit, Esc returns to the menu. 73 tests green incl. determinism round-trip and corrupt-file fallback.
- Phase 3 verification (scratch verify_phase3.py): in-process reload identical + camera restored; real relaunch (subprocess main.py --world)
  advanced ticks 124 -> 164; taskkill /F mid-run with 2 s autosave -> loads at tick 119, no .tmp leftovers; two worlds isolated.
- Phase 4: selected-structure panel (level, fed, next threshold, hp bar, speed/period, buffers, side roles, [H] repair), level badge on
  sprites, health bars for damaged structures (Factory.damaged), Factory.damage/repair. 77 tests green.
- Phase 4 verification (scratch verify_phase4.py): head-on feed -> belt Lv4 at 2.57 tiles/s; back-fed adder 40 -> 23 ticks/op; repair 120 hp = 24.
- Housekeeping: config.json (machine prefs) untracked + gitignored.
- Phase 5: sim/combat.py + sim/pathing.py (enemies grunt/brute/runner, waves seeded per number with budget 20*1.25^n and a spawn ring,
  greedy v1 + hub flow field v2, towers fire belt ammo at dmg value*(1+0.5*(lvl-1)), spawners cap 3+lvl units with rally points
  (RMB on a selected spawner), ranged/heavy shots debit balance, nests aggro within 48 tiles -> raids every 45 s, core kill pays 500*tier
  and renders rubble), render/combat.py, HUD wave countdown + game-over overlay ([L] reload / [Esc] menu), F6 spawn enemy / F7 wave now (debug).
- Phase 5 verification (scratch verify_phase5.py): all six checkpoints pass by script (see PHASES.md). 91 tests green.
- Phase 6 (partial): belt item render interpolation, Space pause + [ ] speed x1/x2/x4, F1 help overlay, minimap; HANDOFF.md rewritten
  for a cold start; README status; memory notes saved (overnight-run preference, Bash heredoc limit, project state).
- Crash insurance: an unhandled exception in Game.run() saves progress (unless game over), appends the traceback to crash.log, then re-raises.
  Wave direction arrow now shows 60 s ahead (WAVE_WARNING_S). 92 tests green; run.bat launch verified.
- Balance probe (scratch bot_player.py, real costs, seed 1337): 3 lines at t=0 give ~2.4/s; 6 lines by 1 min ~5/s; an adder (500) is
  affordable at ~3.3 min; two hub-adjacent towers fed with 3s (56 + 76 each incl. lines) clear wave 1 untouched, waves 2-4 with minor hub
  damage (952/980/774 hp) while adding a tower per wave; balance climbs to 7.4K by wave 5. Observation: one 3-miner (0.5 items/s) cannot keep
  a tower (1 shot/s) stocked through a long fight (one tower hit 0 ammo in wave 4) -> either accept (feed towers from richer lines) or slow
  TOWER_BASE_PERIOD to 30. Towers placed 8+ tiles from the hub never engage hub attackers (range 6): place them next to the hub.
- **For John to decide:** feed-side rules (belt head-on = feed, machine back = feed, tower front = ammo) and voiding of <= 0 results — implemented per PLAN,
  the Phase 4 checkbox stays open until you confirm.
- **For John to eyeball:** zoom feel, checker contrast, deposit colors, belt/item sprites, HUD layout, menu, early-game pacing.

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
