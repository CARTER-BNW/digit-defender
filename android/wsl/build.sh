#!/usr/bin/env bash
# Build the Digit Defender APK inside the WSL build box (run as root by
# android/sync.py build).  DD_SRC = the android folder as a WSL path
# (/mnt/d/...), DD_MODE = debug (default) | release | clean.  (Environment
# variables, not positionals: `wsl -- bash -c script args` drops the args.)
# The folder is mirrored into the Linux filesystem first: builds there are
# fast and python-for-android never sees a path with spaces.
set -euo pipefail
SRC="${DD_SRC:-${1:-}}"
MODE="${DD_MODE:-${2:-debug}}"
if [ -z "$SRC" ]; then
    echo "DD_SRC (the android folder as a wsl path) is not set"
    exit 2
fi
export PATH="$HOME/.local/bin:$PATH"
export PIP_BREAK_SYSTEM_PACKAGES=1
WORK="$HOME/dd-android"
mkdir -p "$WORK"
rsync -a --delete --exclude '.buildozer' --exclude 'bin' --exclude '__pycache__' \
      --exclude 'build.log' --exclude '.pytest_cache' "$SRC/" "$WORK/"
find "$WORK" -name '*.sh' -exec sed -i 's/\r$//' {} +
cd "$WORK"
if [ "$MODE" = "clean" ]; then
    rm -rf "$WORK/.buildozer" "$WORK/bin"
    echo "== project build dir removed (the SDK/NDK cache in ~/.buildozer stays) =="
    exit 0
fi
# an android.api change needs a fresh dist: p4a bakes the API into dists/<name>/project.properties
# and buildozer does not notice (the APK would keep the old targetSdkVersion)
API=$(sed -n 's/^android\.api *= *\([0-9]*\).*/\1/p' buildozer.spec | head -n 1)
for props in .buildozer/android/platform/build-*/dists/*/project.properties; do
    [ -f "$props" ] || continue
    CUR=$(sed -n 's/^target=android-//p' "$props")
    if [ -n "$API" ] && [ -n "$CUR" ] && [ "$CUR" != "$API" ]; then
        echo "== dist was created for API $CUR, the spec wants $API: re-creating the dist =="
        rm -rf "$(dirname "$props")"
    fi
done
echo "== buildozer android $MODE  (work dir $WORK) =="
set +e
buildozer android "$MODE" 2>&1 | tee "$WORK/build.log"
STATUS=${PIPESTATUS[0]}
set -e
mkdir -p "$SRC/bin"
if [ "$STATUS" -ne 0 ]; then
    echo "== BUILD FAILED (exit $STATUS) - see build.log =="
    exit "$STATUS"
fi
cp -f "$WORK"/bin/*.apk "$SRC/bin/"
echo "== APK(s) copied to $SRC/bin =="
ls -la "$SRC/bin"
