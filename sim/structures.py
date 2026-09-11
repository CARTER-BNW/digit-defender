"""Structures: Belt, Miner, MathMachine (Adder/Subtractor/Multiplier/Divider),
Hub, Wall, Tower, Spawner. Headless: no pygame anywhere in sim/.

Directions: 0=N, 1=E, 2=S, 3=W (screen y grows downward, so N = -y).
`direction` is the OUTPUT side for belts, miners and machines.

Relative sides (as seen from the receiving structure): FRONT=0 (its output
side), RIGHT=1, BACK=2, LEFT=3. An item pushed along direction d into a
structure facing nd enters through side entry_side(d, nd).

THE FEED RULE (docs/PLAN.md section 3.5): an item entering through a side that
is not a cargo input is consumed as feed: invested += value, hp += value
(capped). invested drives level, speed/rate and max_hp.
  Belt:     BACK/LEFT/RIGHT = cargo (tail / side merge), FRONT (head-on) = feed
  Machine:  LEFT = operand A, RIGHT = operand B, BACK = feed, FRONT refuses
  Hub:      every side = income
  Miner:    pushes its digit into EVERY adjacent cargo input (belt back/side,
            machine A/B, hub, tower ammo) each period; never into feed sides
            (so two miners never level each other). Belts pointing into it feed it.
  Wall/Spawner: every side = feed
  Tower:    FRONT = ammo, other sides = feed
Every structure has to_dict()/from_dict() from day one (save/load).
"""
from collections import deque

from settings import (COSTS, ITEM_SPACING, MINER_BASE_PERIOD, MACHINE_BASE_PERIOD,
                      MACHINE_BUFFER, TOWER_AMMO_MAX, TOWER_RANGE, TOWER_BASE_PERIOD,
                      TOWER_DMG_LEVEL_MULT, SPAWNER_BASE_PERIOD, SPAWNER_UNIT_CAP)
from sim import leveling

N, E, S, W = 0, 1, 2, 3
DIR_VEC = ((0, -1), (1, 0), (0, 1), (-1, 0))
DIR_NAMES = ("N", "E", "S", "W")
FRONT, RIGHT, BACK, LEFT = 0, 1, 2, 3
EPS = 1e-6                     # a stalled head item parks at 1 - EPS

ROLE_IN, ROLE_OUT, ROLE_FEED = "in", "out", "feed"


def entry_side(from_direction, into_direction):
    """Relative side of a structure facing into_direction through which an
    item travelling along from_direction enters it."""
    return ((from_direction + 2) - into_direction) % 4


class Structure:
    __slots__ = ("x", "y", "direction", "invested", "hp", "next", "next_rel")
    KIND = "structure"
    SIZE = 1                   # footprint side (odd); anchor = centre
    HAS_OUTPUT = False         # resolves `next` (the structure at its front tile)
    SIDE_ROLES = (ROLE_FEED, ROLE_FEED, ROLE_FEED, ROLE_FEED)   # front, right, back, left

    def __init__(self, x, y, direction=N):
        self.x = x
        self.y = y
        self.direction = direction % 4
        self.invested = 0
        self.hp = self.max_hp
        self.next = None       # resolved link cache (Factory.rebuild_links)
        self.next_rel = 0      # relative side of `next` we push into

    # ---- derived -----------------------------------------------------------

    @property
    def cost(self):
        return COSTS.get(self.KIND, 0)

    @property
    def max_hp(self):
        return leveling.max_hp(self.KIND, self.invested)

    @property
    def level(self):
        return leveling.level(self.invested)

    def tiles(self):
        r = self.SIZE // 2
        if r == 0:
            return [(self.x, self.y)]
        return [(self.x + dx, self.y + dy)
                for dy in range(-r, r + 1) for dx in range(-r, r + 1)]

    def front_tile(self):
        dx, dy = DIR_VEC[self.direction]
        r = self.SIZE // 2 + 1
        return self.x + dx * r, self.y + dy * r

    def side_tile(self, rel):
        """Neighbour tile beyond relative side rel (1x1 structures)."""
        d = (self.direction + rel) % 4
        dx, dy = DIR_VEC[d]
        r = self.SIZE // 2 + 1
        return self.x + dx * r, self.y + dy * r

    # ---- item intake -------------------------------------------------------

    def feed(self, value):
        self.invested += value
        self.hp = min(self.max_hp, self.hp + value)

    def accept(self, value, rel, overshoot, factory):
        """An item pushed in through relative side rel. Return True to consume.
        Default: everything is feed."""
        self.feed(value)
        return True

    def tick(self, factory):
        pass

    def label(self):
        """Short text drawn on the sprite (None for none)."""
        return None

    # ---- persistence -------------------------------------------------------

    def to_dict(self):
        return {"kind": self.KIND, "x": self.x, "y": self.y, "dir": self.direction,
                "invested": self.invested, "hp": self.hp}

    @classmethod
    def from_dict(cls, d):
        s = cls(int(d["x"]), int(d["y"]), int(d.get("dir", 0)))
        s.invested = int(d.get("invested", 0))
        s.hp = int(d.get("hp", s.max_hp))
        s._load_extra(d)
        return s

    def _load_extra(self, d):
        pass

    def __repr__(self):
        return f"{self.KIND}({self.x},{self.y},{DIR_NAMES[self.direction]})"


