# Release notes

## v0.2.0 - first public test build (2026-09-12)

Digit Defender is a factory-builder crossed with base defence on an endless grid: mine the digits 1-9,
build number lines through math machines, deliver to your HQ, and defend it against waves and camps.

**Android:** `digitdefender-0.2.0-arm64-v8a-debug.apk` runs on Android 7.0 or newer, 64-bit (arm64) phones,
landscape. It is a sideloaded test build, not from the Play Store: allow "install unknown apps" for the app
you open it with and accept the Play Protect warning ("Install anyway"). Updates install over the previous
version and keep the saves.

**Windows:** `DigitDefender-0.2.0-win64.zip`: unzip anywhere, run `DigitDefender.exe`. It is an unsigned test
build, so SmartScreen warns: "More info", then "Run anyway". Saves and settings are written next to the exe.
Windows 10/11, 64-bit. Linux and macOS: run from source.

**From source (any OS):** clone the repo, `pip install -r requirements.txt`, `python main.py` (Python 3.12).

### What is in this build
- Factory: miners on digit deposits, belts drawn by dragging (auto-turning preview, merges, forced T-splits,
  bridges that cross without mixing), adder / subtractor / multiplier / divider, HQ deliveries as income,
  four levelled targets that pay a bonus for delivering an amount of a number.
- Levels: feed numbers into a building's yellow sides or pay [U] / **Upg** to level it; levels raise belt
  speed, machine and miner rates, tower fire rate, spawner speed and hit points.
- Defence: walls (they link up), belt-fed towers (range 10), spawners that train ranged / melee / heavy /
  repair units for balance, RTS-style orders (select, move, formations box / line / column / wedge / ring,
  patrol), waves every ten minutes, enemy camps that raid when you build within 48 tiles of them, an
  always-present camp about 100 tiles from the HQ.
- Phone: tap, hold (lift = right click, drag = selection box), one- and two-finger pan, pinch zoom,
  two-finger tap = patrol order; a row of buttons above the toolbar that appear only when they can act;
  Settings for text size, button size, info hints and pausing the waves.
- Saves: autosave every minute and on exit, several worlds, a "Test lab" world with every part laid out.

### Known issues and gaps
- Debug-signed APK, 64-bit only (no 32-bit phones), no sound, no statistics screen, economy not balanced
  (it is easy to get rich once a few lines run).
- At the largest text and button sizes together, the wave timer and messages hide behind the button rows.
- "Enemy waves: Paused" freezes the wave countdown only; camp raids still come if you build near a camp.
- A queued unit cannot be cancelled for a refund; an accidental tap on a spawner costs its unit price.
- Naming a new world on the phone depends on the soft keyboard committing text (space / enter); otherwise
  the world is called "World N".

### Feedback
Open a GitHub issue: what you did, what you expected, what happened, phone model and Android version, and
a screenshot if you have one.
