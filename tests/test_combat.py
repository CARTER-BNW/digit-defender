"""Combat: greedy pathing + bump/attack, flow field routing, wave scaling,
towers, ranged shots debit balance, spawners, nests, hub death, determinism."""
import math

from settings import (TICK_RATE, WAVE_FIRST_S, WAVE_BUDGET_BASE, WAVE_BUDGET_GROWTH,
                      WAVE_MIN_RADIUS, ENEMY_STATS, UNIT_STATS, TOWER_RANGE, NEST_BOUNTY,
                      SPAWNER_UNIT_CAP, FLOW_COST_WALL)
from sim.factory import Factory
from sim.combat import Combat, wave_budget, wave_interval_ticks, ENEMY, PLAYER
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
    assert f.hub.hp < f.hub.max_hp                     # now hitting the hub
    assert e.x < 3.0


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
    assert wave_interval_ticks(0) == 240 * TICK_RATE
    assert wave_interval_ticks(100) == 90 * TICK_RATE
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
    assert c.wave.next_at_tick > f.tick_count + 89 * TICK_RATE


def test_tower_kills_with_ammo_and_holds_without():
    f, c = world()
    tower = f.place("tower", 4, 0, N, free=True)
    e = c.spawn_enemy("grunt", 4.5, 3.5)
    e.speed = 0.0                                         # sit still in range
    run(f, 50)
    assert e.hp == e.max_hp                               # no ammo, no shots
    tower.ammo.extend([9, 9, 9])
    run(f, 60)
    assert e.dead and c.stats["kills"] == 1
    assert len(tower.ammo) == 0                           # 3 shots of 9 for 20 hp
    assert c.beams == [] or all(b[6] == PLAYER for b in c.beams)


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
    u = c.spawn_unit("melee", 2.5, 0.5, rally=(2.5, 0.5))
    e = c.spawn_enemy("runner", 6.5, 0.5)
    e.speed = 0.0
    run(f, 400)
    assert e.dead and f.balance == 0
    run(f, 400)
    assert u.dist_to(2.5, 0.5) < 0.5                     # walked back to the rally point


def test_spawner_cap_and_level_scaling():
    f, c = world()
    sp = f.place("spawner_melee", 5, 5, S, free=True)
    run(f, 2000)
    assert c.count_units_of(sp) == SPAWNER_UNIT_CAP
    assert all(u.owner is sp and u.rally == sp.rally_point() for u in c.units)
    sp.invested = 100                                     # level 2: +1 cap, stronger units
    run(f, 600)
    assert c.count_units_of(sp) == SPAWNER_UNIT_CAP + 1
    strong = [u for u in c.units if u.level == 2]
    assert strong and strong[0].max_hp > UNIT_STATS["melee"]["hp"]
    d = sp.to_dict()
    sp.rally = (9.5, 9.5)
    assert sp.to_dict()["rally"] == [9.5, 9.5]


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
