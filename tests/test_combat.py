"""Combat: greedy pathing + bump/attack, flow field routing, wave scaling,
towers, ranged shots debit balance, spawners, nests, hub death, determinism."""
import math

from settings import (TICK_RATE, WAVE_FIRST_S, WAVE_BUDGET_BASE, WAVE_BUDGET_GROWTH,
                      WAVE_MIN_RADIUS, ENEMY_STATS, UNIT_STATS, TOWER_RANGE, NEST_BOUNTY,
                      SPAWNER_QUEUE_MAX, UNIT_COSTS, GATHER_HUB_GAP, FLOW_COST_WALL)
from sim.factory import Factory
from sim.combat import Combat, wave_budget, wave_interval_ticks, spiral_slots, ENEMY, PLAYER
from sim.pathing import FlowField, greedy_step
from sim.structures import N, E, S, W
from sim import nests as nestmod


def world(seed=1, hub=True, balance=10 ** 6):
    f = Factory(seed=seed, balance=balance)
    if hub:
        f.create_hub(0, 0)
    c = Combat(f, seed)
    c.wave.next_at_tick = 10 ** 9            # no waves unless a test wants them
    return f, c


def run(f, n):
    for _ in range(n):
        f.tick()


def test_greedy_bumps_wall_then_reaches_hub():
    f, c = world()
    c.use_flow = False                                 # v1 behaviour: walk straight, chew what blocks
    wall = f.place("wall", 6, 0, N, free=True)
    e = c.spawn_enemy("grunt", 12.5, 0.5)
    run(f, 60)
    assert e.target is wall and wall.hp < wall.max_hp
    assert f.structure_at(6, 0) is wall
    run(f, 2000)
    assert f.structure_at(6, 0) is None               # chewed through
    assert f.hub.hp < f.hub.max_hp                     # now hitting the HQ (its edge is at x = 2)
    assert e.x < 4.5


def test_hub_death_sets_game_over_flag():
    f, c = world()
    f.hub.hp = 5
    c.spawn_enemy("brute", 3.5, 0.5)
    run(f, 200)
    assert f.hub_destroyed


def test_flow_field_routes_through_gap_and_chews_when_enclosed():
    f, c = world()
    # wall ring around the hub at radius 4 with a gap at the east side
    for i in range(-4, 5):
        for (x, y) in ((i, -4), (i, 4), (-4, i), (4, i)):
            if (x, y) == (4, 0):
                continue
            f.place("wall", x, y, N, free=True)
    e = c.spawn_enemy("runner", 0.5, -12.5)             # north of the ring
    run(f, 1)                                            # builds the field
    assert c.flow.built and c.flow.contains(0, -12)
    ring_cost = c.flow.distance(0, -5)
    assert ring_cost < FLOW_COST_WALL                    # the gap makes going around cheaper
    step = c.flow.next_step(0, -5)
    assert step != (0, -4)                               # do not step into the wall
    run(f, 1500)
    walls_left = sum(1 for s in f.walls)
    assert walls_left == 31                              # no wall was attacked
    assert f.hub.hp < f.hub.max_hp
    # fully enclosed: the enemy must chew through the cheapest tile
    f2, c2 = world()
    for i in range(-3, 4):
        for (x, y) in ((i, -3), (i, 3), (-3, i), (3, i)):
            f2.place("wall", x, y, N, free=True)
    e2 = c2.spawn_enemy("brute", 0.5, -10.5)
    run(f2, 3000)
    assert len(f2.walls) < 24 or f2.hub.hp < f2.hub.max_hp


def test_greedy_step_and_flow_outside_field():
    assert greedy_step(0, 0, 5, 1) == (1, 0)
    assert greedy_step(0, 0, -1, 7) == (0, 1)
    assert greedy_step(3, 3, 3, 3) is None
    f, c = world()
    c.spawn_enemy("grunt", 200.5, 0.5)                   # far outside the field: greedy
    run(f, 2)
    assert not c.flow.contains(200, 0)
    assert c.enemies[0].x < 200.5


