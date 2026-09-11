"""Combat: enemies, player units, waves, nest raids, beams. Headless.
Ticks from Factory.tick() after belts (docs/PLAN.md section 2.3 steps 5-7).

Determinism: no free-running RNG. Wave composition and positions come from
random.Random(f"{seed}:wave:{n}"), raids from (seed, region, raid ordinal).
Lists iterate in spawn order; nearest searches tie-break on uid.

Positions are float tile coordinates (tile (tx, ty) has centre (tx+.5, ty+.5)).
Enemies are blocked by structures and melee whatever blocks them, and they
also shoot (free) at the nearest unit or structure within shot_range while
advancing; player units walk over the base. Ranged/heavy unit shots debit
balance by the fired value (hold fire when broke); melee and towers are free
(towers eat ammo).
"""
import math
import random

from settings import (TICK_RATE, UNIT_STATS, ENEMY_STATS, WAVE_FIRST_S, WAVE_INTERVAL_BASE_S,
                      WAVE_INTERVAL_MIN_S, WAVE_INTERVAL_DECAY, WAVE_BUDGET_BASE,
                      WAVE_BUDGET_GROWTH, WAVE_SPAWN_MARGIN, WAVE_MIN_RADIUS, WAVE_MIX,
                      UNIT_AGGRO_TILES, UNIT_LEVEL_MULT, ENEMY_ATTACK_RANGE, FLOW_REFRESH_TICKS,
                      NEST_AGGRO_TILES, NEST_RAID_PERIOD_S, NEST_RAID_SIZE, NEST_BOUNTY,
                      NEST_REGION, CHUNK_SIZE, GATHER_MAX_RING)
from sim.pathing import FlowField, greedy_step, dist_to_tiles
from sim import nests as nestmod
from sim.structures import Structure, Spawner

ENEMY, PLAYER = 0, 1
BEAM_TTL = 6
NEST_SCAN_TICKS = 100
NEST_FIRST_RAID_S = 10
RETARGET_RADIUS = 40


class Unit:
    __slots__ = ("uid", "side", "kind", "x", "y", "hp", "max_hp", "speed", "range", "dmg",
                 "period", "timer", "shot", "shot_dmg", "shot_range", "target", "goal", "rally",
                 "level", "owner", "dead")

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
        self.wave = (WaveState.from_dict(wave) if wave
                     else WaveState(0, WAVE_FIRST_S * TICK_RATE, wave_angle(seed, 0)))
        self.raid_counts = {tuple(int(v) for v in k.split(",")): int(n)
                            for k, n in (raids or {}).items()}
        self.raid_next = {}                    # (rx, ry) -> tick of the next raid
        self.active_nests = {}                 # (rx, ry) -> NestSpec (aggro'd, alive)
        self.known_nests = {}                  # (rx, ry) -> NestSpec near the base (alive)
        self.stats = {"kills": 0, "losses": 0, "waves": 0, "shot_cost": 0, "raids": 0}
        self._last_scan = -NEST_SCAN_TICKS
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
        return {"uid": u.uid, "kind": u.kind, "x": u.x, "y": u.y, "hp": u.hp, "level": u.level,
                "owner": [u.owner.x, u.owner.y] if u.owner is not None else None,
                "rally": list(u.rally) if u.rally is not None else None}

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

    def gather(self, units, gx, gy):
        """Send `units` to a grid formation around (gx, gy): one tile each,
        spiralling out from the centre, flowing around structures and around
        units that are not part of the group. Deterministic (uid order)."""
        group = sorted((u for u in units if not u.dead), key=lambda u: u.uid)
        ids = {id(u) for u in group}
        taken = [u.rally for u in self.units
                 if not u.dead and u.rally is not None and id(u) not in ids]
        slots = spiral_slots(gx, gy)
        for u in group:
            u.rally = self._free_slot(slots, taken)
            taken.append(u.rally)
        return group

    def unit_at(self, x, y, radius=0.6):
        """Nearest live player unit within radius tiles of a point, or None."""
        return self.nearest_unit(x, y, radius)

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
        if t >= self.wave.next_at_tick:
            self.spawn_wave()
        if t - self._last_scan >= NEST_SCAN_TICKS:
            self._scan_nests(t)
        self._raids(t)
        if self.use_flow and self.enemies and (
                not self.flow.built or
                (f.dirty_flowfield and t - self.flow.built_tick >= FLOW_REFRESH_TICKS)):
            self.flow.build(f, t)
            f.dirty_flowfield = False
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

    def _walk_grid(self, u, x, y):
        """Walk to (x, y) along the grid lines through the tile centres:
        larger axis first (L-shaped paths, like the enemies), finishing
        exactly on the target once inside its tile. The unit runs straight
        along the row/column it is on; it only heads for the tile centre when
        the next step turns, or when a fight knocked it off the grid."""
        tx, ty = u.tile()
        gtx, gty = math.floor(x), math.floor(y)
        if tx == gtx and ty == gty:
            self._move_toward(u, x, y)
            return
        cx, cy = tx + 0.5, ty + 0.5
        sx, sy = greedy_step(tx, ty, gtx, gty)
        on_row = abs(u.y - cy) < 1e-9
        on_col = abs(u.x - cx) < 1e-9
        if (sy == ty and on_row) or (sx == tx and on_col):
            self._move_toward(u, sx + 0.5, sy + 0.5)
        else:
            self._move_toward(u, cx, cy)

    def _unit_ai(self, u):
        if u.timer > 0:
            u.timer -= 1
        e = self.nearest_enemy(u.x, u.y, UNIT_AGGRO_TILES)
        if e is not None:
            if u.dist_to(e.x, e.y) <= u.range:
                self._attack(u, e)
            else:
                self._walk_grid(u, e.x, e.y)           # chase along the grid too
            return
        spec = self.nearest_nest(u.x, u.y, UNIT_AGGRO_TILES)
        if spec is not None:
            cx, cy = spec.tx + 0.5, spec.ty + 0.5
            if u.dist_to(cx, cy) <= max(u.range, 1.5):
                self._attack(u, spec)
            else:
                self._walk_grid(u, cx, cy)
            return
        if u.rally is not None and (u.x != u.rally[0] or u.y != u.rally[1]):
            self._walk_grid(u, *u.rally)

    def _enemy_ai(self, e):
        f = self.factory
        if e.timer > 0:
            e.timer -= 1
        # 1. a player unit in reach gets hit first
        u = self.nearest_unit(e.x, e.y, e.range)
        if u is not None:
            self._attack(e, u)
            return
        # 2. current structure target still standing and in reach?
        s = e.target
        if isinstance(s, Structure):
            if f.structures.get((s.x, s.y)) is not s:
                e.target = None
                s = None
            elif dist_to_tiles(e.x, e.y, s.tiles()) <= e.range:
                self._attack(e, s)
                return
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

    def _hub_step(self, tx, ty):
        step = self.flow.next_step(tx, ty) if (self.use_flow and self.flow.built) else None
        if step is None:
            hub = self.factory.hub
            gx, gy = (hub.x, hub.y) if hub is not None else (0, 0)
            step = greedy_step(tx, ty, gx, gy)
        return step
