"""Factory: the world-level structure dict and the fixed tick.

Structures live here (every occupied tile maps to its object), never in
terrain chunks, so the factory simulates whether or not a chunk is loaded.

TICK ORDER (fixed; load-bearing for determinism, docs/PLAN.md section 2.3):
  1. rebuild links if dirty (also sorts the typed lists by (y, x))
  2. miners
  3. machines (push finished output, count down, start next op)
  4. belts, downstream-first (belts_ordered)
  5-7. combat (Phase 5)
Belt ordering: BFS upstream from every sink (a belt whose next is not a belt
it feeds as cargo), sinks and loop-breakers taken in (y, x) order, merge
feeders in BACK, LEFT, RIGHT priority. Never dict iteration order.
"""
from collections import deque

from settings import (CHUNK_SIZE, START_BALANCE, TARGET_COUNT, COSTS)
from sim import economy
from sim.structures import (KINDS, Belt, Miner, MathMachine, Hub, Tower, Spawner,
                            Wall, FRONT, BACK, LEFT, RIGHT, entry_side)

_MERGE_PRIORITY = {BACK: 0, LEFT: 1, RIGHT: 2}


def _key(s):
    return (s.y, s.x)


class Factory:
    def __init__(self, seed=0, terrain=None, balance=START_BALANCE):
        self.seed = seed
        self.terrain = terrain          # deposit_at(tx,ty) / get_tile(tx,ty), or None
        self.balance = balance
        self.structures = {}            # (tx, ty) -> Structure (every occupied tile)
        self.by_chunk = {}              # (cx, cy) -> [Structure] for rendering
        self.belts = []
        self.belts_ordered = []
        self.miners = []
        self.machines = []
        self.towers = []
        self.spawners = []
        self.walls = []
        self.hub = None
        self.targets = []
        self.targets_generated = 0
        self.targets_completed = 0
        self.tick_count = 0
        self.dirty_links = True
        self.dirty_flowfield = True
        self.stats = {"delivered": 0, "mined": 0, "voided": 0, "bonus": 0}
        self.events = []                # transient notifications for the UI (cleared by reader)
        self.damaged = set()            # structures with hp < max_hp (health bars)
        self.hub_destroyed = False
        self.combat = None              # sim.combat.Combat when attached (Phase 5)
        while len(self.targets) < TARGET_COUNT:
            self.targets.append(self._new_target())

    # ---- queries -----------------------------------------------------------

    def structure_at(self, tx, ty):
        return self.structures.get((tx, ty))

    def all_structures(self):
        """Unique structures (the hub occupies 9 keys)."""
        out = list(self.belts) + self.miners + self.machines + self.towers \
            + self.spawners + self.walls
        if self.hub is not None:
            out.append(self.hub)
        return out

    def count(self):
        return len(self.all_structures())

    # ---- placement ---------------------------------------------------------

    def create_hub(self, x=0, y=0):
        hub = Hub(x, y)
        self.add_structure(hub)
        return hub

    def can_place(self, kind, x, y, direction=0):
        """(ok, reason). Does not deduct."""
        cls = KINDS.get(kind)
        if cls is None or kind == "hub":
            return False, "cannot build that"
        probe = cls(x, y, direction)
        for t in probe.tiles():
            if t in self.structures:
                return False, "occupied"
            if self.terrain is not None and not self.terrain.buildable(*t):
                return False, "cannot build here"
        if kind == "miner":
            if self.terrain is None or self.terrain.deposit_at(x, y) == 0:
                return False, "miner needs a deposit"
        cost = COSTS.get(kind, 0)
        if self.balance < cost:
            return False, f"need {cost}"
        return True, ""

    def place(self, kind, x, y, direction=0, free=False, value=None):
        """Build kind at (x, y). Returns the structure or None. `free` skips
        cost and terrain checks (tests / world setup); `value` overrides a
        miner's deposit digit (headless tests)."""
        if not free:
            ok, _ = self.can_place(kind, x, y, direction)
            if not ok:
                return None
        cls = KINDS[kind]
        if kind == "miner":
            if value is None:
                value = self.terrain.deposit_at(x, y) if self.terrain is not None else 0
            s = cls(x, y, direction, value)
        else:
            s = cls(x, y, direction)
        if any(t in self.structures for t in s.tiles()):
            return None
        if not free:
            self.balance -= COSTS.get(kind, 0)
        self.add_structure(s)
        return s

    def add_structure(self, s):
        for t in s.tiles():
            self.structures[t] = s
        for ck in self._chunks_of(s):
            self.by_chunk.setdefault(ck, []).append(s)
        if isinstance(s, Belt):
            self.belts.append(s)
        elif isinstance(s, Miner):
            self.miners.append(s)
        elif isinstance(s, MathMachine):
            self.machines.append(s)
        elif isinstance(s, Tower):
            self.towers.append(s)
        elif isinstance(s, Spawner):
            self.spawners.append(s)
        elif isinstance(s, Wall):
            self.walls.append(s)
        elif isinstance(s, Hub):
            self.hub = s
        self.dirty_links = True

    def remove(self, tx, ty, refund=True):
        """Demolish the structure covering (tx, ty). Returns it or None.
        The hub cannot be demolished."""
        s = self.structures.get((tx, ty))
        if s is None or s is self.hub:
            return None
        self._unregister(s)
        if refund:
            self.balance += economy.demolish_refund(s.KIND)
        return s

    def _unregister(self, s):
        for t in s.tiles():
            self.structures.pop(t, None)
        for ck in self._chunks_of(s):
            lst = self.by_chunk.get(ck)
            if lst:
                lst.remove(s)
                if not lst:
                    del self.by_chunk[ck]
        for lst in (self.belts, self.miners, self.machines, self.towers,
                    self.spawners, self.walls):
            if s in lst:
                lst.remove(s)
                break
        self.dirty_links = True

    def rotate(self, tx, ty):
        s = self.structures.get((tx, ty))
        if s is None or s is self.hub:
            return None
        s.direction = (s.direction + 1) % 4
        self.dirty_links = True
        return s

    def clear_structures(self):
        self.structures.clear()
        self.by_chunk.clear()
        for lst in (self.belts, self.belts_ordered, self.miners, self.machines,
                    self.towers, self.spawners, self.walls):
            lst.clear()
        self.hub = None
        self.dirty_links = True

    @staticmethod
    def _chunks_of(s):
        return {(tx // CHUNK_SIZE, ty // CHUNK_SIZE) for tx, ty in s.tiles()}

    # ---- economy -----------------------------------------------------------

    def deliver(self, value):
        """Hub income; exact target matches pay their bonus and reroll."""
        self.balance += value
        self.stats["delivered"] += value
        for i, t in enumerate(self.targets):
            if t.value == value:
                self.balance += t.reward
                self.stats["bonus"] += t.reward
                self.targets_completed += 1
                self.events.append(("target", t.value, t.reward))
                self.targets[i] = self._new_target()
                break

    def _new_target(self):
        """Next seeded target, skipping values already on the board."""
        active = {t.value for t in self.targets}
        for _ in range(16):
            t = economy.make_target(self.seed, self.targets_generated, self.targets_completed)
            self.targets_generated += 1
            if t.value not in active:
                return t
        return t

    def damage(self, s, amount):
        """Apply combat damage. Returns True if the structure was destroyed."""
        s.hp -= amount
        if s.hp > 0:
            self.damaged.add(s)
            return False
        self.damaged.discard(s)
        if s is self.hub:
            self.hub_destroyed = True
            return True
        self._unregister(s)
        self.events.append(("destroyed", s.KIND, s.x, s.y))
        return True

    def repair(self, s):
        """Restore hp to max at REPAIR_COST_PER_HP per point (Phase 4)."""
        from settings import REPAIR_COST_PER_HP
        missing = s.max_hp - s.hp
        if missing <= 0:
            return 0
        cost = int(missing * REPAIR_COST_PER_HP + 0.999)
        if self.balance < cost:
            return 0
        self.balance -= cost
        s.hp = s.max_hp
        self.damaged.discard(s)
        return cost

    # ---- tick --------------------------------------------------------------

    def tick(self):
        if self.dirty_links:
            self.rebuild_links()
        for m in self.miners:
            m.tick(self)
        for m in self.machines:
            m.tick(self)
        for b in self.belts_ordered:
            b.tick(self)
        for s in self.spawners:
            s.tick(self)
        for t in self.towers:
            t.tick(self)
        if self.combat is not None:
            self.combat.tick()
        self.tick_count += 1

    def rebuild_links(self):
        for lst in (self.belts, self.miners, self.machines, self.towers,
                    self.spawners, self.walls):
            lst.sort(key=_key)
        structures = self.structures
        for s in self.belts + self.miners + self.machines:
            nxt = structures.get(s.front_tile())
            if nxt is s:
                nxt = None
            s.next = nxt
            s.next_rel = entry_side(s.direction, nxt.direction) if nxt is not None else 0
        for b in self.belts:
            b.feeders = []
        for b in self.belts:
            nxt = b.next
            if isinstance(nxt, Belt) and b.next_rel != FRONT:
                nxt.feeders.append(b)
        for b in self.belts:
            if len(b.feeders) > 1:
                b.feeders.sort(key=lambda f: (_MERGE_PRIORITY[f.next_rel], f.y, f.x))
        ordered = []
        visited = set()

        def walk(start):
            queue = deque((start,))
            while queue:
                b = queue.popleft()
                if id(b) in visited:
                    continue
                visited.add(id(b))
                ordered.append(b)
                queue.extend(b.feeders)

        for b in self.belts:                         # sinks first, in (y, x) order
            if not (isinstance(b.next, Belt) and b.next_rel != FRONT):
                walk(b)
        for b in self.belts:                         # loops: smallest (y, x) breaks
            if id(b) not in visited:
                walk(b)
        self.belts_ordered = ordered
        self.dirty_links = False
        self.dirty_flowfield = True

    # ---- persistence -------------------------------------------------------

    def to_dict(self):
        from sim.serialize import structure_records
        return {
            "balance": self.balance,
            "tick_count": self.tick_count,
            "targets": [t.to_dict() for t in self.targets],
            "targets_generated": self.targets_generated,
            "targets_completed": self.targets_completed,
            "stats": dict(self.stats),
            "structures": structure_records(self),
        }

    @classmethod
    def from_dict(cls, d, seed=0, terrain=None):
        from sim.serialize import load_structure_records
        f = cls(seed, terrain, balance=int(d.get("balance", START_BALANCE)))
        f.tick_count = int(d.get("tick_count", 0))
        f.targets_generated = int(d.get("targets_generated", f.targets_generated))
        f.targets_completed = int(d.get("targets_completed", 0))
        if d.get("targets"):
            f.targets = [economy.Target.from_dict(t) for t in d["targets"]]
        f.stats.update(d.get("stats", {}))
        load_structure_records(f, d.get("structures", {}))
        return f