def test_wave_budget_interval_and_spawn_ring():
    assert wave_budget(0) == WAVE_BUDGET_BASE
    assert wave_budget(3) == WAVE_BUDGET_BASE * WAVE_BUDGET_GROWTH ** 3
    assert wave_interval_ticks(0) == wave_interval_ticks(100) == 600 * TICK_RATE   # every 10 minutes, flat (John)
    assert WAVE_FIRST_S == 600
    f, c = world()
    assert Combat(Factory(seed=1), 1).wave.next_at_tick == WAVE_FIRST_S * TICK_RATE
    c.wave.next_at_tick = f.tick_count + 1
    run(f, 2)
    n0 = len(c.enemies)
    assert n0 >= 3 and c.wave.number == 1
    cx, cy, radius = c.spawn_ring()
    assert radius >= WAVE_MIN_RADIUS
    for e in c.enemies:
        assert abs(math.hypot(e.x - cx, e.y - cy) - radius) < 6
    # a later wave brings more
    c.enemies.clear()
    c.wave.number = 6
    c.wave.next_at_tick = f.tick_count + 1
    run(f, 2)
    assert len(c.enemies) > n0
    assert c.wave.next_at_tick == f.tick_count - 1 + 600 * TICK_RATE


def test_tower_kills_with_ammo_and_holds_without():
    f, c = world()
    tower = f.place("tower", 20, 0, N, free=True)         # away from the HQ (the grunt shoots the nearest)
    e = c.spawn_enemy("grunt", 20.5, 3.5)
    e.speed = 0.0                                         # sit still in range
    run(f, 50)
    assert e.hp == e.max_hp                               # no ammo, no shots
    tower.ammo.extend([9, 9, 9])
    run(f, 60)
    assert e.dead and c.stats["kills"] == 1
    assert len(tower.ammo) == 0                           # 3 shots of 9 for 20 hp
    assert all(b[6] == PLAYER for b in c.beams if (b[0], b[1]) == (20.5, 0.5))   # tower beams
    assert tower.hp < tower.max_hp                        # the grunt shot back while it lived


def test_tower_range_and_level_damage():
    f, c = world()
    tower = f.place("tower", 0, 20, N, free=True)
    tower.ammo.extend([5] * 10)
    far = c.spawn_enemy("grunt", 0.5, 20.5 + TOWER_RANGE + 2)
    far.speed = 0.0
    run(f, 40)
    assert far.hp == far.max_hp and len(tower.ammo) == 10
    tower.invested = 100                                  # level 2 -> 1.5x damage
    assert tower.damage_for(5) == 8


def test_ranged_shots_debit_balance_and_hold_when_broke():
    f, c = world(balance=3)
    u = c.spawn_unit("ranged", 5.5, 0.5)
    u.hp = u.max_hp = 10 ** 6                                      # survives the grunt shooting back
    e = c.spawn_enemy("grunt", 8.5, 0.5)
    e.speed = 0.0
    run(f, 200)
    assert f.balance == 0 and c.stats["shot_cost"] == 3           # 3 shots then broke
    assert e.hp == e.max_hp - 3
    f.balance = 1000
    run(f, 500)                                                    # 1 dmg per 20 ticks
    assert e.dead
    c.units.clear()                                                # only the heavy fires now
    heavy = c.spawn_unit("heavy", 5.5, 0.5)
    e2 = c.spawn_enemy("brute", 9.5, 0.5)
    e2.speed = 0.0
    bal = f.balance
    run(f, 1)
    assert f.balance == bal - UNIT_STATS["heavy"]["shot"]         # 100 per heavy shot
    assert e2.dead                                                 # 100 dmg > brute hp


def test_melee_is_free_and_units_rally():
    f, c = world(balance=0)
    u = c.spawn_unit("melee", 3.5, 0.5, rally=(3.5, 0.5))   # just outside the 6x6 HQ (x <= 2)
    e = c.spawn_enemy("runner", 7.5, 0.5)
    e.speed = 0.0
    run(f, 400)
    assert e.dead and f.balance == 0
    run(f, 400)
    assert u.dist_to(3.5, 0.5) < 0.5                     # walked back to the rally point