class Belt(Structure):
    """items: [[value, progress], ...] sorted by progress ascending; the head
    (about to leave) is items[-1]. Spacing >= ITEM_SPACING is enforced from
    the head backwards, which is what makes backpressure propagate."""
    __slots__ = ("items", "feeders", "in_sides")
    KIND = "belt"
    HAS_OUTPUT = True
    SIDE_ROLES = (ROLE_OUT, ROLE_IN, ROLE_IN, ROLE_IN)

    def __init__(self, x, y, direction=E):
        super().__init__(x, y, direction)
        self.items = []
        self.feeders = []      # upstream belts (rebuilt with links)
        self.in_sides = 0      # bitmask of WORLD sides (1 << dir) that push cargo in (render shapes)

    @property
    def speed(self):
        return leveling.belt_speed(self.invested)

    def accept(self, value, rel, overshoot, factory):
        if rel == FRONT:                 # head-on against our flow: feed
            self.feed(value)
            return True
        items = self.items
        p = overshoot
        if items:
            room = items[0][1] - ITEM_SPACING
            if room < 0.0:
                return False
            if p > room:
                p = room
        items.insert(0, [value, p])
        return True

    def tick(self, factory):
        items = self.items
        if not items:
            return
        speed = self.speed
        i = len(items) - 1
        head = items[i]
        p = head[1] + speed
        if p >= 1.0:
            nxt = self.next
            if nxt is not None and nxt.accept(head[0], self.next_rel, p - 1.0, factory):
                items.pop()
                limit = 1.0 - EPS
            else:
                head[1] = 1.0 - EPS
                limit = head[1] - ITEM_SPACING
        else:
            head[1] = p
            limit = p - ITEM_SPACING
        i -= 1
        while i >= 0:
            item = items[i]
            p = item[1] + speed
            if p > limit:
                p = limit
            item[1] = p
            limit = p - ITEM_SPACING
            i -= 1

    def to_dict(self):
        d = super().to_dict()
        d["items"] = [[v, p] for v, p in self.items]
        return d

    def _load_extra(self, d):
        self.items = [[int(v), float(p)] for v, p in d.get("items", [])]


class Miner(Structure):
    """Emits its deposit digit into every adjacent cargo input each period.
    `outputs` [(structure, rel), ...] is rebuilt with the links."""
    __slots__ = ("value", "timer", "outputs", "last_emit_tick")
    KIND = "miner"
    HAS_OUTPUT = False
    SIDE_ROLES = (ROLE_OUT, ROLE_OUT, ROLE_OUT, ROLE_OUT)

    def __init__(self, x, y, direction=E, value=0):
        super().__init__(x, y, direction)
        self.value = value
        self.timer = self.period
        self.outputs = []
        self.last_emit_tick = -10 ** 9

    @property
    def period(self):
        return leveling.period(MINER_BASE_PERIOD, self.invested)

    def label(self):
        return str(self.value)

    def tick(self, factory):
        if self.timer > 0:
            self.timer -= 1
            return
        emitted = False
        for nb, rel in self.outputs:
            if nb.accept(self.value, rel, 0.0, factory):
                emitted = True
                factory.stats["mined"] += 1
        if emitted:
            self.timer = self.period
            self.last_emit_tick = factory.tick_count
        # else: every output blocked; retry next tick

    def to_dict(self):
        d = super().to_dict()
        d["value"] = self.value
        d["timer"] = self.timer
        return d

    def _load_extra(self, d):
        self.value = int(d.get("value", 0))
        self.timer = int(d.get("timer", self.period))


