"""Android entry point: what the APK runs as main.py (android/sync.py writes
a two-line main.py that calls this). Same world loop as the desktop main.py,
with the touch layer (mobile.touch) on top of the untouched Game / Menu.

    python android/app/main.py --desktop [--world NAME] [--frames N] [--size 1616x720]

--desktop runs the phone layout in a window on the PC: the mouse acts as one
finger (left button = tap / drag / long press), wheel and the other buttons
stay native. On the phone the display is a logical 720-px-high canvas scaled
to the screen (pygame.SCALED), so the HUD keeps its desktop layout.
"""
import argparse
import os
import sys
import traceback
from pathlib import Path

import pygame

from world import persistence, testworld
from render import numbers
from ui.menu import Menu
from game import Game
from .touch import TouchLayer, STATE, FINGER_EVENTS

LOGICAL_H = 720
MIN_LOGICAL_W = 1180                  # narrower and the toolbar + minimap would not fit
DEFAULT_DESKTOP_SIZE = (1616, 720)    # a Pixel 9a's 2424x1080 at 1.5x

MOUSE_EVENTS = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL)
K_AC_BACK = getattr(pygame, "K_AC_BACK", -1)
BACKGROUND_EVENTS = tuple(getattr(pygame, name) for name in
                          ("APP_WILLENTERBACKGROUND", "APP_DIDENTERBACKGROUND", "APP_TERMINATING")
                          if hasattr(pygame, name))


def on_android():
    return ("ANDROID_PRIVATE" in os.environ or "ANDROID_ARGUMENT" in os.environ
            or hasattr(sys, "getandroidapilevel"))


def escape_event():
    return pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="\x1b", scancode=0)


class MobileGame(Game):
    """Game with finger input. touch_only=True (the phone): the mouse events
    SDL mirrors from touches are dropped, fingers drive everything. False
    (--desktop): the left mouse button acts as a finger."""
    touch_only = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_hints = False                 # the right-hand buttons take that space
        self.touch = TouchLayer(self)
        orig = self.hud.over_ui
        self.hud.over_ui = lambda pos, _o=orig: _o(pos) or self.touch.hit(pos)
        self._mouse_finger = False

    def dispatch(self, ev):
        """The desktop handler (what the touch layer feeds)."""
        Game.handle_event(self, ev)

    def handle_event(self, ev):
        t = ev.type
        if t in FINGER_EVENTS:
            self.touch.handle(ev)
            return
        if t == pygame.MULTIGESTURE:
            return
        if t in BACKGROUND_EVENTS:
            self.background_save()
            return
        if t == pygame.KEYDOWN and ev.key == K_AC_BACK:
            ev = escape_event()
        elif t in MOUSE_EVENTS:
            if self.touch_only:
                return
            if self._emulate_finger(ev):
                return
        self.dispatch(ev)

    def _emulate_finger(self, ev):
        t = self.touch
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._mouse_finger = True
            t.finger_down(0, ev.pos)
            return True
        if ev.type == pygame.MOUSEMOTION and self._mouse_finger:
            t.finger_motion(0, ev.pos)
            return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self._mouse_finger:
            self._mouse_finger = False
            t.finger_up(0, ev.pos)
            return True
        return False

    def background_save(self):
        """Android pauses the app: keep the progress (the loop blocks until
        the app is back in front)."""
        if self.meta is not None and not self.game_over:
            try:
                self.save()
            except Exception:                   # never crash on the way to the background
                traceback.print_exc()

    def update(self, dt):
        self.touch.update(dt)                   # long press before the frame acts on it
        super().update(dt)

    def draw(self):
        self.renderer.draw(self)
        self.hud.draw(self)
        self.touch.draw(self.screen)
        try:
            pygame.display.flip()
        except pygame.error:                    # surface gone while backgrounded
            pass

    def toggle_fullscreen(self):
        """[F11]: the phone is always fullscreen; a set_mode here would drop
        the scaled canvas."""


class MobileMenu(Menu):
    def _toggle_fullscreen(self):
        self.config["fullscreen"] = True
        persistence.save_config(self.config)

    def _new_world(self):
        pygame.key.start_text_input()           # soft keyboard for the name / seed
        try:
            return super()._new_world()
        finally:
            pygame.key.stop_text_input()


# ---- pygame patches -------------------------------------------------------------

_REAL = {}