def test_spawner_trains_only_queued_units_and_charges_for_them():
    f, c = world(balance=120)
    sp = f.place("spawner_melee", 8, 0, S, free=True)
    run(f, 2000)
    assert c.units == [] and sp.queue == 0                 # nothing spawns on its own
    assert sp.enqueue(f) is None and f.balance == 120 - UNIT_COSTS["melee"]
    assert sp.enqueue(f) is None and f.balance == 20
    assert sp.enqueue(f) == "need 50" and sp.queue == 2    # broke: refused, nothing charged
    assert sp.label() == "2"
    run(f, 1)                                              # timer was ready: first unit at once
    assert len(c.units) == 1 and sp.queue == 1 and sp.timer == sp.period
    run(f, sp.period - 1)
    assert len(c.units) == 1
    run(f, 1)
    assert len(c.units) == 2 and sp.queue == 0 and sp.label() is None
    assert all(u.owner is sp for u in c.units)
    f.balance = 10 ** 6
    for _ in range(SPAWNER_QUEUE_MAX + 2):
        sp.enqueue(f)
    assert sp.queue == SPAWNER_QUEUE_MAX and sp.enqueue(f) == "queue full"
    sp.invested = 100                                      # level 2: faster training, stronger units
    assert sp.period < 200
    run(f, sp.period * 2 + 2)
    strong = [u for u in c.units if u.level == 2]
    assert strong and strong[0].max_hp > UNIT_STATS["melee"]["hp"]
    d = sp.to_dict()
    assert d["queue"] == sp.queue
    sp.rally = (9.5, 9.5)
    assert sp.to_dict()["rally"] == [9.5, 9.5]


