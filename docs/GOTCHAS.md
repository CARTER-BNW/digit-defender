# Gotchas

Format: Symptom / Cause / Fix. Add an entry the moment a trap is found (`/gotcha`).

## hash() of tuples with strings is salted per process
- **Symptom:** "deterministic" generation that seeds random.Random(hash((seed, cx, cy, "dep"))) differs between runs.
- **Cause:** Python salts str hashes per process (PYTHONHASHSEED), so hash() of any tuple containing a string changes every launch.
- **Fix:** seed with a string: random.Random(f"{seed}:{cx}:{cy}:dep") (str seeds go through sha512, stable everywhere). Used in world/generator.py and sim/nests.py.

## Cached pygame Fonts die across pygame.quit()/init()
- **Symptom:** pygame.error: Invalid font (font module quit since font created) in the second test that builds a Game.
- **Cause:** render/numbers.py LRU-caches Font objects; tests call pygame.quit() between Games, invalidating cached fonts.
- **Fix:** Renderer.__init__ calls numbers.reset() (clears both caches) right after pygame.font.init().

## Stale hover tile regenerates chunks that streaming just dropped
- **Symptom:** after flying 200 chunks away, chunk (0,0) is still loaded every frame.
- **Cause:** HUD hover info and the ghost preview query terrain at game.hover_tile; if the mouse never moved, that tile is far off-screen and get_tile() regenerates its chunk each frame right after update() unloads it.
- **Fix:** Game.update() recomputes hover_tile from the current mouse position every frame, so hover queries always land inside the visible (kept) area.

## Backslash-n inside a Bash heredoc patch script becomes a real newline
- **Symptom:** game.py stopped importing: SyntaxError "unterminated string literal" at a line that should read fh.write(... + "\n").
- **Cause:** the Bash tool layer unescapes backslashes before bash sees the (quoted) heredoc, so a Python patch script containing an escaped newline wrote a literal line break into the source.
- **Fix:** never route escape sequences through Bash heredocs; use the Edit/Write tools for any text containing backslashes. Always run the test suite (which imports game.py) before committing.

## Belt items are 3-field lists, not (value, progress) pairs
- **Symptom:** `ValueError: too many values to unpack` in code doing `for v, p in belt.items`.
- **Cause:** since STATUS v5 every item is `[value, progress, entry_rel]`; the third field is render-only (corner animation) and the sim never reads it, but pair-unpacking anywhere breaks.
- **Fix:** index (`it[0]`, `it[1]`) or unpack with `v, p, *_`. `Belt.to_dict/from_dict` accept both shapes (old two-field saves load with entry BACK); tests that hand-append items may still append pairs.

## A short scripted run shows an "empty" belt line that is actually fine
- **Symptom:** a verification script places a miner + belts + bridge, runs 60 ticks, and the belts past the bridge carry nothing (looks like a broken link).
- **Cause:** a new miner's timer starts at the BASE period (40 ticks) even if `invested` is raised right after placement, and level-1 belts move 1 tile/s (0.05 tiles/tick), so nothing reaches tile 5 of a line inside 60 ticks.
- **Fix:** run 200+ ticks before judging a line (or set `miner.timer = 0`); check `stats["mined"]` and the items on the FIRST belt before suspecting the links.

## A second Combat on the same Factory silently takes over its ticks
- **Symptom:** in a test, a unit stops moving right after a save round-trip check that built `Combat(f, ..., units=records)` on the same factory.
- **Cause:** `Combat.__init__` sets `factory.combat = self`; `Factory.tick()` ticks whatever `combat` points at, so the original Combat (and its units) is no longer simulated.
- **Fix:** restore `f.combat = c` after building a throwaway Combat, or build the twin on its own Factory (tests/test_combat.py does the former).

## Long Bash heredocs silently fail in this tool
- **Symptom:** "unexpected EOF while looking for matching quote" from a multi-file heredoc command; nothing written.
- **Cause:** suspected tool-side length limit (~8 KB) on a single Bash command; large heredocs get cut mid-line.
- **Fix:** write big files with the Write tool; keep Bash heredocs short (patch scripts, small files).

## `wsl -- bash -c script args` drops the positional arguments
- **Symptom:** android/wsl/build.sh died with `1: android folder (wsl path)`; inside the script `$0` was `/bin/bash` and `$1`, `$2` empty, although Python's subprocess passed them (a direct `wsl -- printf ... "a b" c` receives its args intact, spaces included).
- **Cause:** wsl.exe forwards `bash -c <script>` but loses whatever follows the script string.
- **Fix:** `android/sync.py wsl_bash()` puts parameters into the command string as environment assignments (`DD_SRC='...' DD_MODE=debug bash /tmp/dd_build.sh`); the scripts read `DD_*` with a positional fallback. Same for any future `wsl -- bash -c` call.

