"""Chunk: a 16x16 block of tile ids. Terrain only (ground, deposits, nests);
player structures never live here (docs/PLAN.md section 0).

`surface`/`surface_zoom` are an opaque render cache owned by render/renderer.py
so this module stays pygame-free and importable from tests and sim code.
"""
from settings import CHUNK_SIZE


class Chunk:
    __slots__ = ("cx", "cy", "tiles", "dirty", "modified", "surface", "surface_zoom")

    def __init__(self, cx, cy, tiles):
        self.cx = cx
        self.cy = cy
        self.tiles = tiles            # flat row-major list, index = ly * CHUNK_SIZE + lx
        self.dirty = True             # render cache stale
        self.modified = False         # differs from generated (needs saving)
        self.surface = None           # cached pygame Surface at surface_zoom
        self.surface_zoom = None

    def get(self, lx, ly):
        """Local coords 0..CHUNK_SIZE-1 -> tile id."""
        return self.tiles[ly * CHUNK_SIZE + lx]

    def set(self, lx, ly, tile_id):
        i = ly * CHUNK_SIZE + lx
        if self.tiles[i] != tile_id:
            self.tiles[i] = tile_id
            self.dirty = True
            self.modified = True

    def invalidate(self):
        self.dirty = True
        self.surface = None
        self.surface_zoom = None