def test_units_gather_beside_the_hub_in_a_grid():
    f, c = world()
    sp = f.place("spawner_ranged", 12, 1, S, free=True)    # east of the HQ
    gx, gy = sp.rally_point(f)
    assert (gx, gy) == (f.hub.SIZE // 2 + GATHER_HUB_GAP + 0.5, 0.5)    # two tiles clear of the HQ edge
    assert (math.floor(gx), math.floor(gy)) not in f.structures
    for _ in range(5):
        sp.enqueue(f)
    run(f, sp.period * 4 + 2)
    assert len(c.units) == 5
    slots = [u.rally for u in c.units]
    assert len(set(slots)) == 5                            # one tile each, never stacked
    assert all(s[0] % 1 == 0.5 and s[1] % 1 == 0.5 for s in slots)   # tile centres
    assert all((math.floor(s[0]), math.floor(s[1])) not in f.structures for s in slots)
    assert max(math.hypot(s[0] - gx, s[1] - gy) for s in slots) <= 1.5   # compact
    run(f, 400)
    assert all((u.x, u.y) == u.rally for u in c.units)     # arrived exactly on the grid
    # move the group: new compact grid around the target, still one per tile
    c.gather(c.units, 20.2, -7.7)
    assert (20.5, -7.5) in [u.rally for u in c.units]
    assert len({u.rally for u in c.units}) == 5
    run(f, 600)
    assert all((u.x, u.y) == u.rally for u in c.units)
    # a unit knocked off-grid re-centres first, then walks straight down its column
    u = c.units[0]
    u.x, u.y = 30.3, 2.9
    c.gather([u], 30.5, 10.5)
    run(f, 3)
    assert (u.x, u.y) == (30.5, 2.5)
    xs = set()
    for _ in range(300):
        f.tick()
        xs.add(u.x)
    assert xs == {30.5} and (u.x, u.y) == (30.5, 10.5)
    first = list(spiral_slots(4.4, -2.2, 1))
    assert first[0] == (4.5, -2.5) and len(first) == 9 and len(set(first)) == 9


def test_slots_skip_structures_and_other_units():
    f, c = world()
    for x in range(2, 6):
        f.place("wall", x, 0, N, free=True)                # a wall line east of the hub
    a = c.spawn_unit("melee", 2.5, 0.5, rally=(3.5, 1.5))
    slot = c.slot_near(3.5, 0.5)
    assert slot not in [(3.5, 0.5), (3.5, 1.5)] and (math.floor(slot[0]), math.floor(slot[1])) not in f.structures
    b = c.spawn_unit("melee", 2.5, 0.5, rally=slot)
    c.gather([a, b], 3.5, 0.5)
    assert a.rally != b.rally and all((math.floor(r[0]), math.floor(r[1])) not in f.structures
                                      for r in (a.rally, b.rally))


def test_wall_links_follow_neighbours():
    f, c = world()
    a = f.place("wall", 10, 10, N, free=True)
    b = f.place("wall", 11, 10, N, free=True)
    d = f.place("wall", 10, 11, N, free=True)
    f.rebuild_links()
    assert a.links == (1 << E) | (1 << S) and b.links == (1 << W) and d.links == (1 << N)
    assert a.label() == "1"
    f.remove(11, 10)
    f.rebuild_links()
    assert a.links == (1 << S)
    a.invested = 100
    assert a.label() == "2"


def test_nest_aggro_raid_and_destruction_bounty():
    seed = 1337
    spec = None
    for rx in range(-6, 7):
        for ry in range(-6, 7):
            spec = nestmod.nest_at(seed, rx, ry)
            if spec:
                break
        if spec:
            break
    assert spec is not None
    f = Factory(seed=seed, balance=0)
    f.create_hub(spec.tx + 10, spec.ty)                   # base right next to the nest
    c = Combat(f, seed)
    c.wave.next_at_tick = 10 ** 9
    run(f, 1)
    assert (spec.rx, spec.ry) in c.active_nests
    run(f, 10 * TICK_RATE + 5)
    assert c.stats["raids"] == 1 and len(c.enemies) >= 3
    assert all(e.goal is not None for e in c.enemies)
    # units kill the core
    c.enemies.clear()
    u = c.spawn_unit("melee", spec.tx + 2.5, spec.ty + 0.5, level=20)
    u.dmg = 10 ** 6
    run(f, 60)
    assert c.nests.is_destroyed(spec.rx, spec.ry)
    assert f.balance == NEST_BOUNTY * spec.tier
    assert any(ev[0] == "nest_destroyed" for ev in f.events)
    # persists through the registry round-trip and the nest stays quiet
    reg = nestmod.NestRegistry.from_dict(c.nests.to_dict())
    assert reg.is_destroyed(spec.rx, spec.ry)
    c2 = Combat(f, seed, nests=reg, raids=c.to_dict()["raids"])
    c2.wave.next_at_tick = 10 ** 9
    run(f, NEST_SCAN := 200)
    assert (spec.rx, spec.ry) not in c2.active_nests and c2.stats["raids"] == 0


def test_wave_state_roundtrip_and_determinism():
    def build(seed=9):
        f = Factory(seed=seed, balance=10 ** 6)
        f.create_hub(0, 0)
        for x in range(-6, 7):
            f.place("wall", x, -6, N, free=True)
        t = f.place("tower", 0, -4, N, free=True)
        t.ammo.extend([7] * 10)
        sp = f.place("spawner_ranged", 3, 3, S, free=True)
        c = Combat(f, seed)
        c.wave.next_at_tick = 50
        return f, c
    fa, ca = build()
    fb, cb = build()
    for _ in range(1500):
        fa.tick()
        fb.tick()
    assert ca.stats["waves"] == 1 and ca.stats == cb.stats
    assert [(e.uid, e.x, e.y, e.hp) for e in ca.enemies] == [(e.uid, e.x, e.y, e.hp) for e in cb.enemies]
    assert fa.to_dict() == fb.to_dict()
    d = ca.to_dict()
    c3 = Combat(fa, 9, wave=d, raids=d["raids"])
    assert c3.wave.number == ca.wave.number and c3.wave.next_at_tick == ca.wave.next_at_tick


def test_player_units_survive_a_save_round_trip():
    f, c = world()
    sp = f.place("spawner_heavy", 6, 6, S, free=True)
    sp.enqueue(f)
    run(f, 1)
    u = c.units[0]
    u.hp = 77
    e = c.spawn_enemy("grunt", 40.5, 40.5)
    d = c.to_dict()
    assert len(d["units"]) == 1 and d["units"][0]["kind"] == "heavy" and d["next_uid"] == c.next_uid
    c2 = Combat(f, 1, wave=d, raids=d["raids"], units=d["units"])
    assert len(c2.units) == 1 and c2.enemies == []              # enemies disperse, units stay
    v = c2.units[0]
    assert (v.uid, v.kind, v.x, v.y, v.hp, v.level) == (u.uid, "heavy", u.x, u.y, 77, 1)
    assert v.owner is sp and v.rally == u.rally and c2.next_uid == c.next_uid
    assert Combat(f, 1, wave={"number": 0, "next_at_tick": 5, "angle": 0.0}).units == []   # old saves


def test_tower_takes_ammo_from_every_side():
    from sim.structures import FRONT, BACK, LEFT, RIGHT
    f, c = world()
    tower = f.place("tower", 10, 10, N, free=True)
    for rel in (FRONT, RIGHT, BACK, LEFT):
        assert tower.accept(4, rel, 0.0, f)
    assert list(tower.ammo) == [4, 4, 4, 4] and tower.invested == 0    # never feed
    tower.ammo.clear()
    f.place("miner", 11, 10, E, free=True, value=6)        # beside it: pushes ammo in
    b = f.place("belt", 10, 11, N, free=True)              # belt from behind: ammo too
    b.items.append([5, 0.99, BACK])
    run(f, 41)
    assert sorted(tower.ammo) == [5, 6] and tower.invested == 0 and tower.level == 1
    tower.ammo.clear()
    assert tower.ammo_max == 20                             # 20 at level 1 (John)...
    tower.ammo.extend([1] * 20)
    assert not tower.accept(9, LEFT, 0.0, f)               # full: the belt stalls instead
    tower.invested = 225                                    # level 3: ...+10 per level
    assert tower.level == 3 and tower.ammo_max == 40 and tower.accept(9, LEFT, 0.0, f)


def test_enemies_shoot_while_advancing_and_melee_in_contact():
    f, c = world()
    wall = f.place("wall", 6, 0, N, free=True)
    e = c.spawn_enemy("grunt", 9.5, 0.5)                  # 3 tiles off: in shot range (4), not melee
    e.speed = 0.0
    run(f, 1)
    assert wall.hp == wall.max_hp - e.shot_dmg and any(b[6] == ENEMY for b in c.beams)
    run(f, e.period)
    assert wall.hp == wall.max_hp - 2 * e.shot_dmg
    far = c.spawn_enemy("brute", 20.5, 0.5)                # out of range: nothing to shoot
    far.speed = 0.0
    hp_wall = wall.hp
    run(f, far.period + 1)
    assert wall.hp == hp_wall - e.shot_dmg                 # only the grunt fired
    # a player unit in range is preferred over the wall
    u = c.spawn_unit("melee", 12.5, 0.5, rally=(12.5, 0.5))
    u.speed = 0.0
    hp_u, hp_wall = u.hp, wall.hp
    run(f, e.period + 1)
    assert u.hp < hp_u and wall.hp == hp_wall
    # in contact the melee hit lands (bigger than the shot)
    c.units.clear()
    e.x, e.target = 7.5, wall
    hp_wall = wall.hp
    run(f, e.period + 1)
    assert wall.hp == hp_wall - e.dmg and e.dmg > e.shot_dmg
    # raid tiers scale the shot too
    strong = c.spawn_enemy("grunt", 40.5, 40.5, mult=3)
    assert strong.shot_dmg == 3 and strong.shot_range == 4


def test_units_chase_along_the_grid():
    f, c = world()
    u = c.spawn_unit("melee", 2.5, 0.5, rally=(2.5, 0.5))
    e = c.spawn_enemy("grunt", 6.5, 3.5)
    e.speed = 0.0
    e.shot_dmg = None                                      # keep the unit alive and simple
    on_grid = True
    for _ in range(80):
        f.tick()
        on_grid &= abs(u.x % 1 - 0.5) < 1e-9 or abs(u.y % 1 - 0.5) < 1e-9
        if u.dist_to(e.x, e.y) <= u.range:
            break
    assert on_grid and u.dist_to(e.x, e.y) <= u.range     # walked rows/columns, arrived in reach
    run(f, 200)
    assert e.dead


def test_hub_hits_raise_the_alert_for_a_while():
    from settings import HUB_ALERT_S, TICK_RATE
    f, c = world()
    assert not f.hub_under_attack()
    f.damage(f.hub, 5)
    assert f.hub_under_attack()
    run(f, HUB_ALERT_S * TICK_RATE - 1)
    assert f.hub_under_attack()
    run(f, 2)
    assert not f.hub_under_attack()
    wall = f.place("wall", 5, 5, N, free=True)
    f.damage(wall, 5)
    assert not f.hub_under_attack()                        # only the hub counts


def test_home_camp_is_known_from_the_start_and_wakes_when_built_near():
    f, c = world(seed=1337)
    home = nestmod.home_nest(1337)
    run(f, 1)
    assert (home.rx, home.ry) in c.known_nests and (home.rx, home.ry) not in c.active_nests
    run(f, 300)
    assert c.stats["raids"] == 0                                   # nothing built near it: dormant
    f.place("wall", home.tx + 20, home.ty, N, free=True)           # within 48 tiles: it notices
    run(f, 101)
    assert (home.rx, home.ry) in c.active_nests
    run(f, 10 * TICK_RATE + 5)
    assert c.stats["raids"] >= 1 and all(e.shot_dmg for e in c.enemies)


def test_attackers_spread_over_distinct_tiles_instead_of_stacking():
    f, c = world()
    e = c.spawn_enemy("brute", 20.5, 10.5)
    e.speed, e.shot_dmg, e.dmg = 0.0, None, 0
    e.hp = e.max_hp = 10 ** 6
    for _ in range(4):
        c.spawn_unit("melee", 12.5, 10.5)                      # same spot, same target
    run(f, 300)
    tiles = {(math.floor(u.x), math.floor(u.y)) for u in c.units}
    assert len(tiles) == 4                                     # one tile each
    assert all(u.dist_to(e.x, e.y) <= u.range + 1e-9 for u in c.units)   # all in reach
    assert all(c._at_post(u) for u in c.units) and e.hp < e.max_hp
    # enemies attacking a wall line fan out along it and never slip through it
    f2, c2 = world()
    c2.use_flow = False
    walls = [f2.place("wall", 6, y, N, free=True) for y in range(-4, 5)]
    for w in walls:
        w.hp = 10 ** 6
    for _ in range(4):
        en = c2.spawn_enemy("grunt", 14.5, 0.5)
        en.shot_dmg = None
    run(f2, 400)
    tiles = {(math.floor(en.x), math.floor(en.y)) for en in c2.enemies}
    assert len(tiles) == 4 and all(t[0] >= 7 for t in tiles), tiles
    assert all(en.target in walls for en in c2.enemies)
    assert sum(10 ** 6 - w.hp for w in walls) > 0             # the wall line is being chewed


def test_units_route_around_walls_and_hold_when_enclosed():
    from sim.pathing import route
    f, c = world()
    ring = {}                                                  # walled yard east of the HQ, gate at (13, 4)
    for x in range(3, 14):
        for y in (1, 9):
            ring[(x, y)] = f.place("wall", x, y, N, free=True)
    for y in range(2, 9):
        for x in (3, 13):
            if (x, y) != (13, 4):
                ring[(x, y)] = f.place("wall", x, y, N, free=True)
    u = c.spawn_unit("melee", 5.5, 4.5, rally=(5.5, 4.5))
    c.gather([u], 16.5, 4.5)                                   # outside the yard
    visited = set()
    for _ in range(300):
        f.tick()
        visited.add(u.tile())
        assert abs(u.x % 1 - 0.5) < 1e-9 or abs(u.y % 1 - 0.5) < 1e-9   # stays on the grid lines
    assert (u.x, u.y) == u.rally == (16.5, 4.5)
    assert (13, 4) in visited                                  # went out through the gate...
    assert not (visited & set(ring))                           # ...never through a wall
    # belts are walked over, walls are not
    f.place("belt", 15, 4, S, free=True)
    c.gather([u], 5.5, 4.5)
    visited = set()
    for _ in range(300):
        f.tick()
        visited.add(u.tile())
    assert (u.x, u.y) == (5.5, 4.5) and (15, 4) in visited
    # close the gate: the unit is shut in and holds inside
    f.place("wall", 13, 4, N, free=True)
    c.gather([u], 16.5, 4.5)
    run(f, 300)
    assert u.x < 13 and u.tile() not in ring
    assert route((5, 4), (16, 4), c.solid) is None            # no route at all
    assert route((5, 4), (3, 4), c.solid) == [(4, 4)]         # a solid goal: the route stops beside it
    assert route((14, 4), (16, 4), c.solid) == [(15, 4), (16, 4)]   # the belt tile is fine to walk on
    # an enemy outside: no post across the wall, the unit stays put inside
    e = c.spawn_enemy("grunt", 15.5, 4.5)
    e.speed, e.shot_dmg = 0.0, None
    run(f, 60)
    assert u.x < 13 and (u.post is None or u.post not in c.solid)


def test_patrol_between_rally_and_a_second_point():
    f, c = world()
    u = c.spawn_unit("melee", 4.5, 0.5, rally=(4.5, 0.5))
    c.patrol([u], 12.2, 0.7)
    assert u.patrol == (12.5, 0.5) and u.leg == 1 and u.rally == (4.5, 0.5)
    far = home = 0
    for i in range(600):
        f.tick()
        if (u.x, u.y) == u.patrol:
            far += 1
        elif (u.x, u.y) == u.rally and i > 5:
            home += 1
    assert far > 3 and home > 3                                # bounced between the two points
    assert min(u.x for _ in (0,)) >= 4.5                       # never past either end
    d = c.to_dict()["units"][0]
    assert d["patrol"] == [12.5, 0.5] and "leg" in d and d["panchor"] == [12.5, 0.5]
    c2 = Combat(f, 1, wave=c.to_dict(), raids={}, units=[d])
    v = c2.units[0]
    assert v.patrol == (12.5, 0.5) and v.leg == d["leg"] and v.panchor == (12.5, 0.5)
    f.combat = c                                               # (a new Combat takes over the factory)
    c.gather([u], 8.5, 0.5)                                    # a move order ends the patrol
    assert u.patrol is None and u.leg == 0 and u.panchor is None
    run(f, 200)
    assert (u.x, u.y) == (8.5, 0.5)


def test_formations_shapes_persist_and_recentre():
    from settings import FORMATIONS
    from sim.combat import formation_slots
    f, c = world()
    units = [c.spawn_unit("ranged", 20.5 + i, 20.5, rally=(20.5 + i, 20.5)) for i in range(5)]
    assert c.group_formation(units) == "box"
    c.set_formation(units, "line")
    assert sorted(u.rally for u in units) == [(20.5 + i, 20.5) for i in range(5)]
    assert all(u.anchor == (22.5, 20.5) for u in units)
    c.set_formation(units, "column")
    assert sorted(u.rally for u in units) == [(22.5, 18.5 + i) for i in range(5)]
    c.set_formation(units, "wedge")
    assert set(u.rally for u in units) == {(22.5, 19.5), (21.5, 20.5), (23.5, 20.5), (20.5, 21.5), (24.5, 21.5)}
    c.set_formation(units, "ring")
    ring = set(u.rally for u in units)
    assert (22.5, 20.5) not in ring and all(max(abs(x - 22.5), abs(y - 20.5)) == 1 for x, y in ring)
    assert c.next_formation(units, 1) == "box" and c.next_formation(units, -1) == "ring"
    assert all(u.anchor == (22.5, 20.5) for u in units)        # cycling never drifts
    eight = list(formation_slots("ring", 0.5, 0.5, 8))[:8]
    assert len(set(eight)) == 8 and all(max(abs(x - 0.5), abs(y - 0.5)) == 1 for x, y in eight)
    assert eight[0] == (0.5, -0.5)                             # clockwise from the north
    # a move order keeps the group's formation, and it survives a save
    c.set_formation(units, "line")
    c.gather(units, 40.5, 40.5)
    assert sorted(u.rally for u in units) == [(38.5 + i, 40.5) for i in range(5)]
    assert {u.formation for u in units} == {"line"} and c.group_formation(units) == "line"
    recs = c.to_dict()["units"]
    assert all(r["formation"] == "line" for r in recs)
    c2 = Combat(f, 1, wave=c.to_dict(), raids={}, units=recs)
    assert c2.group_formation(c2.units) == "line" and len(FORMATIONS) == 5
    f.combat = c
    # formations flow around structures (a wall on a slot) and other units' slots
    f.place("wall", 39, 40, N, free=True)
    c.set_formation(units, "line")
    slots = [u.rally for u in units]
    assert (39.5, 40.5) not in slots and len(set(slots)) == 5


def test_repair_unit_heals_buildings_and_units_and_refills_at_the_hq():
    from settings import REPAIR_UNIT_CAPACITY, REPAIR_HP_PER_NUMBER, UNIT_COSTS, COSTS
    f, c = world(balance=2000)
    sp = f.place("spawner_repair", 8, 6, S, free=True)
    assert sp.KIND == "spawner_repair" and sp.UNIT == "repair" and COSTS["spawner_repair"] == 100
    wall = f.place("wall", 9, 3, N, free=True)
    f.damage(wall, 150)
    hurt = c.spawn_unit("melee", 10.5, 8.5, rally=(10.5, 8.5))
    hurt.hp = 10
    assert sp.enqueue(f) is None and f.balance == 2000 - UNIT_COSTS["repair"]
    run(f, 1)
    r = c.units[-1]
    assert r.kind == "repair" and r.heal == 25 and r.carry == 0 and r.shot is None
    run(f, 100)
    assert c.stats["refilled"] == REPAIR_UNIT_CAPACITY and f.balance == 1900 - REPAIR_UNIT_CAPACITY   # loaded at the HQ
    assert any(ev[0] == "refill" for ev in f.events)
    assert r.anchor == (5.5, 0.5)                              # the spawner's gather point
    run(f, 400)
    assert wall.hp == wall.max_hp and hurt.hp == hurt.max_hp
    spent = (150 + 50) // REPAIR_HP_PER_NUMBER
    assert r.carry == REPAIR_UNIT_CAPACITY - spent and c.stats["healed"] == 200
    assert wall not in f.damaged and (r.x, r.y) == r.rally      # back on its slot when nothing is damaged
    # repair units never fight: an enemy next to it is ignored (it keeps healing / idling)
    e = c.spawn_enemy("grunt", 4.5, 2.5)
    e.speed, e.shot_dmg, e.dmg = 0.0, None, 0
    run(f, 40)
    assert e.hp == e.max_hp
    # empty and broke: it waits at the HQ until numbers come in, then takes what there is
    c.enemies.clear()
    r.carry = 0
    f.balance = 0
    run(f, 200)
    assert r.carry == 0 and f.balance == 0
    from sim.pathing import dist_to_tiles
    assert dist_to_tiles(r.x, r.y, f.hub.tiles()) <= 1.5
    f.balance = 300
    run(f, 2)
    assert r.carry == 300 and f.balance == 0
    d = c.to_dict()
    rec = [u for u in d["units"] if u["kind"] == "repair"][0]
    assert rec["carry"] == 300 and rec["owner"] == [8, 6]
    c2 = Combat(f, 1, wave=d, raids={}, units=d["units"])
    assert [u.carry for u in c2.units if u.kind == "repair"] == [300]
