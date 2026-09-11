"""Touch layer for the Android build. Finger events become the mouse and
keyboard events game.Game already understands, so the desktop code stays
untouched:

    tap                = left click (select, place, train, toolbar, minimap)
    long press         = right click (move units / gather point / cancel tool)
    one-finger drag    = pan; with a build tool active (or the Box button
                         armed) it is a left-button drag: belt path, paint,
                         demolish box, selection box
    two-finger drag    = pan;  pinch = zoom in discrete steps at the pinch
    two-finger tap     = middle click (patrol with units selected)
    on-screen buttons  = the hotkeys (R, Esc, Del, Q, U, H, T, C, Home, Space,
                         speed, F1, zoom, formation) plus sticky Shift / Box,
                         Save, Menu and Load (game over)

STATE is read by the pygame patches installed in entry.py: `mods` are the
sticky modifier bits ORed into pygame.key.get_mods(), `last_pos` is what
pygame.mouse.get_pos() reports on the phone (the last finger position).
"""
import math
import time

import pygame

from render import numbers
from settings import COLORS
from ui.hud import TOOLS, BTN as HUD_BTN, GAP as HUD_GAP

try:                                        # written by android/sync.py
    from . import build_info as _bi
    BUILD_LABEL = f"v{_bi.VERSION} {_bi.COMMIT}"
except Exception:                           # pragma: no cover - dev tree
    BUILD_LABEL = "dev"

STATE = {"mods": 0, "last_pos": (0, 0)}

TAP_MAX_PX = 14          # a finger may wander this far (logical px) and still tap / long-press
LONG_PRESS_S = 0.45      # hold this long without moving = right click
TWO_TAP_S = 0.35         # two fingers down and up within this, without moving = middle click
PINCH_STEP = 1.22        # finger-distance ratio per discrete zoom step
BTN_W, BTN_H, GAP = 64, 64, 6
FINGER_EVENTS = (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP)
PANEL_H = 190            # ui.hud single-structure panel height (the left block sits under it)

LEFT_BUTTONS = [         # (label, action): a key code, or a named action below; two columns
    ("Rot", pygame.K_r), ("Esc", pygame.K_ESCAPE),
    ("Del", pygame.K_DELETE), ("Pick", pygame.K_q),
    ("Upg", pygame.K_u), ("Fix", pygame.K_h),
    ("Split", pygame.K_t), ("Train", pygame.K_c),
    ("Shift", "shift"), ("Box", "box"),
    ("HQ", pygame.K_HOME), ("Form", "formation"),
]
RIGHT_BUTTONS = [        # four columns under the HQ button, above the minimap
    ("Zoom -", "zoom_out"), ("Zoom +", "zoom_in"), ("Pause", pygame.K_SPACE), ("Speed", "speed"),
    ("Help", pygame.K_F1), ("Save", "save"), ("Menu", "menu"), ("Load", "load"),
]


class Finger:
    __slots__ = ("fid", "x", "y", "x0", "y0", "t0", "ui")

    def __init__(self, fid, x, y, t, ui=False):
        self.fid = fid
        self.x = self.x0 = x
        self.y = self.y0 = y
        self.t0 = t
        self.ui = ui                          # landed on an overlay button: never a gesture


