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

from settings import (COLORS, COSTS, TEXT_MIN_ZOOM, TILE_SIZE, ITEM_SPACING, SPRITE_DIR,
                      MINER_PULSE_TICKS, CHUNK_SIZE, TOWER_RANGE)
from sim.structures import DIR_VEC, KINDS, ROLE_IN, ROLE_OUT, ROLE_FEED, BACK, Belt
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
    if kind == "belt" and tp >= 12:
        outs = variant >> 4
        if outs & (outs - 1):                          # more than one exit: a splitter, mark every exit
            surf = surf.copy()
            for d in range(4):
                if outs & (1 << d):
                    dx, dy = DIR_VEC[d]
                    _arrow(surf, tp / 2 + dx * tp * 0.34, tp / 2 + dy * tp * 0.34, d, tp * 0.1, (255, 240, 160))
            surf = _convert(surf)
    if level > 1 and tp >= 16 and kind != "wall":      # walls show their level as the label
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


def _wall_sprite(direction, links, tp, label):
    """A wall block with a connector bar to every neighbouring wall (`links`
    = bitmask of world sides) and its level in the middle. wall.png, if
    present, replaces the block; the connectors are drawn underneath it."""
    base = COLORS["wall"]
    surf = pygame.Surface((tp, tp), pygame.SRCALPHA)
    block = max(3, int(round(tp * 0.64)))
    b0 = (tp - block) // 2
    lw = max(2, int(round(tp * 0.36)))
    l0 = (tp - lw) // 2
    reach = b0 + max(1, tp // 16)                     # overlap the block a little
    for d in range(4):
        if not links & (1 << d):
            continue
        if d == 0:
            rect = (l0, 0, lw, reach)
        elif d == 2:
            rect = (l0, tp - reach, lw, reach)
        elif d == 1:
            rect = (tp - reach, l0, reach, lw)
        else:
            rect = (0, l0, reach, lw)
        pygame.draw.rect(surf, _darker(base, 0.8), rect)
        if tp >= 12:
            pygame.draw.rect(surf, _darker(base, 0.45), rect, 1)
    png = load_png("wall")
    if png is not None:
        surf.blit(_png_sprite(png, direction, tp), (0, 0))
    else:
        rad = max(1, tp // 10)
        pygame.draw.rect(surf, base, (b0, b0, block, block), border_radius=rad)
        pygame.draw.rect(surf, _darker(base, 0.45), (b0, b0, block, block), max(1, tp // 16),
                         border_radius=rad)
    if label and tp >= 12:
        numbers.blit_centered(surf, numbers.glyph(label, max(8, int(tp * 0.4))), tp // 2, tp // 2)
    return _convert(surf)


def _bridge_sprite(tp):
    """A belt crossing: the east-west lane in belt grey underneath, the
    north-south lane raised in bridge brown with dark rails. bridge.png
    replaces it when present."""
    png = load_png("bridge")
    if png is not None:
        return _convert(_fit(png, tp).copy())
    surf = pygame.Surface((tp, tp), pygame.SRCALPHA)
    belt = COLORS["belt"]
    base = COLORS["bridge"]
    wpx = max(2, int(round(tp * BELT_WIDTH)))
    off = (tp - wpx) // 2
    pygame.draw.rect(surf, belt, (0, off, tp, wpx))
    if tp >= 12:
        pygame.draw.rect(surf, COLORS["belt_edge"], (0, off, tp, 1))
        pygame.draw.rect(surf, COLORS["belt_edge"], (0, off + wpx - 1, tp, 1))
    pygame.draw.rect(surf, base, (off, 0, wpx, tp))
    rail = max(1, tp // 12)
    pygame.draw.rect(surf, _darker(base, 0.45), (off, 0, rail, tp))
    pygame.draw.rect(surf, _darker(base, 0.45), (off + wpx - rail, 0, rail, tp))
    return _convert(surf)


@lru_cache(maxsize=2048)
def _sprite(kind, direction, tp, label=None, variant=0):
    cls = KINDS[kind]
    size = tp * cls.SIZE
    base = COLORS.get(kind, (200, 0, 200))
    if kind == "belt":
        img = _belt_png(direction, variant, size)
        return _convert(img.copy()) if img is not None else _belt_procedural(direction, variant, tp)
    if kind == "wall":
        return _wall_sprite(direction, variant, tp, label)
    if kind == "bridge":
        return _bridge_sprite(tp)
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
        if cls.HAS_OUTPUT:
            dx, dy = DIR_VEC[direction]
            ex, ey = size / 2 + dx * (size / 2 - tp * 0.18), size / 2 + dy * (size / 2 - tp * 0.18)
            _arrow(surf, ex, ey, direction, tp * 0.16, (240, 240, 240))
        if kind == "spawner_repair" and tp >= 8:       # white cross, like the units it trains
            arm, th = max(2, int(tp * 0.28)), max(2, int(tp * 0.12))
            c = size // 2
            pygame.draw.rect(surf, (255, 255, 255), (c - arm, c - th // 2, 2 * arm, th))
            pygame.draw.rect(surf, (255, 255, 255), (c - th // 2, c - arm, th, 2 * arm))
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
    empty_towers = []
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
                kind = s.KIND
                if kind == "belt":
                    blits.append((sprite("belt", s.direction, tp, None, s.level,
                                         s.in_sides | (s.out_sides << 4)), (sx, sy)))
                elif kind == "wall":
                    blits.append((sprite("wall", s.direction, tp, s.label(), s.level, s.links), (sx, sy)))
                else:
                    blits.append((sprite(kind, s.direction, tp, s.label(), s.level), (sx, sy)))
                    if kind == "tower" and not s.ammo:
                        empty_towers.append((sx, sy))
                if kind == "belt" and s.items:
                    dx, dy = DIR_VEC[s.direction]
                    d_in = s.direction
                    cxp = sx + half
                    cyp = sy + half
                    lead = s.speed * frac
                    limit = 0.999
                    outs = s.outputs
                    n_out = len(outs)
                    branching = any(o[2] != s.direction for o in outs)
                    for i, item in enumerate(reversed(s.items)):    # head first
                        value, p = item[0], item[1]
                        q = p + lead
                        if q > limit:
                            q = limit
                        limit = q - ITEM_SPACING
                        spr = item_sprite(value, tp, with_text)
                        if q < 0.5:
                            # first half: slide in from the edge the item entered
                            # through (a side entry curves through the centre)
                            entry = (d_in + (item[2] if len(item) > 2 else BACK)) % 4
                            vx, vy = DIR_VEC[entry]
                            off = (0.5 - q) * tp
                        else:
                            off = (q - 0.5) * tp
                            vx, vy = dx, dy
                            if branching:
                                # past the centre, head for the branch this item will take
                                side = outs[(s.rr + i) % n_out][2]
                                vx, vy = DIR_VEC[side]
                        item_blits.append((spr, (int(cxp + vx * off) - spr.get_width() // 2,
                                                 int(cyp + vy * off) - spr.get_height() // 2)))
                elif kind == "bridge" and any(s.lanes):
                    cxp = sx + half
                    cyp = sy + half
                    lead = s.speed * frac
                    for d in range(4):                 # each lane runs straight across from its entry edge
                        lane = s.lanes[d]
                        if not lane:
                            continue
                        ex, ey = DIR_VEC[d]
                        limit = 0.999
                        for value, p in reversed(lane):
                            q = p + lead
                            if q > limit:
                                q = limit
                            limit = q - ITEM_SPACING
                            spr = item_sprite(value, tp, with_text)
                            off = (0.5 - q) * tp
                            item_blits.append((spr, (int(cxp + ex * off) - spr.get_width() // 2,
                                                     int(cyp + ey * off) - spr.get_height() // 2)))
    screen.blits(blits, doreturn=False)
    screen.blits(item_blits, doreturn=False)
    if empty_towers and tp >= 8:                      # a tower with nothing to fire
        th = max(1, tp // 12)
        for sx, sy in empty_towers:
            pygame.draw.rect(screen, (230, 60, 60), (sx, sy, tp, tp), th)


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


@lru_cache(maxsize=8)
def _range_surface(r, color):
    surf = pygame.Surface((2 * r + 2, 2 * r + 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*color, 26), (r + 1, r + 1), r)
    pygame.draw.circle(surf, (*color, 150), (r + 1, r + 1), r, 1)
    return surf


def draw_range(screen, camera, x, y, radius_tiles, color=(120, 220, 255)):
    """Translucent disc of radius_tiles around the centre of tile (x, y)."""
    tp = camera.tile_px
    ox, oy = camera.screen_origin()
    r = int(radius_tiles * tp)
    surf = _range_surface(r, color)
    screen.blit(surf, (int((x + 0.5) * tp + ox) - r - 1, int((y + 0.5) * tp + oy) - r - 1))


def draw_tower_ranges(screen, camera, factory, selected, hover_tile):
    """Range disc of the selected tower, or of the one under the cursor."""
    s = selected if (selected is not None and selected.KIND == "tower") else None
    if s is None and hover_tile is not None:
        h = factory.structure_at(*hover_tile)
        if h is not None and h.KIND == "tower":
            s = h
    if s is not None:
        draw_range(screen, camera, s.x, s.y, s.range)


def draw_ghost(screen, camera, kind, x, y, direction, ok, cost):
    cls = KINDS[kind]
    tp = camera.tile_px
    r = cls.SIZE // 2
    sx, sy = camera.tile_to_screen(x - r, y - r)
    if kind == "tower":
        draw_range(screen, camera, x, y, TOWER_RANGE)
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


def draw_belt_preview(screen, camera, factory, path, turn=0):
    """Transparent belts along the drag path (shapes follow the path; with an
    [R] turn every belt faces its turned direction instead), tinted green
    where a belt will be built or turned and red where it cannot be, plus
    the tile count and cost at the end of the path."""
    if not path:
        return
    tp = camera.tile_px
    ok_tint = pygame.Surface((tp, tp), pygame.SRCALPHA)
    ok_tint.fill((*COLORS["ghost_ok"], 60))
    bad_tint = pygame.Surface((tp, tp), pygame.SRCALPHA)
    bad_tint.fill((*COLORS["ghost_bad"], 80))
    new = 0
    for i, (x, y, d) in enumerate(path):
        in_sides = 0
        if i > 0 and not turn:
            px, py = path[i - 1][0], path[i - 1][1]
            if (px - x, py - y) in DIR_VEC:
                in_sides = 1 << DIR_VEC.index((px - x, py - y))
        d = (d + turn) % 4
        spr = sprite("belt", d, tp, None, 1, in_sides | ((1 << d) << 4)).copy()
        spr.set_alpha(150)
        sx, sy = camera.tile_to_screen(x, y)
        screen.blit(spr, (sx, sy))
        s = factory.structure_at(x, y)
        if isinstance(s, Belt):
            ok = True
        else:
            ok = s is None and factory.can_place("belt", x, y, d)[0]
            new += ok
        screen.blit(ok_tint if ok else bad_tint, (sx, sy))
    if tp >= 12:
        x, y, _ = path[-1]
        sx, sy = camera.tile_to_screen(x, y)
        txt = numbers.text(f"{new} belts = {new * COSTS['belt']}", 14, COLORS["ghost_ok"])
        screen.blit(txt, (sx + tp + 2, sy))


def draw_demolish_cursor(screen, camera, factory, tile):
    """Red frame around what the demolish tool would remove."""
    if tile is None:
        return
    tp = camera.tile_px
    s = factory.structure_at(*tile)
    if s is not None:
        r = s.SIZE // 2
        sx, sy = camera.tile_to_screen(s.x - r, s.y - r)
        size = tp * s.SIZE
        pygame.draw.rect(screen, (255, 70, 70), (sx - 1, sy - 1, size + 2, size + 2), 2)
        if tp >= 12:
            screen.blit(numbers.text(f"+{int(s.cost * 0.5)}", 14, (255, 110, 110)), (sx + size + 2, sy))
    else:
        sx, sy = camera.tile_to_screen(*tile)
        pygame.draw.rect(screen, (200, 70, 70), (sx, sy, tp, tp), 1)


def draw_hub_alert(screen, camera, factory, pulse):
    """Pulsing red double frame around the hub while it is taking damage
    (pulse in 0..1 from the caller's clock)."""
    hub = factory.hub
    if hub is None or not factory.hub_under_attack():
        return
    tp = camera.tile_px
    r = hub.SIZE // 2
    sx, sy = camera.tile_to_screen(hub.x - r, hub.y - r)
    size = tp * hub.SIZE
    th = max(2, int(tp * 0.12))
    bright = int(150 + 105 * pulse)
    pygame.draw.rect(screen, (bright // 2, 15, 15),
                     (sx - 2 * th - 2, sy - 2 * th - 2, size + 4 * th + 4, size + 4 * th + 4), th)
    pygame.draw.rect(screen, (bright, 30, 30), (sx - th - 1, sy - th - 1, size + 2 * th + 2, size + 2 * th + 2), th)


def draw_group_selection(screen, camera, structures):
    """Thin frames around every structure of a drag-box selection."""
    tp = camera.tile_px
    for s in structures:
        r = s.SIZE // 2
        sx, sy = camera.tile_to_screen(s.x - r, s.y - r)
        pygame.draw.rect(screen, (255, 255, 120), (sx, sy, tp * s.SIZE, tp * s.SIZE), 1)


def draw_selection(screen, camera, s):
    tp = camera.tile_px
    r = s.SIZE // 2
    sx, sy = camera.tile_to_screen(s.x - r, s.y - r)
    pygame.draw.rect(screen, (255, 255, 120), (sx - 1, sy - 1, tp * s.SIZE + 2, tp * s.SIZE + 2), 2)
    draw_side_roles(screen, camera, type(s), s.x, s.y, s.direction)


def draw_health_bars(screen, camera, factory):
    """Bars for damaged structures only (Factory.damaged): above a 1x1
    structure; for the hub a narrow bar just under its label."""
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
        frac = s.hp / s.max_hp
        if s.SIZE > 1:
            size = tp * s.SIZE
            label_px = max(8, int(tp * 0.38))
            bw, bh = tp, max(3, tp // 8)
            bx = sx + size // 2 - bw // 2
            by = sy + size // 2 + label_px // 2 + 2
        else:
            bw, bh = tp, 3
            bx, by = sx, sy - 4
        pygame.draw.rect(screen, COLORS["hp_bar_bg"], (bx, by, bw, bh))
        pygame.draw.rect(screen, COLORS["hp_bar"] if frac > 0.5 else (230, 160, 60) if frac > 0.25 else (230, 70, 60),
                         (bx, by, int(bw * frac), bh))
    for s in healed:
        factory.damaged.discard(s)
