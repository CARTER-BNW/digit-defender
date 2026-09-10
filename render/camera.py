"""Camera: (x, y) is the world-px coordinate (at zoom 1.0) under the screen
centre; zoom is a discrete step of ZOOM_LEVELS. All ZOOM_LEVELS * TILE_SIZE
are integers, so tiles and chunk surfaces land on whole pixels (no seams).
"""
import math

from settings import (CHUNK_PX, TILE_SIZE, ZOOM_LEVELS, DEFAULT_ZOOM_INDEX,
                      PRELOAD_CHUNKS, UNLOAD_MARGIN)


class Camera:
    def __init__(self, screen_w, screen_h, x=0.0, y=0.0,
                 zoom_index=DEFAULT_ZOOM_INDEX):
        self.x = float(x)
        self.y = float(y)
        self.w = screen_w
        self.h = screen_h
        self.zoom_index = max(0, min(len(ZOOM_LEVELS) - 1, zoom_index))

    @property
    def zoom(self):
        return ZOOM_LEVELS[self.zoom_index]

    @property
    def tile_px(self):
        """Screen pixels per tile at the current zoom (always an int)."""
        return int(round(TILE_SIZE * self.zoom))

    def resize(self, w, h):
        self.w, self.h = w, h

    def move(self, dx, dy):
        """Pan by world px."""
        self.x += dx
        self.y += dy

    # ---- transforms ------------------------------------------------------

    def world_to_screen(self, wx, wy):
        z = self.zoom
        return (round((wx - self.x) * z + self.w / 2),
                round((wy - self.y) * z + self.h / 2))

    def screen_to_world(self, sx, sy):
        z = self.zoom
        return ((sx - self.w / 2) / z + self.x,
                (sy - self.h / 2) / z + self.y)

    def screen_to_tile(self, sx, sy):
        wx, wy = self.screen_to_world(sx, sy)
        return math.floor(wx / TILE_SIZE), math.floor(wy / TILE_SIZE)

    def tile_to_screen(self, tx, ty):
        """Screen position of a tile's top-left corner."""
        return self.world_to_screen(tx * TILE_SIZE, ty * TILE_SIZE)

    # ---- zoom ------------------------------------------------------------

    def set_zoom_index(self, index, anchor=None):
        """Change zoom step keeping the world point under `anchor` (screen px,
        default: screen centre) fixed on screen."""
        index = max(0, min(len(ZOOM_LEVELS) - 1, index))
        if index == self.zoom_index:
            return
        if anchor is None:
            anchor = (self.w / 2, self.h / 2)
        sx, sy = anchor
        wx, wy = self.screen_to_world(sx, sy)
        self.zoom_index = index
        z = self.zoom
        self.x = wx - (sx - self.w / 2) / z
        self.y = wy - (sy - self.h / 2) / z

    def zoom_by(self, steps, anchor=None):
        self.set_zoom_index(self.zoom_index + steps, anchor)

    # ---- chunk ranges ----------------------------------------------------

    def visible_chunk_range(self, margin=0):
        """Inclusive (cx0, cy0, cx1, cy1) of chunks overlapping the screen,
        expanded by margin chunks on every side."""
        z = self.zoom
        left = self.x - (self.w / 2) / z
        top = self.y - (self.h / 2) / z
        right = left + self.w / z
        bottom = top + self.h / z
        return (math.floor(left / CHUNK_PX) - margin,
                math.floor(top / CHUNK_PX) - margin,
                math.floor(right / CHUNK_PX) + margin,
                math.floor(bottom / CHUNK_PX) + margin)

    def keep_unload_rects(self):
        return (self.visible_chunk_range(PRELOAD_CHUNKS),
                self.visible_chunk_range(UNLOAD_MARGIN))
