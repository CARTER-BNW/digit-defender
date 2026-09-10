"""Belt transport: travel time, spacing, corners, merges, feed vs cargo sides,
chunk borders, loops, backpressure, link rebuilds, determinism."""
from settings import ITEM_SPACING, BELT_BASE_SPEED, CHUNK_SIZE
from sim.factory import Factory
from sim.structures import N, E, S, W, FRONT, BACK, LEFT, RIGHT, entry_side, EPS


def factory():
    return Factory(seed=1, balance=10 ** 9)


def line(f, x0, x1, y=0, direction=E):
    return [f.place("belt", x, y, direction, free=True) for x in range(x0, x1 + 1)]


def run(f, n):
    for _ in range(n):
        f.tick()


def items_on(belt):
    return [v for v, _ in belt.items]


def test_entry_side_table():
    # belt facing E, fed from the west by another E belt: enters the BACK
    assert entry_side(E, E) == BACK
    assert entry_side(W, E) == FRONT          # head-on
    assert entry_side(S, E) == LEFT           # coming down from the north
    assert entry_side(N, E) == RIGHT          # coming up from the south
    assert entry_side(E, S) == RIGHT          # corner: E line into an S belt


def test_travel_time_matches_speed():
    f = factory()
    miner = f.place("miner", 0, 0, E, free=True, value=5)
    belts = line(f, 1, 12)
    assert miner.period == 40
    run(f, 41)                                # first emission lands on belt 1
    assert items_on(belts[0]) == [5]
    ticks_per_tile = round(1 / BELT_BASE_SPEED)   # 20

    def tick_when_on(belt):
        n = 0
        while not belt.items:
            f.tick()
            n += 1
            assert n < 1000
        return f.tick_count

    t5 = tick_when_on(belts[4])
    t9 = tick_when_on(belts[8])
    assert abs((t9 - t5) - 4 * ticks_per_tile) <= 1


def test_items_stay_sorted_and_spaced_under_flood():
    f = factory()
    miner = f.place("miner", 0, 0, E, free=True, value=1)
    miner.invested = 10 ** 6                  # very fast miner
    assert miner.period < 10
    belts = line(f, 1, 4)                     # dead end at belt 4
    run(f, 600)
    total = 0
    for b in belts:
        ps = [p for _, p in b.items]
        assert ps == sorted(ps)
        for a, c in zip(ps, ps[1:]):
            assert c - a >= ITEM_SPACING - 1e-9
        assert all(0.0 <= p < 1.0 for p in ps)
        total += len(b.items)
    assert total == 16                        # 4 per tile when jammed
    assert belts[-1].items[-1][1] == 1.0 - EPS


def test_corner_turns():
    f = factory()
    f.place("miner", 0, 0, E, free=True, value=7)
    f.place("belt", 1, 0, E, free=True)
    f.place("belt", 2, 0, S, free=True)       # corner: enters from its right side
    f.place("belt", 2, 1, S, free=True)
    f.place("belt", 2, 2, W, free=True)       # second corner
    end = f.place("belt", 1, 2, W, free=True)
    run(f, 41 + 20 * 5 + 5)
    assert items_on(end) == [7]


def test_merge_preserves_items_and_orders_feeders():
    f = factory()
    f.place("miner", 0, 0, E, free=True, value=2)      # straight feeder (BACK)
    f.place("miner", 3, -2, S, free=True, value=3)     # side feeder from the north
    f.place("belt", 1, 0, E, free=True)
    a = f.place("belt", 2, 0, E, free=True)
    b = f.place("belt", 3, -1, S, free=True)
    c = f.place("belt", 3, 0, E, free=True)
    tail = line(f, 4, 9)
    run(f, 1)
    assert c.feeders == [a, b]                # BACK before side
    assert f.belts_ordered.index(c) < f.belts_ordered.index(a)
    assert f.belts_ordered.index(c) < f.belts_ordered.index(b)
    run(f, 400)
    on_belts = sum(len(x.items) for x in f.belts)
    assert on_belts == f.stats["mined"]
    values = set()
    for x in tail:
        values.update(items_on(x))
    assert values == {2, 3}


