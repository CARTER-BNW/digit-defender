from settings import (LEVEL_THRESHOLDS, BELT_BASE_SPEED, BELT_SPEED_PER_FED,
                      MAX_BELT_SPEED, BASE_HP, RATE_STEP)
from sim import leveling
from sim.structures import Belt, Miner, Wall


def test_level_thresholds():
    assert LEVEL_THRESHOLDS[:4] == [100, 200, 400, 800]
    assert leveling.level(0) == 1
    assert leveling.level(99) == 1
    assert leveling.level(100) == 2
    assert leveling.level(200) == 3
    assert leveling.level(399) == 3
    assert leveling.level(400) == 4
    assert leveling.next_threshold(0) == 100
    assert leveling.next_threshold(100) == 200
    assert leveling.next_threshold(150) == 200
    assert leveling.next_threshold(10 ** 12) is None


def test_belt_speed_formula():
    assert leveling.belt_speed(0) == BELT_BASE_SPEED
    assert abs(leveling.belt_speed(100) - (BELT_BASE_SPEED + 100 * BELT_SPEED_PER_FED)) < 1e-12
    assert leveling.belt_speed(10 ** 9) == MAX_BELT_SPEED
    b = Belt(0, 0)
    b.invested = 300
    assert abs(b.speed - leveling.belt_speed(300)) < 1e-12


def test_period_formula():
    assert leveling.period(40, 0) == 40
    assert leveling.period(40, 100) == round(40 / (1 + RATE_STEP))
    assert leveling.period(40, 400) == round(40 / (1 + 3 * RATE_STEP))
    assert leveling.period(40, 10 ** 12) >= 1


def test_max_hp_and_feed_caps():
    assert leveling.max_hp("belt", 0) == BASE_HP["belt"]
    assert leveling.max_hp("wall", 250) == BASE_HP["wall"] + 250
    w = Wall(0, 0)
    assert w.hp == BASE_HP["wall"]
    w.hp = 10
    w.feed(30)
    assert w.invested == 30 and w.hp == 40 and w.max_hp == BASE_HP["wall"] + 30
    w.feed(10 ** 6)                  # heals by the fed value, never past max
    assert w.hp == 40 + 10 ** 6 and w.hp <= w.max_hp
    w.hp = w.max_hp
    w.feed(5)
    assert w.hp == w.max_hp          # cap moves with invested


def test_miner_period_scales_with_investment():
    m = Miner(0, 0, value=3)
    p0 = m.period
    m.invested = 400
    assert m.period < p0


def test_feed_through_belts_levels_and_speeds():
    """Head-on feeder line: the fed belt gains invested/level/speed while a
    normal tail entry never does (feed rule, docs/PLAN.md 3.5)."""
    from sim.factory import Factory
    from sim.structures import E, W, S
    f = Factory(seed=1, balance=10 ** 9)
    fed = f.place("belt", 5, 0, E, free=True)
    feeder = f.place("miner", 7, 0, W, free=True, value=9)     # points head-on at fed's front
    feeder.invested = 10 ** 6                                  # emits fast
    f.place("belt", 6, 0, W, free=True)                        # carries 9s west into fed's front
    cargo_src = f.place("miner", 3, 0, E, free=True, value=1)  # normal tail feed of cargo
    f.place("belt", 4, 0, E, free=True)
    s0 = fed.speed
    for _ in range(800):
        f.tick()
    assert fed.invested >= 100 and fed.level >= 2
    assert fed.speed > s0 and abs(fed.speed - leveling.belt_speed(fed.invested)) < 1e-12
    assert f.structure_at(4, 0).invested == 0                  # cargo entry is not feed
    assert cargo_src.invested == 0


def test_machine_fed_from_back_gets_faster():
    from sim.factory import Factory
    from sim.structures import E, W, S, N, BACK
    f = Factory(seed=1, balance=10 ** 9)
    m = f.place("adder", 5, 5, E, free=True)
    assert m.period == 40
    m.accept(120, BACK, 0.0, f)
    assert m.invested == 120 and m.level == 2 and m.period == 32
    # and the belt behind it (pointing E into the machine's back) feeds it
    back = f.place("belt", 4, 5, E, free=True)
    back.items.append([50, 0.99])
    f.tick()
    assert m.invested == 170 and not back.items


def test_damage_repair_and_destruction():
    from settings import REPAIR_COST_PER_HP
    from sim.factory import Factory
    from sim.structures import N
    f = Factory(seed=1, balance=1000)
    hub = f.create_hub(0, 0)
    w = f.place("wall", 5, 5, N, free=True)
    assert not f.damage(w, 50)
    assert w.hp == w.max_hp - 50 and w in f.damaged
    cost = f.repair(w)
    assert cost == int(50 * REPAIR_COST_PER_HP + 0.999) and w.hp == w.max_hp
    assert f.balance == 1000 - cost and w not in f.damaged
    f.balance = 0
    f.damage(w, 10)
    assert f.repair(w) == 0 and w.hp == w.max_hp - 10          # cannot afford
    assert f.damage(w, 10 ** 6)                                # destroyed
    assert f.structure_at(5, 5) is None and w not in f.walls
    assert f.events[-1][0] == "destroyed"
    assert f.damage(hub, 10 ** 9) and f.hub_destroyed and f.hub is hub


def test_panel_numbers_match_formulas():
    from sim.structures import Belt
    b = Belt(0, 0)
    b.invested = 250
    b.hp = 100
    assert b.level == leveling.level(250) == 3
    assert leveling.next_threshold(250) == 400
    assert b.max_hp == leveling.max_hp("belt", 250) == 270
    assert abs(b.speed - leveling.belt_speed(250)) < 1e-12
