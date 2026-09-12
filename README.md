# Digit Defender

A factory-builder crossed with base defence on an endless grid. Mine the digits 1-9, run them along
belts through adders, subtractors, multipliers and dividers, deliver numbers to your HQ for income
and target bonuses, and spend that balance on walls, belt-fed towers and trained units: enemy waves
come every ten minutes and the camps around you raid when you build too close. HQ destroyed = game over.

Written in Python with pygame-ce. Runs on a PC from source and on Android as an APK.

> **Status:** playable test build. Phases 0-5 done (terrain, factory, save/load, leveling, combat);
> Phase 6 polish in progress. See `docs/PHASES.md` and `docs/RELEASE_NOTES.md`.

## Play on Android (testers)
1. Download the newest `digitdefender-<version>-arm64-v8a-debug.apk` from the
   [Releases page](https://github.com/CARTER-BNW/digit-defender/releases).
2. Needs Android 7.0 or newer on a 64-bit (arm64) phone, landscape. That is nearly every phone since 2017.
3. Open the APK to install it. Allow "install unknown apps" for your browser or file manager if asked, and
   when Play Protect warns that the app is not from the store choose "Install anyway" / "More details".
   Updates install over the old version and keep your saves.
4. Controls: [android/README.md](android/README.md) (tap, hold, drag, pinch, two-finger tap, the button
   row above the toolbar). The in-game **Help** button lists the rules; **Menu > Settings** has text and
   button sizes, info hints and a switch to pause the enemy waves while you learn the factory side.
5. Feedback: open a GitHub issue with what you did, what you expected, what happened, your phone model
   and Android version, and a screenshot if you have one.

## Play on Windows (testers)
Download `DigitDefender-<version>-win64.zip` from the
[Releases page](https://github.com/CARTER-BNW/digit-defender/releases), unzip it anywhere and run
`DigitDefender.exe`. SmartScreen warns about an unknown publisher on an unsigned test build: "More info",
then "Run anyway". Saves and settings are written next to the exe, so keep the folder together; a newer
build can replace the folder (copy `saves/` across). F1 in the game shows the controls and rules.

## Play from source (Windows, Linux, macOS)
Python 3.12. `pip install -r requirements.txt`, then `python main.py` (world menu) or `run.bat`.
`python build_pc.py` makes the Windows zip above (PyInstaller, one-folder app).
`python main.py --world NAME` skips the menu; `python main.py --testworld` (or the menu entry "Test lab")
opens a hand-built world with every part and junction type laid out around the HQ (`world/testworld.py`
has the legend). F1 shows the controls and rules in the game. Tests: `python -m pytest -q`.

## Custom sprites
Drop PNGs into `assets/sprites/` named after the structure kind: `belt.png`, `bridge.png` (a crossing; never rotated), `miner.png`, `adder.png`,
`subtractor.png`, `multiplier.png`, `divider.png`, `wall.png`, `tower.png`, `spawner_ranged.png`,
`spawner_melee.png`, `spawner_heavy.png`, `spawner_repair.png`, `hub.png`. Size: **32x32 px** per tile (`hub.png` is 192x192: the HQ is 6x6).
Draw everything facing **left** (a belt flows to the left, a machine outputs to the left; miners, walls
and towers have no facing); the game rotates for the other directions and scales for every zoom level.
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
| `docs/RELEASE_NOTES.md` | What each released build contains and its known issues |
| `android/README.md` | The phone build: pipeline, install facts and controls |
