"""Math machines: the four ops, voiding, buffers, stalls, sides."""
import pytest

from settings import MACHINE_BUFFER, MACHINE_BASE_PERIOD
from sim.factory import Factory
from sim.structures import N, E, S, W, FRONT, LEFT, RIGHT, BACK


def rig(kind, a, b):
    """Machine at (5,5) facing E; operand A from the north (its left side),
    operand B from the south (its right side); output belt at (6,5) that
    dead-ends so the result can be read."""
    f = Factory(seed=1, balance=10 ** 9)
    m = f.place(kind, 5, 5, E, free=True)
    f.place("miner", 5, 4, S, free=True, value=a)
    f.place("miner", 5, 6, N, free=True, value=b)
    out = f.place("belt", 6, 5, E, free=True)
    return f, m, out


def first_output(f, out, max_ticks=400):
    for _ in range(max_ticks):
        f.tick()
        if out.items:
            return out.items[0][0]
    return None


@pytest.mark.parametrize("kind,a,b,expected", [
    ("adder", 3, 4, 7),
    ("subtractor", 7, 2, 5),
    ("multiplier", 3, 4, 12),
    ("divider", 7, 2, 3),
    ("divider", 9, 3, 3),
])
def test_ops(kind, a, b, expected):
    f, m, out = rig(kind, a, b)
    assert first_output(f, out) == expected


@pytest.mark.parametrize("kind,a,b", [("subtractor", 3, 5), ("subtractor", 4, 4), ("divider", 2, 7)])
def test_nonpositive_results_are_voided(kind, a, b):
    f, m, out = rig(kind, a, b)
    assert first_output(f, out, 300) is None
    assert f.stats["voided"] >= 1
    assert m.out is None


def test_operand_sides_and_front_refuses():
    f = Factory(seed=1, balance=10 ** 9)
    m = f.place("adder", 0, 0, E, free=True)
    assert m.accept(1, LEFT, 0.0, f) and list(m.in_a) == [1]
    assert m.accept(2, RIGHT, 0.0, f) and list(m.in_b) == [2]
    assert m.accept(50, BACK, 0.0, f) and m.invested == 50
    assert not m.accept(3, FRONT, 0.0, f)
    # a belt pointing into the machine's front stalls with its item
    belt = f.place("belt", 1, 0, W, free=True)
    belt.items.append([9, 0.95])
    for _ in range(5):
        f.tick()
    assert belt.items and belt.items[0][0] == 9


def test_buffer_full_stalls_upstream():
    f = Factory(seed=1, balance=10 ** 9)
    m = f.place("adder", 0, 0, E, free=True)
    for i in range(MACHINE_BUFFER):
        assert m.accept(1, LEFT, 0.0, f)
    assert not m.accept(1, LEFT, 0.0, f)
    # operand-B side is independent
    assert m.accept(1, RIGHT, 0.0, f)


def test_output_stall_holds_result_until_space():
    f = Factory(seed=1, balance=10 ** 9)
    m = f.place("adder", 0, 0, E, free=True)     # nothing in front
    m.accept(2, LEFT, 0.0, f)
    m.accept(3, RIGHT, 0.0, f)
    for _ in range(MACHINE_BASE_PERIOD + 2):
        f.tick()
    assert m.out == 5
    for _ in range(50):
        f.tick()
    assert m.out == 5                              # still held
    out = f.place("belt", 1, 0, E, free=True)      # now there is space
    f.tick()
    assert m.out is None and out.items[0][0] == 5


def test_processing_rate_and_ordering():
    f, m, out = rig("adder", 1, 1)
    # dead-end output belt holds 4 items max, so count deliveries on the belt
    for _ in range(41 + MACHINE_BASE_PERIOD * 2):
        f.tick()
    assert out.items                       # at least one 2 produced
    assert all(it[0] == 2 for it in out.items)
    assert m.period == MACHINE_BASE_PERIOD
    m.invested = 100                       # level 2 -> faster
    assert m.period == round(MACHINE_BASE_PERIOD / 1.25)


def test_machine_roundtrip_mid_operation():
    f, m, out = rig("multiplier", 3, 4)
    for _ in range(60):
        f.tick()
    d = m.to_dict()
    from sim.structures import KINDS
    m2 = KINDS[d["kind"]].from_dict(d)
    assert m2.to_dict() == d
    assert (m2.busy, m2.timer, m2.out, list(m2.in_a), list(m2.in_b)) == \
        (m.busy, m.timer, m.out, list(m.in_a), list(m.in_b))
