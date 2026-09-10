"""Structure, belt-item and ghost drawing. Sprites are pre-rendered per
(kind, direction, tile px, label) and LRU-cached; a frame collects blit
tuples and hands them to Surface.blits in two batches (structures, items).
Only structures in visible chunks are touched (Factory.by_chunk). Positions
are integer multiples of the tile size from Camera.screen_origin(), the same
origin the terrain uses, so structures never drift off the grid.
"""
from functools import lru_cache

import pygame

from settings import COLORS, TEXT_MIN_ZOOM
from sim.structures import DIR_VEC, KINDS, ROLE_IN, ROLE_OUT, ROLE_FEED
from render import numbers

ROLE_COLORS = {ROLE_IN: COLORS["side_input"], ROLE_OUT: COLORS["side_output"],
               ROLE_FEED: COLORS["side_feed"]}
MAGNITUDE_COLORS = ((225, 225, 225), (120, 200, 255), (120, 255, 120), (255, 230, 90),
                    (255, 170, 60), (255, 100, 100), (230, 120, 255))


def magnitude_color(value):
    digits = len(str(abs(int(value))))
    return MAGNITUDE_COLORS[min(len(MAGNITUDE_COLORS), digits) - 1]


def _darker(c, f=0.6):
    return tuple(int(v * f) for v in c)


def _convert(surf, alpha=True):
    """Match the display format (much faster blits); harmless without one."""
    try:
        return surf.convert_alpha() if alpha else surf.convert()
    except pygame.error:
        return surf


def _arrow(surf, cx, cy, direction, size, color):
    dx, dy = DIR_VEC[direction]
    px, py = -dy, dx                       # perpendicular
    tip = (cx + dx * size, cy + dy * size)
    base = (cx - dx * size * 0.4, cy - dy * size * 0.4)
    pts = [tip, (base[0] + px * size * 0.7, base[1] + py * size * 0.7),
           (base[0] - px * size * 0.7, base[1] - py * size * 0.7)]
    pygame.draw.polygon(surf, color, pts)


