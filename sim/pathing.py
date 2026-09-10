"""Enemy pathing (docs/PLAN.md section 3.7).

v1 greedy_step: walk toward a goal along the larger axis; whatever blocks
gets attacked (Combat handles that).
v2 FlowField: one Dijkstra from the hub tiles over the structure bounding box
(+ FLOW_MARGIN) with tile costs empty 1 / wall FLOW_COST_WALL / other
structure FLOW_COST_STRUCT, so enemies route around walls and chew through
the cheapest point when enclosed. Rebuilt only when Factory.dirty_flowfield
and at most every FLOW_REFRESH_TICKS ticks; enemies outside it fall back to
greedy. Ties break on (cost, y, x): deterministic.
"""
import heapq
import math

from settings import FLOW_COST_WALL, FLOW_COST_STRUCT, FLOW_MARGIN

MAX_FIELD_TILES = 60000
NEIGHBOURS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def greedy_step(tx, ty, gx, gy):
    """Neighbour tile of (tx, ty) that reduces the larger axis gap to the
    goal tile; None when already there."""
    dx, dy = gx - tx, gy - ty
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy):
        return (tx + (1 if dx > 0 else -1), ty)
    return (tx, ty + (1 if dy > 0 else -1))


def tile_cost(factory, tx, ty):
    s = factory.structures.get((tx, ty))
    if s is None:
        return 1
    if s.KIND == "wall":
        return FLOW_COST_WALL
    return FLOW_COST_STRUCT


class FlowField:
    def __init__(self):
        self.dist = {}
        self.rect = None
        self.built_tick = -10 ** 9
        self.built = False

    def contains(self, tx, ty):
        return (tx, ty) in self.dist

    def build(self, factory, tick=0):
        self.built_tick = tick
        self.built = True
        self.dist = {}
        hub = factory.hub
        if hub is None or not factory.structures:
            self.rect = None
            return
        keys = factory.structures.keys()
        xs = [k[0] for k in keys]
        ys = [k[1] for k in keys]
        margin = FLOW_MARGIN
        x0, x1 = min(xs) - margin, max(xs) + margin
        y0, y1 = min(ys) - margin, max(ys) + margin
        while (x1 - x0 + 1) * (y1 - y0 + 1) > MAX_FIELD_TILES and margin > 2:
            margin -= 2
            x0, x1 = min(xs) - margin, max(xs) + margin
            y0, y1 = min(ys) - margin, max(ys) + margin
        self.rect = (x0, y0, x1, y1)
        dist = self.dist
        heap = []
        for t in hub.tiles():
            dist[t] = 0
            heapq.heappush(heap, (0, t[1], t[0]))
        structures = factory.structures
        while heap:
            d, y, x = heapq.heappop(heap)
            if dist.get((x, y), 10 ** 12) < d:
                continue
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if not (x0 <= nx <= x1 and y0 <= ny <= y1):
                    continue
                s = structures.get((nx, ny))
                cost = 1 if s is None else (FLOW_COST_WALL if s.KIND == "wall" else FLOW_COST_STRUCT)
                nd = d + cost
                if nd < dist.get((nx, ny), 10 ** 12):
                    dist[(nx, ny)] = nd
                    heapq.heappush(heap, (nd, ny, nx))

    def next_step(self, tx, ty):
        """Neighbour with the lowest distance to the hub, or None when the
        tile is outside the field or nothing is lower."""
        here = self.dist.get((tx, ty))
        if here is None:
            return None
        best = None
        best_key = (here, ty, tx)
        for dx, dy in NEIGHBOURS:
            n = (tx + dx, ty + dy)
            d = self.dist.get(n)
            if d is None:
                continue
            key = (d, n[1], n[0])
            if key < best_key:
                best_key = key
                best = n
        return best

    def distance(self, tx, ty):
        return self.dist.get((tx, ty))


def dist_to_tiles(x, y, tiles):
    """Distance from a point to the nearest tile centre of a footprint."""
    return min(math.hypot(x - (tx + 0.5), y - (ty + 0.5)) for tx, ty in tiles)
