"""Combat: enemies, player units, waves, nest raids, beams. Headless.
Ticks from Factory.tick() after belts (docs/PLAN.md section 2.3 steps 5-7).

Determinism: no free-running RNG. Wave composition and positions come from
random.Random(f"{seed}:wave:{n}"), raids from (seed, region, raid ordinal).
Lists iterate in spawn order; nearest searches tie-break on uid.

Positions are float tile coordinates (tile (tx, ty) has centre (tx+.5, ty+.5)).
Enemies are blocked by structures and melee whatever blocks them, and they
also shoot (free) at the nearest unit or structure within shot_range while
advancing. Player units walk over belts and bridges but are blocked by every
other structure (walls, towers, machines, the HQ...; John: no phasing through
walls): they route around them with A* (sim.pathing.route) and hold when
enclosed. Ranged/heavy unit shots debit balance by the fired value (hold fire
when broke); melee and towers are free (towers eat ammo).

Formations (John): a commanded group keeps a formation (box / line / column /
wedge / ring, [wheel] with units selected) that every move and patrol order
re-forms; a patrol ([MMB] click) walks the group between its rally slots
and a second set of slots. Repair units heal damaged buildings and units
next to them from a load of numbers and refill at the HQ.
"""
import math
import random

from settings import (TICK_RATE, UNIT_STATS, ENEMY_STATS, WAVE_FIRST_S, WAVE_INTERVAL_BASE_S,
                      WAVE_INTERVAL_MIN_S, WAVE_INTERVAL_DECAY, WAVE_BUDGET_BASE,
                      WAVE_BUDGET_GROWTH, WAVE_SPAWN_MARGIN, WAVE_MIN_RADIUS, WAVE_MIX,
                      UNIT_AGGRO_TILES, UNIT_LEVEL_MULT, ENEMY_ATTACK_RANGE, FLOW_REFRESH_TICKS,
                      NEST_AGGRO_TILES, NEST_RAID_PERIOD_S, NEST_RAID_SIZE, NEST_BOUNTY,
                      NEST_REGION, CHUNK_SIZE, GATHER_MAX_RING, POST_MAX_SHIFT, FORMATIONS,
                      UNIT_PASSABLE_KINDS, UNIT_PATH_BUDGET, REPAIR_UNIT_CAPACITY,
                      REPAIR_UNIT_SEARCH, REPAIR_HP_PER_NUMBER)
from sim.pathing import FlowField, greedy_step, dist_to_tiles, route
from sim import nests as nestmod
from sim.structures import Structure, Spawner

ENEMY, PLAYER = 0, 1
HEAL = 2                                       # beam "side" of a repair unit's heal
BEAM_TTL = 6
NEIGHBOURS4 = ((0, -1), (1, 0), (0, 1), (-1, 0))
NEST_SCAN_TICKS = 100
NEST_FIRST_RAID_S = 10
RETARGET_RADIUS = 40
REPAIR_RANGE = 1.5                             # a repair unit works on the 8 tiles around it


class SolidMap:
    """`(tx, ty) in solid` is True where a structure blocks player units:
    everything but the walk-over kinds (belts, bridges). A live view of the
    factory's structure dict, so it never goes stale."""
    __slots__ = ("structures",)

    def __init__(self, structures):
        self.structures = structures

    def __contains__(self, tile):
        s = self.structures.get(tile)
        return s is not None and s.KIND not in UNIT_PASSABLE_KINDS


class Unit:
    __slots__ = ("uid", "side", "kind", "x", "y", "hp", "max_hp", "speed", "range", "dmg",
                 "period", "timer", "shot", "shot_dmg", "shot_range", "target", "goal", "rally",
                 "level", "owner", "dead", "post", "patrol", "leg", "formation", "anchor", "panchor",
                 "heal", "carry", "path", "path_goal", "path_ver")

    def __init__(self, uid, side, kind, x, y, stats, mult=1.0, level=1, owner=None):
        self.uid = uid
        self.side = side
        self.kind = kind
        self.x = float(x)
        self.y = float(y)
        self.max_hp = max(1, int(stats["hp"] * mult))
        self.hp = self.max_hp
        self.speed = stats["speed"]
        self.range = stats.get("range", ENEMY_ATTACK_RANGE)
        self.dmg = max(1, int(round(stats.get("dmg", 1) * mult)))
        self.shot = stats.get("shot")          # player ranged: base fired value (cost per shot)
        shot_dmg = stats.get("shot_dmg")       # enemies: free ranged damage, fired while advancing
        self.shot_dmg = None if shot_dmg is None else max(1, int(round(shot_dmg * mult)))
        self.shot_range = stats.get("shot_range", 0)
        self.period = stats["period"]
        self.timer = 0
        self.target = None                     # Unit | Structure | NestSpec
        self.goal = None                       # (tx, ty) walk-to tile for raiders
        self.rally = None                      # (x, y) for player units
        self.level = level
        self.owner = owner                     # spawner (player units)
        self.dead = False
        self.post = None                       # (tx, ty) tile claimed while attacking (no stacking)
        self.patrol = None                     # (x, y) second patrol point (player units), or None
        self.leg = 0                           # 1 while heading for the patrol point, 0 for the rally
        self.formation = FORMATIONS[0]         # the group's formation, kept for every later order
        self.anchor = None                     # centre the rally formation was laid out around
        self.panchor = None                    # centre of the patrol formation
        heal = stats.get("heal")               # repair units: hp restored per action
        self.heal = None if heal is None else max(1, int(round(heal * mult)))
        self.carry = 0                         # repair units: numbers on board (spent on healing)
        self.path = None                       # cached A* route (player units), tiles ahead
        self.path_goal = None
        self.path_ver = -1                     # factory.layout_version the route was checked against

    def tile(self):
        return math.floor(self.x), math.floor(self.y)

    def dist_to(self, x, y):
        return math.hypot(self.x - x, self.y - y)

    def shot_damage(self):
        return int(round(self.shot * (1 + UNIT_LEVEL_MULT * (self.level - 1))))


