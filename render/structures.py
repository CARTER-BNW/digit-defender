"""Structure, belt-item and ghost drawing. Sprites are pre-rendered per
(kind, direction, tile px, label, level) and LRU-cached; a frame collects
blit tuples and hands them to Surface.blits in two batches (structures,
items). Only structures in visible chunks are touched (Factory.by_chunk).
Positions are integer multiples of the tile size from Camera.screen_origin(),
the same origin the terrain uses, so structures never drift off the grid.

Custom art: drop assets/sprites/<kind>.png (32x32 per tile, hub 96x96,
transparent background or pure magenta as the colour key, drawn facing UP).
The game rotates it for E/S/W and scales it for each zoom; labels (miner
digit, machine symbol, level badge) are still drawn on top.
"""
import os
from functools import lru_cache

import pygame

from settings import (COLORS, TEXT_MIN_ZOOM, TILE_SIZE, ITEM_SPACING, SPRITE_DIR,
                      MINER_PULSE_TICKS, CHUNK_SIZE)
from sim.structures import DIR_VEC, KINDS, ROLE_IN, ROLE_OUT, ROLE_FEED
from render import numbers

ROLE_COLORS = {ROLE_IN: COLORS["side_input"], ROLE_OUT: COLORS["side_output"],
               ROLE_FEED: COLORS["side_feed"]}
MAGNITUDE_COLORS = ((235, 235, 235), (120, 200, 255), (120, 255, 120), (255, 230, 90),
                    (255, 170, 60), (255, 100, 100), (230, 120, 255))
BELT_WIDTH = 0.62            # strip width as a fraction of the tile
ASSET_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), SPRITE_DIR)


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


# ---- optional PNG art -------------------------------------------------------------------

@lru_cache(maxsize=64)
def load_png(kind):
    """assets/sprites/<kind>.png or None. Pure white and pure magenta pixels
    become transparent (Paint cannot save transparency)."""
    path = os.path.join(ASSET_ROOT, f"{kind}.png")
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path)
    except pygame.error:
        return None
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    try:
        import numpy as np
        import pygame.surfarray as sa
        rgb = sa.pixels3d(out)
        alpha = sa.pixels_alpha(out)
        white = (rgb[..., 0] == 255) & (rgb[..., 1] == 255) & (rgb[..., 2] == 255)
        magenta = (rgb[..., 0] == 255) & (rgb[..., 1] == 0) & (rgb[..., 2] == 255)
        alpha[white | magenta] = 0
        del rgb, alpha
    except (ImportError, pygame.error):
        out.set_colorkey((255, 255, 255))
    return _convert(out)


def _rotate_cw(img, quarter_turns):
    """Rotate by quarter turns clockwise (pygame's positive angle is CCW)."""
    q = quarter_turns % 4
    return pygame.transform.rotate(img, -90 * q) if q else img


def _fit(img, size):
    if img.get_width() != size:
        img = (pygame.transform.smoothscale(img, (size, size)) if size < img.get_width()
               else pygame.transform.scale(img, (size, size)))
    return img


def _png_sprite(img, direction, size):
    """Sprites are drawn facing LEFT (W); rotate clockwise to face `direction`."""
    return _fit(_rotate_cw(img, (direction - 3) % 4), size)


# belt shape files, as drawn: the set of open (connected) world sides
BELT_SHAPES = {
    "belt": {3, 1},              # straight: W (output, arrow) + E
    "belt_corner": {2, 1},       # L: S + E
    "belt_t": {2, 3, 1},         # T: S + W + E (closed at N)
    "belt_cross": {0, 1, 2, 3},
}


def belt_openings(direction, variant):
    """World sides a belt connects: every cargo input side and every output
    side (variant packs in_sides | out_sides << 4). A lone belt shows straight."""
    mask = (variant & 15) | (variant >> 4)
    opens = {d for d in range(4) if mask & (1 << d)}
    if not opens:
        return {direction, (direction + 2) % 4}
    if len(opens) == 1:
        opens.add((next(iter(opens)) + 2) % 4)
    return opens


def _belt_png(direction, variant, size):
    """Pick the shape file whose rotated openings match, or None."""
    opens = belt_openings(direction, variant)
    n = len(opens)
    if n == 2:
        a, b = sorted(opens)
        name = "belt" if (b - a) == 2 else "belt_corner"
    elif n == 3:
        name = "belt_t"
    else:
        name = "belt_cross"
    img = load_png(name)
    if img is None:
        img = load_png("belt")
        if img is None:
            return None
        name = "belt"
    drawn = BELT_SHAPES[name]
    if name == "belt":
        r = (direction - 3) % 4                      # the arrow must point at the output
    else:
        for r in range(4):
            if {(d + r) % 4 for d in drawn} == opens:
                break
        else:
            r = 0
    return _fit(_rotate_cw(img, r), size)


# ---- sprites ----------------------------------------------------------------------------

