# Digit Defender

Digit Defender - a Python game

> **Status:** Phases 0-5 built (terrain, factory, save/load, leveling, combat); Phase 6 polish in progress. See `docs/PHASES.md`.

Run `python main.py` (or `run.bat`). Tests: `python -m pytest -q`.

## Custom sprites
Drop PNGs into `assets/sprites/` named after the structure kind: `belt.png`, `miner.png`, `adder.png`,
`subtractor.png`, `multiplier.png`, `divider.png`, `wall.png`, `tower.png`, `spawner_ranged.png`,
`spawner_melee.png`, `spawner_heavy.png`, `hub.png`. Size: **32x32 px** per tile (`hub.png` is 96x96).
Draw everything facing **left** (a belt flows to the left, a machine outputs to the left, a tower's ammo
intake is on the left); the game rotates for the other directions and scales for every zoom level.
Pure white (255, 255, 255) and pure magenta (255, 0, 255) are treated as transparent, so a Paint white
background just disappears (use 254,254,254 if you want real white). Numbers, symbols and level badges
are drawn on top.

Belts pick a shape from their connections: `belt.png` straight (arrow pointing left), `belt_corner.png`
(openings bottom + right), `belt_t.png` (openings bottom + left + right), `belt_cross.png` (all four).
The game rotates each shape so its openings match the belt's inputs and output; missing shapes fall
back to the straight belt.

## Project docs
| File | What it is |
|---|---|
| `HANDOFF.md` | Current state — read first in a new session |
| `STATUS.md` | Session log |
| `docs/PHASES.md` | Roadmap and phase checkpoints |
| `docs/GOTCHAS.md` | Known traps |
