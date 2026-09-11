# Digit Defender

Digit Defender - a Python game

> **Status:** Phases 0-5 built (terrain, factory, save/load, leveling, combat); Phase 6 polish in progress. See `docs/PHASES.md`.

Run `python main.py` (or `run.bat`). Tests: `python -m pytest -q`.

## Custom sprites
Drop PNGs into `assets/sprites/` named after the structure kind: `belt.png`, `miner.png`, `adder.png`,
`subtractor.png`, `multiplier.png`, `divider.png`, `wall.png`, `tower.png`, `spawner_ranged.png`,
`spawner_melee.png`, `spawner_heavy.png`, `hub.png`. Size: **32x32 px** per tile (`hub.png` is 96x96).
Draw them facing **up** (belts: flow upward); the game rotates them for the other directions and
scales them for every zoom level. Use a transparent background, or pure magenta (255, 0, 255) if your
editor cannot save transparency (Paint). Numbers, symbols and level badges are drawn on top.

## Project docs
| File | What it is |
|---|---|
| `HANDOFF.md` | Current state — read first in a new session |
| `STATUS.md` | Session log |
| `docs/PHASES.md` | Roadmap and phase checkpoints |
| `docs/GOTCHAS.md` | Known traps |
