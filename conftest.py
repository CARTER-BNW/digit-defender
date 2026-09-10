import os

# Headless SDL so tests run without opening a window (render/ui tests only;
# sim/ and world/generator.py never touch pygame at all).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
