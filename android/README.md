# Digit Defender on Android

The phone build is the desktop game, untouched, plus a touch layer (`mobile/`) packaged as an
APK by python-for-android (buildozer). The desktop code stays the master: `sync.py` copies it in.

## Pipeline (all on D:)
| Piece | Where | What |
|---|---|---|
| `sync.py` | this folder | the tool: `python android\sync.py [sync|setup|build|clean|install|run|logs|status|all]` |
| `mobile/` | this folder | touch layer: `touch.py` (gestures + on-screen buttons), `entry.py` (the phone's main.py) |
| `app/` | generated | the synced copy of the game + `mobile/` + `main.py` stub (gitignored) |
| `buildozer.spec`, `VERSION`, `icon.png`, `presplash.png` | this folder | packaging config; `sync` bumps VERSION and rewrites `version =` |
| `p4a-recipes/pygame/` | this folder | local python-for-android recipe: pygame-ce 2.5.8 (the desktop's pygame) instead of p4a's pygame 2.1.0, which cannot build on p4a's Python 3.14 |
| `wsl/setup.sh`, `wsl/build.sh` | this folder | run inside the WSL build box |
| `dd-android` | `D:\WSL\dd-android` | Ubuntu 24.04 WSL distro holding buildozer, the Android SDK/NDK and the build dir (`~/dd-android`) |
| `bin/*.apk`, `build.log` | this folder | outputs (gitignored) |
| adb | `D:\Android\sdk\platform-tools\adb.exe` | install / run / logcat (override with the `ADB` env var) |

Typical update: `python android\sync.py all` (sync, build, install, run, log dump). The Claude
skill `/android_update_copy` walks through it with checks.

The build runs in the Linux filesystem (`~/dd-android` inside the distro, mirrored with rsync
from this folder) because python-for-android is Linux-only and dislikes paths with spaces.
The first build downloads the SDK/NDK and compiles Python, SDL2, numpy and pygame (30-60 min);
later builds take a few minutes.

## On the phone
- Build facts: python-for-android (May 2026) with CPython 3.14, SDL 2.30, numpy from git, pygame-ce 2.5.8
  through `p4a-recipes/pygame`, NDK r28c, targetSdk 36 (Android 16's Play Protect refuses sideloaded APKs
  targeting 33), predictive back disabled in the manifest (`manifest_application_args.xml`) so the Back key
  reaches the game. docs/GOTCHAS.md explains each of those.
- Logical canvas: 720 px high, width from the screen aspect (Pixel 9a: 1616x720), scaled up by SDL
  (`pygame.SCALED`), so the HUD keeps its desktop layout. Landscape only, immersive fullscreen.
- Saves and config: `/data/data/org.johncarter.digitdefender/files/digit_defender/` (survive updates;
  an uninstall deletes them). `adb shell run-as org.johncarter.digitdefender ls files/digit_defender/saves`.
- The app saves when it goes to the background and every 60 s; the Back button acts as Escape
  (cancel tool / clear selection / menu; in the menu: back into the world) and never quits.
- Log: `python android\sync.py logs` (python + SDL tags), `--follow 30` for a live stream.

## Controls
| Touch | Action |
|---|---|
| tap | left click: select, place, train (spawner), toolbar, minimap, HQ button |
| long press (0.45 s, a ring closes in) | right click: move selected units / gather point / cancel the tool / clear selection |
| one-finger drag | pan; with a build tool it is the left-button drag (belt path, paint, demolish box); with **Box** armed it is a selection box |
| two-finger drag | pan (also while a tool is active) |
| pinch | zoom in / out one step per 22% change, anchored at the pinch |
| two-finger tap | middle click: patrol between the rally point and the tap (units selected) |
| Back button | Escape |

On-screen buttons sit in one row just above the toolbar and appear only while they can do
something (John, phone round 1). Left end, the actions: **Rot** R (a tool with a facing, or a
rotatable building selected), **Shift** (sticky: straight belt drag / add to a selection; shown
with the belt tool, with a selection, or while on), **Box** (next drag selects; no tool active),
**Upg** U (something selected), **Fix** H (a selected building is damaged), **Split** T (a belt
selected), **Train** C (a spawner selected), **Form** (units selected: next formation). Right end:
**Pause**, **Speed** x1/x2/x4, **Help** F1, **Save**, **Menu**, and **Load** on the game-over screen
(when both ends would overlap, the right group moves one row up). Gone on purpose: Esc (the Back
key), Del (the X tool), Pick, HQ (the HQ button in the right column) and the zoom buttons (pinch).
Menu > Settings: text size, button size (toolbar + these buttons), info hints (off by default on the
phone), enemy waves on / paused; the fullscreen row is desktop-only.

Naming a new world: the New World screen opens the soft keyboard; letters arrive when the keyboard
commits a word (space / enter), or just tap Create for an automatic name.

## Testing on the PC
- `python -m pytest tests/test_android_touch.py -q` drives the layer with finger events headlessly.
- `python android\app\main.py --desktop --world lab` (after a sync) shows the phone layout in a
  window; the left mouse button acts as a finger (tap / drag / hold), the wheel and other buttons
  stay native.