def test_head_on_is_feed_side_is_merge_tail_is_cargo():
    # tail cargo
    f = factory()
    a = f.place("belt", 0, 0, E, free=True)
    b = f.place("belt", 1, 0, E, free=True)
    a.items.append([9, 0.9])
    run(f, 3)
    assert items_on(b) == [9] and not a.items and b.invested == 0
    # side merge
    f = factory()
    a = f.place("belt", 0, 0, E, free=True)
    b = f.place("belt", 1, 0, N, free=True)
    a.items.append([9, 0.9])
    run(f, 3)
    assert items_on(b) == [9] and b.invested == 0
    # head-on = feed: value goes into invested/hp, item disappears
    f = factory()
    a = f.place("belt", 0, 0, E, free=True)
    b = f.place("belt", 1, 0, W, free=True)
    b.hp = 5
    a.items.append([9, 0.9])
    run(f, 3)
    assert not a.items and not b.items
    assert b.invested == 9 and b.hp == 14 and b.max_hp == 20 + 9


def test_line_across_chunk_borders():
    f = factory()
    f.place("miner", -20, 0, E, free=True, value=4)
    belts = line(f, -19, 20)
    assert (-1 // CHUNK_SIZE, 0) in f.by_chunk and (16 // CHUNK_SIZE, 0) in f.by_chunk
    assert f.structures[(-1, 0)] in f.by_chunk[(-1, 0)]
    assert f.structures[(16, 0)] in f.by_chunk[(1, 0)]
    run(f, 41 + 20 * 42)
    assert items_on(belts[-1]) and set(items_on(belts[-1])) == {4}
    assert f.stats["mined"] == sum(len(b.items) for b in belts)


def test_loop_keeps_items_and_keeps_moving():
    f = factory()
    a = f.place("belt", 0, 0, E, free=True)
    b = f.place("belt", 1, 0, S, free=True)
    c = f.place("belt", 1, 1, W, free=True)
    d = f.place("belt", 0, 1, N, free=True)
    a.items.append([1, 0.1])
    b.items.append([2, 0.5])
    d.items.append([3, 0.7])
    positions = set()
    for _ in range(1000):
        f.tick()
        count = sum(len(x.items) for x in (a, b, c, d))
        assert count == 3
        positions.add(tuple(sorted(items_on(x)[0] for x in (a, b, c, d) if x.items)))
    assert len(f.belts_ordered) == 4
    assert f.belts_ordered[0] is a          # smallest (y, x) breaks the loop
    # every belt saw traffic
    assert sum(len(x.items) for x in (a, b, c, d)) == 3


def test_backpressure_stalls_miner():
    f = factory()
    miner = f.place("miner", 0, 0, E, free=True, value=1)
    line(f, 1, 3)                             # dead end
    run(f, 2000)
    mined = f.stats["mined"]
    assert mined == 12                        # 3 belts * 4 items
    assert miner.timer == 0                   # ready and blocked
    run(f, 200)
    assert f.stats["mined"] == mined


def test_links_rebuild_on_place_remove_rotate():
    f = factory()
    a = f.place("belt", 0, 0, E, free=True)
    run(f, 1)
    assert a.next is None
    b = f.place("belt", 1, 0, E, free=True)
    assert f.dirty_links
    run(f, 1)
    assert a.next is b and a.next_rel == BACK
    f.rotate(1, 0)                            # b now faces S: side entry
    run(f, 1)
    assert a.next is b and a.next_rel == RIGHT
    f.remove(1, 0)
    run(f, 1)
    assert a.next is None and b not in f.belts


def test_determinism_same_build_same_state():
    def build():
        f = factory()
        f.create_hub(0, 0)
        f.place("miner", 8, 0, W, free=True, value=3)
        f.place("miner", 8, 2, W, free=True, value=5)
        line(f, 2, 7, 0, W)
        line(f, 2, 7, 2, W)
        f.place("belt", 0, 2, N, free=True)
        f.place("belt", 1, 2, W, free=True)
        return f
    a, b = build(), build()
    for _ in range(600):
        a.tick()
        b.tick()
    assert a.to_dict() == b.to_dict()
    assert a.balance > 10 ** 9


def test_belt_order_independent_of_insertion_order():
    def build(order):
        f = factory()
        spec = {(0, 0): E, (1, 0): E, (2, 0): E, (3, 0): S, (3, 1): S, (2, -1): S, (2, -2): S}
        for key in order:
            f.place("belt", key[0], key[1], spec[key], free=True)
        f.rebuild_links()
        return [(b.x, b.y) for b in f.belts_ordered]
    keys = [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (2, -1), (2, -2)]
    assert build(keys) == build(list(reversed(keys)))
