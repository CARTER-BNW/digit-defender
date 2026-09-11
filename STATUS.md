# STATUS
_Last updated: 2026-09-12 (v10) by Claude_

## v10 (2026-09-12): John's phone round 1 - Settings screen, contextual buttons above the toolbar (tests 156 -> 167)
John: "few things on the phone. add setting options in menu that has ui text size, and move the full screen and
info text there too. instead of being on the left, can the buttons be above the hot bar. I don't need HQ (already
got home), esc, pick, del. buttons only show when needed (spawner selected -> train, units selected -> form).
make the button and text adjustable in menu. no zoom buttons, I can pinch. in menu option to pause waves."
- `ui/prefs.py` (new, pygame-free): `text_scale` / `button_scale` read from config.json (`apply`), step tables
  TEXT_SCALES 0.8-1.8 and BUTTON_SCALES 0.8-2.0, `tsize` / `tpx` helpers. `persistence.DEFAULT_CONFIG` gained
  hints / text_scale / button_scale / waves_paused. main.py and the Android entry call `prefs.apply(config)` at
  startup and `Game.apply_config(config)` (hints panel + wave pause) after every load.
- `ui/menu.py`: main list is Continue / New World / Test lab / worlds / **Settings** / Quit; the Settings screen
  (`settings_rows` / `adjust` / `_settings`) cycles Text size, Button size, Fullscreen (desktop only:
  `fullscreen_toggle`, MobileMenu sets False), Info hints, Enemy waves On / Paused, Back; Enter / tap / Right = next
  value, Left = previous, Esc back; every change saves config.json and applies at once. Menu rows draw at the text
  size and shrink to fit above the footer (a 6-world list at 150% still fits 720 px).
- `ui/hud.py`: `Hud.px` / `Hud.text` scale the right column (width 340 x scale), targets rows, HQ button, hints
  (clamped to the room above the minimap; no room = no panel), structure / group panels, wave timer, messages,
  hub alert, help (steps down until it fits) and the game-over screen with the text size; the toolbar buttons
  follow the button size (BTN 60 x scale, still shrunk to fit 14 left of the minimap: 78 px at 1616 wide, 54 at
  1280) and their key / name / cost text scales with the button. The wave timer is drawn after the structure
  panel and steps right of it, or under it, when big text makes the panel reach the screen centre; messages start
  under the timer.
- `sim/combat.py`: `Combat.waves_paused` - while set and the wave is not due, `next_at_tick` advances one per
  tick (countdown frozen); `[F7]` (next_at_tick <= now) still spawns; camp raids unaffected. HUD line says
  "(waves paused)"; the urgent red never shows while paused.
- `android/mobile/touch.py`: ACTION_BUTTONS (Rot, Shift, Box, Upg, Fix, Split, Train, Form) each with a `when`
  predicate, SYSTEM_BUTTONS (Pause, Speed, Help, Save, Menu, Load on game over); `layout()` puts them in one row
  just above `hud.toolbar_rect` (actions from the left, system from the right, system one row up when both do
  not fit), sized 64 x `prefs.button_scale`, labels scaled; Esc / Del / Pick / HQ / Zoom -/+ removed; no buttons
  but the system ones after a game over; the build tag sits over the row's right end. README controls updated.
- Tests: `tests/test_settings.py` (8: prefs apply / step / clamp, settings rows adjust + save, settings screen keys,
  main menu lists Settings not the toggles, phone menu has no fullscreen row, HUD sizes at 150% + a full draw at
  180% with every panel on, apply_config, waves paused freeze + F7); `tests/test_android_touch.py` rewritten for
  the row (which buttons show when, above the toolbar / no overlaps, 150% = 96 px buttons + toolbar 78, 200% =
  two rows). 167 green.
- Verification: scratch verify_phone_ui.py (dummy driver, 1616x720, Test Lab): idle = Box + system; belt tool =
  Rot Shift; spawner selected = Rot Shift Box Upg Fix Train; belt = ... Split; units = Shift Box Form; 150% text +
  150% buttons with hints on (wave timer moved under the wide panel, hints clipped to 2 lines above the minimap);
  180% / 200% (two button rows); game over (system + Load only); Settings screen at 100% / 150%; main menu at 150%
  with 6 worlds. APK 0.1.1 built in 1.3 min (`python android\sync.py sync build`, 25.0 MB) and installed on the
  Pixel 9a with `install run logs` (see the commit message for the log result).
- **Open:** John to re-test on the phone; at the extreme Settings (180% + 200%) the timer / messages sit under
  the button rows; "waves paused" leaves camp raids alone (ask if he wants both); economy / Phase 4 checkbox /
  Phase 6 leftovers as before.