## python-for-android's libffi recipe dies in autoreconf on a fresh Ubuntu 24.04
- **Symptom:** the first APK build fails after ~7 min with `configure.ac:215: error: possibly undefined macro: LT_SYS_SYMBOL_USCORE` / `autoreconf: error: /usr/bin/autoconf failed` (buried 60 lines above buildozer's "Command failed" env dump in android/build.log).
- **Cause:** that macro lives in libtool's `ltdl.m4`, shipped by `libltdl-dev`, which the usual buildozer apt list leaves out.
- **Fix:** `apt-get install libltdl-dev` (now in android/wsl/setup.sh); rerun `python android\sync.py build`, cached recipes (hostpython3 etc.) are reused.

## Android 16's Play Protect refuses a sideloaded APK that targets API 33
- **Symptom:** `adb install` hangs, the phone shows "Google Play Protect - Unsafe app blocked - This app was built for an older version of Android and doesn't include the latest privacy protections" with only OK, and adb then reports `INSTALL_FAILED_VERIFICATION_FAILURE: Install not allowed`.
- **Cause:** buildozer's default `android.api` is 33 (the APK's targetSdkVersion); the Pixel 9a on Android 16 treats that as too old for sideloading.
- **Fix:** `android.api = 36` in android/buildozer.spec (p4a has no upper bound, only MIN_TARGET_API 30; buildozer downloads platforms;android-36 itself) AND delete the dist, `rm -rf ~/dd-android/.buildozer/android/platform/build-arm64-v8a/dists/digitdefender` in the box: p4a bakes the API into the dist's `project.properties` when it creates the dist, buildozer does not notice the spec change, and the APK keeps targetSdkVersion 33 (check with `aapt dump badging`). Re-creating the dist from the compiled recipes takes a minute. Read a stuck dialog with `adb shell uiautomator dump /sdcard/x.xml` + `adb shell cat` from PowerShell, not Git Bash (MSYS rewrites `/sdcard/...` into a Windows path). The developer option "Verify apps over USB" (`settings put global verifier_verify_adb_installs 0`) would also silence Play Protect for adb installs; not used.

## With targetSdk 36 the phone's Back key kills the app instead of reaching SDL
- **Symptom:** Back on the Pixel 9a closed Digit Defender at once (logcat: a CLOSE transition, onPause/onDestroy, "exited cleanly (0)"), although the save was written and `SDL_ANDROID_TRAP_BACK_BUTTON=1` was set and mobile/entry maps K_AC_BACK to Escape.
- **Cause:** apps targeting API 36 get Android's predictive back by default: the system invokes the back callback (default = finish) and never dispatches a KEYCODE_BACK key event, so neither SDLActivity.handleKeyEvent (which would hand SDL an AC_BACK key) nor onBackPressed (which honours the trap hint) runs.
- **Fix:** `android/manifest_application_args.xml` holds `android:enableOnBackInvokedCallback="false"`, appended to `<application>` through buildozer's `android.extra_manifest_application_arguments`; the legacy key flow returns and Back arrives in pygame as K_AC_BACK. Test with `adb shell input keyevent KEYCODE_BACK`: the menu must appear and `adb shell pidof org.johncarter.digitdefender` must stay non-empty.

## python-for-android's stock pygame recipe is pygame 2.1.0 and cannot build on its Python 3.14
- **Symptom:** the APK build dies in `Building compiled components in pygame` with `src_c/_sdl2/sdl2.c: fatal error: 'longintrepr.h' file not found` (Cython 0.29 output for a header Python 3.12+ removed); the numpy `ERROR: No matching distribution found for numpy==2.3.0` a few hundred lines earlier is only p4a's `--dry-run` wheel probe and is harmless.
- **Cause:** p4a (2026) still pins pygame 2.1.0 (2021) while shipping CPython 3.14; the GitHub archive has no generated C for the `_sdl2` Cython modules, so the host `cython` on PATH (0.29.37, pinned by buildozer's `cython<3.0`) generates it.
- **Fix:** `android/p4a-recipes/pygame/__init__.py` (buildozer `p4a.local_recipes = ./p4a-recipes`) keeps the stock recipe's steps but downloads pygame-ce 2.5.8 (the desktop's pygame; declares Python 3.14) and sets `hostpython_prerequisites = ['setuptools', 'Cython>=3.0.11']` so p4a's host python can `import Cython` (pygame-ce's setup.py cythonizes itself; without it: "You need cython"). Second trap in the same recipe: p4a installs with `pip install .`, which obeys pygame-ce's pyproject build backend meson-python and dies in `meson setup` ("Could not invoke sanity check executable ... wrong architecture": a native meson build with the cross clang). The recipe rewrites `[build-system]` to `setuptools.build_meta:__legacy__` (the same setup.py p4a just compiled with) and installs with `--no-build-isolation --no-deps`. When a recipe version changes, delete `~/dd-android/.buildozer/android/platform/build-arm64-v8a/{build/other_builds,packages}/<recipe>` first: p4a keeps an already-unpacked source tree regardless of version.

