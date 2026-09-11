"""Renderer: terrain chunk surfaces cached per (chunk, zoom), drawn every
frame; structures/items/units draw directly (Phase 2+); F3 overlay.

Chunk surfaces are rendered straight at the target tile size (8..64 px), not
scaled from a 1.0 master: crisp at every zoom and small at low zoom. Only
chunks near the screen keep a surface (evict_offscreen), so memory stays
bounded even at 2.0 zoom (4 MB per chunk there).
"""
import math

import pygame

from settings import (CHUNK_SIZE, CHUNK_PX, TILE_SIZE, COLORS, GROUND_SHADES,
                      DEPOSIT_COLORS, TEXT_MIN_ZOOM)
from world.tiles import GROUND_MAX, deposit_value, NEST_GROUND, NEST_CORE
from render import numbers
from render import structures as rstruct
from render import combat as rcombat
from sim import nests as nestmod


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.debug = False
        pygame.font.init()
        numbers.reset()
        self.font = numbers.font(16)
        self.surfaces_built = 0        # lifetime count (overlay / tests)
        self.nests = None              # NestRegistry: destroyed nests render as rubble

    # ---- frame -----------------------------------------------------------

    def draw(self, game):
        screen, camera, terrain = self.screen, game.camera, game.terrain
        screen.fill(COLORS["bg"])
        zoom = camera.zoom
        cx0, cy0, cx1, cy1 = camera.visible_chunk_range()
        chunk_px = int(CHUNK_PX * zoom)
        ox, oy = camera.screen_origin()
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                chunk = terrain.peek_chunk(cx, cy)    # budgeted generation: may lag a frame
                if chunk is None:
                    continue
                sx, sy = cx * chunk_px + ox, cy * chunk_px + oy
                screen.blit(self.chunk_surface(chunk, zoom), (sx, sy))
                if self.debug:
                    pygame.draw.rect(screen, (255, 60, 60),
                                     (sx, sy, chunk_px, chunk_px), 1)
        self.evict_offscreen(terrain, (cx0 - 1, cy0 - 1, cx1 + 1, cy1 + 1))
        factory = getattr(game, "factory", None)
        if factory is not None:
            rect = (cx0, cy0, cx1, cy1)
            rstruct.draw_structures(screen, camera, factory, rect, getattr(game, "render_frac", 0.0))
            rstruct.draw_miner_pulses(screen, camera, factory, rect)
            rstruct.draw_health_bars(screen, camera, factory)
            rstruct.draw_hub_alert(screen, camera, factory, 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 120.0))
            selected = getattr(game, "selected", None)
            rstruct.draw_tower_ranges(screen, camera, factory, selected, getattr(game, "hover_tile", None))
            if selected is not None:
                rstruct.draw_selection(screen, camera, selected)
            group = getattr(game, "selected_structures", None)
            if group:
                rstruct.draw_group_selection(screen, camera, group)
            combat = factory.combat
            if combat is not None:
                box = None
                if getattr(game, "box_start", None) is not None:
                    box = (game.box_start, game.box_end)
                rcombat.draw_combat(screen, camera, combat, selected,
                                    getattr(game, "selected_units", ()), box)
            ghost = game.ghost() if hasattr(game, "ghost") else None
            if ghost is not None:
                rstruct.draw_ghost(screen, camera, *ghost)
            if getattr(game, "belt_path", None):
                rstruct.draw_belt_preview(screen, camera, factory, game.belt_path, getattr(game, "belt_turn", 0))
            if getattr(game, "tool", None) == "demolish":
                rstruct.draw_demolish_cursor(screen, camera, factory, getattr(game, "hover_tile", None))
            if combat is not None:
                rcombat.draw_offscreen_indicators(screen, camera, combat)
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
        rubble = (self.nests is not None and
                  self.nests.is_destroyed(*nestmod.region_of_chunk(chunk.cx, chunk.cy)))
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
                    numbers.blit_centered(surf, numbers.glyph(str(digit), digit_px, color),
                                          lx * tp + tp // 2, ly * tp + tp // 2)
                else:
                    pad = max(1, tp // 4)
                    fill(color, (lx * tp + pad, ly * tp + pad, tp - 2 * pad, tp - 2 * pad))
            elif tile == NEST_GROUND:
                fill((48, 44, 40) if rubble else COLORS["nest_ground"], rect)
            elif tile == NEST_CORE:
                fill((70, 62, 56) if rubble else COLORS["nest_core"], rect)
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