## v9 (2026-09-12): Android copy - the game runs on John's Pixel 9a (tests 144 -> 156)
John: "i want a copy of this game so i can play on android ... make a new command /android_update_copy".
Everything on D: and no Docker (his call when Docker Desktop came up as a build-box candidate).
- `android/` holds the phone build: `mobile/touch.py` (TouchLayer: tap = LMB, long press = RMB, one-finger
  drag = pan, or the LMB drag with a build tool / [Box] armed, two-finger drag = pan, pinch = discrete zoom at
  the pinch, two-finger tap = MMB patrol; on-screen hotkey buttons left (Rot Esc Del Pick Upg Fix Split Train
  Shift Box HQ Form) and right (Zoom -/+ Pause Speed Help Save Menu, Load on game over), version tag),
  `mobile/entry.py` (the APK's main: MobileGame subclasses Game through handle_event/update/draw, drops SDL's
  mirrored mouse events, saves on APP_WILLENTERBACKGROUND, F11 no-op; MobileMenu opens the soft keyboard on
  New World; pygame patches: Back -> Escape in every event loop, sticky Shift in key.get_mods, mouse.get_pos =
  last finger; SCALED canvas 720 px high, Pixel 9a 2424x1080 -> 1616x720 at 1.5x; saves + config in the app's
  private dir `files/digit_defender/`, which survives updates; hints off by default), `sync.py`
  (sync/setup/build/clean/install/run/logs/status/all), `wsl/setup.sh` + `wsl/build.sh`, `buildozer.spec`,
  `p4a-recipes/pygame` (pygame-ce 2.5.8 local recipe), `manifest_application_args.xml`, `VERSION`,
  `icon.png`/`presplash.png` (drawn by sync), README with the controls. Generated and gitignored: `android/app/`
  (the synced copy + a main.py stub), `bin/*.apk`, `build.log`.
- Build box: Ubuntu 24.04 WSL distro `dd-android` imported to `D:\WSL\dd-android` (root; buildozer 1.6.0,
  Cython 3.3, libltdl-dev). python-for-android master (May 2026): CPython 3.14.2, SDL 2.30.11, numpy from git,
  NDK r28c, targetSdk 36, arm64-v8a. First build: SDK/NDK download + ~12 min compiling; rebuilds 0.5-4 min.
- Traps hit, all in docs/GOTCHAS.md: `wsl -- bash -c script args` drops the args (env assignments instead);
  libffi's autoreconf needs libltdl-dev; p4a's pygame 2.1.0 recipe cannot build on Python 3.14 -> local
  pygame-ce recipe with `hostpython_prerequisites` Cython and the pyproject build backend swapped to setuptools
  for p4a's `pip install .`; Android 16 Play Protect refuses targetSdk 33 (`INSTALL_FAILED_VERIFICATION_FAILURE`)
  -> API 36 plus a re-created dist (p4a bakes the API into `project.properties`; build.sh now does that itself);
  predictive back on targetSdk 36 closes the app before SDL sees the key -> `android:enableOnBackInvokedCallback="false"`.
- Skill `/android_update_copy` (.claude/skills/android_update_copy/SKILL.md): status check, sync, optional
  desktop-mode look, background build with log reading, install/run/logs, report.
- Tests: `tests/test_android_touch.py` (12): tap places a belt, long press = RMB cancels the tool, one-finger
  drag pans, belt drag builds a line, pinch zooms both ways, a second finger cancels a belt drag and pans,
  two-finger tap, overlay buttons (Rot/Esc/Shift/Zoom/Pause/Speed, Load only on game over), Box + drag selects,
  K_AC_BACK -> Escape in the queue, desktop mouse emulation, `entry.main --desktop` headless smoke. 156 green.
