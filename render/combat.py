"""Draw enemies, player units, beams (number lasers), rally flags, nest core
hp bars and off-screen enemy/wave indicators."""
import math

import pygame

from settings import COLORS, TILE_SIZE, WAVE_WARNING_S
from render import numbers
from sim.combat import ENEMY, PLAYER
from sim import nests as nestmod

ENEMY_COLORS = {"grunt": (220, 50, 50), "brute": (170, 30, 60), "runner": (255, 110, 90)}
UNIT_COLORS = {"ranged": (80, 210, 230), "melee": (90, 230, 150), "heavy": (230, 200, 80)}
ENEMY_RADIUS = {"grunt": 0.32, "brute": 0.44, "runner": 0.24}


def _bar(screen, x, y, w, frac, color):
    pygame.draw.rect(screen, COLORS["hp_bar_bg"], (x, y, w, 3))
    pygame.draw.rect(screen, color, (x, y, max(0, int(w * frac)), 3))


def draw_combat(screen, camera, combat, selected=None, selected_units=(), box=None, flag_spawners=None):
    """flag_spawners: spawners whose gather flag is drawn (default: the
    selected one)."""
    tp = camera.tile_px
    ox, oy = camera.screen_origin()
    w, h = screen.get_size()
    chosen = {id(u) for u in selected_units}
    if flag_spawners is None:
        flag_spawners = [selected] if hasattr(selected, "rally_point") else []
    # beams first (under the units)
    for x0, y0, x1, y1, value, ttl, side in combat.beams:
        color = (255, 140, 70) if side == ENEMY else (120, 220, 255)
        a = (x0 * tp + ox, y0 * tp + oy)
        b = (x1 * tp + ox, y1 * tp + oy)
        pygame.draw.line(screen, color, a, b, max(1, tp // 10))
        if tp >= 16:
            screen.blit(numbers.text(numbers.abbrev(value), max(9, tp // 2), color),
                        (b[0] + 3, b[1] - tp // 2))
    # enemies
    for e in combat.enemies:
        sx, sy = int(e.x * tp + ox), int(e.y * tp + oy)
        if not (-tp <= sx <= w + tp and -tp <= sy <= h + tp):
            continue
        r = max(2, int(tp * ENEMY_RADIUS.get(e.kind, 0.3)))
        pygame.draw.circle(screen, ENEMY_COLORS.get(e.kind, COLORS["enemy"]), (sx, sy), r)
        pygame.draw.circle(screen, (60, 10, 10), (sx, sy), r, 1)
        if e.hp < e.max_hp and tp >= 8:
            _bar(screen, sx - r, sy - r - 5, 2 * r, e.hp / e.max_hp, (240, 80, 80))
    # player units
    for u in combat.units:
        sx, sy = int(u.x * tp + ox), int(u.y * tp + oy)
        if not (-tp <= sx <= w + tp and -tp <= sy <= h + tp):
            continue
        r = max(2, int(tp * (0.36 if u.kind == "heavy" else 0.28)))
        color = UNIT_COLORS.get(u.kind, COLORS["unit"])
        if id(u) in chosen:
            pygame.draw.circle(screen, (255, 255, 120), (sx, sy), r + max(2, tp // 8), max(1, tp // 16))
            if u.rally is not None and (u.x != u.rally[0] or u.y != u.rally[1]):
                gx, gy = int(u.rally[0] * tp + ox), int(u.rally[1] * tp + oy)
                q = max(2, tp // 6)
                pygame.draw.rect(screen, (255, 255, 120), (gx - q, gy - q, 2 * q, 2 * q), 1)
        pygame.draw.rect(screen, color, (sx - r, sy - r, 2 * r, 2 * r), border_radius=max(1, r // 3))
        pygame.draw.rect(screen, (10, 40, 50), (sx - r, sy - r, 2 * r, 2 * r), 1, border_radius=max(1, r // 3))
        if u.shot is not None and tp >= 12:
            pygame.draw.circle(screen, (255, 255, 255), (sx, sy), max(1, r // 3))
        if u.hp < u.max_hp and tp >= 8:
            _bar(screen, sx - r, sy - r - 5, 2 * r, u.hp / u.max_hp, COLORS["hp_bar"])
    # gather flags of the selected spawner(s)
    drawn = set()
    for sp in flag_spawners:
        rx, ry = sp.rally_point(combat.factory)
        if (rx, ry) in drawn:
            continue
        drawn.add((rx, ry))
        sx, sy = int(rx * tp + ox), int(ry * tp + oy)
        pygame.draw.line(screen, (255, 255, 120), (sx, sy), (sx, sy - tp), 2)
        pygame.draw.polygon(screen, (255, 255, 120), [(sx, sy - tp), (sx + tp // 2, sy - tp * 3 // 4), (sx, sy - tp // 2)])
    # drag box while selecting units
    if box is not None:
        (x0, y0), (x1, y1) = box
        rect = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        if rect.width >= 4 or rect.height >= 4:
            fill = pygame.Surface(rect.size, pygame.SRCALPHA)
            fill.fill((120, 220, 255, 40))
            screen.blit(fill, rect.topleft)
            pygame.draw.rect(screen, (120, 220, 255), rect, 1)
    # nest core hp bars
    for key, spec in combat.known_nests.items():
        if key not in combat.nests.damage:
            continue
        sx, sy = spec.tx * tp + ox, spec.ty * tp + oy
        if -tp <= sx <= w and -tp <= sy <= h:
            _bar(screen, sx - tp, sy - 6, tp * 3, combat.nests.hp(spec) / nestmod.nest_max_hp(spec), (240, 80, 80))


def draw_offscreen_indicators(screen, camera, combat, wave_warning_s=WAVE_WARNING_S):
    """Red edge arrows toward living enemies off-screen; a pulsing arrow
    toward the coming wave's direction in its last seconds."""
    w, h = screen.get_size()
    cx, cy = w / 2, h / 2
    targets = []
    for e in combat.enemies:
        sx, sy = camera.world_to_screen(e.x * TILE_SIZE, e.y * TILE_SIZE)
        if not (0 <= sx < w and 0 <= sy < h):
            targets.append((sx - cx, sy - cy, (240, 70, 70)))
    secs = combat.seconds_to_wave()
    if secs <= wave_warning_s:
        rx, ry, radius = combat.spawn_ring()
        wx = (rx + radius * math.cos(combat.wave.angle)) * TILE_SIZE
        wy = (ry + radius * math.sin(combat.wave.angle)) * TILE_SIZE
        sx, sy = camera.world_to_screen(wx, wy)
        pulse = 150 + int(100 * abs(math.sin(pygame.time.get_ticks() / 200)))
        targets.append((sx - cx, sy - cy, (pulse, 40, 40)))
    for dx, dy, color in targets[:40]:
        d = math.hypot(dx, dy)
        if d < 1:
            continue
        ux, uy = dx / d, dy / d
        # clamp to the screen edge (with margin)
        m = 30
        scale = min((w / 2 - m) / abs(ux) if ux else 1e9, (h / 2 - m) / abs(uy) if uy else 1e9)
        px, py = cx + ux * scale, cy + uy * scale
        tip = (px + ux * 12, py + uy * 12)
        left = (px - uy * 7, py + ux * 7)
        right = (px + uy * 7, py - ux * 7)
        pygame.draw.polygon(screen, color, [tip, left, right])
