"""Terrain: single owner of the chunk dict. Lazy generate-on-first-sight,
keep/unload hysteresis. Holds NO gameplay state: the factory lives in
sim.factory.Factory and simulates whether or not a chunk is loaded.

Persistence (Phase 3): only modified chunks are ever written, and deposits are
infinite, so in practice nothing is; the hook stays for the future.
"""
from settings import CHUNK_SIZE, WORLD_SEED, CHUNK_GEN_BUDGET
from world.chunk import Chunk
from world.generator import generate_chunk
from world.tiles import deposit_value, is_buildable


class Terrain:
    def __init__(self, seed=WORLD_SEED, save_dir=None):
        self.seed = seed
        self.save_dir = save_dir
        self.chunks = {}              # (cx, cy) -> Chunk
        self.generated = 0            # lifetime count (debug overlay / tests)
        self.loader = None            # Phase 3: callable(cx, cy) -> tiles | None
        self.saver = None             # Phase 3: callable(chunk)

    # ---- chunks --------------------------------------------------------------

    def get_chunk(self, cx, cy):
        chunk = self.chunks.get((cx, cy))
        if chunk is None:
            tiles = self.loader(cx, cy) if self.loader else None
            if tiles is None:
                tiles = generate_chunk(self.seed, cx, cy)
                self.generated += 1
            chunk = Chunk(cx, cy, tiles)
            self.chunks[(cx, cy)] = chunk
        return chunk

    def peek_chunk(self, cx, cy):
        """Loaded chunk or None; never generates."""
        return self.chunks.get((cx, cy))

    # ---- tiles ---------------------------------------------------------------

    def get_tile(self, tx, ty):
        """World tile coords (any sign) -> tile id. Always divmod: negative
        coordinates are everywhere."""
        cx, lx = divmod(tx, CHUNK_SIZE)
        cy, ly = divmod(ty, CHUNK_SIZE)
        return self.get_chunk(cx, cy).tiles[ly * CHUNK_SIZE + lx]

    def deposit_at(self, tx, ty):
        """Digit 1..9 of the deposit under a tile, else 0."""
        return deposit_value(self.get_tile(tx, ty))

    def buildable(self, tx, ty):
        """Structures may go on ground and deposits, never on nest tiles."""
        return is_buildable(self.get_tile(tx, ty))

    def set_tile(self, tx, ty, tile_id):
        cx, lx = divmod(tx, CHUNK_SIZE)
        cy, ly = divmod(ty, CHUNK_SIZE)
        self.get_chunk(cx, cy).set(lx, ly, tile_id)

    # ---- streaming -----------------------------------------------------------

    def update(self, keep_rect, unload_rect, priority_rect=None, budget=None):
        """keep_rect: inclusive (cx0, cy0, cx1, cy1) that should be loaded.
        unload_rect: larger inclusive range; chunks outside it are saved (if
        modified) and dropped. The gap between the two is the hysteresis.
        At most `budget` chunks are generated per call (priority_rect, the
        visible area, first) so a full zoom-out never freezes a frame; the
        rest arrive over the next frames."""
        if budget is None:
            budget = CHUNK_GEN_BUDGET
        generated = 0
        rects = (priority_rect, keep_rect) if priority_rect else (keep_rect,)
        for rect in rects:
            cx0, cy0, cx1, cy1 = rect
            for cy in range(cy0, cy1 + 1):
                for cx in range(cx0, cx1 + 1):
                    if (cx, cy) not in self.chunks:
                        if generated >= budget:
                            break
                        self.get_chunk(cx, cy)
                        generated += 1
        ux0, uy0, ux1, uy1 = unload_rect
        stale = [k for k in self.chunks
                 if not (ux0 <= k[0] <= ux1 and uy0 <= k[1] <= uy1)]
        for key in stale:
            self._save_if_modified(self.chunks.pop(key))

    def save_modified(self):
        for chunk in self.chunks.values():
            self._save_if_modified(chunk)

    def _save_if_modified(self, chunk):
        if chunk.modified and self.saver:
            self.saver(chunk)
            chunk.modified = False
