"""Touch layer for the Android build. Finger events become the mouse and
keyboard events game.Game already understands, so the desktop code stays
untouched:

    tap                = left click (select, place, train, toolbar, minimap)
    hold (0.45 s)      = a ring closes in and turns green: LIFT = right click
                         (move units / gather point / cancel tool / clear the
                         selection); DRAG = selection box over units and
                         buildings (with a build tool: the tool's own drag)
    one-finger drag    = pan; with a build tool active (or the Box button
                         armed) it is a left-button drag: belt path, paint,
                         demolish box, selection box
    two-finger drag    = pan;  pinch = zoom in discrete steps at the pinch
    two-finger tap     = middle click (patrol with units selected)
    on-screen buttons  = one row just above the toolbar. Left: the actions
                         that apply right now (Rot, Shift, Box, Upg, Fix,
                         Split, Train, Form), each shown only while it can
                         do something. Right: Pause, Speed, Help, Save, Menu
                         and Load (game over). Sizes follow the menu's
                         Settings "Button size" (ui/prefs.py).

STATE is read by the pygame patches installed in entry.py: `mods` are the
sticky modifier bits ORed into pygame.key.get_mods(), `last_pos` is what
pygame.mouse.get_pos() reports on the phone (the last finger position).
"""
import math
import time

import pygame

from render import numbers
from settings import COLORS
from sim.structures import Belt, Spawner
from ui import prefs

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
BTN_W, BTN_H, GAP = 64, 64, 6   # at button scale 1.0 (menu Settings "Button size")
FINGER_EVENTS = (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP)
NO_FACING = ("miner", "wall", "hub", "tower", "bridge", "demolish")   # kinds [R] does nothing to


def _selected(g):
    """The selected structures: the clicked one, or the boxed group."""
    if g.selected is not None:
        return [g.selected]
    return list(g.selected_structures)


# (label, action, when): the action is a key code or a name handled by
# activate(); when(game, layer) says whether the button is shown this frame.
ACTION_BUTTONS = [
    ("Rot", pygame.K_r, lambda g, t: (g.tool not in NO_FACING) if g.tool is not None
     else (g.selected is not None and g.selected.KIND not in NO_FACING)),
    ("Shift", "shift", lambda g, t: bool(STATE["mods"] & pygame.KMOD_SHIFT) or g.tool == "belt"
     or t.box_armed or bool(_selected(g)) or bool(g.selected_units)),
    ("Box", "box", lambda g, t: g.tool is None),
    ("Upg", pygame.K_u, lambda g, t: bool(_selected(g))),
    ("Fix", pygame.K_h, lambda g, t: any(s.hp < s.max_hp for s in _selected(g))),
    ("Split", pygame.K_t, lambda g, t: any(isinstance(s, Belt) for s in _selected(g))),
    ("Train", pygame.K_c, lambda g, t: any(isinstance(s, Spawner) for s in _selected(g))),
    ("Form", "formation", lambda g, t: any(not u.dead for u in g.selected_units)),
]
SYSTEM_BUTTONS = [       # right end of the row (a row higher when the actions need the width)
    ("Pause", pygame.K_SPACE, lambda g, t: True), ("Speed", "speed", lambda g, t: True),
    ("Help", pygame.K_F1, lambda g, t: True), ("Save", "save", lambda g, t: True),
    ("Menu", "menu", lambda g, t: True), ("Load", "load", lambda g, t: g.game_over),
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
        if self.mode in ("pending", "held"):
            if math.hypot(x - f.x0, y - f.y0) <= TAP_MAX_PX:
                return
            # a finger that moves after a hold drags a selection box (or the tool's
            # drag); a quick move pans unless a tool or the Box button says otherwise
            if self.mode == "held" or self.game.tool is not None or self.box_armed:
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
        elif self.mode == "held":                      # a hold lifted in place: right click
            self.mouse(pygame.MOUSEBUTTONDOWN, 3, pos)
            self.mouse(pygame.MOUSEBUTTONUP, 3, pos)
        elif self.mode == "lmb":
            self.mouse(pygame.MOUSEBUTTONUP, 1, pos)
        self.mode = None
        self.press = None

    def update(self, dt=0.0):
        """Once per frame: a finger resting long enough is "held" (the ring
        turns green): lifted in place it is a right click (finger_up), moved
        it drags a selection box or the tool's drag (finger_motion)."""
        f = self.press
        if self.mode == "pending" and f is not None and self.clock() - f.t0 >= LONG_PRESS_S:
            self.mode = "held"

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
        """Button rects for the current game state: one row just above the
        toolbar, the actions that apply now from its left edge, the system
        buttons from its right edge (one row higher when both would not fit
        side by side)."""
        g = self.game
        hud = g.hud
        hud.buttons()                             # toolbar_rect for this frame (also before the first draw)
        tb = hud.toolbar_rect
        bs = prefs.button_scale
        bw, bh, gap = int(round(BTN_W * bs)), int(round(BTN_H * bs)), max(3, int(round(GAP * bs)))
        actions = [] if g.game_over else [(l, a) for l, a, when in ACTION_BUTTONS if when(g, self)]
        system = [(l, a) for l, a, when in SYSTEM_BUTTONS if when(g, self)]

        def span(items):
            return len(items) * bw + max(0, len(items) - 1) * gap

        y = tb.top - gap - bh
        out = []
        x = tb.left
        for label, action in actions:
            out.append((pygame.Rect(x, y, bw, bh), label, action))
            x += bw + gap
        if actions and span(actions) + gap + span(system) > tb.width:
            y -= bh + gap                         # the row is full: system buttons one row up
        x = max(8, tb.right - span(system))
        for label, action in system:
            out.append((pygame.Rect(x, y, bw, bh), label, action))
            x += bw + gap
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
        bs = prefs.button_scale
        buttons = self.layout()
        for rect, label, action in buttons:
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
            t = numbers.text(text, max(8, int(round((15 if len(text) <= 5 else 13) * bs))))
            screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
        if self.mode in ("pending", "held") and self.press is not None:   # hold progress ring, green once held
            frac = (self.clock() - self.press.t0) / LONG_PRESS_S
            if frac > 0.25:
                r = int(30 - 22 * min(1.0, frac))
                held = self.mode == "held"
                pygame.draw.circle(screen, (140, 255, 140) if held else (255, 230, 120),
                                   (int(self.press.x), int(self.press.y)), max(5, r), 3 if held else 2)
        if buttons:                                                  # build tag over the row's right end
            t = numbers.text(BUILD_LABEL, 11, (150, 170, 150))
            top = min(r.top for r, _, _ in buttons)
            screen.blit(t, (buttons[-1][0].right - t.get_width(), top - t.get_height()))
