"""Costs, refusals, hub income, targets, refunds, round-trip."""
from settings import COSTS, TARGET_COUNT, START_BALANCE
from sim.factory import Factory
from sim.economy import Target, initial_targets, next_level, target_reward, top_up
from sim.structures import N, E, S, W


class FakeTerrain:
    def __init__(self, deposits=None, nests=()):
        self.deposits = deposits or {}
        self.nests = set(nests)

    def deposit_at(self, tx, ty):
        return self.deposits.get((tx, ty), 0)

    def buildable(self, tx, ty):
        return (tx, ty) not in self.nests


def test_costs_deducted_and_refunded():
    f = Factory(seed=1, terrain=FakeTerrain({(3, 0): 4}), balance=100)
    assert f.place("belt", 0, 0, E) is not None
    assert f.balance == 100 - COSTS["belt"]
    assert f.place("miner", 3, 0, W) is not None
    assert f.balance == 100 - COSTS["belt"] - COSTS["miner"]
    assert f.remove(0, 0).KIND == "belt"
    assert f.balance == 100 - COSTS["miner"] - COSTS["belt"] + COSTS["belt"] // 2
    assert f.structure_at(0, 0) is None


def test_insufficient_balance_and_other_refusals():
    f = Factory(seed=1, terrain=FakeTerrain({(3, 0): 4}, nests=[(9, 9)]), balance=1)
    assert f.can_place("belt", 0, 0, E) == (False, "need 2")
    assert f.place("belt", 0, 0, E) is None and f.balance == 1
    f.balance = 10 ** 6
    assert f.can_place("miner", 0, 0, E) == (False, "miner needs a deposit")
    assert f.can_place("miner", 3, 0, E)[0]
    assert f.can_place("belt", 9, 9, E) == (False, "cannot build here")
    assert f.can_place("hub", 20, 20, E)[0] is False
    f.place("belt", 0, 0, E)
    assert f.can_place("belt", 0, 0, E) == (False, "occupied")
    assert f.can_place("adder", 0, 0, E) == (False, "occupied")


def test_hub_delivery_credits_face_value_via_any_hub_tile():
    f = Factory(seed=1, balance=0)
    for t in f.targets:
        t.value = 10 ** 9            # keep bonuses out of this test
    f.create_hub(0, 0)
    # belt pointing at a hub corner tile from the north-east
    b = f.place("belt", 1, -2, S, free=True)
    b.items.append([7, 0.99])
    f.tick()
    assert f.balance == 7 and not b.items and f.stats["delivered"] == 7
    # miner straight into the hub's west edge
    m = f.place("miner", -2, 1, E, free=True, value=9)
    for _ in range(41):
        f.tick()
    assert f.balance == 16


def test_target_amount_progress_payout_and_level_up():
    f = Factory(seed=1, balance=0)
    f.targets[0] = Target(0, 1, 7, 3)                  # slot 0: deliver three 7s
    reward = f.targets[0].reward
    assert reward == target_reward(7, 3) == int(7 * 3 * 1.5) + 20
    f.deliver(7)
    f.deliver(7)
    assert f.targets[0].delivered == 2 and f.balance == 14 and f.targets_completed == 0
    f.deliver(7)                                        # the third one completes it
    assert f.balance == 21 + reward and f.stats["bonus"] == reward and f.targets_completed == 1
    nxt = f.targets[0]
    assert nxt.slot == 0 and nxt.level == 2 and nxt.delivered == 0
    assert 7 < nxt.value <= 14 and 3 < nxt.amount <= 6          # each grew 25-75% (+dupe bump)
    assert nxt.value not in {t.value for t in f.targets if t is not nxt}
    assert len(f.targets) == TARGET_COUNT
    assert f.events[-1] == ("target", 7, reward, 3, 2, nxt.value, nxt.amount)
    f.deliver(7)                                        # 7 is no longer a target: plain income
    assert f.balance == 21 + reward + 7 and f.targets_completed == 1


