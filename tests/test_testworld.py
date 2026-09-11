"""The Test Lab builds, runs, delivers, crosses, splits and merges as documented."""
from sim.factory import Factory
from world import testworld


def build():
    f = Factory(seed=testworld.SEED, balance=1000)
    f.create_hub(0, 0)
    lab = testworld.build(f)
    return f, lab


def vals(belts):
    return {it[0] for b in belts for it in b.items}


def test_lab_builds_every_part_and_runs():
    f, lab = build()
    assert not testworld.is_empty(f)
    kinds = {s.KIND for s in f.all_structures()}
    assert {"belt", "bridge", "miner", "adder", "subtractor", "multiplier", "divider", "wall", "tower",
            "spawner_ranged", "spawner_melee", "spawner_heavy", "spawner_repair", "hub"} <= kinds
    assert all(s is not None for s in lab["row"] + lab["under"] + lab["walls"])
    assert len(lab["spawners"]) == 4 and all(sp.queue == 2 for sp in lab["spawners"])
    assert lab["walls"][4].hp < lab["walls"][4].max_hp and lab["walls"][4] in f.damaged
    for _ in range(900):
        f.tick()
    assert f.stats["delivered"] > 0 and f.stats["voided"] == 0
    # the bridge keeps the two lines apart: only 6s go south, no 6 on the row after it
    assert vals(lab["under"]) == {6} and vals(lab["south_run"]) == {6}
    assert 6 not in vals(lab["row"][5:6])                           # (-10,-2): right after the bridge
    # junction shapes: merge T, cross merge, forced split T, forced X split, auto branch
    row = {(b.x, b.y): b for b in lab["row"]}
    assert bin(row[(-12, -2)].in_sides).count("1") == 2 and len(row[(-12, -2)].outputs) == 1
    assert bin(row[(-9, -2)].in_sides).count("1") == 3
    assert [o[2] for o in lab["split"].outputs] == [1, 0]           # E + N
    assert len(lab["xsplit"].outputs) == 3
    assert [o[2] for o in row[(-6, -2)].outputs] == [1, 0]          # auto branch north
    assert lab["towerA"].ammo and lab["towerB"].ammo and lab["towerC"].ammo and not lab["towerD"].ammo
    assert lab["side_fed"][0].in_sides & (1 << 3)                   # fed from the west by miner 7
    # machines
    assert vals(lab["mul_out"]) == {9} and vals(lab["sub_out"]) == {5} and vals(lab["div_out"]) == {4}
    assert vals(lab["adder_out"]) <= {5, 4, 6} and vals(lab["adder_out"])
    # units trained, walls linked and levelled
    assert f.combat is None
    assert lab["walls"][4].level == 2 and lab["walls"][-1].level == 3
    assert lab["walls"][0].links and lab["walls"][-1].links
    assert lab["row"][0].level == 3


def test_lab_top_up_adds_the_repair_spawner_to_an_older_lab():
    f, lab = build()
    f.remove(12, 6, refund=False)                                   # a lab saved before the repair spawner existed
    assert not any(s.KIND == "spawner_repair" for s in f.spawners)
    bal = f.balance
    added = testworld.top_up(f)
    assert [s.KIND for s in added] == ["spawner_repair"] and added[0].queue == 2 and f.balance < bal
    assert testworld.top_up(f) == []                                # idempotent


def test_lab_is_deterministic_through_a_save():
    f, _ = build()
    for _ in range(300):
        f.tick()
    d = f.to_dict()
    g = Factory.from_dict(d, seed=testworld.SEED)
    for _ in range(200):
        f.tick()
        g.tick()
    assert g.to_dict() == f.to_dict()
