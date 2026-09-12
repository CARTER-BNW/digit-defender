# HANDOFF — Digit Defender
_Last updated: 2026-09-12 (v10: John's phone round 1 - Settings screen, contextual buttons above the toolbar) by Claude_

New-session bootstrap. Read this, then docs/PLAN.md (design authority), docs/PHASES.md (checkpoints), docs/GOTCHAS.md.

## Live state
- **Phases 0-5 are built and verified** (tests + real-window runs + screenshots). Phase 6 (polish) is in progress.
  167 pytest tests green (`python -m pytest -q`, ~12 s). Last commits: cbf056b (round 16), 6d00eaf (wrap v8),
  70a3393 (Android copy, STATUS v9), bb3870b (handoff v9) and the phone round 1 commit (STATUS v10), all
  2026-09-12.
- **Phone round 1 (2026-09-12, STATUS v10):** menu "Settings" screen (`ui/menu.py`: text size 80-180%, button size
  80-200%, fullscreen (desktop only), info hints, enemy waves on / paused; values in config.json, scales through
  `ui/prefs.py`) replaces the old Fullscreen / Info hints rows; the HUD scales its panels, hints, messages, wave
  timer, help and game-over text with the text size (`Hud.px` / `Hud.text`; the toolbar and the Android buttons
  follow the button size); `Combat.waves_paused` freezes the wave countdown ([F7] still fires, camp raids go on;
  `Game.apply_config` reads it with the hints flag). Android buttons now sit in ONE row above the toolbar and
  appear only when they can act (Rot / Shift / Box / Upg / Fix / Split / Train / Form at the left, Pause / Speed /
  Help / Save / Menu / Load at the right); Esc, Del, Pick, HQ and the zoom buttons are gone (Back key, X tool,
  the HQ button, pinch).
- **Phone round 2 (2026-09-12, same STATUS v10 entry):** toolbar buttons are keycaps (the hotkey centred in the
  kind's colour, name and cost centred below, nothing overlapping); on the phone a HOLD (0.45 s, the ring turns
  green) then LIFT = right click and HOLD then DRAG = selection box (with a tool active: the tool's own drag);
  the Box button stays as the explicit way. The repo is public on GitHub (CARTER-BNW/digit-defender) with release
  v0.2.0 (APK attached, notes in docs/RELEASE_NOTES.md, tester-facing README.md) - John: "so people can test".
  The APK needs Android 7.0+ (minapi 24) on a 64-bit phone (arm64 only; add `armeabi-v7a` to `android.archs`
  for 32-bit phones at the cost of a long first build and a bigger APK). PC testers get
  `DigitDefender-0.2.0-win64.zip` from the same release: `python build_pc.py` (PyInstaller one-folder app,
  assets bundled, saves/config next to the exe because `persistence.ROOT` follows `sys.executable` when frozen).
- **Android copy (2026-09-12, STATUS v9):** `android/` = the untouched desktop game + `android/mobile/` (touch
  layer: tap / long press / drags / pinch / two-finger tap + on-screen hotkey buttons; `entry.py` is the APK's
  main), packaged by python-for-android inside the WSL distro `dd-android` (Ubuntu on `D:\WSL`, everything on
  D:, no Docker - John's call). `python android\sync.py all` = sync copy -> build -> adb install -> run -> log
  dump; `/android_update_copy` is the checked walkthrough; `android/README.md` has the pipeline table and the
  phone controls. APK 0.1.x (pygame-ce 2.5.8, CPython 3.14, targetSdk 36, arm64) runs on his Pixel 9a (adb-driven
  checks: menu, Test Lab running, Pause by touch, swipe pan, Back -> menu, saves in the app's private dir).
  John played it once and sent phone round 1 (STATUS v10, implemented; see the bullet above). Every build trap
  hit is in docs/GOTCHAS.md (five Android entries); keep the game on APIs pygame-ce offers on Android (no
  SysFont: `consolas` falls back to the default font there).
- **John play-tested sixteen rounds on 2026-09-11/12; every item is implemented** (STATUS v4-v8 list them round by
  round, HANDOFF decisions 1-11 below hold the resulting rules). The game he now has, in one breath: a 6x6 HQ; belts
  drawn by drag with a transparent preview (Shift = straight L, R turns the drag), items that curve through corners;
  junctions = merge by pointing in, split only with [T] or an unfed belt starting beside a line, [B] bridge to cross
  (it drops straight onto a belt of a finished line); machines take operands on all three non-output sides; towers take
  ammo from any side, range 10, buffer 20+10/level; walls link and show their level; hp only moves on level-ups, [U]
  buys the next level at a fixed geometric price; spawners train paid units on click / [C] (panels show the price),
  units gather one per tile beside the HQ, are commanded RTS-style (RMB move, wheel = formation box / line / column /
  wedge / ring that sticks to the group, middle click = patrol between rally and the click), route around walls and
  buildings with A* (belts and bridges are walked over; a walled base needs a gate), and fight from distinct posts;
  `[=]` repair spawner trains red white-cross units that heal the nearest damaged building or unit anywhere from a
  500-number load (5 hp per number, refilled at the HQ from the balance); enemies shoot while advancing and melee in
  contact; waves every 10 minutes flat; four levelled targets that want an amount of a number and pay 10-20x; a
  guaranteed enemy camp 100 tiles out; sparse rarity-weighted deposits; HUD right column + top-left info panels that
  grow to their text + 2x minimap + hints toggle; X demolish tool drags a box (Del removes the selection); a click that
  cannot build says why ("occupied by a Tower", "belt kept its direction: it feeds a line"); delete worlds from the menu.
- **Unresolved from round 15**: John's Test Lab reports at (-22,2)/(-21,2) ("cannot connect") and (-26,1) ("cannot
  make a bridge after drawing a belt from -28,1 to -24,1") had nothing built there in his save, so they were never
  reproduced; the likely causes (a bridge on an occupied belt tile, a mid-line belt that refuses to turn, a silent
  "occupied") were fixed blind. If he hits them again, ask him to leave the pieces in place and quit normally.
- **Test Lab**: `python main.py --testworld` (or the menu entry "Test lab") opens a hand-built world with every part and
  junction laid out around the HQ (legend in `world/testworld.py`). John will bug-hunt there; when he reports a tile
  coordinate, rebuild the scene from the legend and reproduce headlessly (tests/test_testworld.py shows how).
- John is drawing PNG sprites: 32x32 per tile (hub.png 192x192 for the 6x6 HQ; bridge.png never rotated), drawn facing
  LEFT, pure white/magenta transparent, named by kind in `assets/sprites/` (belt shapes: belt, belt_corner, belt_t,
  belt_cross). wall.png, if it arrives, is drawn over the procedural connector bars.
- **Code changes need a game restart** (a running `python main.py` keeps the code it started with).
- Directory: D:\Claude\projects\games\Digit Defender (git on `main`, remote `origin` = github.com/CARTER-BNW/digit-defender,
  public; push after each session wrap, releases via `gh release create`). Saves in `saves/` (gitignored;
  "Test Lab" lives there too), machine prefs in `config.json` (gitignored; holds fullscreen, hints, last world).
  The phone keeps its own saves and config on the device (`files/digit_defender/`), separate from the PC's.
- Run: `python main.py` (menu) or `python main.py --world NAME [--seed N]` (skip menu), `--testworld`, `--frames N`
  auto-quit, `--autosave S`, `--fullscreen`. `run.bat` passes args through.
- Open design checkbox in Phase 4: John to confirm feed-side rules and voiding of <= 0 results (implemented per PLAN;
  he has played with them for a day without objection, so likely just tick it).

## Health check (what "working" looks like)
1. `python -m pytest -q` -> all green.
2. `python main.py --world smoke --frames 120` -> window opens on a fresh world with the hub, exits 0, `saves/smoke/` written.
3. In game: 1 = belt, 2 = miner (needs a deposit), 3-6 = machines, 7 = wall, 8 = tower, 9/0/-/= = spawners, X = demolish
   tool (click a building or drag a box over many, removed on release, 50% refund; X/Esc leaves it; Del = remove the
   selection, else the hovered one); R rotate, LMB place (belts: hold
   and drag = transparent preview path that auto-turns, Shift = one straight run + one square corner, R during the
   drag turns every belt a quarter (twice = the line runs backwards), release builds it, drag back undoes; a drag off
   the middle of a line leaves that belt alone so the new belt is a T branch, from a line's end the last belt turns,
   dragging backwards over a line reverses it; other kinds place on every tile crossed), Q pick, H repair, U upgrade
   (fixed level price), T = force/release a T-junction on a belt, B = bridge tool, click = select (info panel top
   left; decided on release), drag a box — even one that starts on a belt — = select every structure inside (U/H/T/C
   apply to all; group panel; Shift+click adds one) and/or units, click a spawner or press C = train one unit,
   click / Shift+click / drag a box = select units, RMB = move selected units (grid formation) or set the gather
   point of the selected spawner(s) for units trained from then on, or cancel, wheel with units selected = next /
   previous formation (box, line, column, wedge, ring), middle CLICK with units selected = patrol between their rally
   point and the clicked point, = repair spawner,
   wheel zoom (Ctrl+wheel while units are selected), MMB drag pan, WASD pan (Shift fast), F3 debug, Space pause,
   [ ] sim speed x1/x2/x4, F1 help overlay,
   Home or the HQ button = camera back to the HQ, minimap click = recentre there, F6 spawn an enemy at the cursor,
   F7 trigger the next wave, F11 fullscreen, Esc = cancel tool / clear selection / menu (Esc in the menu = back into
   the game; Del in the menu deletes the highlighted world after a confirm screen). Minimap bottom-right (2x).
4. Belt rules a player sees (final, round 14): a belt pointing into another belt's side or back MERGES (T / X shapes
   with several inputs). A belt SPLITS only when [T] is pressed on it, or when an unfed belt starts beside a straight
   belt (auto branch); splitting belts show small arrows at every exit and alternate items between them. [B] bridge =
   two lines cross without mixing (in a side, out the opposite); the bridge tool drops straight onto a belt of a
   finished line (round 15). Numbers cannot be built on except by miners; a miner pushes into every adjacent cargo input.
5. `python main.py --testworld` (or the menu entry "Test lab") opens the Test Lab world: every part and junction type
   laid out around the HQ (legend in `world/testworld.py`; tests/test_testworld.py checks it runs as documented).
6. Android: `python android\sync.py status` shows the phone (`device`), the build box and the latest APK;
   `python android\sync.py all` rebuilds and reinstalls (2-5 min after the first build); `python
   android\app\main.py --desktop --world lab` shows the phone layout in a window with the mouse as a finger.

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
- `game.py`: Game.load/save, event loop, fixed timestep (20 Hz, cap 4 ticks/frame), build mode (belt preview path,
  demolish tool, drag-box selection of structures and units), unit commands, autosave, game over -> [L] reload.

Android in one screen (`android/`, STATUS v9, `android/README.md` for the player-facing controls):
- `mobile/entry.py` = the APK's main (sync writes a two-line `app/main.py` stub calling it). `MobileGame(Game)`
  overrides only `handle_event` (finger events -> `TouchLayer`; SDL's mirrored mouse events dropped on the phone;
  K_AC_BACK -> Escape; APP_WILLENTERBACKGROUND -> save), `update` (long-press timer first), `draw` (overlay after
  the HUD, flip guarded) and `toggle_fullscreen` (no-op); `dispatch()` is the untouched desktop handler the touch
  layer feeds. `MobileMenu` turns the soft keyboard on for New World. `install_patches()` wraps `pygame.event.get`
  (Back -> Escape in the menu loop too), `pygame.key.get_mods` (sticky Shift from `touch.STATE["mods"]`) and, on
  the phone, `pygame.mouse.get_pos` (= last finger, `STATE["last_pos"]`, so hover/ghost follow the finger).
  Display: `set_mode((round(w/scale), 720), SCALED | FULLSCREEN)` with scale = native height / 720 (Pixel 9a
  2424x1080 -> 1616x720 at 1.5x); saves + config redirected to `$ANDROID_PRIVATE/digit_defender/` (the unpacked
  app dir is wiped on every update); `DEFAULT_CONFIG["hints"] = False` (the right-hand buttons sit where the hints
  panel would be). `--desktop` runs the same code in a window on the PC with the left mouse button as a finger.
- `mobile/touch.py` = `TouchLayer`: modes None / pending / held (a rested finger: lift = right click, move = LMB
  drag, i.e. a selection box with no tool) / lmb / pan / two; TAP_MAX_PX 14, LONG_PRESS_S
  0.45, TWO_TAP_S 0.35, PINCH_STEP 1.22; `layout()` recomputes the button rects every frame: one row just above
  `hud.toolbar_rect` (it calls `hud.buttons()` first), ACTION_BUTTONS from the left edge, each with a `when(game,
  layer)` predicate (Rot: a tool or selected building with a facing; Shift: belt tool, a selection, Box armed or
  Shift on; Box: no tool; Upg: a selection; Fix: a damaged selection; Split: a belt selected; Train: a spawner
  selected; Form: live units selected; none after a game over), SYSTEM_BUTTONS (Pause, Speed, Help, Save, Menu,
  Load on game over) from the right edge, one row up when both groups would not fit side by side; size 64 px x
  `prefs.button_scale` (labels scale too); `hud.over_ui` is wrapped per instance to include them. Synthesized
  events carry `touch=False` and go through `game.dispatch`.
- Pipeline: `sync.py` (Windows, stdlib) -> `wsl/build.sh` inside `dd-android` (mirrors `android/` to
  `~/dd-android`, re-creates the p4a dist when `android.api` changed, runs buildozer, copies the APK back) ->
  adb (`D:\Android\sdk\platform-tools\adb.exe`, env `ADB` overrides). `p4a-recipes/pygame` builds pygame-ce
  2.5.8 (p4a's own pygame 2.1.0 cannot build on its Python 3.14); `manifest_application_args.xml` disables
  predictive back; `buildozer.spec` targets API 36 (Play Protect refuses 33). `VERSION` bumps on every sync.
- Testing on the phone without touching it: `adb shell input tap X Y` / `input swipe x1 y1 x2 y2 ms` /
  `input keyevent KEYCODE_BACK` (device px: menu entries sit at x 1212, y 344 + 66 per row), `adb shell screencap
  -p /sdcard/s.png` + `adb pull` then Read the PNG, `python android\sync.py logs` (python + SDL tags;
  `--follow 30` streams), `adb shell pidof org.johncarter.digitdefender`, `adb shell run-as
  org.johncarter.digitdefender ls files/digit_defender/saves`. Use PowerShell for adb paths: Git Bash rewrites
  `/sdcard/...` into a Windows path. A stuck install = a dialog on the phone (`uiautomator dump`, docs/GOTCHAS.md).

Naming: the player sees "HQ" everywhere (sprite label, HQ button, alerts, help, panel via `hud.DISPLAY_NAMES`); the
code, saves and docs keep the kind name `hub` (John, round 10).
HUD layout (John, round 11; `ui/hud.py` docstring): right column 340 px = balance (centred) / targets / HQ button /
hints panel (word-wrapped controls + hovered-tile + selection lines; menu toggle "Info hints", config["hints"],
`Game.show_hints`); wave timer top centre; the clicked structure's info panel and the group panel top LEFT; minimap
440x300 (128 tiles across, click = recentre) bottom right; toolbar centred in the space left of the minimap;
off-screen edge arrows are drawn by the HUD on top of the panels. `Hud.over_ui` covers all of these, so scripted
tests must keep their tiles clear of the right column (x >= 932 px) and the minimap corner (x >= 832, y >= 412).

## Load-bearing decisions (do not re-litigate casually; rationale in PLAN.md)
1. Structures live in `Factory.structures[(tx,ty)]` (+ `by_chunk` index for rendering), never in terrain chunks. Terrain
   unloads freely; the factory always simulates (verified: a line 40 chunks away ran while its chunk was unloaded).
   Footprints: `origin()` = anchor - SIZE//2, `tiles()` = origin + range(SIZE)^2, `centre()` = origin + SIZE/2. The HQ is
   6x6 (John, round 12): anchor (0,0), tiles -3..2, SPAWN_CLEAR_RADIUS 4 keeps a deposit-free ring; older saves drop
   anything the bigger HQ covers (`Factory._drop_hub_overlaps`). Default gather point = HQ edge + GATHER_HUB_GAP (2).
2. Fixed timestep 20 ticks/s; render 60 fps; MAX_TICKS_PER_FRAME = 4, leftover time dropped.
3. Deterministic sim: belts update downstream-first (`belts_ordered`, rebuilt only when `dirty_links`), typed lists sorted
   by (y, x), no free-running RNG anywhere (targets/waves/raids are string-seeded by ordinal). Acid test in
   tests/test_persistence.py: save@100 + load + 100 == twin@200.
4. Side rules (`sim/structures.py` docstring): item entering through a non-cargo side is FEED (invested += value; hp
   moves only when a level-up raises max_hp — feeding never heals, repair does; John, round 6). Belt: back/sides cargo,
   head-on feed. Machine: left = A, right = B, back = the emptier buffer (all three inputs; no feed side — John,
   round 7), front refuses. Hub: all income.
   Tower: every side = ammo, no facing, no feed sides (John, round 3) — towers level only via `[U]`. Wall/Spawner: all
   feed. sub/div <= 0 voided.
   Miners (John, 2026-09-11) push into every adjacent cargo input, never into feed sides, no facing. Belt outputs = the front
   target plus, for a STRAIGHT (back-fed) belt only, belts beside it that point straight away and have no cargo source of
   their own; items alternate evenly over outputs (implicit splitter; `rr` cursor saved). Corners/merges never branch and
   a belt already fed by its own line is never stolen as a branch (John, round 3: parallel lines stay separate) — UNLESS
   the junction belt has `split` set ([T] key, saved): then it branches into every side belt pointing away, even a fed
   one (John, round 12: a split feeding a merge = two T-junctions; the auto rule cannot tell that layout from the
   parallel-lines one, so the player decides per belt). Bridge (round 14, `sim/structures.Bridge`, cost 10): four
   lanes keyed by entry side, an item leaves through the opposite side into whatever stands there; `exits` are cached
   in rebuild_links for fed lanes only (a belt pointing in, a miner, a machine, another bridge); ticks after belts;
   never rotated (relative side == world side); a fed exit belt counts as pushed / side-fed for the branch rule and
   gets its `in_sides` bit. Only miners may be built on number tiles. Belt sprites are shape-aware (in_sides | out_sides -> straight/corner/T/cross).
   Belt items are `[value, progress, entry_rel]`; the third field is render-only (corner animation) and the sim never
   reads it; old two-field saves load as BACK.
5. Leveling: level n -> n+1 costs 100 * 1.25^(n-1) fed (100, 125, 156, 196, 244...), thresholds are the running sum
   (`leveling.threshold`), NO level cap (John, round 5); belt speed = 0.05 + invested*0.0001 tiles/tick (cap 0.5);
   periods /(1 + 0.25*levels); max_hp = BASE_HP + threshold(level-1), stepwise (hp rises by exactly the gain on a
   level-up, never otherwise). Repair costs 0.2/hp. `[U]` upgrade = pay the FIXED level price `level_cost(level)`
   (100, 125, 156...) and feed it in full (excess carries over; fed progress is not discounted — the price never drifts
   while numbers trickle in) — idea.txt: balance is spent to create / improve / repair.
6. Ranged/heavy unit shots debit balance by the fired value; hold fire when broke; melee free; towers eat belt ammo
   (dmg = value * (1 + 0.5*(level-1)), range TOWER_RANGE = 10, buffer TOWER_AMMO_BASE 20 + TOWER_AMMO_PER_LEVEL 10 per
   level above 1 — John, round 11). Spawners never spawn on their own: a click queues one unit
   (UNIT_COSTS 50/50/150, SPAWNER_QUEUE_MAX 9), one unit walks out per period (timer keeps counting while idle, so the
   first click after a pause trains at once). Units take grid slots: `Combat.slot_near` / `gather` spiral tile centres out
   from the gather point, skipping structure tiles and other units' slots (one unit per tile, compact grid); default gather
   point = HQ edge + GATHER_HUB_GAP on the spawner's side; units walk along grid lines (row/column, larger axis first,
   re-centre only to turn), when chasing enemies and nests too (John, round 6). Setting a spawner's gather point (RMB,
   one or a boxed group) affects only units trained from then on (John, round 12); [C] queues one unit at the selected
   spawner or at every spawner in the group. Attack posts (round 12, no stacking): `Combat.claim_post` gives every
   attacker its own tile within range of its victim (a unit's position, or a structure's tiles plus the tiles of
   structures touching it so a crowd fans out along a wall), free of structures and other attackers, reachable in a
   straight line (`_clear_line`, so enemies never slip through a wall), at most POST_MAX_SHIFT (3) from where it stands;
   player units walk to it along the grid (`_engage`), enemies shuffle to it (`_hold_post`). Melee ranges are 1.5 so
   the 8 tiles around a target all count. `_posts` is rebuilt every tick from live units (uid order: deterministic).
   Hub alert: `Factory.hub_hit_tick` / `hub_under_attack()` (HUB_ALERT_S = 3 s after a hub hit) drives a pulsing red
   double frame around the hub (render/structures.draw_hub_alert) and a red screen frame + "HUB UNDER ATTACK" (hud). Player units are saved in meta
   `wave.units` (uid, kind, pos, hp, level, owner spawner, slot, formation, anchor, patrol/leg/panchor, carry); enemies
   still disperse on reload.
   Round 15 rules: (a) player units are blocked by every structure except belts and bridges (`UNIT_PASSABLE_KINDS`;
   `Combat.solid` is a live SolidMap over the structure dict); `_walk_grid` follows a cached A* route (`Unit.path`,
   re-planned when the goal changes, the unit leaves the route, or `Factory.layout_version` shows a structure landed on
   it; `UNIT_PATH_BUDGET` 4000 expansions, then greedy-but-never-into-a-wall, then hold); attack posts use the solid
   map too. Enemies keep greedy + flow field (they chew what blocks them). (b) Formations: `formation_slots(name, gx,
   gy, n)` yields slots best-first with fallbacks (structures / other units' slots are skipped); `gather` (RMB) keeps
   the group's formation, `set_formation` re-forms around the remembered `anchor` (no drift when cycling), `patrol`
   (middle click) hands out a second set of slots (`patrol`, `panchor`) and `leg` says which end the unit walks to;
   arrival flips the leg. (c) Repair units (`UNIT_STATS["repair"]`: heal 25 per 10 ticks, never fight): `_repair_ai`
   heals the nearest damaged unit (self included) or `Factory.damaged_structures()` entry within REPAIR_UNIT_SEARCH,
   spending ceil(hp / REPAIR_HP_PER_NUMBER) numbers from `carry` (capacity REPAIR_UNIT_CAPACITY 500); at 0 it walks
   to the nearest free tile touching the HQ (`_hub_side_tile`) and takes min(500, balance) from the balance (event
   "refill"); a new unit spawns empty and fetches its first load. Heal beams are green (`HEAL` side).
7. Waves: every 10 minutes flat (first at 10 min; John, round 16 — was 5 min then max(90 s, 240*0.97^n)), budget
   20*1.25^n, spawn ring = base bbox + 12 tiles (min radius
   30), direction pre-rolled (edge arrow in the last 60 s). Enemies use the hub flow field (walls 40, other structures 15)
   when inside it, greedy otherwise; whatever blocks gets meleed. Every enemy also shoots while advancing (John, round
   5): `shot_dmg` at the nearest unit, else the nearest structure (`Combat.nearest_structure_in`, a bounded tile scan),
   within `shot_range` 3-5 tiles, same cooldown as melee, free; raid tiers scale shot_dmg like dmg.
8. Nests: region grid 12 chunks, none within 1 region of origin, chance 0.3 per region ring beyond (cap 0.6), tier = ring;
   PLUS one guaranteed "home camp" (`nests.home_nest(seed)`: tier 1, NEST_HOME_DISTANCE = 100 tiles from the origin in a
   seeded direction, footprint nudged inside one chunk; `nest_at` returns it for its region despite the safe zone —
   John, round 10: he had never seen a camp). It is always in `known_nests` (minimap + dark-red edge arrow) but only
   aggro when a structure is within 48 tiles -> raids every 45 s; core hp 500*tier, bounty 500*tier; destruction lives in
   NestRegistry (enemies.json), never in terrain; renderer draws rubble from the registry.
9. Saves: meta.json (identity + balance/tick/targets/camera/wave incl. player units), structures.json, enemies.json; write
   .tmp -> rotate .bak -> replace; readers fall back to .bak. Autosave 60 s + on exit; a game-over state is never saved.
11. Targets (John, round 8): TARGET_COUNT = 4 slots, each with its own level. A target wants `amount` deliveries of
    its `value` (progress `delivered`); done -> bonus `value*amount*k` with k rolled 10-20 per target from the same
    seeded rng (John, round 13: 5 x 7 pays 350-700), `targets_completed += 1`, the slot moves to
    its next level via `economy.next_level` (number and amount each grow by a seeded random 25-75%, number bumped past
    any value another slot uses). Level 1 = distinct numbers from 5..9 with amount 5 (`economy.initial_targets`, seeded
    by `seed:targets:init`). Saved per slot; older 3-slot / {value,reward} saves load and get topped up (`top_up`).
10. Rendering: chunk surfaces rendered per (chunk, zoom) at the target tile size and cached on the chunk, evicted off-screen;
    CHUNK_GEN_BUDGET = 24 chunks/frame (visible first). Everything positions from `Camera.screen_origin()` (no seams).
    Walls carry `links` (bitmask of wall neighbours, rebuilt with the links) and draw connector bars + their level;
    a tower with empty ammo gets a red frame; the hub's damage bar sits under its label, one tile wide.
12. Settings (John, phone round 1, 2026-09-12): config.json keys `text_scale` / `button_scale` (`ui/prefs.py`, steps
    0.8-1.8 / 0.8-2.0), `hints`, `fullscreen`, `waves_paused`; the menu's "Settings" screen replaces the Fullscreen /
    Info hints rows (Enter / tap / Right steps a value, Left steps back). Text size scales every HUD panel, the
    hints, messages, wave timer, help, game over and the menu rows (world numbers never; the hints panel stops
    short of the minimap, the wave timer steps aside from a wide structure panel); button size scales the toolbar
    (still shrunk to fit left of the minimap) and the Android buttons with their labels. Waves paused =
    `Combat.waves_paused`: `next_at_tick` advances with the tick so the countdown stands still, [F7] still fires,
    camp raids are unaffected; it is a machine setting (config), not saved per world.

## Known rough edges / ideas (not blockers)
- Towers take ammo from every side now, so a tower cannot be belt-levelled; `[U]` is the only way to level one.
- No way to cancel a queued unit (refund) yet; an accidental click on a spawner costs its unit price.
- Units are picked within 0.6 tile of the click; box select needs a 4 px drag. Selected units are not saved (selection is
  transient); their slots are.
- The economy has drifted far from the STATUS v3 probe: four-side miners, 2 items/tile belts, paid units, 10-20x target
  bonuses (a level-1 target pays 350-900), fixed geometric upgrade prices, sparse deposits. Nothing has been re-balanced
  on purpose; do a balance pass only after John says the mechanics feel right (bot_player.py in scratch is stale).
- Auto-branch reminder: an unfed belt that starts beside a straight belt becomes a branch on its own; if John reports a
  "surprise split", that rule is the first suspect (the exit arrows on splitting belts show it).
- Sprite label sizes/positions were tuned for the procedural art; check them once John's miner/machine PNGs land.
- Item spacing is half a tile (2 per tile) so numbers do not overlap; belt throughput is 2 items/s at base speed.
- Custom PNG sprites: assets/sprites/<kind>.png, 32x32 per tile (hub 192x192), facing left (see README).
- Player units walk over belts and bridges but are blocked by everything else (round 15); a fully walled base needs a
  gate (a gap) or the units stay inside and only the ranged ones fire over the wall. Enemies shoot over walls (3-5
  tiles); towers (10) and ranged units (6) outrange them.
- Formations are axis-aligned (a line is always east-west, a column north-south, a wedge points north); they do not
  turn toward the move direction. While attacking, units still spread over attack posts (nearest free tile), so a
  formation bends into an arc around the target rather than holding its exact shape.
- Repair units go to whatever is damaged anywhere, nearest first (John, round 16); with a big base they may walk a
  long way, and a route that needs more than UNIT_PATH_BUDGET expansions falls back to greedy walking (can stall at a
  wall). A repair unit's first load is fetched from the HQ right after training (the unit costs 100, the load 500).
- Waves come every 10 minutes flat (round 16; WAVE_FIRST_S / BASE / MIN = 600, DECAY 1.0). Saves keep their running
  countdown for the next wave, then switch to the 10-minute interval.
- The demolish tool is a box: press, drag, release (nothing is removed until the release; Esc / RMB cancels); a tiny
  box removes the one building under the cursor. Del removes the selection (boxed group or single), else the hovered
  one. The HQ is never removed.
- With units selected the wheel no longer zooms (Ctrl+wheel does); Esc clears the selection.
- Deposits: at most one blob per chunk (chance 0.45), digit weights decay**(digit-1) with decay 0.45 near the origin
  -> 0.8 far out (`world/generator.py`); re-probe the economy since 4-9 are now much rarer near the hub.
- Combat stats (kills) are transient; the game-over line shows kills since load.
- Phase 6 left: copy/paste blueprints, sounds, stats graphs, balance pass after a play test. Flow-field rebuild on very large bases
  (60k-tile cap) can cost ~200 ms when structures change during a wave (throttled to every 2 s).
- Android (phone round 1 done 2026-09-12, John to re-test): text is pygame's default font at 1.5x (no `consolas`
  on the phone; bundle a TTF in assets and point `render/numbers.font` at it if it still reads badly at a bigger
  "Text size"); buttons are 64 logical px x the "Button size" setting (100% = 96 device px, about 6 mm); the long
  press is 0.45 s; a second finger cancels a belt drag in progress (by design, so two-finger pan never commits
  half a line); at the extreme Settings (text 180% + buttons 200%) the wave timer and messages end up under the
  two button rows on the 720-px canvas; naming a new world depends on the soft keyboard committing text (space /
  enter), otherwise Create gives "World N"; F3/F6/F7 debug keys have no button; the Settings screen hides the
  Fullscreen row on the phone; deleting a world needs the Del key (desktop only); the first install of a new
  package name raises a Play Protect prompt (not repeated for updates); a Bluetooth mouse or keyboard would be
  ignored on the phone (mouse events are dropped in touch-only mode). No Esc / Del / Pick / HQ buttons any more:
  Back = Escape, the X tool demolishes, a long press = right click, the HQ button recentres.

## Next actions
0. John's phone round 2: round 1 (STATUS v10) gave him the Settings screen (text size, button size, hints, waves
   paused; fullscreen desktop-only), one row of buttons above the toolbar that appear only when useful, and no
   Esc / Del / Pick / HQ / zoom buttons. Expect follow-ups on the same lines (which button shows when, the sizes,
   whether "waves paused" should also stop camp raids). Change the touch layer or the desktop code, then
   `/android_update_copy` (sync -> build -> install -> run -> logs); the desktop code stays the master and
   `android/app/` is never edited by hand. APK 0.2.0 was built while his phone was away: install it with
   `python android\sync.py install run` when it is plugged in again (or he installs it from the GitHub release).
   Testers' reports arrive as GitHub issues on CARTER-BNW/digit-defender; new builds = a new release
   (CLAUDE.md "Releases for testers").
1. Expect the next round of play-test feedback (John gives tile coordinates / screenshots, usually from the Test Lab):
   rebuild the scene from the legend in `world/testworld.py`, reproduce headlessly, fix, screenshot-verify (dummy
   driver + Read the PNG is fine; keep scene tiles clear of the HUD rects), commit (local only). His existing Test Lab
   save gets the repair spawner via `testworld.top_up` on the next launch; everything else in his lab is as he left it.
2. Likely follow-ups from rounds 15-16 if he asks: formations that face the move direction; a way to cancel a queued
   unit (refund); repair units that prefer their own area; a fully walled base with no gate (units stuck inside).
3. When his remaining PNGs arrive (now incl. `spawner_repair.png`): same convention (32x32, hub 192x192, facing left,
   white transparent); check label overlap on miners/machines/spawners and the bridge.
4. Tick the Phase 4 design checkbox if John confirms; then the remaining Phase 6 items (sounds, stats graphs, blueprints,
   balance pass) per docs/PHASES.md; keep `/phase-gate` discipline and the gotchas log.