class TouchLayer:
    def __init__(self, game):
        self.game = game
        self.clock = time.monotonic           # tests inject a fake clock
        self.fingers = {}                     # finger id -> Finger (insertion ordered)
        self.mode = None                      # None | pending | held | lmb | pan | two
        self.press = None                     # the Finger driving a one-finger gesture
        self.two = None                       # two-finger gesture state
        self.box_armed = False                # next one-finger drag = selection box
        self.buttons = []                     # [(rect, label, action)] from layout()
        w, h = game.screen.get_size()
        STATE["mods"] = 0
        STATE["last_pos"] = (w // 2, h // 2)

    # ---- geometry ---------------------------------------------------------

    def size(self):
        return self.game.screen.get_size()

    def pos_of(self, ev):
        """Finger events carry normalized coordinates."""
        w, h = self.size()
        return (ev.x * w, ev.y * h)

    def gesture_fingers(self):
        return [f for f in self.fingers.values() if not f.ui]

    # ---- pygame events ----------------------------------------------------

    def handle(self, ev):
        """Consume a FINGER* event. Returns True when it was one."""
        if ev.type == pygame.FINGERDOWN:
            self.finger_down(ev.finger_id, self.pos_of(ev))
        elif ev.type == pygame.FINGERMOTION:
            self.finger_motion(ev.finger_id, self.pos_of(ev))
        elif ev.type == pygame.FINGERUP:
            self.finger_up(ev.finger_id, self.pos_of(ev))
        else:
            return False
        return True

    def finger_down(self, fid, pos):
        now = self.clock()
        x, y = pos
        STATE["last_pos"] = (int(x), int(y))
        if fid in self.fingers:                        # a lost FINGERUP: close the old one first
            self.finger_up(fid, (self.fingers[fid].x, self.fingers[fid].y))
        if not self.fingers and self.button_press(pos):
            self.fingers[fid] = Finger(fid, x, y, now, ui=True)
            return
        f = Finger(fid, x, y, now)
        self.fingers[fid] = f
        gesture = self.gesture_fingers()
        if len(gesture) == 1:
            self.press = f
            self.mode = "pending"
        elif len(gesture) == 2:
            self.begin_two(gesture, now)
        # a third finger changes nothing

    def finger_motion(self, fid, pos):
        f = self.fingers.get(fid)
        if f is None or f.ui:
            return
        px, py = f.x, f.y
        f.x, f.y = x, y = pos
        STATE["last_pos"] = (int(x), int(y))
        if self.mode == "two":
            self.two_motion()
            return
        if f is not self.press:
            return
        if self.mode == "pending":
            if math.hypot(x - f.x0, y - f.y0) <= TAP_MAX_PX:
                return
            if self.game.tool is not None or self.box_armed:
                self.box_armed = False
                self.mode = "lmb"
                self.mouse(pygame.MOUSEBUTTONDOWN, 1, (f.x0, f.y0))
                self.mouse(pygame.MOUSEMOTION, 1, pos, rel=(x - f.x0, y - f.y0))
            else:
                self.mode = "pan"
                self.pan(x - f.x0, y - f.y0)
        elif self.mode == "lmb":
            self.mouse(pygame.MOUSEMOTION, 1, pos, rel=(x - px, y - py))
        elif self.mode == "pan":
            self.pan(x - px, y - py)
        # "held": the right click already fired; the finger just rests

    def finger_up(self, fid, pos):
        f = self.fingers.pop(fid, None)
        if f is None or f.ui:
            return
        x, y = pos
        STATE["last_pos"] = (int(x), int(y))
        now = self.clock()
        if self.mode == "two":
            t, self.two = self.two, None
            if t is not None and not t["moved"] and now - t["t0"] <= TWO_TAP_S:
                c = (t["cx"], t["cy"])
                self.mouse(pygame.MOUSEBUTTONDOWN, 2, c)
                self.mouse(pygame.MOUSEBUTTONUP, 2, c)
            rest = self.gesture_fingers()
            if rest:                                   # the other finger pans on
                self.press = rest[0]
                self.mode = "pan"
            else:
                self.press = None
                self.mode = None
            return
        if f is not self.press:
            return
        if self.mode == "pending":                     # a tap
            self.mouse(pygame.MOUSEBUTTONDOWN, 1, pos)
            self.mouse(pygame.MOUSEBUTTONUP, 1, pos)
        elif self.mode == "lmb":
            self.mouse(pygame.MOUSEBUTTONUP, 1, pos)
        self.mode = None
        self.press = None

    def update(self, dt=0.0):
        """Once per frame: a finger resting long enough is a right click."""
        f = self.press
        if self.mode == "pending" and f is not None and self.clock() - f.t0 >= LONG_PRESS_S:
            self.mode = "held"
            self.mouse(pygame.MOUSEBUTTONDOWN, 3, (f.x, f.y))
            self.mouse(pygame.MOUSEBUTTONUP, 3, (f.x, f.y))

    # ---- gestures ---------------------------------------------------------

    def begin_two(self, pair, now):
        if self.mode == "lmb":
            self.cancel_drag()
        a, b = pair[0], pair[1]
        cx, cy = (a.x + b.x) / 2, (a.y + b.y) / 2
        dist = max(1.0, math.hypot(a.x - b.x, a.y - b.y))
        self.two = {"cx": cx, "cy": cy, "dist": dist, "cx0": cx, "cy0": cy, "dist0": dist,
                    "t0": now, "moved": False}
        self.press = None
        self.mode = "two"

    def two_motion(self):
        pair = self.gesture_fingers()[:2]
        t = self.two
        if len(pair) < 2 or t is None:
            return
        a, b = pair
        cx, cy = (a.x + b.x) / 2, (a.y + b.y) / 2
        dist = max(1.0, math.hypot(a.x - b.x, a.y - b.y))
        self.pan(cx - t["cx"], cy - t["cy"])
        ratio = dist / t["dist"]
        cam = self.game.camera
        if ratio >= PINCH_STEP:
            cam.zoom_by(1, (cx, cy))
            t["dist"] = dist
        elif ratio <= 1.0 / PINCH_STEP:
            cam.zoom_by(-1, (cx, cy))
            t["dist"] = dist
        if (math.hypot(cx - t["cx0"], cy - t["cy0"]) > TAP_MAX_PX
                or abs(dist - t["dist0"]) > 2 * TAP_MAX_PX):
            t["moved"] = True
        t["cx"], t["cy"] = cx, cy

    def cancel_drag(self):
        """A second finger lands mid-drag: drop the belt preview / paint /
        demolish or selection box, keep the tool."""
        g = self.game
        if g.tool is not None:
            g.set_tool(g.tool)
        g.box_start = g.box_end = None
        g.click_target = None
        g.painting = False

    def pan(self, dx, dy):
        cam = self.game.camera
        z = cam.zoom
        cam.move(-dx / z, -dy / z)

    # ---- synthesized events ----------------------------------------------

    def mouse(self, etype, button, pos, rel=None):
        pos = (int(round(pos[0])), int(round(pos[1])))
        if etype == pygame.MOUSEMOTION:
            rel = (int(round(rel[0])), int(round(rel[1]))) if rel else (0, 0)
            ev = pygame.event.Event(etype, pos=pos, rel=rel, touch=False,
                                    buttons=(int(button == 1), int(button == 2), int(button == 3)))
        else:
            ev = pygame.event.Event(etype, pos=pos, button=button, touch=False)
        self.game.dispatch(ev)

    def press_key(self, key):
        self.game.dispatch(pygame.event.Event(pygame.KEYDOWN, key=key, mod=STATE["mods"],
                                              unicode="", scancode=0))

    # ---- overlay buttons --------------------------------------------------

    def layout(self):
        """Button rects for the current screen and HUD state (mirrors the
        ui.hud layout: under the info panel / HQ button, clear of the toolbar
        and the minimap)."""
        g = self.game
        hud = g.hud
        w, h = self.size()
        out = []
        n = len(TOOLS)
        avail = w - hud.MINI_W - 16
        tb = max(40, min(HUD_BTN, (avail - 16 - (n - 1) * HUD_GAP) // n))
        toolbar_top = h - tb - 10 - 8
        top = 8 + PANEL_H + 8
        rows = (len(LEFT_BUTTONS) + 1) // 2
        bh = min(BTN_H, max(36, (toolbar_top - 8 - top - (rows - 1) * GAP) // rows))
        for i, (label, action) in enumerate(LEFT_BUTTONS):
            col, row = i % 2, i // 2
            out.append((pygame.Rect(8 + col * (BTN_W + GAP), top + row * (bh + GAP), BTN_W, bh), label, action))
        targets = len(getattr(g.factory, "targets", ()) or ())
        rtop = 8 + 58 + 6 + (24 + 22 * targets) + 6 + 26 + 8      # balance, targets, HQ button
        mini_top = h - hud.MINI_H - 8
        col_x = w - hud.COL_W - 8
        bw = (hud.COL_W - 3 * GAP) // 4
        bh2 = min(BTN_H, max(36, (mini_top - 8 - rtop - GAP) // 2))
        for i, (label, action) in enumerate(RIGHT_BUTTONS):
            if action == "load" and not g.game_over:
                continue
            col, row = i % 4, i // 4
            out.append((pygame.Rect(col_x + col * (bw + GAP), rtop + row * (bh2 + GAP), bw, bh2), label, action))
        self.buttons = out
        return out

    def hit(self, pos):
        return any(r.collidepoint(pos) for r, _, _ in self.layout())

    def button_press(self, pos):
        for rect, label, action in self.layout():
            if rect.collidepoint(pos):
                self.activate(action)
                return True
        return False

    def activate(self, action):
        g = self.game
        if isinstance(action, int):
            self.press_key(action)
        elif action == "shift":
            STATE["mods"] ^= pygame.KMOD_SHIFT
        elif action == "box":
            self.box_armed = not self.box_armed
            if self.box_armed:
                g.hud.message("Box: drag over units or buildings to select them", 1.5)
        elif action == "formation":
            if g.cycle_formation(1) is None:
                g.hud.message("Select units first (tap one, or Box + drag)", 1.5)
        elif action == "zoom_in":
            g.camera.zoom_by(1)
        elif action == "zoom_out":
            g.camera.zoom_by(-1)
        elif action == "speed":
            g.speed = {1: 2, 2: 4}.get(g.speed, 1)
            g.hud.message(f"Speed x{g.speed}", 1.0)
        elif action == "save":
            g.hud.message("Saved" if g.save() else "Nothing to save", 1.5)
        elif action == "menu":
            g.result = "menu"
            g.running = False
        elif action == "load":
            if g.game_over:
                self.press_key(pygame.K_l)

    def draw(self, screen):
        g = self.game
        shift = bool(STATE["mods"] & pygame.KMOD_SHIFT)
        last = None
        for rect, label, action in self.layout():
            active = ((action == "shift" and shift) or (action == "box" and self.box_armed)
                      or (action == pygame.K_SPACE and g.paused) or (action == pygame.K_F1 and g.show_help))
            text = label
            if action == "speed":
                text = f"x{g.speed}"
            elif action == pygame.K_SPACE and g.paused:
                text = "Play"
            surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            surf.fill((70, 95, 60, 215) if active else (22, 32, 22, 195))
            screen.blit(surf, rect.topleft)
            pygame.draw.rect(screen, (255, 230, 120) if active else COLORS["panel_border"], rect,
                             2 if active else 1, border_radius=6)
            t = numbers.text(text, 15 if len(text) <= 5 else 13)
            screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
            last = rect
        if self.mode == "pending" and self.press is not None:       # long-press progress ring
            frac = (self.clock() - self.press.t0) / LONG_PRESS_S
            if frac > 0.25:
                r = int(30 - 22 * min(1.0, frac))
                pygame.draw.circle(screen, (255, 230, 120), (int(self.press.x), int(self.press.y)), max(5, r), 2)
        if last is not None:
            t = numbers.text(BUILD_LABEL, 11, (150, 170, 150))
            screen.blit(t, (last.right - t.get_width(), last.bottom + 2))
