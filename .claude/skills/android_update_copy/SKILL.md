---
name: android_update_copy
description: Refresh the Android copy of Digit Defender from the desktop code, rebuild the APK in the WSL build box, install and run it on the USB phone, and report what landed
---

# Android update copy

The Android version is the desktop game plus a touch layer (`android/mobile/`), packaged by
python-for-android inside the WSL distro `dd-android` (Ubuntu on `D:\WSL`). `android/sync.py`
drives every step; `android/README.md` has the details and the phone controls.

## 0. Preconditions
- `python android\sync.py status` - the phone must show `device` (not `unauthorized`: accept the
  USB-debugging prompt on the phone), the build box `present` and the toolchain `installed`.
  Missing build box: `python android\sync.py setup` (one-time, ~10 min, downloads Ubuntu to `D:\WSL`).
- The desktop suite is green: `python -m pytest -q` (it includes `tests/test_android_touch.py`).

## 1. Sync the copy
`python android\sync.py sync` - wipes and refills `android/app/` (game.py, settings.py, sim/, world/,
render/, ui/, assets/ plus mobile/ and a generated main.py), bumps `android/VERSION` (patch number)
and rewrites `version =` in `android/buildozer.spec`. Pass `--version X.Y.Z` for a deliberate number.
If the desktop code gained a new package or top-level module, add it to `COPY_DIRS` / `COPY_FILES`
in `android/sync.py` first.

## 2. Check the phone layout on the PC (optional, 30 s)
`python android\app\main.py --desktop --world lab --frames 120` opens the phone layout in a window
(mouse = finger). Any AttributeError here means game.py changed a hook the touch layer relies on
(`handle_event`, `draw`, `set_tool`, `belt_path`, `box_start`, `hud.over_ui`): fix `android/mobile/`.

## 3. Build
`python android\sync.py build` - run it in the background (first build 30-60 min, later builds
2-5 min) and watch `android/build.log`. Success prints `built in N min: <apk>`; the APK lands in
`android/bin/`. On a failure, search `android/build.log` for the last `Command failed` and read the
60 lines above it (buildozer's env dump hides the real error); recipe / toolchain problems are fixed
in `android/buildozer.spec`, `android/p4a-recipes/` (pygame-ce recipe) or `android/wsl/*.sh`, then
rebuild. After changing a recipe's version, remove that recipe's dirs under
`~/dd-android/.buildozer/android/platform/build-arm64-v8a/{build/other_builds,packages}/` in the
box (p4a reuses an unpacked tree). `python android\sync.py clean build` rebuilds the whole project
from scratch (the SDK/NDK cache stays). docs/GOTCHAS.md lists the traps already hit.

## 4. Install, run, check the log
`python android\sync.py install run logs` - installs over the previous version (saves are kept:
they live in the app's private data dir, not in the unpacked app), launches it, waits 10 s and
dumps the python / SDL lines from logcat. A `Traceback` there is a bug to fix; `--follow 30` streams
30 s live. Reinstalling never needs an uninstall; a downgrade is allowed.

## 5. Report and record
- Tell John: version on the phone, APK size, anything the log complained about, and what changed in
  the touch layer if anything.
- Note the version in STATUS.md when wrapping the session; commit `android/` sources (never `app/`,
  `bin/`, `build.log` - `android/.gitignore` covers them).
