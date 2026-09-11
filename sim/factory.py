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
                            Wall, FRONT, BACK, LEFT, RIGHT, entry_side, DIR_VEC, ROLE_IN)

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
        self.targets = economy.initial_targets(seed, TARGET_COUNT)   # one per slot, level 1
        self.targets_completed = 0
        self.tick_count = 0
        self.dirty_links = True
        self.dirty_flowfield = True
        self.stats = {"delivered": 0, "mined": 0, "voided": 0, "bonus": 0}
        self.events = []                # transient notifications for the UI (cleared by reader)
        self.damaged = set()            # structures with hp < max_hp (health bars)
        self.hub_hit_tick = -10 ** 9    # last tick the hub took damage (alert border)
        self.hub_destroyed = False
        self.combat = None              # sim.combat.Combat when attached (Phase 5)

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
            if kind != "miner" and self.terrain is not None and self.terrain.deposit_at(*t):
                return False, "only miners go on numbers"
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
        """Hub income. A delivery of a target's number counts toward its
        amount; a finished target pays its bonus and its slot levels up
        (event: ("target", value, reward, amount, next level, next value,
        next amount))."""
        self.balance += value
        self.stats["delivered"] += value
        for i, t in enumerate(self.targets):
            if t.value != value:
                continue
            t.delivered += 1
            if t.done:
                self.balance += t.reward
                self.stats["bonus"] += t.reward
                self.targets_completed += 1
                nxt = economy.next_level(self.seed, t, (o.value for o in self.targets if o is not t))
                self.targets[i] = nxt
                self.events.append(("target", t.value, t.reward, t.amount, nxt.level, nxt.value, nxt.amount))
            break

    def hub_under_attack(self):
        """True for HUB_ALERT_S after the hub last took damage."""
        from settings import HUB_ALERT_S, TICK_RATE
        return self.tick_count - self.hub_hit_tick < HUB_ALERT_S * TICK_RATE

    def damage(self, s, amount):
        """Apply combat damage. Returns True if the structure was destroyed."""
        s.hp -= amount
        if s is self.hub:
            self.hub_hit_tick = self.tick_count
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

    @staticmethod
    def upgrade_cost(s):
        """Fixed price of s's next level: 100 * 1.25^(level-1) balance, the
        same as the fed total that level needs (1 balance = 1 fed). Numbers
        already fed toward the level are not discounted; the paid amount is
        fed in full, so any excess carries into the following level."""
        from sim import leveling
        return leveling.level_cost(s.level)

    def upgrade(self, s):
        """Pay balance to lift s to its next level (idea.txt: balance is spent
        to create / improve / repair). Returns the cost paid, or 0."""
        cost = self.upgrade_cost(s)
        if not cost or self.balance < cost:
            return 0
        self.balance -= cost
        s.feed(cost)
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
        for s in self.belts + self.machines:
            nxt = structures.get(s.front_tile())
            if nxt is s:
                nxt = None
            s.next = nxt
            s.next_rel = entry_side(s.direction, nxt.direction) if nxt is not None else 0
        for m in self.miners:                        # every neighbour that takes cargo
            outs = []
            for d in range(4):
                dx, dy = DIR_VEC[d]
                nb = structures.get((m.x + dx, m.y + dy))
                if nb is None or nb is m:
                    continue
                rel = entry_side(d, nb.direction)
                if nb.SIDE_ROLES[rel] == ROLE_IN:
                    outs.append((nb, rel))
            m.outputs = outs
        # belts that already receive cargo (from a line, a miner or a machine),
        # and those receiving it through a side (corners and merges)
        pushed = set()
        side_fed = set()
        for s in self.belts + self.machines:
            nxt = s.next
            if isinstance(nxt, Belt) and s.next_rel != FRONT:
                pushed.add(id(nxt))
                if s.next_rel != BACK:
                    side_fed.add(id(nxt))
        for m in self.miners:
            for nb, rel in m.outputs:
                if isinstance(nb, Belt):
                    pushed.add(id(nb))
                    if rel != BACK:
                        side_fed.add(id(nb))
        # belt outputs: the front target plus, for a straight (back-fed) belt,
        # belts beside it that lead straight away and have no cargo source of
        # their own. A belt that merely starts beside a line is a branch (that
        # is how T-junctions are made); the corner of a parallel line, or the
        # old tail left beside a turned belt, is not (John, 2026-09-11).
        for b in self.belts:
            outs = []
            if b.next is not None:
                outs.append((b.next, b.next_rel, b.direction))
            if id(b) not in side_fed:
                for rel in (LEFT, RIGHT):
                    d = (b.direction + rel) % 4
                    dx, dy = DIR_VEC[d]
                    nb = structures.get((b.x + dx, b.y + dy))
                    if isinstance(nb, Belt) and nb.direction == d and id(nb) not in pushed:
                        outs.append((nb, BACK, d))
            b.outputs = outs
            b.feeders = []
            b.in_sides = 0
            b.out_sides = 0
        for b in self.belts:
            side_outs = False
            for nb, rel, d in b.outputs:
                if d != b.direction:
                    side_outs = True
                b.out_sides |= 1 << d
                if isinstance(nb, Belt) and rel != FRONT:
                    nb.feeders.append(b)
                    nb.in_sides |= 1 << DIR_VEC.index((b.x - nb.x, b.y - nb.y))
            if not side_outs:
                b.out_sides |= 1 << b.direction      # a plain belt always continues forward
        for m in self.miners:
            for nb, rel in m.outputs:
                if isinstance(nb, Belt):
                    nb.in_sides |= 1 << DIR_VEC.index((m.x - nb.x, m.y - nb.y))
        for mc in self.machines:
            nb = mc.next
            if isinstance(nb, Belt) and mc.next_rel != FRONT:
                nb.in_sides |= 1 << DIR_VEC.index((mc.x - nb.x, mc.y - nb.y))
        for w in self.walls:                         # walls join their wall neighbours
            links = 0
            for d, (dx, dy) in enumerate(DIR_VEC):
                if isinstance(structures.get((w.x + dx, w.y + dy)), Wall):
                    links |= 1 << d
            w.links = links
        for b in self.belts:
            if len(b.feeders) > 1:
                b.feeders.sort(key=lambda f: (
                    _MERGE_PRIORITY[entry_side(DIR_VEC.index((b.x - f.x, b.y - f.y)), b.direction)],
                    f.y, f.x))
        # downstream-first order (Kahn over cargo links); loops broken at the smallest (y, x)
        remaining = {id(b): sum(1 for nb, rel, _ in b.outputs
                                if isinstance(nb, Belt) and rel != FRONT)
                     for b in self.belts}
        ordered = []
        visited = set()
        ready = deque(b for b in self.belts if remaining[id(b)] == 0)

        def drain():
            while ready:
                b = ready.popleft()
                if id(b) in visited:
                    continue
                visited.add(id(b))
                ordered.append(b)
                for f in b.feeders:
                    remaining[id(f)] -= 1
                    if remaining[id(f)] <= 0:
                        ready.append(f)

        drain()
        for b in self.belts:
            if id(b) not in visited:
                remaining[id(b)] = 0
                ready.append(b)
                drain()
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
            "targets_completed": self.targets_completed,
            "stats": dict(self.stats),
            "structures": structure_records(self),
        }

    @classmethod
    def from_dict(cls, d, seed=0, terrain=None):
        from sim.serialize import load_structure_records
        f = cls(seed, terrain, balance=int(d.get("balance", START_BALANCE)))
        f.tick_count = int(d.get("tick_count", 0))
        f.targets_completed = int(d.get("targets_completed", 0))
        if d.get("targets"):
            f.targets = [economy.Target.from_dict(t, i) for i, t in enumerate(d["targets"])]
            economy.top_up(seed, f.targets, TARGET_COUNT)      # older saves carried fewer slots
        f.stats.update(d.get("stats", {}))
        load_structure_records(f, d.get("structures", {}))
        return f