@lru_cache(maxsize=4096)
def sprite(kind, direction, tp, label=None, level=1, variant=0):
    """Surface for one structure: tp px per tile (hub is 3 tiles). Levels
    above 1 get a small badge in the top-right corner. `variant` is the
    belt's input-side mask (its shape)."""
    surf = _sprite(kind, direction, tp, label, variant)
    if level > 1 and tp >= 16:
        surf = surf.copy()
        badge = numbers.text(str(level), max(8, tp // 3), (255, 230, 120))
        surf.blit(badge, (surf.get_width() - badge.get_width() - 1, 0))
        surf = _convert(surf)
    return surf


def _belt_procedural(direction, variant, tp):
    """Strip from every open side to the centre plus a small dark arrow."""
    surf = pygame.Surface((tp, tp), pygame.SRCALPHA)
    base = COLORS["belt"]
    wpx = max(2, int(round(tp * BELT_WIDTH)))
    off = (tp - wpx) // 2
    half = tp // 2
    for d in belt_openings(direction, variant):
        if d == 0:
            rect = (off, 0, wpx, half + wpx // 2)
        elif d == 2:
            rect = (off, half - wpx // 2, wpx, tp - (half - wpx // 2))
        elif d == 1:
            rect = (half - wpx // 2, off, tp - (half - wpx // 2), wpx)
        else:
            rect = (0, off, half + wpx // 2, wpx)
        pygame.draw.rect(surf, base, rect)
    if tp >= 12:
        # thin edge around the whole shape, then the arrow toward the output
        mask = pygame.mask.from_surface(surf)
        for pt in mask.outline():
            surf.set_at(pt, COLORS["belt_edge"])
        _arrow(surf, tp / 2, tp / 2, direction, max(2, tp * 0.11), COLORS["belt_arrow"])
    return _convert(surf)


@lru_cache(maxsize=2048)
def _sprite(kind, direction, tp, label=None, variant=0):
    cls = KINDS[kind]
    size = tp * cls.SIZE
    base = COLORS.get(kind, (200, 0, 200))
    if kind == "belt":
        img = _belt_png(direction, variant, size)
        return _convert(img.copy()) if img is not None else _belt_procedural(direction, variant, tp)
    png = load_png(kind)
    if png is not None:
        surf = _png_sprite(png, direction, size).copy()
    else:
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
        numbers.blit_centered(surf, numbers.glyph(label, px), size // 2, size // 2)
    return _convert(surf)


@lru_cache(maxsize=4096)
def item_sprite(value, tp, with_text):
    """A belt item: the plain outlined number (no circle); a coloured square
    when zoomed out too far for text."""
    color = magnitude_color(value)
    if with_text:
        return numbers.glyph(numbers.abbrev(value), max(8, int(tp * 0.44)), color)
    r = max(1, int(tp * 0.18))
    surf = pygame.Surface((2 * r, 2 * r), pygame.SRCALPHA)
    surf.fill(color)
    return _convert(surf)


def draw_structures(screen, camera, factory, chunk_rect, frac=0.0):
    """frac = fraction of the next sim tick already elapsed (accumulator /
    TICK_DT): items are drawn advanced by speed * frac, clamped by the same
    spacing rule the sim uses, so motion is smooth and blocked items stay
    put. Render-only; the sim never sees it."""
    tp = camera.tile_px
    ox, oy = camera.screen_origin()
    with_text = camera.zoom >= TEXT_MIN_ZOOM
    half = tp // 2
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
                if s.KIND == "belt":
                    blits.append((sprite("belt", s.direction, tp, None, s.level,
                                         s.in_sides | (s.out_sides << 4)), (sx, sy)))
                else:
                    blits.append((sprite(s.KIND, s.direction, tp, s.label(), s.level), (sx, sy)))
                if s.KIND == "belt" and s.items:
                    dx, dy = DIR_VEC[s.direction]
                    cxp = sx + half
                    cyp = sy + half
                    lead = s.speed * frac
                    limit = 0.999
                    outs = s.outputs
                    n_out = len(outs)
                    branching = any(o[2] != s.direction for o in outs)
                    for i, (value, p) in enumerate(reversed(s.items)):    # head first
                        q = p + lead
                        if q > limit:
                            q = limit
                        limit = q - ITEM_SPACING
                        spr = item_sprite(value, tp, with_text)
                        off = (q - 0.5) * tp
                        vx, vy = dx, dy
                        if branching and q > 0.5:
                            # past the centre, head for the branch this item will take
                            side = outs[(s.rr + i) % n_out][2]
                            vx, vy = DIR_VEC[side]
                        item_blits.append((spr, (int(cxp + vx * off) - spr.get_width() // 2,
                                                 int(cyp + vy * off) - spr.get_height() // 2)))
    screen.blits(blits, doreturn=False)
    screen.blits(item_blits, doreturn=False)


def draw_miner_pulses(screen, camera, factory, chunk_rect):
    """White border flash on a miner's tile right after it extracts."""
    now = factory.tick_count
    tp = camera.tile_px
    if tp < 8:
        return
    ox, oy = camera.screen_origin()
    cx0, cy0, cx1, cy1 = chunk_rect
    for m in factory.miners:
        age = now - m.last_emit_tick
        if age < 0 or age >= MINER_PULSE_TICKS:
            continue
        if not (cx0 <= m.x // CHUNK_SIZE <= cx1 and cy0 <= m.y // CHUNK_SIZE <= cy1):
            continue
        k = 1.0 - age / MINER_PULSE_TICKS
        c = int(90 + 165 * k)
        pygame.draw.rect(screen, (c, c, c), (m.x * tp + ox, m.y * tp + oy, tp, tp), max(1, int(1 + 2 * k)))


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