class WaveState:
    __slots__ = ("number", "next_at_tick", "angle")

    def __init__(self, number, next_at_tick, angle):
        self.number = number
        self.next_at_tick = next_at_tick
        self.angle = angle

    def to_dict(self):
        return {"number": self.number, "next_at_tick": self.next_at_tick, "angle": self.angle}

    @classmethod
    def from_dict(cls, d):
        return cls(int(d["number"]), int(d["next_at_tick"]), float(d.get("angle", 0.0)))


def wave_angle(seed, n):
    return random.Random(f"{seed}:waveangle:{n}").uniform(0, 2 * math.pi)


def wave_budget(n):
    return WAVE_BUDGET_BASE * WAVE_BUDGET_GROWTH ** n


def wave_interval_ticks(n):
    return int(max(WAVE_INTERVAL_MIN_S, WAVE_INTERVAL_BASE_S * WAVE_INTERVAL_DECAY ** n) * TICK_RATE)


def spiral_slots(gx, gy, max_ring=GATHER_MAX_RING):
    """Tile centres around the tile holding (gx, gy), nearest first: the
    centre, then each Chebyshev ring ordered by distance then (y, x). Units
    gathering here stand one per tile, so a group forms a compact grid."""
    tx, ty = math.floor(gx), math.floor(gy)
    yield (tx + 0.5, ty + 0.5)
    for r in range(1, max_ring + 1):
        ring = []
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r:
                    ring.append((dx * dx + dy * dy, dy, dx))
        ring.sort()
        for _, dy, dx in ring:
            yield (tx + dx + 0.5, ty + dy + 0.5)


