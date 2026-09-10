"""Renderer: terrain chunk surfaces cached per (chunk, zoom), drawn every
frame; structures/items/units draw directly (Phase 2+); F3 overlay.

Chunk surfaces are rendered straight at the target tile size (8..64 px), not
scaled from a 1.0 master: crisp at every zoom and small at low zoom. Only
chunks near the screen keep a surface (evict_offscreen), so memory stays
bounded even at 2.0 zoom (4 MB per chunk there).
"""
import pygame

from settings import (CHUNK_SIZE, CHUNK_PX, TILE_SIZE, COLORS, GROUND_SHADES,
                      DEPOSIT_COLORS, TEXT_MIN_ZOOM)
from world.tiles import GROUND_MAX, deposit_value, NEST_GROUND, NEST_CORE
from render import numbers


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.debug = False
        pygame.font.init()
        numbers.reset()
        self.font = numbers.font(16)
        self.surfaces_built = 0        # lifetime count (overlay / tests)

    # ---- frame -----------------------------------------------------------

    def draw(self, game):
        screen, camera, terrain = self.screen, game.camera, game.terrain
        screen.fill(COLORS["bg"])
        zoom = camera.zoom
        cx0, cy0, cx1, cy1 = camera.visible_chunk_range()
        chunk_px = int(CHUNK_PX * zoom)
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                chunk = terrain.get_chunk(cx, cy)
                sx, sy = camera.world_to_screen(cx * CHUNK_PX, cy * CHUNK_PX)
                screen.blit(self.chunk_surface(chunk, zoom), (sx, sy))
                if self.debug:
                    pygame.draw.rect(screen, (255, 60, 60),
                                     (sx, sy, chunk_px, chunk_px), 1)
        self.evict_offscreen(terrain, (cx0 - 1, cy0 - 1, cx1 + 1, cy1 + 1))
        if self.debug:
            self._overlay(game)

    # ---- chunk surface cache ---------------------------------------------

    def chunk_surface(self, chunk, zoom):
        if chunk.surface is None or chunk.dirty or chunk.surface_zoom != zoom:
            chunk.surface = self._render_chunk(chunk, zoom)
            chunk.surface_zoom = zoom
            chunk.dirty = False
            self.surfaces_built += 1
        return chunk.surface

    def _render_chunk(self, chunk, zoom):
        tp = int(round(TILE_SIZE * zoom))
        surf = pygame.Surface((CHUNK_SIZE * tp, CHUNK_SIZE * tp))
        tiles = chunk.tiles
        fill = surf.fill
        show_text = zoom >= TEXT_MIN_ZOOM
        digit_px = max(6, int(tp * 0.7))
        for i, tile in enumerate(tiles):
            lx, ly = i % CHUNK_SIZE, i // CHUNK_SIZE
            rect = (lx * tp, ly * tp, tp, tp)
            if tile <= GROUND_MAX:
                fill(GROUND_SHADES[tile >> 1][tile & 1], rect)
                continue
            digit = deposit_value(tile)
            if digit:
                fill(COLORS["deposit_bg"], rect)
                color = DEPOSIT_COLORS[digit]
                if show_text:
                    numbers.blit_centered(surf, numbers.text(str(digit), digit_px, color),
                                          lx * tp + tp // 2, ly * tp + tp // 2)
                else:
                    pad = max(1, tp // 4)
                    fill(color, (lx * tp + pad, ly * tp + pad, tp - 2 * pad, tp - 2 * pad))
            elif tile == NEST_GROUND:
                fill(COLORS["nest_ground"], rect)
            elif tile == NEST_CORE:
                fill(COLORS["nest_core"], rect)
            else:
                fill((255, 0, 255), rect)   # unknown id: loud
        return surf

    def evict_offscreen(self, terrain, rect):
        """Drop cached surfaces of loaded chunks outside rect (inclusive)."""
        x0, y0, x1, y1 = rect
        for (cx, cy), chunk in terrain.chunks.items():
            if chunk.surface is not None and not (x0 <= cx <= x1 and y0 <= cy <= y1):
                chunk.surface = None
                chunk.surface_zoom = None

    # ---- debug overlay ---------------------------------------------------

    def _overlay(self, game):
        cam, terrain = game.camera, game.terrain
        mx, my = pygame.mouse.get_pos()
        mtx, mty = cam.screen_to_tile(mx, my)
        cached = sum(1 for c in terrain.chunks.values() if c.surface is not None)
        lines = [
            f"FPS {game.clock.get_fps():.0f}   frame {game.frame}   tick {game.tick_count}",
            f"cam ({cam.x:.0f}, {cam.y:.0f}) px  tile ({cam.x / TILE_SIZE:.1f}, {cam.y / TILE_SIZE:.1f})  zoom {cam.zoom}",
            f"chunks loaded {len(terrain.chunks)}  surfaces {cached}  generated {terrain.generated}  built {self.surfaces_built}",
            f"mouse tile ({mtx}, {mty})  id {terrain.get_tile(mtx, mty)}  deposit {terrain.deposit_at(mtx, mty)}",
        ]
        lines.extend(game.debug_lines())
        surfs = [numbers.text(line, 16) for line in lines]
        panel = pygame.Surface((max(s.get_width() for s in surfs) + 16,
                                len(surfs) * 20 + 12), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 150))
        self.screen.blit(panel, (0, 0))
        y = 8
        for surf in surfs:
            self.screen.blit(surf, (8, y))
            y += 20
