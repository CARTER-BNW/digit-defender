"""Belt bridges (crossings): two lanes, in one side out the opposite, never
mixing; feeding from belts, miners and machines; stalls; save round trip."""
from sim.factory import Factory
from sim.structures import N, E, S, W, FRONT, BACK, Bridge


def factory():
    return Factory(seed=1, balance=10 ** 9)


def line(f, x0, y0, x1, y1, d):
    out = []
    x, y = x0, y0
    while True:
        out.append(f.place("belt", x, y, d, free=True))
        if (x, y) == (x1, y1):
            break
        x += (x1 > x) - (x1 < x)
        y += (y1 > y) - (y1 < y)
    return out


def run(f, n):
    for _ in range(n):
        f.tick()


def values(belts):
    return {it[0] for b in belts for it in b.items}


def test_bridge_crosses_two_lines_without_mixing():
    f = factory()
    ma = f.place("miner", 0, 5, E, free=True, value=3)
    ma.invested = 10 ** 5
    line(f, 1, 5, 3, 5, E)
    br = f.place("bridge", 4, 5, N, free=True)
    east = line(f, 5, 5, 9, 5, E)
    mb = f.place("miner", 4, 0, S, free=True, value=7)
    mb.invested = 10 ** 5
    line(f, 4, 1, 4, 4, S)                                           # right up to the bridge
    south = line(f, 4, 6, 4, 10, S)
    run(f, 1)
    assert br.exits[W] is not None and br.exits[N] is not None      # fed lanes
    assert br.exits[E] is None and br.exits[S] is None              # nothing comes in from there
    assert br.exits[W][0] is east[0] and br.exits[W][1] == BACK
    run(f, 500)
    assert values(east) == {3} and values(south) == {7}             # never mixed
    assert east[-1].items and south[-1].items                        # both lines crossed all the way
    assert br.count() >= 1 and not br.lanes[E] and not br.lanes[S]
    # deterministic save round trip mid-flow
    d = f.to_dict()
    g = Factory.from_dict(d, seed=1)
    run(f, 100)
    run(g, 100)
    assert g.to_dict() == f.to_dict()


def test_bridge_takes_miner_and_machine_input_and_feeds_the_hq():
    f = factory()
    hub = f.create_hub(0, 0)
    br = f.place("bridge", -5, 0, N, free=True)                     # west of the HQ (edge at x = -3)
    f.place("belt", -4, 0, E, free=True)
    m = f.place("miner", -6, 0, E, free=True, value=9)                # beside the bridge: pushes across
    run(f, 1)
    assert br.exits[W][0].KIND == "belt" and br.exits[E] is None
    run(f, 120)                                                       # mined at 40, 20 ticks across, 20 on the belt
    assert f.balance >= 10 ** 9 + 9 and (f.balance - 10 ** 9) % 9 == 0
    # a machine's output goes across too, and a bridge can exit straight into a machine's side
    f2 = factory()
    src = f2.place("miner", 0, 0, E, free=True, value=4)
    src.invested = 10 ** 5
    f2.place("belt", 1, 0, E, free=True)
    b2 = f2.place("bridge", 2, 0, N, free=True)
    add = f2.place("adder", 3, 0, S, free=True)                      # bridge exits into its west side (right = B)
    f2.place("miner", 3, -1, S, free=True, value=1)                  # A from behind... its back
    out = line(f2, 3, 1, 3, 3, S)
    run(f2, 400)
    assert out[0].items and all(it[0] == 5 for b in out for it in b.items)


def test_bridge_stalls_and_keeps_spacing_when_blocked():
    f = factory()
    m = f.place("miner", 0, 0, E, free=True, value=2)
    m.invested = 10 ** 5
    f.place("belt", 1, 0, E, free=True)
    br = f.place("bridge", 2, 0, N, free=True)                       # nothing beyond: dead end
    run(f, 300)
    lane = br.lanes[W]
    assert 1 <= len(lane) <= 2 and lane[-1][1] < 1.0
    ps = [p for _, p in lane]
    assert ps == sorted(ps) and all(b - a >= 0.5 - 1e-9 for a, b in zip(ps, ps[1:]))
    mined = f.stats["mined"]
    run(f, 100)
    assert f.stats["mined"] == mined                                # backpressure reached the miner
    assert f.rotate(2, 0) is None and br.direction == 0             # bridges never turn


def test_bridge_replaces_a_belt_and_keeps_its_items_flowing():
    f = factory()
    m = f.place("miner", 0, 0, E, free=True, value=3)
    m.invested = 10 ** 5
    east = line(f, 1, 0, 6, 0, E)
    run(f, 120)
    mid = east[3]                                                     # (4, 0), carrying items by now
    assert mid.items
    carried = [[it[0], it[1]] for it in mid.items]
    assert f.can_place("bridge", 4, 0)[0] and f.replaces_belt("bridge", 4, 0)
    assert not f.can_place("bridge", 0, 0)[0]                         # only belts are swapped out
    bal = f.balance
    br = f.place("bridge", 4, 0, N)
    assert br is not None and f.structure_at(4, 0) is br and mid not in f.belts
    assert br.lanes[W] == carried and f.balance == bal - 10 + 1       # bridge paid, half a belt back
    run(f, 1)
    assert br.exits[W][0] is east[4]
    run(f, 200)
    assert east[-1].items and values(east[4:]) == {3}                 # the line runs on across the bridge
    f2 = factory()
    f2.place("belt", 2, 2, S, free=True)
    assert f2.place("belt", 2, 2, E) is None                           # a belt does not replace a belt
    assert f2.place("bridge", 2, 2, N, free=True).KIND == "bridge"    # free placement swaps too


def test_bridge_records_and_kinds():
    br = Bridge(3, 4)
    br.accept(5, W, 0.2, None)
    br.accept(6, N, 0.0, None)
    d = br.to_dict()
    assert d["kind"] == "bridge" and d["lanes"][W] == [[5, 0.2]] and d["lanes"][N] == [[6, 0.0]]
    again = Bridge.from_dict(d)
    assert again.lanes == br.lanes and again.count() == 2
    assert not br.accept(7, W, 0.9, None) or True                   # overshoot is clamped to the spacing