def formation_slots(name, gx, gy, n, max_ring=GATHER_MAX_RING):
    """Tile centres for n units in formation `name` around the tile holding
    (gx, gy), best slots first; the generator carries on with fallback slots
    so blocked tiles (structures, other units) can be skipped.
      box:    compact grid spiralling out (spiral_slots)
      line:   one row of n, left to right (extra rows below/above if needed)
      column: one column of n, top to bottom (extra columns right/left)
      wedge:  a V with its tip to the north, then its inside
      ring:   a hollow ring around the point, clockwise from the north"""
    tx, ty = math.floor(gx), math.floor(gy)
    if name == "line":
        lo, hi = -((n - 1) // 2), n // 2
        for r in range(max_ring + 1):
            for row in ((0,) if r == 0 else (r, -r)):
                for dx in range(lo, hi + 1):
                    yield (tx + dx + 0.5, ty + row + 0.5)
    elif name == "column":
        lo, hi = -((n - 1) // 2), n // 2
        for r in range(max_ring + 1):
            for col in ((0,) if r == 0 else (r, -r)):
                for dy in range(lo, hi + 1):
                    yield (tx + col + 0.5, ty + dy + 0.5)
    elif name == "wedge":
        depth = -(-(n - 1) // 2)                       # arms needed for n units...
        ty -= depth // 2                               # ...so the V is centred on the point
        yield (tx + 0.5, ty + 0.5)
        for k in range(1, max_ring + 1):
            yield (tx - k + 0.5, ty + k + 0.5)
            yield (tx + k + 0.5, ty + k + 0.5)
        for k in range(1, max_ring + 1):
            for dx in range(-k + 1, k):
                yield (tx + dx + 0.5, ty + k + 0.5)
    elif name == "ring":
        r0 = max(1, -(-n // 8))                        # the ring at distance r holds 8r units
        for r in range(r0, max_ring + 1):
            ring = []
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) == r:
                        ring.append((math.atan2(dx, -dy) % (2 * math.pi), dy, dx))
            ring.sort()
            for _, dy, dx in ring:
                yield (tx + dx + 0.5, ty + dy + 0.5)
        yield (tx + 0.5, ty + 0.5)
    else:
        yield from spiral_slots(gx, gy, max_ring)


class Combat:
    def __init__(self, factory, seed, nests=None, wave=None, raids=None, units=None):
        self.factory = factory
        factory.combat = self
        self.seed = seed
        self.nests = nests if nests is not None else nestmod.NestRegistry()
        self.units = []
        self.enemies = []
        self.beams = []                        # [x0, y0, x1, y1, value, ttl, side]
        self.next_uid = 1
        self.flow = FlowField()
        self.use_flow = True                   # False -> v1 greedy only (tests)
        self.waves_paused = False              # menu Settings: the wave countdown stands still (raids go on)
        self.wave = (WaveState.from_dict(wave) if wave
                     else WaveState(0, WAVE_FIRST_S * TICK_RATE, wave_angle(seed, 0)))
        self.raid_counts = {tuple(int(v) for v in k.split(",")): int(n)
                            for k, n in (raids or {}).items()}
        self.raid_next = {}                    # (rx, ry) -> tick of the next raid
        self.active_nests = {}                 # (rx, ry) -> NestSpec (aggro'd, alive)
        self.known_nests = {}                  # (rx, ry) -> NestSpec near the base (alive)
        self.stats = {"kills": 0, "losses": 0, "waves": 0, "shot_cost": 0, "raids": 0,
                      "healed": 0, "refilled": 0}
        self._last_scan = -NEST_SCAN_TICKS
        self._posts = {}                       # (tx, ty) -> uid of the attacker standing there
        self.solid = SolidMap(factory.structures)   # what blocks player units
        if units:
            self._load_units(units)
        if wave and "next_uid" in wave:
            self.next_uid = max(self.next_uid, int(wave["next_uid"]))

    # ---- persistence ------------------------------------------------------------

    def to_dict(self):
        """Wave timer, raid counters and the player's units (they cost
        balance, so they survive a save; enemies disperse on reload)."""
        d = self.wave.to_dict()
        d["raids"] = {f"{k[0]},{k[1]}": v for k, v in sorted(self.raid_counts.items())}
        d["next_uid"] = self.next_uid
        d["units"] = [self._unit_record(u) for u in self.units if not u.dead]
        return d

    @staticmethod
    def _unit_record(u):
        d = {"uid": u.uid, "kind": u.kind, "x": u.x, "y": u.y, "hp": u.hp, "level": u.level,
             "owner": [u.owner.x, u.owner.y] if u.owner is not None else None,
             "rally": list(u.rally) if u.rally is not None else None}
        if u.formation != FORMATIONS[0]:
            d["formation"] = u.formation
        if u.anchor is not None:
            d["anchor"] = list(u.anchor)
        if u.patrol is not None:
            d["patrol"] = list(u.patrol)
            d["leg"] = u.leg
            if u.panchor is not None:
                d["panchor"] = list(u.panchor)
        if u.carry:
            d["carry"] = u.carry
        return d

    def _load_units(self, records):
        structures = self.factory.structures
        for r in records:
            kind = r.get("kind")
            if kind not in UNIT_STATS:
                continue
            owner = None
            if r.get("owner"):
                s = structures.get((int(r["owner"][0]), int(r["owner"][1])))
                if isinstance(s, Spawner):
                    owner = s
            rally = tuple(float(v) for v in r["rally"]) if r.get("rally") else None
            u = self.spawn_unit(kind, float(r["x"]), float(r["y"]), level=int(r.get("level", 1)),
                                owner=owner, rally=rally)
            u.hp = max(1, min(u.max_hp, int(r.get("hp", u.max_hp))))
            if r.get("formation") in FORMATIONS:
                u.formation = r["formation"]
            if r.get("anchor"):
                u.anchor = (float(r["anchor"][0]), float(r["anchor"][1]))
            if r.get("patrol"):
                u.patrol = (float(r["patrol"][0]), float(r["patrol"][1]))
                u.leg = 1 if r.get("leg") else 0
                if r.get("panchor"):
                    u.panchor = (float(r["panchor"][0]), float(r["panchor"][1]))
            u.carry = max(0, min(REPAIR_UNIT_CAPACITY, int(r.get("carry", 0))))
            if "uid" in r:
                u.uid = int(r["uid"])
                self.next_uid = max(self.next_uid, u.uid + 1)

    # ---- spawning -----------------------------------------------------------------

    def spawn_enemy(self, kind, x, y, mult=1.0, goal=None):
        u = Unit(self.next_uid, ENEMY, kind, x, y, ENEMY_STATS[kind], mult)
        u.goal = goal
        self.next_uid += 1
        self.enemies.append(u)
        return u

    def spawn_unit(self, kind, x, y, level=1, owner=None, rally=None):
        mult = 1 + UNIT_LEVEL_MULT * (level - 1)
        u = Unit(self.next_uid, PLAYER, kind, x, y, UNIT_STATS[kind], mult, level, owner)
        u.rally = rally if rally is not None else (x, y)
        self.next_uid += 1
        self.units.append(u)
        return u

    def count_units_of(self, owner):
        return sum(1 for u in self.units if u.owner is owner and not u.dead)

    # ---- formations ---------------------------------------------------------------

    def _free_slot(self, slots, taken):
        """First slot from the iterator that is open ground and not already
        someone's gather slot. Falls back to the last candidate."""
        structures = self.factory.structures
        pos = None
        for pos in slots:
            if (math.floor(pos[0]), math.floor(pos[1])) in structures:
                continue
            if any(abs(t[0] - pos[0]) < 0.5 and abs(t[1] - pos[1]) < 0.5 for t in taken):
                continue
            return pos
        return pos

    def slot_near(self, gx, gy):
        """Gather slot for one new unit near (gx, gy), avoiding every live
        unit's slot and every structure tile."""
        taken = [u.rally for u in self.units if not u.dead and u.rally is not None]
        return self._free_slot(spiral_slots(gx, gy), taken)

    @staticmethod
    def _formation_order(group, formation):
        """Units in the order they take the formation's slots: a line fills
        left to right by where the units stand, a column top to bottom, the
        rest by uid. Deterministic (positions are exact sim state)."""
        if formation == "line":
            return sorted(group, key=lambda u: (u.x, u.uid))
        if formation == "column":
            return sorted(group, key=lambda u: (u.y, u.uid))
        return sorted(group, key=lambda u: u.uid)

    def _assign(self, group, formation, gx, gy, attr):
        """Hand every unit of the group its own slot (attr = "rally" or
        "patrol") in `formation` around (gx, gy), skipping structure tiles
        and the slots of units outside the group; the group remembers the
        centre (anchor / panchor) so a formation change re-forms in place."""
        ids = {id(u) for u in group}
        taken = [u.rally for u in self.units
                 if not u.dead and u.rally is not None and id(u) not in ids]
        taken += [u.patrol for u in self.units
                  if not u.dead and u.patrol is not None and id(u) not in ids]
        centre = (math.floor(gx) + 0.5, math.floor(gy) + 0.5)
        slots = formation_slots(formation, gx, gy, len(group))
        for u in self._formation_order(group, formation):
            pos = self._free_slot(slots, taken)
            setattr(u, attr, pos)
            setattr(u, "anchor" if attr == "rally" else "panchor", centre)
            taken.append(pos)

    @staticmethod
    def _centre(group, attr):
        """Where a group's formation is centred: the remembered anchor when
        the group shares one, else the middle of its slots."""
        anchors = {getattr(u, "anchor" if attr == "rally" else "panchor") for u in group}
        anchors.discard(None)
        if len(anchors) == 1:
            return next(iter(anchors))
        points = [getattr(u, attr) for u in group]
        return (math.floor(sum(p[0] for p in points) / len(points)) + 0.5,
                math.floor(sum(p[1] for p in points) / len(points)) + 0.5)

    @staticmethod
    def group_formation(units):
        """The formation a group of units shares (the first unit's, by uid)."""
        live = [u for u in units if not u.dead]
        if not live:
            return FORMATIONS[0]
        return min(live, key=lambda u: u.uid).formation

    def gather(self, units, gx, gy, formation=None):
        """Move order: send `units` to their formation around (gx, gy), one
        tile each, flowing around structures and around units that are not
        part of the group. The group's formation (or `formation`) is kept on
        every unit for later orders; a patrol is cancelled. Deterministic."""
        group = sorted((u for u in units if not u.dead), key=lambda u: u.uid)
        if not group:
            return group
        if formation is None:
            formation = group[0].formation
        for u in group:
            u.formation = formation
            u.patrol = None
            u.panchor = None
            u.leg = 0
        self._assign(group, formation, gx, gy, "rally")
        return group

    def patrol(self, units, px, py):
        """Patrol order ([MMB] click): the group walks between its rally slots
        and a second formation around (px, py), starting toward the new point."""
        group = sorted((u for u in units if not u.dead), key=lambda u: u.uid)
        if not group:
            return group
        formation = group[0].formation
        for u in group:
            u.formation = formation
            if u.rally is None:
                u.rally = (u.x, u.y)
        self._assign(group, formation, px, py, "patrol")
        for u in group:
            u.leg = 1
        return group

    def set_formation(self, units, formation):
        """[wheel]: give the group a new formation and re-form it in place
        (around the centre of its rally slots; the patrol end too)."""
        group = sorted((u for u in units if not u.dead), key=lambda u: u.uid)
        if not group or formation not in FORMATIONS:
            return group
        for u in group:
            u.formation = formation
            if u.rally is None:
                u.rally = (u.x, u.y)
        gx, gy = self._centre(group, "rally")
        self._assign(group, formation, gx, gy, "rally")
        patrolling = [u for u in group if u.patrol is not None]
        if patrolling:
            px, py = self._centre(patrolling, "patrol")
            self._assign(patrolling, formation, px, py, "patrol")
        return group

    def next_formation(self, units, step=1):
        """Cycle the group's formation ([wheel] up / down). Returns the new name."""
        cur = self.group_formation(units)
        name = FORMATIONS[(FORMATIONS.index(cur) + step) % len(FORMATIONS)]
        self.set_formation(units, name)
        return name

    def unit_at(self, x, y, radius=0.6):
        """Nearest live player unit within radius tiles of a point, or None."""
        return self.nearest_unit(x, y, radius)

    # ---- attack posts (attackers never stack) ---------------------------------------

    @staticmethod
    def _clear_line(x0, y0, x1, y1, blocked):
        """True when no structure tile lies on the straight walk from one
        point to the other (sampled every half tile)."""
        if blocked is None:
            return True
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / 0.5))
        for i in range(1, n + 1):
            t = i / n
            if (math.floor(x0 + (x1 - x0) * t), math.floor(y0 + (y1 - y0) * t)) in blocked:
                return False
        return True

    def release_post(self, u):
        if u.post is not None:
            if self._posts.get(u.post) == u.uid:
                del self._posts[u.post]
            u.post = None

    def claim_post(self, u, points, radius, blocked=None):
        """A tile for u to fight from: within `radius` of one of the target's
        points (tile centres / a unit's position), free of structures and of
        other attackers, reachable in a straight line, at most POST_MAX_SHIFT
        from where u stands; the nearest such tile (ties by (y, x)). Keeps
        the current post while it still qualifies. None when nothing fits."""
        cur = u.post
        if cur is not None and self._posts.get(cur) == u.uid:
            cx, cy = cur[0] + 0.5, cur[1] + 0.5
            if any(math.hypot(cx - px, cy - py) <= radius for px, py in points):
                return cur
        self.release_post(u)
        rr = int(math.ceil(radius))
        best, best_key = None, None
        seen = {(math.floor(px), math.floor(py)) for px, py in points}   # never stand on the victim
        for px, py in points:
            tx, ty = math.floor(px), math.floor(py)
            for ny in range(ty - rr, ty + rr + 1):
                for nx in range(tx - rr, tx + rr + 1):
                    if (nx, ny) in seen:
                        continue
                    seen.add((nx, ny))
                    if (nx, ny) in self._posts or (blocked is not None and (nx, ny) in blocked):
                        continue
                    cx, cy = nx + 0.5, ny + 0.5
                    if not any(math.hypot(cx - qx, cy - qy) <= radius for qx, qy in points):
                        continue
                    shift = math.hypot(cx - u.x, cy - u.y)
                    if shift > POST_MAX_SHIFT:
                        continue
                    key = (shift, ny, nx)
                    if (best_key is None or key < best_key) and self._clear_line(u.x, u.y, cx, cy, blocked):
                        best, best_key = (nx, ny), key
        if best is not None:
            self._posts[best] = u.uid
            u.post = best
        return best

    def _at_post(self, u):
        return u.post is not None and u.x == u.post[0] + 0.5 and u.y == u.post[1] + 0.5

    # ---- queries ------------------------------------------------------------------

    def nearest_enemy(self, x, y, max_dist):
        best, best_d = None, max_dist
        for e in self.enemies:
            if e.dead:
                continue
            d = math.hypot(e.x - x, e.y - y)
            if d < best_d or (d == best_d and best is not None and e.uid < best.uid):
                best, best_d = e, d
        return best

    def nearest_unit(self, x, y, max_dist):
        best, best_d = None, max_dist
        for u in self.units:
            if u.dead:
                continue
            d = math.hypot(u.x - x, u.y - y)
            if d < best_d or (d == best_d and best is not None and u.uid < best.uid):
                best, best_d = u, d
        return best

    def nearest_structure_tile(self, x, y, max_dist=RETARGET_RADIUS):
        """Nearest structure to a point (scans structure keys; rare calls)."""
        best, best_d = None, max_dist
        for (tx, ty), s in self.factory.structures.items():
            d = math.hypot(tx + 0.5 - x, ty + 0.5 - y)
            if d < best_d or (d == best_d and best is not None and (ty, tx) < (best[1], best[0])):
                best, best_d = (tx, ty), d
        return best

    def nearest_structure_in(self, x, y, r):
        """Nearest structure within r tiles of a point: scans the (2r+1)^2
        tiles around it (cheap, bounded); ties break on (y, x)."""
        structures = self.factory.structures
        tx, ty = math.floor(x), math.floor(y)
        rr = int(math.ceil(r))
        best, best_key = None, None
        for ny in range(ty - rr, ty + rr + 1):
            for nx in range(tx - rr, tx + rr + 1):
                s = structures.get((nx, ny))
                if s is None:
                    continue
                d = math.hypot(nx + 0.5 - x, ny + 0.5 - y)
                if d > r:
                    continue
                key = (d, ny, nx)
                if best_key is None or key < best_key:
                    best, best_key = s, key
        return best

    def nearest_nest(self, x, y, max_dist):
        best, best_d = None, max_dist
        for key, spec in sorted(self.known_nests.items()):
            d = math.hypot(spec.tx + 0.5 - x, spec.ty + 0.5 - y)
            if d < best_d:
                best, best_d = spec, d
        return best

    def structure_bbox(self):
        keys = self.factory.structures.keys()
        if not keys:
            return (0, 0, 0, 0)
        xs = [k[0] for k in keys]
        ys = [k[1] for k in keys]
        return min(xs), min(ys), max(xs), max(ys)

    # ---- damage -------------------------------------------------------------------

    def hit_unit(self, victim, dmg, source=None, value=None, side=ENEMY):
        victim.hp -= dmg
        if source is not None:
            self.beams.append([source[0], source[1], victim.x, victim.y,
                               value if value is not None else dmg, BEAM_TTL, side])
        if victim.hp <= 0 and not victim.dead:
            victim.dead = True
            if victim.side == ENEMY:
                self.stats["kills"] += 1
            else:
                self.stats["losses"] += 1

    def hit_structure(self, s, dmg):
        return self.factory.damage(s, dmg)

    def hit_nest(self, spec, dmg, source=None, value=None):
        if self.nests.hit(spec, dmg):
            bounty = NEST_BOUNTY * spec.tier
            self.factory.balance += bounty
            key = (spec.rx, spec.ry)
            self.active_nests.pop(key, None)
            self.known_nests.pop(key, None)
            self.raid_next.pop(key, None)
            self.factory.events.append(("nest_destroyed", spec.rx, spec.ry, spec.tx, spec.ty, bounty))
            return True
        if source is not None:
            self.beams.append([source[0], source[1], spec.tx + 0.5, spec.ty + 0.5,
                               value if value is not None else dmg, BEAM_TTL, PLAYER])
        return False

    def _attack(self, attacker, victim):
        """attacker swings at victim (Unit, Structure or NestSpec) if ready."""
        if attacker.timer > 0:
            return False
        f = self.factory
        if attacker.shot is not None:                  # ranged: pay per shot
            cost = attacker.shot
            if f.balance < cost:
                return False                           # hold fire, stay ready
            f.balance -= cost
            self.stats["shot_cost"] += cost
            dmg = attacker.shot_damage()
            value = attacker.shot
        else:
            dmg = attacker.dmg
            value = None
        attacker.timer = attacker.period
        src = (attacker.x, attacker.y)
        if isinstance(victim, Unit):
            self.hit_unit(victim, dmg, src if value is not None else None, value, attacker.side)
        elif isinstance(victim, Structure):
            self.hit_structure(victim, dmg)
        else:
            self.hit_nest(victim, dmg, src if value is not None else None, value)
        return True

    def _shoot(self, e, victim):
        """Enemy ranged fire (free): shot_dmg on a unit or a structure, with a beam."""
        e.timer = e.period
        src = (e.x, e.y)
        if isinstance(victim, Unit):
            self.hit_unit(victim, e.shot_dmg, src, e.shot_dmg, ENEMY)
        else:
            self.hit_structure(victim, e.shot_dmg)
            self.beams.append([e.x, e.y, victim.x + 0.5, victim.y + 0.5, e.shot_dmg, BEAM_TTL, ENEMY])

    # ---- tick ---------------------------------------------------------------------

    def tick(self):
        f = self.factory
        t = f.tick_count
        if self.waves_paused and t < self.wave.next_at_tick:
            self.wave.next_at_tick += 1        # frozen countdown; [F7] (next_at_tick <= t) still fires
        elif t >= self.wave.next_at_tick:
            self.spawn_wave()
        if t - self._last_scan >= NEST_SCAN_TICKS:
            self._scan_nests(t)
        self._raids(t)
        if self.use_flow and self.enemies and (
                not self.flow.built or
                (f.dirty_flowfield and t - self.flow.built_tick >= FLOW_REFRESH_TICKS)):
            self.flow.build(f, t)
            f.dirty_flowfield = False
        self._posts = {u.post: u.uid for u in self.units + self.enemies if not u.dead and u.post is not None}
        for u in self.units:
            if not u.dead:
                self._unit_ai(u)
        for e in self.enemies:
            if not e.dead:
                self._enemy_ai(e)
        if any(u.dead for u in self.units):
            self.units = [u for u in self.units if not u.dead]
        if any(e.dead for e in self.enemies):
            self.enemies = [e for e in self.enemies if not e.dead]
        if self.beams:
            for b in self.beams:
                b[5] -= 1
            self.beams = [b for b in self.beams if b[5] > 0]

    # ---- waves --------------------------------------------------------------------

    def spawn_ring(self):
        x0, y0, x1, y1 = self.structure_bbox()
        cx, cy = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2
        half = math.hypot((x1 - x0 + 1) / 2, (y1 - y0 + 1) / 2)
        return cx, cy, max(WAVE_MIN_RADIUS, half + WAVE_SPAWN_MARGIN)

    def spawn_wave(self):
        n = self.wave.number
        rng = random.Random(f"{self.seed}:wave:{n}")
        budget = wave_budget(n)
        kinds = [k for k in WAVE_MIX if k != "brute" or n >= 2]
        weights = [WAVE_MIX[k] for k in kinds]
        cx, cy, radius = self.spawn_ring()
        angle = self.wave.angle
        mult = 1 + 0.1 * n
        cheapest = min(ENEMY_STATS[k]["cost"] for k in kinds)
        count = 0
        while budget >= cheapest:
            kind = rng.choices(kinds, weights)[0]
            cost = ENEMY_STATS[kind]["cost"]
            if cost > budget:
                continue
            a = angle + rng.uniform(-0.3, 0.3)
            r = radius + rng.uniform(-2, 4)
            self.spawn_enemy(kind, cx + r * math.cos(a), cy + r * math.sin(a), mult)
            budget -= cost
            count += 1
        self.wave.number = n + 1
        self.wave.next_at_tick = self.factory.tick_count + wave_interval_ticks(n + 1)
        self.wave.angle = wave_angle(self.seed, n + 1)
        self.stats["waves"] += 1
        self.factory.events.append(("wave", n + 1, count))
        return count

    def seconds_to_wave(self):
        return max(0, self.wave.next_at_tick - self.factory.tick_count) / TICK_RATE

    # ---- nests --------------------------------------------------------------------

    def _scan_nests(self, t):
        """Find live nests near the base; aggro those with a structure within
        NEST_AGGRO_TILES of the core."""
        self._last_scan = t
        home = nestmod.home_nest(self.seed)            # the camp is always on the map
        if not self.nests.is_destroyed(home.rx, home.ry):
            self.known_nests[(home.rx, home.ry)] = home
        if not self.factory.structures:
            return
        x0, y0, x1, y1 = self.structure_bbox()
        span = NEST_REGION * CHUNK_SIZE
        rx0, rx1 = (x0 - NEST_AGGRO_TILES) // span, (x1 + NEST_AGGRO_TILES) // span
        ry0, ry1 = (y0 - NEST_AGGRO_TILES) // span, (y1 + NEST_AGGRO_TILES) // span
        keys = self.factory.structures.keys()
        for ry in range(ry0, ry1 + 1):
            for rx in range(rx0, rx1 + 1):
                if self.nests.is_destroyed(rx, ry):
                    continue
                spec = nestmod.nest_at(self.seed, rx, ry)
                if spec is None:
                    continue
                if not (x0 - NEST_AGGRO_TILES <= spec.tx <= x1 + NEST_AGGRO_TILES
                        and y0 - NEST_AGGRO_TILES <= spec.ty <= y1 + NEST_AGGRO_TILES):
                    continue
                self.known_nests[(rx, ry)] = spec
                if (rx, ry) in self.active_nests:
                    continue
                for tx, ty in keys:
                    if max(abs(tx - spec.tx), abs(ty - spec.ty)) <= NEST_AGGRO_TILES:
                        self.active_nests[(rx, ry)] = spec
                        self.raid_next[(rx, ry)] = t + NEST_FIRST_RAID_S * TICK_RATE
                        self.factory.events.append(("nest_aggro", rx, ry, spec.tx, spec.ty))
                        break

    def _raids(self, t):
        for key, spec in list(self.active_nests.items()):
            if t < self.raid_next.get(key, 0):
                continue
            self.raid_next[key] = t + NEST_RAID_PERIOD_S * TICK_RATE
            self.spawn_raid(spec)

    def spawn_raid(self, spec):
        key = (spec.rx, spec.ry)
        k = self.raid_counts.get(key, 0)
        self.raid_counts[key] = k + 1
        rng = random.Random(f"{self.seed}:raid:{spec.rx}:{spec.ry}:{k}")
        goal = self.nearest_structure_tile(spec.tx + 0.5, spec.ty + 0.5, max_dist=NEST_AGGRO_TILES + 8)
        size = NEST_RAID_SIZE * spec.tier
        kinds = list(WAVE_MIX)
        for _ in range(size):
            kind = rng.choices(kinds, [WAVE_MIX[c] for c in kinds])[0]
            a = rng.uniform(0, 2 * math.pi)
            self.spawn_enemy(kind, spec.tx + 0.5 + 3 * math.cos(a), spec.ty + 0.5 + 3 * math.sin(a),
                             mult=spec.tier, goal=goal)
        self.stats["raids"] += 1
        self.factory.events.append(("raid", spec.rx, spec.ry, size))
        return size

    # ---- AI -----------------------------------------------------------------------

    def _move_toward(self, u, x, y):
        dx, dy = x - u.x, y - u.y
        d = math.hypot(dx, dy)
        if d <= u.speed:
            u.x, u.y = x, y
        elif d > 0:
            u.x += dx / d * u.speed
            u.y += dy / d * u.speed

    def _next_tile(self, u, tx, ty, gtx, gty):
        """The neighbour tile a player unit steps to on its way from (tx, ty)
        to (gtx, gty): the next tile of its cached A* route, re-planned when
        the goal changed, the unit left the route, or a new structure landed
        on it. With no route (enclosed) the unit walks greedily but never
        into a solid tile, and holds when both axes are blocked. Enemies keep
        their greedy step (whatever blocks them gets attacked)."""
        if u.side == ENEMY:
            return greedy_step(tx, ty, gtx, gty)
        solid = self.solid
        goal = (gtx, gty)
        ver = self.factory.layout_version
        path = u.path
        replan = u.path_goal != goal
        if not replan:
            if path is None:
                replan = u.path_ver != ver              # known unreachable until the layout changes
            else:
                while path and path[0] == (tx, ty):
                    path.pop(0)
                if u.path_ver != ver:
                    replan = any(t in solid for t in path)   # something was built across the route
                    if not replan:
                        u.path_ver = ver
                if not replan:
                    if not path:
                        return None                     # as close as the route gets (goal is solid)
                    nxt = path[0]
                    if abs(nxt[0] - tx) + abs(nxt[1] - ty) == 1:
                        return nxt
                    replan = True                       # knocked off the route
        if replan:
            path = route((tx, ty), goal, solid, UNIT_PATH_BUDGET)
            u.path, u.path_goal, u.path_ver = path, goal, ver
            if path is not None:
                return path[0] if path else None
        # unreachable within the budget: greedy, but never through a wall
        step = greedy_step(tx, ty, gtx, gty)
        if step is None or step not in solid:
            return step
        dx, dy = gtx - tx, gty - ty
        if step[0] != tx:                               # blocked along x: try y, and vice versa
            alt = (tx, ty + (1 if dy > 0 else -1)) if dy else None
        else:
            alt = (tx + (1 if dx > 0 else -1), ty) if dx else None
        if alt is not None and alt not in solid:
            return alt
        return None

    def _walk_grid(self, u, x, y):
        """Walk to (x, y) along the grid lines through the tile centres:
        larger axis first (L-shaped paths, like the enemies), finishing
        exactly on the target once inside its tile. The unit runs straight
        along the row/column it is on; it only heads for the tile centre when
        the next step turns, or when a fight knocked it off the grid. Player
        units follow their A* route around walls and buildings (_next_tile)."""
        tx, ty = u.tile()
        gtx, gty = math.floor(x), math.floor(y)
        if tx == gtx and ty == gty:
            self._move_toward(u, x, y)
            return
        step = self._next_tile(u, tx, ty, gtx, gty)
        if step is None:
            return                                      # blocked in: hold
        cx, cy = tx + 0.5, ty + 0.5
        sx, sy = step
        on_row = abs(u.y - cy) < 1e-9
        on_col = abs(u.x - cx) < 1e-9
        if (sy == ty and on_row) or (sx == tx and on_col):
            self._move_toward(u, sx + 0.5, sy + 0.5)
        else:
            self._move_toward(u, cx, cy)

    def _unit_ai(self, u):
        if u.timer > 0:
            u.timer -= 1
        if u.heal is not None:                          # repair units never fight
            if self._repair_ai(u):
                return
        else:
            e = self.nearest_enemy(u.x, u.y, UNIT_AGGRO_TILES)
            if e is not None:
                self._engage(u, [(e.x, e.y)], u.range, e)
                return
            spec = self.nearest_nest(u.x, u.y, UNIT_AGGRO_TILES)
            if spec is not None:
                self._engage(u, [(spec.tx + 0.5, spec.ty + 0.5)], max(u.range, 1.5), spec)
                return
        self.release_post(u)
        self._idle_walk(u)

    def _idle_walk(self, u):
        """Nothing to fight: walk to the rally slot; on a patrol, bounce
        between the rally slot and the patrol slot. A slot buried under a
        new structure is swapped for a free one nearby."""
        dest = u.patrol if (u.patrol is not None and u.leg) else u.rally
        if dest is None:
            return
        if (math.floor(dest[0]), math.floor(dest[1])) in self.factory.structures:
            dest = self.slot_near(*dest)
            if u.patrol is not None and u.leg:
                u.patrol = dest
            else:
                u.rally = dest
        if u.x == dest[0] and u.y == dest[1]:
            if u.patrol is not None:
                u.leg ^= 1
            return
        self._walk_grid(u, *dest)

    def _engage(self, u, points, radius, victim):
        """Fight from a post: strike whenever the victim is in range, and walk
        (along the grid, around walls) to a free post around it so attackers
        never stack. With no post available, close in on the victim directly."""
        in_range = any(u.dist_to(px, py) <= radius for px, py in points)
        if in_range:
            self._attack(u, victim)
        post = self.claim_post(u, points, radius, self.solid)
        if post is not None:
            if not self._at_post(u):
                self._walk_grid(u, post[0] + 0.5, post[1] + 0.5)
        elif not in_range:
            px, py = points[0]
            self._walk_grid(u, px, py)

    # ---- repair units -------------------------------------------------------------

    def _repair_ai(self, u):
        """Repair unit (John): heal the nearest damaged building or unit
        (anywhere, unless REPAIR_UNIT_SEARCH limits it), spending carried
        numbers; with the load gone, walk to the HQ and take a new load from
        the balance (wait there while broke). True when the unit is busy."""
        f = self.factory
        if u.carry <= 0:
            hub = f.hub
            if hub is None:
                return False
            self.release_post(u)
            if dist_to_tiles(u.x, u.y, hub.tiles()) <= REPAIR_RANGE:
                take = min(REPAIR_UNIT_CAPACITY - u.carry, f.balance)
                if take > 0:
                    f.balance -= take
                    u.carry += take
                    self.stats["refilled"] += take
                    f.events.append(("refill", u.uid, take))
                return True
            spot = self._hub_side_tile(u, hub)
            if spot is not None:
                self._walk_grid(u, spot[0] + 0.5, spot[1] + 0.5)
            return True
        target = self._repair_target(u)
        if target is None:
            return False
        if isinstance(target, Unit):
            points = [(target.x, target.y)]
        else:
            points = self._structure_points(target)
        in_range = any(u.dist_to(px, py) <= REPAIR_RANGE for px, py in points)
        if in_range and u.timer <= 0:
            self._heal(u, target)
        post = self.claim_post(u, points, REPAIR_RANGE, self.solid)
        if post is not None:
            if not self._at_post(u):
                self._walk_grid(u, post[0] + 0.5, post[1] + 0.5)
        elif not in_range:
            px, py = points[0]
            self._walk_grid(u, px, py)
        return True

    def _hub_side_tile(self, u, hub):
        """Nearest walkable tile touching the HQ's footprint (ties by (y, x))."""
        ox, oy = hub.origin()
        n = hub.SIZE
        best, best_key = None, None
        for dy in range(-1, n + 1):
            for dx in range(-1, n + 1):
                if 0 <= dx < n and 0 <= dy < n:
                    continue
                t = (ox + dx, oy + dy)
                if t in self.solid:
                    continue
                key = (math.hypot(t[0] + 0.5 - u.x, t[1] + 0.5 - u.y), t[1], t[0])
                if best_key is None or key < best_key:
                    best, best_key = t, key
        return best

    def _repair_target(self, u):
        """Nearest damaged player unit (itself included) or damaged structure
        within REPAIR_UNIT_SEARCH tiles (None = anywhere; John: a repair unit
        fixes and heals anything); ties go to units, then (y, x) / uid."""
        best, best_d = None, (REPAIR_UNIT_SEARCH if REPAIR_UNIT_SEARCH else float("inf"))
        for v in self.units:
            if v.dead or v.hp >= v.max_hp:
                continue
            d = math.hypot(v.x - u.x, v.y - u.y)
            if d < best_d or (d == best_d and best is not None and isinstance(best, Unit) and v.uid < best.uid):
                best, best_d = v, d
        for s in self.factory.damaged_structures():
            d = dist_to_tiles(u.x, u.y, s.tiles())
            if d < best_d:
                best, best_d = s, d
        return best

    def _heal(self, u, target):
        """One repair action: up to `heal` hp, paid from the load at
        REPAIR_HP_PER_NUMBER hp per number (the [H] price). Draws a beam."""
        missing = target.max_hp - target.hp
        amount = min(u.heal, missing, u.carry * REPAIR_HP_PER_NUMBER)
        if amount <= 0:
            return 0
        if isinstance(target, Unit):
            target.hp += amount
            tx, ty = target.x, target.y
        else:
            amount = self.factory.heal(target, amount)
            cx, cy = target.centre()
            tx, ty = cx, cy
        spent = -(-amount // REPAIR_HP_PER_NUMBER)      # ceil
        u.carry = max(0, u.carry - spent)
        u.timer = u.period
        self.stats["healed"] += amount
        self.beams.append([u.x, u.y, tx, ty, amount, BEAM_TTL, HEAL])
        return amount

    def _enemy_ai(self, e):
        f = self.factory
        if e.timer > 0:
            e.timer -= 1
        # 1. a player unit in reach gets hit first (from a free post around it)
        u = self.nearest_unit(e.x, e.y, e.range)
        if u is not None:
            self._attack(e, u)
            self._hold_post(e, [(u.x, u.y)])
            return
        # 2. current structure target still standing and in reach?
        s = e.target
        if isinstance(s, Structure):
            if f.structures.get((s.x, s.y)) is not s:
                e.target = None
                s = None
            elif dist_to_tiles(e.x, e.y, s.tiles()) <= e.range:
                self._attack(e, s)
                self._hold_post(e, self._structure_points(s))
                return
        self.release_post(e)
        # 3. ranged fire while advancing: the nearest unit, else the nearest
        #    structure, within shot range (free; melee still needs contact)
        if e.shot_dmg is not None and e.timer <= 0 and e.shot_range > 0:
            victim = self.nearest_unit(e.x, e.y, e.shot_range)
            if victim is None:
                victim = self.nearest_structure_in(e.x, e.y, e.shot_range)
            if victim is not None:
                self._shoot(e, victim)
        # 4. choose where to go
        tx, ty = e.tile()
        if e.goal is not None:
            if f.structures.get(e.goal) is None:
                near = self.nearest_structure_tile(e.x, e.y)
                e.goal = near                       # None -> fall through to the hub
            step = greedy_step(tx, ty, *e.goal) if e.goal is not None else None
            if e.goal is None:
                step = self._hub_step(tx, ty)
        else:
            step = self._hub_step(tx, ty)
        if step is None:
            return
        blocker = f.structures.get(step)
        if blocker is not None:
            e.target = blocker
        self._move_toward(e, step[0] + 0.5, step[1] + 0.5)

    def _hold_post(self, e, points):
        """An attacking enemy shuffles to a free tile around its victim
        (never through a structure) so a crowd spreads out instead of stacking."""
        post = self.claim_post(e, points, e.range, self.factory.structures)
        if post is not None and not self._at_post(e):
            self._move_toward(e, post[0] + 0.5, post[1] + 0.5)

    def _structure_points(self, s):
        """Tile centres of s plus of the structures touching it, so a crowd
        fans out along a wall line (each enemy re-targets the segment it
        ends up next to)."""
        structures = self.factory.structures
        tiles = list(s.tiles())
        own = set(tiles)
        extra = []
        for tx, ty in tiles:
            for dx, dy in NEIGHBOURS4:
                t = (tx + dx, ty + dy)
                if t not in own and t in structures and t not in extra:
                    extra.append(t)
        return [(tx + 0.5, ty + 0.5) for tx, ty in tiles + extra]

    def _hub_step(self, tx, ty):
        step = self.flow.next_step(tx, ty) if (self.use_flow and self.flow.built) else None
        if step is None:
            hub = self.factory.hub
            gx, gy = (hub.x, hub.y) if hub is not None else (0, 0)
            step = greedy_step(tx, ty, gx, gy)
        return step
