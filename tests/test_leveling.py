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