def install_patches(touch_only):
    """Back button -> Escape (also inside the menu loop), sticky Shift from the
    overlay, and on the phone mouse.get_pos() = the last finger position."""
    if not _REAL:
        _REAL.update(event_get=pygame.event.get, get_mods=pygame.key.get_mods,
                     get_pos=pygame.mouse.get_pos)
    real_get = _REAL["event_get"]
    real_mods = _REAL["get_mods"]

    def event_get(*args, **kwargs):
        out = []
        for ev in real_get(*args, **kwargs):
            if ev.type == pygame.KEYDOWN and ev.key == K_AC_BACK:
                out.append(escape_event())
            elif ev.type == pygame.KEYUP and ev.key == K_AC_BACK:
                continue
            else:
                out.append(ev)
        return out

    pygame.event.get = event_get
    pygame.key.get_mods = lambda: real_mods() | STATE["mods"]
    pygame.mouse.get_pos = (lambda: STATE["last_pos"]) if touch_only else _REAL["get_pos"]


def uninstall_patches():
    if _REAL:
        pygame.event.get = _REAL["event_get"]
        pygame.key.get_mods = _REAL["get_mods"]
        pygame.mouse.get_pos = _REAL["get_pos"]


# ---- display --------------------------------------------------------------------

def open_display(args, android):
    if android and not args.desktop:
        info = pygame.display.Info()
        nw, nh = info.current_w, info.current_h
        if nw < nh:
            nw, nh = nh, nw
        scale = nh / LOGICAL_H if nh > 0 else 1.0
        lw = max(MIN_LOGICAL_W, int(round(nw / scale)))
        try:
            screen = pygame.display.set_mode((lw, LOGICAL_H), pygame.SCALED | pygame.FULLSCREEN)
            print(f"[mobile] display {nw}x{nh} -> logical {lw}x{LOGICAL_H} (scaled {scale:.2f}x)")
            return screen
        except pygame.error as exc:
            print(f"[mobile] SCALED display failed ({exc}); using the native resolution")
            return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    return pygame.display.set_mode(args.size)


def parse_size(text):
    w, h = text.lower().split("x")
    return int(w), int(h)


def parse_args(argv):
    p = argparse.ArgumentParser(description="Digit Defender (Android build)")
    p.add_argument("--desktop", action="store_true", help="phone layout in a window; the mouse is a finger")
    p.add_argument("--world", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--frames", type=int, default=None)
    p.add_argument("--autosave", type=float, default=None)
    p.add_argument("--testworld", action="store_true")
    p.add_argument("--size", type=parse_size, default=DEFAULT_DESKTOP_SIZE, help="--desktop window, e.g. 1616x720")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    android = on_android()
    touch_only = android and not args.desktop
    if android:
        os.environ.setdefault("SDL_ANDROID_TRAP_BACK_BUTTON", "1")   # back = Escape, never kills the app
    MobileGame.touch_only = touch_only
    pygame.init()
    numbers.reset()
    if android:
        # the unpacked app dir is wiped on every update: keep saves in the app's private dir
        data = Path(os.environ.get("ANDROID_PRIVATE", ".")) / "digit_defender"
        data.mkdir(parents=True, exist_ok=True)
        persistence.set_saves_dir(data / "saves")
        persistence.CONFIG_PATH = data / "config.json"
        os.chdir(data)                          # crash.log lands here too
    persistence.DEFAULT_CONFIG["hints"] = False
    config = persistence.load_config()
    screen = open_display(args, android)
    pygame.display.set_caption("Digit Defender")
    if touch_only:
        pygame.key.stop_text_input()            # no soft keyboard until the New World screen asks
    install_patches(touch_only)

    while True:
        lab = args.testworld
        if args.testworld:
            meta = persistence.find_or_create(testworld.NAME, testworld.SEED)
        elif args.world:
            meta = persistence.find_or_create(args.world, args.seed)
        else:
            choice = MobileMenu(config, max_frames=args.frames).run()
            if choice["action"] == "quit":
                break
            meta = choice["meta"]
            lab = choice.get("lab", False)
        game = MobileGame.load(pygame.display.get_surface(), meta)
        game.show_hints = config.get("hints", False)
        if lab:
            if testworld.is_empty(game.factory):
                testworld.build(game.factory)
            else:
                testworld.top_up(game.factory)
        if args.autosave is not None:
            game.autosave_s = args.autosave
        result = game.run(max_frames=args.frames)
        config["last_world"] = meta["slug"]
        persistence.save_config(config)
        if result == "reload":
            continue
        if result == "quit" or args.world or args.testworld:
            break
    screen = None
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