class MathMachine(Structure):
    """Two operand buffers (A = left side, B = right side), one output slot.
    sub -> a-b, div -> a//b; results <= 0 are voided."""
    __slots__ = ("in_a", "in_b", "out", "timer", "busy")
    OP = None
    HAS_OUTPUT = True
    SIDE_ROLES = (ROLE_OUT, ROLE_IN, ROLE_FEED, ROLE_IN)

    def __init__(self, x, y, direction=E):
        super().__init__(x, y, direction)
        self.in_a = deque()
        self.in_b = deque()
        self.out = None
        self.timer = 0
        self.busy = None       # (a, b) being processed

    @property
    def period(self):
        return leveling.period(MACHINE_BASE_PERIOD, self.invested)

    def label(self):
        return self.SYMBOL

    def compute(self, a, b):
        op = self.OP
        if op == "add":
            return a + b
        if op == "sub":
            return a - b
        if op == "mul":
            return a * b
        if op == "div":
            return a // b if b else 0
        return 0

    def accept(self, value, rel, overshoot, factory):
        if rel == LEFT:
            buf = self.in_a
        elif rel == RIGHT:
            buf = self.in_b
        elif rel == BACK:
            self.feed(value)
            return True
        else:
            return False
        if len(buf) >= MACHINE_BUFFER:
            return False
        buf.append(value)
        return True

    def tick(self, factory):
        if self.out is not None:
            nxt = self.next
            if nxt is not None and nxt.accept(self.out, self.next_rel, 0.0, factory):
                self.out = None
        if self.busy is not None:
            self.timer -= 1
            if self.timer <= 0:
                result = self.compute(*self.busy)
                self.busy = None
                if result > 0:
                    self.out = result
                else:
                    factory.stats["voided"] += 1
        if self.busy is None and self.out is None and self.in_a and self.in_b:
            self.busy = (self.in_a.popleft(), self.in_b.popleft())
            self.timer = self.period

    def to_dict(self):
        d = super().to_dict()
        d["a"] = list(self.in_a)
        d["b"] = list(self.in_b)
        d["out"] = self.out
        d["timer"] = self.timer
        d["busy"] = list(self.busy) if self.busy else None
        return d

    def _load_extra(self, d):
        self.in_a = deque(int(v) for v in d.get("a", []))
        self.in_b = deque(int(v) for v in d.get("b", []))
        self.out = d.get("out")
        self.timer = int(d.get("timer", 0))
        busy = d.get("busy")
        self.busy = (int(busy[0]), int(busy[1])) if busy else None


class Adder(MathMachine):
    __slots__ = ()
    KIND, OP, SYMBOL = "adder", "add", "+"


class Subtractor(MathMachine):
    __slots__ = ()
    KIND, OP, SYMBOL = "subtractor", "sub", "-"


class Multiplier(MathMachine):
    __slots__ = ()
    KIND, OP, SYMBOL = "multiplier", "mul", "x"


class Divider(MathMachine):
    __slots__ = ()
    KIND, OP, SYMBOL = "divider", "div", "/"


class Hub(Structure):
    """3x3, anchored at its centre. Everything delivered is income."""
    __slots__ = ()
    KIND = "hub"
    SIZE = 3
    SIDE_ROLES = (ROLE_IN, ROLE_IN, ROLE_IN, ROLE_IN)

    def accept(self, value, rel, overshoot, factory):
        factory.deliver(value)
        return True

    def label(self):
        return "HUB"


class Wall(Structure):
    __slots__ = ()
    KIND = "wall"