@lru_cache(maxsize=4096)
def sprite(kind, direction, tp, label=None, level=1):
    """Surface for one structure: tp px per tile (hub is 3 tiles). Levels
    above 1 get a small badge in the top-right corner."""
    surf = _sprite(kind, direction, tp, label)
    if level > 1 and tp >= 16:
        surf = surf.copy()
        badge = numbers.text(str(level), max(8, tp // 3), (255, 230, 120))
        surf.blit(badge, (surf.get_width() - badge.get_width() - 1, 0))
        surf = _convert(surf)
    return surf


@lru_cache(maxsize=2048)
def _sprite(kind, direction, tp, label=None):
    cls = KINDS[kind]
    size = tp * cls.SIZE
    base = COLORS.get(kind, (200, 0, 200))
    if kind == "belt":
        surf = pygame.Surface((size, size))
        surf.fill(base)
        if tp >= 12:
            pygame.draw.rect(surf, _darker(base, 0.5), (0, 0, size, size), 1)
            _arrow(surf, size / 2, size / 2, direction, tp * 0.28, COLORS["belt_arrow"])
        else:
            cx, cy = size / 2, size / 2
            dx, dy = DIR_VEC[direction]
            pygame.draw.line(surf, COLORS["belt_arrow"], (cx - dx * tp * 0.3, cy - dy * tp * 0.3),
                             (cx + dx * tp * 0.3, cy + dy * tp * 0.3), 1)
        return _convert(surf, alpha=False)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pad = max(1, tp // 10)
    pygame.draw.rect(surf, base, (pad, pad, size - 2 * pad, size - 2 * pad),
                     border_radius=max(2, tp // 6))
    pygame.draw.rect(surf, _darker(base, 0.45), (pad, pad, size - 2 * pad, size - 2 * pad),
                     max(1, tp // 16), border_radius=max(2, tp // 6))
    if cls.HAS_OUTPUT or kind == "tower":
        dx, dy = DIR_VEC[direction]
        ex, ey = size / 2 + dx * (size / 2 - tp * 0.18), size / 2 + dy * (size / 2 - tp * 0.18)
        color = COLORS["side_input"] if kind == "tower" else (240, 240, 240)
        if kind == "tower":
            direction = (direction + 2) % 4       # intake: arrow points inward
        _arrow(surf, ex, ey, direction, tp * 0.16, color)
    if label and tp >= 10:
        px = max(8, int(tp * (0.6 if len(label) == 1 else 0.38)))
        numbers.blit_centered(surf, numbers.text(label, px), size // 2, size // 2)
    return _convert(surf)


@lru_cache(maxsize=4096)
def item_sprite(value, tp, with_text):
    r = item_radius(tp)
    surf = pygame.Surface((2 * r + 2, 2 * r + 2), pygame.SRCALPHA)
    color = magnitude_color(value)
    if with_text:
        pygame.draw.circle(surf, (20, 20, 24), (r + 1, r + 1), r)
        pygame.draw.circle(surf, color, (r + 1, r + 1), r, 1)
        txt = numbers.text(numbers.abbrev(value), max(8, int(tp * 0.42)))
        numbers.blit_centered(surf, txt, r + 1, r + 1)
    else:
        pygame.draw.rect(surf, color, (1, 1, 2 * r, 2 * r))
    return _convert(surf)


def item_radius(tp):
    return max(2, int(tp * 0.32))


def draw_structures(screen, camera, factory, chunk_rect):
    tp = camera.tile_px
    ox, oy = camera.screen_origin()
    with_text = camera.zoom >= TEXT_MIN_ZOOM
    half = tp // 2
    hw = item_radius(tp) + 1
    cx0, cy0, cx1, cy1 = chunk_rect
    by_chunk = factory.by_chunk
    blits = []
    item_blits = []
    drawn_big = set()
    for cy in range(cy0, cy1 + 1):
        for cx in range(cx0, cx1 + 1):
            lst = by_chunk.get((cx, cy))
            if not lst:
                continue
            for s in lst:
                if s.SIZE > 1:
                    if id(s) in drawn_big:
                        continue
                    drawn_big.add(id(s))
                    r = s.SIZE // 2
                    blits.append((sprite(s.KIND, s.direction, tp, s.label(), s.level),
                                  ((s.x - r) * tp + ox, (s.y - r) * tp + oy)))
                    continue
                sx = s.x * tp + ox
                sy = s.y * tp + oy
                blits.append((sprite(s.KIND, s.direction, tp, s.label(), s.level), (sx, sy)))
                if s.KIND == "belt" and s.items:
                    dx, dy = DIR_VEC[s.direction]
                    cxp = sx + half - hw
                    cyp = sy + half - hw
                    for value, p in s.items:
                        off = (p - 0.5) * tp
                        item_blits.append((item_sprite(value, tp, with_text),
                                           (int(cxp + dx * off), int(cyp + dy * off))))
    screen.blits(blits, doreturn=False)
    screen.blits(item_blits, doreturn=False)


def draw_side_roles(screen, camera, cls, x, y, direction):
    """Colour each edge of a footprint by its role (input/output/feed)."""
    tp = camera.tile_px
    r = cls.SIZE // 2
    sx, sy = camera.tile_to_screen(x - r, y - r)
    size = tp * cls.SIZE
    th = max(2, tp // 8)
    for rel, role in enumerate(cls.SIDE_ROLES):
        if role is None:
            continue
        d = (direction + rel) % 4
        color = ROLE_COLORS[role]
        if d == 0:
            rect = (sx, sy, size, th)
        elif d == 1:
            rect = (sx + size - th, sy, th, size)
        elif d == 2:
            rect = (sx, sy + size - th, size, th)
        else:
            rect = (sx, sy, th, size)
        pygame.draw.rect(screen, color, rect)


def draw_ghost(screen, camera, kind, x, y, direction, ok, cost):
    cls = KINDS[kind]
    tp = camera.tile_px
    r = cls.SIZE // 2
    sx, sy = camera.tile_to_screen(x - r, y - r)
    spr = sprite(kind, direction, tp, None).copy()
    spr.set_alpha(150)
    screen.blit(spr, (sx, sy))
    tint = pygame.Surface(spr.get_size(), pygame.SRCALPHA)
    tint.fill((*(COLORS["ghost_ok"] if ok else COLORS["ghost_bad"]), 70))
    screen.blit(tint, (sx, sy))
    draw_side_roles(screen, camera, cls, x, y, direction)
    if tp >= 12:
        txt = numbers.text(str(cost), 14, COLORS["ghost_ok"] if ok else COLORS["ghost_bad"])
        screen.blit(txt, (sx + tp * cls.SIZE + 2, sy))


def draw_selection(screen, camera, s):
    tp = camera.tile_px
    r = s.SIZE // 2
    sx, sy = camera.tile_to_screen(s.x - r, s.y - r)
    pygame.draw.rect(screen, (255, 255, 120), (sx - 1, sy - 1, tp * s.SIZE + 2, tp * s.SIZE + 2), 2)
    draw_side_roles(screen, camera, type(s), s.x, s.y, s.direction)


def draw_health_bars(screen, camera, factory):
    """Bars under damaged structures only (Factory.damaged)."""
    if not factory.damaged:
        return
    tp = camera.tile_px
    if tp < 8:
        return
    healed = []
    for s in factory.damaged:
        if s.hp >= s.max_hp or factory.structures.get((s.x, s.y)) is not s:
            healed.append(s)
            continue
        r = s.SIZE // 2
        sx, sy = camera.tile_to_screen(s.x - r, s.y - r)
        w = tp * s.SIZE
        pygame.draw.rect(screen, COLORS["hp_bar_bg"], (sx, sy - 4, w, 3))
        pygame.draw.rect(screen, COLORS["hp_bar"], (sx, sy - 4, int(w * s.hp / s.max_hp), 3))
    for s in healed:
        factory.damaged.discard(s)
