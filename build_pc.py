"""Windows test build: dist/DigitDefender-<version>-win64.zip, a PyInstaller
one-folder app (unzip, run DigitDefender.exe; saves and config.json are
written next to the exe: world/persistence.ROOT follows sys.executable when
frozen).

    python build_pc.py [--version X.Y.Z] [--no-zip]

The version defaults to android/VERSION so the PC and the phone builds of a
release carry the same number. Needs `pip install pyinstaller`; Pillow, when
installed, turns android/icon.png into the exe icon. Output dirs build/pc and
dist/ are gitignored. Release recipe: CLAUDE.md "Releases for testers".
"""
import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "DigitDefender"
DIST = ROOT / "dist" / "pc"
WORK = ROOT / "build" / "pc"
# not imported by the game; keeps optional accelerators / test tools out of the bundle
EXCLUDES = ("numba", "llvmlite", "tkinter", "matplotlib", "scipy", "IPython", "pytest", "PIL")


def version(arg):
    if arg:
        return arg
    try:
        return (ROOT / "android" / "VERSION").read_text().strip()
    except OSError:
        return "0.0.0"


def make_icon():
    """android/icon.png -> build/pc/icon.ico (None when Pillow or the PNG is missing)."""
    src = ROOT / "android" / "icon.png"
    if not src.exists():
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    WORK.mkdir(parents=True, exist_ok=True)
    ico = WORK / "icon.ico"
    Image.open(src).convert("RGBA").save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    return ico


def build(ver):
    icon = make_icon()
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
           "--name", NAME, "--distpath", str(DIST), "--workpath", str(WORK), "--specpath", str(WORK),
           "--add-data", f"{ROOT / 'assets'}{os.pathsep}assets"]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    if icon is not None:
        cmd += ["--icon", str(icon)]
    cmd.append(str(ROOT / "main.py"))
    print("[build_pc] " + " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)
    app = DIST / NAME
    (app / "VERSION").write_text(ver + "\n", encoding="utf-8")
    (app / "README.txt").write_text(
        f"Digit Defender {ver} (Windows test build)\n\n"
        "Run DigitDefender.exe. Windows SmartScreen may warn about an unknown publisher:\n"
        "More info -> Run anyway. Saves and config.json are written next to the exe, so\n"
        "keep the folder together; a newer build can replace the folder (copy saves/ over).\n"
        "F1 in the game lists the controls and rules.\n"
        "Feedback: https://github.com/CARTER-BNW/digit-defender/issues\n", encoding="utf-8")
    return app


def zip_app(app, ver):
    out = ROOT / "dist" / f"{NAME}-{ver}-win64.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(app.rglob("*")):
            zf.write(path, str(Path(NAME) / path.relative_to(app)))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Windows one-folder build of Digit Defender (PyInstaller)")
    p.add_argument("--version", default=None, help="defaults to android/VERSION")
    p.add_argument("--no-zip", action="store_true", help="build the folder only")
    args = p.parse_args(argv)
    ver = version(args.version)
    app = build(ver)
    print(f"[build_pc] app folder: {app}")
    if not args.no_zip:
        out = zip_app(app, ver)
        print(f"[build_pc] zip: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