def test_targets_start_distinct_5_to_9_and_climb_a_seeded_ladder():
    f1, f2 = Factory(seed=77), Factory(seed=77)
    assert [t.value for t in f1.targets] == [t.value for t in f2.targets]
    for seed in range(40):
        ts = Factory(seed=seed).targets
        vals = [t.value for t in ts]
        assert len(ts) == TARGET_COUNT and len(set(vals)) == len(vals), (seed, vals)
        assert all(5 <= v <= 9 for v in vals)
        assert all(t.level == 1 and t.amount == 5 and t.delivered == 0 for t in ts)
        assert [t.slot for t in ts] == list(range(TARGET_COUNT))
    # the ladder is seeded per (world, slot, level) and always climbs 25-75% (at least +1)
    t = Target(2, 1, 9, 5)
    a, b = next_level(5, t), next_level(5, t)
    assert (a.value, a.amount, a.level) == (b.value, b.amount, 2)
    assert 11 <= a.value <= 16 and 6 <= a.amount <= 9
    cur = Target(0, 1, 5, 5)
    for lvl in range(2, 12):
        nxt = next_level(11, cur)
        assert nxt.level == lvl and nxt.value > cur.value and nxt.amount > cur.amount
        assert nxt.value <= cur.value * 1.75 + 1 and nxt.amount <= cur.amount * 1.75 + 1
        cur = nxt
    assert cur.value >= 39 and cur.amount >= 39                # ten levels of at least x1.25
    # a number another slot already uses is bumped past it
    assert next_level(5, t, taken={a.value, a.value + 1}).value == a.value + 2
    assert target_reward(10, 4) == int(10 * 4 * 1.5) + 20
    assert [t.value for t in initial_targets(5, 7)] and len({t.value for t in initial_targets(5, 7)}) == 7


def test_hub_is_permanent():
    f = Factory(seed=1)
    hub = f.create_hub(0, 0)
    assert f.remove(1, 1) is None and f.rotate(0, 0) is None
    assert f.structure_at(-1, -1) is hub and f.structure_at(1, 1) is hub
    assert len([k for k, v in f.structures.items() if v is hub]) == 9
    assert f.can_place("belt", 0, 0, E) == (False, "occupied")


def test_factory_roundtrip_preserves_economy_state():
    f = Factory(seed=3, balance=START_BALANCE)
    f.create_hub(0, 0)
    f.place("belt", 5, 5, N, free=True)
    f.targets[1] = Target(1, 3, 42, 4, reward=999)
    f.deliver(42)                                       # progress 1/4, not done yet
    d = f.to_dict()
    g = Factory.from_dict(d, seed=3)
    assert g.balance == f.balance
    assert [t.to_dict() for t in g.targets] == [t.to_dict() for t in f.targets]
    assert g.targets[1].delivered == 1 and g.targets[1].level == 3 and g.targets[1].reward == 999
    assert g.hub is not None and g.structure_at(5, 5).KIND == "belt"
    assert g.to_dict() == d


def test_old_saves_with_three_value_reward_targets_still_load():
    d = Factory(seed=3).to_dict()
    d["targets"] = [{"value": 4, "reward": 40}, {"value": 6, "reward": 50}, {"value": 9, "reward": 65}]
    g = Factory.from_dict(d, seed=3)
    assert len(g.targets) == TARGET_COUNT
    assert [t.value for t in g.targets[:3]] == [4, 6, 9]
    assert all(t.level == 1 and t.amount == 5 and t.delivered == 0 for t in g.targets[:3])
    assert g.targets[0].reward == 40                    # kept as saved
    vals = [t.value for t in g.targets]
    assert len(set(vals)) == TARGET_COUNT and g.targets[3].slot == 3
    assert top_up(3, [Target(0, 1, 5, 5)], 2)[1].value != 5
