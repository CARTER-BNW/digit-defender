# HANDOFF — Digit Defender
_Last updated: 2026-09-11 (v2) by Claude_

New-session bootstrap. Read this, then docs/PLAN.md (full design), docs/PHASES.md (checkpoints), idea.txt (original concept).

## Project state
- Directory: D:\Claude\projects\games\Digit Defender (git already initialized on main; local only, no GitHub)
- Status: **plan approved, nothing built. Start at Phase 0.**
- Stack: Python 3.12 on Windows, pygame-ce, numpy, opensimplex, pytest.
- Reference codebase to ADAPT (not copy): D:\Claude\projects\games\Pixel_Worlds
  (world/world.py chunk registry + lazy gen + keep/unload; world/chunk.py __slots__ + dirty-flag cached surface;
   world/generator.py pure seeded gen + noise upsample + region-grid stamping; world/persistence.py versioned
   .bin + meta.json; render/camera.py — needs zoom added; ui/menu.py; conftest.py headless SDL.)

## Game in one paragraph
Infinite borderless grid factory game (Beltmatic-like) crossed with base defense. No player character; free
pan + zoom camera. Chunks generate only when first seen. Mine digits 1-9, belt them through add/sub/mul/div
machines, deliver to a central 3x3 hub: face value adds to a number balance (starts 1000) that pays for
everything; hub posts target numbers for bonuses. Enemies: deterministic nests in distant chunks (raids) +
escalating timed waves. Hub destroyed = game over.

## Load-bearing decisions (do not re-litigate casually — rationale in PLAN.md)
1. Structures live in a world-level dict Factory.structures[(tx,ty)] -> Structure, NOT in terrain chunks.
   Terrain chunks = ground + deposits + nest tiles only; they unload freely; the factory ALWAYS simulates.
   Chunk-border belts and unload-vs-simulate are non-problems by construction.
2. Fixed timestep: 20 ticks/s accumulator in game.py, render 60 fps, MAX_TICKS_PER_FRAME=4 (drop excess).
3. sim/ package is headless — never imports pygame. All factory/combat logic pytest-tested windowless.
4. Deposits are infinite (terrain ~never modified; modified-chunk save machinery kept but mostly idle).
5. Deterministic sim: belts update in explicit downstream-first chain order (rebuilt on place/remove/rotate,
   never dict iteration order). Acid test: save@100 + load + run 100 == unsaved twin @200.
6. Every Structure has to_dict()/from_dict() FROM PHASE 2 so Phase 3 save/load is assembly.
7. Feed rule (whole upgrade system): an item entering a structure through a non-cargo side is consumed as
   feed (invested += value; invested drives level, speed/rate, AND max_hp; hp tracked separately for damage).
   Belts: head-on = feed, side = merge, tail = cargo. Machines: front = output, left/right = operands A/B,
   back = feed. Hub: all sides = income. sub/div results <= 0 are voided.
8. Ranged UNIT fire costs balance: long-range and heavy units deduct the fired number's value from balance
   per shot (long-range dmg 1 = 1/shot; heavy 100 = 100/shot); balance too low -> hold fire. Melee free.
   TOWERS are belt-fed ammo (no balance cost). Armies are an economic drain by design.
9. Zoom: discrete steps (0.25/0.5/0.75/1.0/1.5/2.0), cursor-anchored; chunks cache base surface at zoom 1.0
   (TILE_SIZE=32) + lazily scaled copy for the current step only. Number text via LRU-cached surfaces,
   abbreviated (1.2K); below zoom 0.5 items render as colored dots, no text.
10. Nests: deterministic region grid (12 chunks/region, nest-free within 1 region of origin, strength scales
    with distance); destruction recorded in a saved registry, never by editing terrain. Pathing: v1 greedy +
    attack-what-blocks, v2 shared BFS flow field from hub. No A*.

## Module layout (detail in PLAN.md)
main.py / game.py / settings.py / conftest.py / run.bat / requirements.txt
world/   terrain.py, chunk.py, generator.py, persistence.py
sim/     factory.py, structures.py, economy.py, leveling.py, combat.py, nests.py, pathing.py, serialize.py
render/  camera.py, renderer.py, numbers.py
ui/      hud.py, menu.py
tests/   test_generator|belts|machines|economy|leveling|persistence|combat.py
docs/    PLAN.md, PHASES.md, GOTCHAS.md  (idea.txt at root)
saves/   (gitignored) <slug>/meta.json, chunks/*.bin, structures.json, enemies.json

## Economy quick sheet
Start balance 1000. Costs: belt 2, wall 5, miner 10, tower 20, add/sub 500, mul/div 1000, spawner
ranged/melee 50, heavy 150. Demolish refund 50%. Repair costs balance. Ranged unit shots debit balance (#8).
Belt speed = base + 0.01 tiles/s per 100 fed. Level thresholds 100*2^k. Fed total (invested) drives max hp.

## Top pitfalls (full list PLAN.md §7)
- Always divmod() for tile->chunk coords (negative coords). Test borders -1/0 and 15/16 explicitly.
- Never iterate the structures dict for sim updates — chain order + (y,x)-sorted typed lists only.
- Never font.render or transform.scale chunks per frame — cache everything.
- Gameplay never writes terrain (nest death goes through the registry).
- Hub is 3x3: all 9 tiles map to the object; belt `next` resolution must accept any hub tile.
- Cap ticks/frame at 4 or a slow frame becomes a frozen game.

## First actions
1. Phase 0 scaffold per docs/PHASES.md (requirements.txt deps, settings.py, packages, conftest.py, run.bat).
2. Then Phase 1. Keep docs/GOTCHAS.md updated as you go; /phase-gate before advancing.