- Verified on the phone (adb screenshots + logcat, APK 0.1.0, 25 MB): menu, Test Lab running (items flowing,
  targets levelling, units out), Pause via a real touch, a one-finger swipe pans exactly 300 device px, Back ->
  menu with the app alive, the save written to `files/digit_defender/saves/Test_Lab`, config `last_world`;
  CPU ~70% of one core; no tracebacks (only pygame's missing-`consolas` warnings: default font).
- **Open:** John has not played it yet (touch feel, button sizes, text legibility at 1.5x, the soft keyboard on
  the New World screen); economy / Phase 4 checkbox / Phase 6 leftovers as v8.

## v8 (2026-09-12): John's round 16 - demolish box, Del on a selection, unit costs, 10-minute waves (tests 143 -> 144)
Commits 6606f99 (round 15, see v7) and cbf056b (round 16); session wrap after that.
- "I can't click and drag to delete" (`game.py`, `render/renderer.py`, `render/structures.py`): the demolish tool [X]
  now drags a BOX (red translucent rect, a frame on every structure inside, "demolish N = +refund" at the corner) and
  removes everything inside on release; a tiny box removes the one under the cursor; Esc / RMB before the release
  cancels; the HQ is never removed. The old 1-tile-wide sweep along the drag is gone (`Game._end_demolish`,
  `demolish_targets`, `_structures_in_box` shared with the select box). Del removes the selection (boxed group or
  single) with a "Demolished N, +refund back" message, else the hovered one (`Game.demolish_many`).
- Spawner panels show what [C] costs (`ui/hud.py`): single panel "[click] or [C] train a Ranged unit: 50 each
  queue 2 (100 paid)"; the group panel and the hints line say "[C] train a unit at each of 3 spawners for 250
  (Ranged 50 x2, Heavy 150)" (`hud.unit_cost_summary`); the hover line names the unit and its price; the group panel
  also totals [Del] refunds. Both info panels now grow to their widest line instead of overflowing 372 px.
- Waves every 10 minutes, flat (`settings.py`, `docs/PLAN.md` 3.8): WAVE_FIRST_S = WAVE_INTERVAL_BASE_S =
  WAVE_INTERVAL_MIN_S = 600, DECAY 1.0 (was 5 min then 240 s * 0.97^n, min 90 s). Existing saves keep their current
  countdown, then run 10-minute intervals.
- Repair units: unlimited range (`settings.REPAIR_UNIT_SEARCH` None, `sim/combat.py` `_repair_target`): the nearest
  damaged unit or building anywhere, nearest first. Help / hints text updated.
- Tests (`tests/test_game.py`, `tests/test_combat.py`): demolish click-vs-box (preview count, HQ never removed, Esc
  cancels), Del on a boxed group / a single selection / hovered fallback, `unit_cost_summary`, flat 10-minute waves.
- Verification: dummy-driver screenshots of the demolish box over the lab (37 structures framed, label + hint line),
  the group panel with four spawners ("for 350 (Heavy 150, Melee 50, Ranged 50, Repair 100)") and the single Heavy
  spawner panel ("150 each, queue 1 (150 paid)"); wave timer reads "Wave 1 in 9:59"; suite green; `python main.py
  --world smoke --frames 120` exits 0.
- **Open:** as v7 (John's (-22,2)/(-26,1) Test Lab reports need his layout; formations do not turn; economy not
  re-balanced; Phase 4 design checkbox; Phase 6 leftovers).

## v7 (2026-09-12): John's round 15 - formations, patrols, walls block units, repair units (tests 134 -> 143)
- Middle CLICK with units selected = patrol: `Combat.patrol` hands the group a second formation at the click (`patrol`
  slot + `panchor`), `leg` picks the end each unit walks to and flips on arrival; RMB move ends it; patrol lines and a
  diamond marker draw for selected units; saved per unit. A middle DRAG still pans (click = under 4 px of movement).
- Units no longer phase through walls: `sim.pathing.route` (bounded A*, 4-neighbour, deterministic ties, a solid goal
  ends beside it) drives `_walk_grid` for player units through `Combat._next_tile`; routes are cached on the unit and
  re-planned when the goal changes, the unit leaves the route, or `Factory.layout_version` says a structure landed on
  it; enclosed units hold (greedy fallback never steps into a solid tile). `Combat.solid` (SolidMap) = every structure
  except belts and bridges (`UNIT_PASSABLE_KINDS`); attack posts for player units avoid solid tiles too. A rally slot
  buried under a new structure is swapped for a free one. Enemies unchanged (greedy/flow field, chew what blocks).
- Wheel with units selected cycles the formation (Ctrl+wheel zooms): `FORMATIONS` box / line / column / wedge / ring,
  `formation_slots` yields best-first with fallbacks, `set_formation` re-forms around the remembered `anchor` so cycling
  never drifts (the wedge is centred on its point), `gather` keeps the group's formation for every later move; line and
  column assign by the units' current x / y so they do not cross; saved per unit (`formation`, `anchor`).
- Repair spawner `[=]` (COSTS 100, hp 120) and repair unit (UNIT_COSTS 100; UNIT_STATS hp 40, speed 0.18, heal 25 per
  10 ticks, never fights): heals the nearest damaged player unit (self included) or damaged structure within
  REPAIR_UNIT_SEARCH (16 tiles here; unlimited since v8) from a load of REPAIR_UNIT_CAPACITY 500 numbers at REPAIR_HP_PER_NUMBER 5 hp each (the [H]
  price; `Factory.heal`, `damaged_structures()` sorted for determinism); empty -> walks to the nearest free tile touching
  the HQ and takes min(500, balance) (event "refill" -> HUD message; waits while broke). Drawn red with a white cross and
  its load underneath; green heal beams (`HEAL`); toolbar button and procedural spawner sprite carry the cross; toolbar
  buttons shrink to fit 14 left of the minimap (11 px names at 1280 wide). K_EQUALS moved from zoom-in to the tool.
- Test Lab: repair spawner at (12,6) with two queued, wall (-8,8) starts damaged; `testworld.top_up` adds the spawner
  to a lab saved before it existed (main.py calls it when the lab is not empty).
- Bridge tool drops onto a belt (`Factory.replaces_belt`/`can_place`/`place`: the belt is removed with its refund and
  its items move into the lane of its back side) - John's "cannot make a bridge after drawing the belt" at (-26,1).
- Build refusals explain themselves on a click: "(x, y) is occupied by a Tower: [X] demolish it first"; a belt drag that
  built nothing says "Belt at (x, y) kept its direction: it feeds a line (drag from a line's end, or [R] on it)" -
  John's "cannot connect (-22,2) and (-21,2)" (not reproducible from his save: nothing was built there).
- Help overlay: six new lines (formations, patrol, walls block units, repair); it drops to a 13 px font when 30 lines
  would not fit the window height.
- Verification: scratch verify_units.py screenshots (line of 5 leaving a walled yard through its gate without touching
  a wall, wedge + patrol lines, two repair units refilling 500 each at the HQ then fixing the lab wall, 14-button
  toolbar, help overlay, bridge dropped onto a running line with both lines flowing); 100 ticks with 43 routing units
  plus a structure placed every tick = 2.2 ms/tick; `python main.py --world smokeunits --frames 120` exits 0.
- **Open:** John's (-22,2)/(-26,1) reports need his layout left in place to confirm; formations do not turn toward the
  move direction; a walled-in base needs a gate for melee units; economy still not re-balanced; Phase 4 design
  checkbox; Phase 6 leftovers (sounds, stats graphs, blueprints, balance pass).

## v6 (2026-09-11 evening to 2026-09-12): John's rounds 4-14, all implemented (tests 110 -> 134)
Round 4 opened this entry; every later round the same day was appended below as a "Round N" bullet.
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
- Round 12 (same evening): (1) HQ 6x6 - footprints generalised (origin/tiles/centre for even sizes), tiles -3..2,
  SPAWN_CLEAR_RADIUS 4, camera/home/gather use hub.centre(), old saves drop covered structures, hub.png now 192x192.
  (2) [T] on a belt = forced T-junction (`Belt.split`, saved): splits into side belts pointing away even if fed - John's
  up-line + south-fed corner layout (two T's) is impossible under the auto rule, which cannot be told apart from the
  parallel-lines case he did not want. (3) Attack posts: attackers on both sides claim distinct tiles around their
  victim (`claim_post` / `_engage` / `_hold_post`, line-of-sight so enemies never cross a wall, crowds fan out along a
  wall line via `_structure_points`); melee ranges 1.5. (4) [C] queues a unit at the selected spawner or every spawner
  in a boxed group; RMB gather points no longer move units already out. Tests 126 -> 128.
- Round 13: target bonus = value * amount * k, k rolled 10-20 per target (seeded; midpoint 15 when constructed
  by hand), no flat part - 5 x 7 pays 350-700 (was 72). Economy will inflate; balance pass still pending.
- Round 14 (John: "sort out T and X junctions, add bridges, generate a test world"): (1) Bridge structure ([B],
  cost 10, hp 40): four lanes keyed by entry side, in a side -> out the opposite at belt speed, lanes never mix,
  exits cached per fed lane, saved as `lanes`; procedural crossing sprite (bridge.png override), items drawn straight
  across. (2) Junction rules written down (help overlay + HANDOFF): merge = any belt pointing into a side/back;
  split = [T] or an unfed belt starting beside a straight belt; splitting belts show exit arrows. (3) Test Lab:
  `world/testworld.py` builds every part and junction around the HQ (row with forced T/X splits, merge T, cross
  merge, bridge crossing, auto branch, four machines with routed outputs, towers stocked/empty, three spawners with
  queues, levelled walls and belts); `--testworld` / menu "Test lab" opens it (built once into a world named
  "Test Lab"); tests/test_bridge.py + tests/test_testworld.py. Toolbar 13 buttons (60 px). Tests 128 -> 134.
- **Open:** John bug-hunts in the Test Lab next; no dequeue/refund for queued units; the economy has not been
  re-balanced after paid units, 10-20x target bonuses and sparse deposits; Phase 4 design checkbox; Phase 6 leftovers
  (sounds, stats graphs, blueprints, balance pass). HANDOFF v6 is the cold-start document.


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
