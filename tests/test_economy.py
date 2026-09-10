"""Costs, refusals, hub income, targets, refunds, round-trip."""
from settings import COSTS, TARGET_COUNT, START_BALANCE
from sim.factory import Factory
from sim.economy import Target, make_target, target_range, target_reward
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


def test_target_payout_and_reroll():
    f = Factory(seed=1, balance=0)
    old = f.targets[0]
    f.targets[0] = Target(7, 55)
    f.deliver(7)
    assert f.balance == 7 + 55
    assert f.targets_completed == 1 and f.stats["bonus"] == 55
    assert f.targets[0].value != 7 or f.targets[0].reward != 55
    assert len(f.targets) == TARGET_COUNT
    assert f.events and f.events[-1] == ("target", 7, 55)
    f.deliver(7)                     # no longer a target: plain income
    assert f.balance == 7 + 55 + 7 and f.targets_completed == 1


def test_target_generation_is_seeded_and_scales():
    assert make_target(5, 0, 0).value == make_target(5, 0, 0).value
    lo, hi = target_range(0)
    assert lo <= make_target(5, 0, 0).value <= hi
    assert target_range(10)[0] > target_range(0)[0]
    assert target_reward(10) > 10
    f1, f2 = Factory(seed=77), Factory(seed=77)
    assert [t.value for t in f1.targets] == [t.value for t in f2.targets]
    for seed in range(40):                       # no duplicate values on the board
        vals = [t.value for t in Factory(seed=seed).targets]
        assert len(set(vals)) == len(vals), (seed, vals)


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
    f.targets[1] = Target(42, 999)
    f.deliver(42)
    d = f.to_dict()
    g = Factory.from_dict(d, seed=3)
    assert g.balance == f.balance
    assert [t.to_dict() for t in g.targets] == [t.to_dict() for t in f.targets]
    assert g.targets_generated == f.targets_generated
    assert g.hub is not None and g.structure_at(5, 5).KIND == "belt"
    assert g.to_dict() == d