class Tower(Structure):
    """Belt-fed ammo (front side); fires number lasers (Phase 5)."""
    __slots__ = ("ammo", "timer")
    KIND = "tower"
    SIDE_ROLES = (ROLE_IN, ROLE_FEED, ROLE_FEED, ROLE_FEED)

    def __init__(self, x, y, direction=N):
        super().__init__(x, y, direction)
        self.ammo = deque()
        self.timer = 0

    def accept(self, value, rel, overshoot, factory):
        if rel == FRONT:
            if len(self.ammo) >= TOWER_AMMO_MAX:
                return False
            self.ammo.append(value)
            return True
        self.feed(value)
        return True

    def label(self):
        return str(len(self.ammo)) if self.ammo else None

    @property
    def period(self):
        return leveling.period(TOWER_BASE_PERIOD, self.invested)

    def damage_for(self, value):
        return int(round(value * (1 + TOWER_DMG_LEVEL_MULT * (self.level - 1))))

    def tick(self, factory):
        """Fire the next ammo number at the nearest enemy in range."""
        if self.timer > 0:
            self.timer -= 1
            return
        combat = factory.combat
        if combat is None or not self.ammo:
            return
        cx, cy = self.x + 0.5, self.y + 0.5
        enemy = combat.nearest_enemy(cx, cy, TOWER_RANGE)
        if enemy is None:
            return
        value = self.ammo.popleft()
        combat.hit_unit(enemy, self.damage_for(value), source=(cx, cy), value=value, side=1)
        self.timer = self.period

    def to_dict(self):
        d = super().to_dict()
        d["ammo"] = list(self.ammo)
        d["timer"] = self.timer
        return d

    def _load_extra(self, d):
        self.ammo = deque(int(v) for v in d.get("ammo", []))
        self.timer = int(d.get("timer", 0))


class Spawner(Structure):
    """Spawns player units at its front tile on a timer, up to a cap that
    grows with level; units gather at the rally point (right-click)."""
    __slots__ = ("timer", "rally")
    UNIT = None
    SIDE_ROLES = (ROLE_OUT, ROLE_FEED, ROLE_FEED, ROLE_FEED)

    def __init__(self, x, y, direction=S):
        super().__init__(x, y, direction)
        self.timer = SPAWNER_BASE_PERIOD // 4
        self.rally = None

    def label(self):
        return self.UNIT[0].upper()

    @property
    def period(self):
        return leveling.period(SPAWNER_BASE_PERIOD, self.invested)

    @property
    def cap(self):
        return SPAWNER_UNIT_CAP + (self.level - 1)

    def rally_point(self):
        if self.rally is not None:
            return tuple(self.rally)
        fx, fy = self.front_tile()
        dx, dy = DIR_VEC[self.direction]
        return (fx + 0.5 + dx, fy + 0.5 + dy)

    def tick(self, factory):
        combat = factory.combat
        if combat is None:
            return
        if self.timer > 0:
            self.timer -= 1
            return
        if combat.count_units_of(self) >= self.cap:
            return
        fx, fy = self.front_tile()
        combat.spawn_unit(self.UNIT, fx + 0.5, fy + 0.5, level=self.level, owner=self,
                          rally=self.rally_point())
        self.timer = self.period

    def to_dict(self):
        d = super().to_dict()
        d["timer"] = self.timer
        d["rally"] = list(self.rally) if self.rally is not None else None
        return d

    def _load_extra(self, d):
        self.timer = int(d.get("timer", 0))
        r = d.get("rally")
        self.rally = (float(r[0]), float(r[1])) if r else None


class SpawnerRanged(Spawner):
    __slots__ = ()
    KIND, UNIT = "spawner_ranged", "ranged"


class SpawnerMelee(Spawner):
    __slots__ = ()
    KIND, UNIT = "spawner_melee", "melee"


class SpawnerHeavy(Spawner):
    __slots__ = ()
    KIND, UNIT = "spawner_heavy", "heavy"


KINDS = {cls.KIND: cls for cls in
         (Belt, Miner, Adder, Subtractor, Multiplier, Divider, Hub, Wall, Tower,
          SpawnerRanged, SpawnerMelee, SpawnerHeavy)}
MACHINE_KINDS = ("adder", "subtractor", "multiplier", "divider")
