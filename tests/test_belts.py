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
    return [it[0] for it in belt.items]


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
        ps = [it[1] for it in b.items]
        assert ps == sorted(ps)
        for a, c in zip(ps, ps[1:]):
            assert c - a >= ITEM_SPACING - 1e-9
        assert all(0.0 <= p < 1.0 for p in ps)
        total += len(b.items)
    assert total == 4 * round(1 / ITEM_SPACING)   # 2 per tile when jammed
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
    assert b.invested == 9 and b.hp == 5 and b.max_hp == 20       # feed levels, never heals


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
    assert mined == 3 * round(1 / ITEM_SPACING)   # 3 belts * 2 items
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


def test_miner_outputs_on_all_four_sides_but_never_feeds():
    f = factory()
    m = f.place("miner", 5, 5, E, free=True, value=4)
    east = f.place("belt", 6, 5, E, free=True)     # cargo from behind
    north = f.place("belt", 5, 4, N, free=True)    # cargo from behind (belt points away)
    west = f.place("belt", 4, 5, S, free=True)     # side entry (belt runs south past the miner)
    south = f.place("belt", 5, 6, N, free=True)    # points INTO the miner: head-on, miner must not push
    other = f.place("miner", 7, 5, W, free=True, value=9)   # miners never feed each other
    run(f, 41)
    assert items_on(east) == [4] and items_on(north) == [4] and items_on(west) == [4]
    assert items_on(south) == []
    assert f.stats["mined"] == 3 and m.last_emit_tick == 40
    assert other.invested == 0 and m.invested == 0
    # a belt pointing into the miner still feeds it
    south.items.append([7, 0.99])
    run(f, 1)
    assert m.invested == 7 and not south.items
    # a wall next to a miner is not fed by it either
    f2 = factory()
    m2 = f2.place("miner", 0, 0, E, free=True, value=3)
    w = f2.place("wall", 1, 0, N, free=True)
    run(f2, 100)
    assert w.invested == 0 and f2.stats["mined"] == 0 and m2.timer == 0


def test_belt_connection_sides_for_sprites():
    f = factory()
    a = f.place("belt", 1, 0, E, free=True)        # straight, fed from the west
    b = f.place("belt", 2, 0, S, free=True)        # corner: fed from its west side
    c = f.place("belt", 2, 1, S, free=True)        # straight, fed from the north
    m = f.place("miner", 3, 1, W, free=True, value=1)   # miner east of c pushes into c's side
    f.place("belt", 0, 0, E, free=True)            # feeds a from the west
    f.rebuild_links()
    W_, N_, E_ = 1 << W, 1 << N, 1 << E
    assert a.in_sides == W_
    assert b.in_sides == W_
    assert c.in_sides == N_ | E_                   # a T: back + one side
    f.place("belt", 1, 1, E, free=True)            # feeds c from the west too
    f.rebuild_links()
    assert c.in_sides == N_ | E_ | W_               # a cross


def test_splitter_alternates_evenly_and_shapes_as_t():
    f = factory()
    m = f.place("miner", 5, 8, N, free=True, value=1)
    m.invested = 10 ** 6                              # fast source
    for y in range(7, 4, -1):
        f.place("belt", 5, y, N, free=True)          # up into the junction
    j = f.place("belt", 5, 4, N, free=True)          # junction: nothing in front
    left = [f.place("belt", x, 4, W, free=True) for x in range(4, 0, -1)]
    right = [f.place("belt", x, 4, E, free=True) for x in range(6, 10)]
    run(f, 400)
    nl = sum(len(b.items) for b in left)
    nr = sum(len(b.items) for b in right)
    assert nl > 0 and nr > 0 and abs(nl - nr) <= 1, (nl, nr)
    assert [o[2] for o in j.outputs] == [W, E]
    assert j.out_sides == (1 << W) | (1 << E) and j.in_sides == 1 << S
    from render.structures import belt_openings
    assert belt_openings(N, j.in_sides | (j.out_sides << 4)) == {S, W, E}
    # a straight continuation plus one side branch splits three ways
    f2 = factory()
    src = f2.place("miner", 0, 0, E, free=True, value=2)
    src.invested = 10 ** 6
    a = f2.place("belt", 1, 0, E, free=True)
    ahead = [f2.place("belt", x, 0, E, free=True) for x in range(2, 8)]
    branch = [f2.place("belt", 1, y, N, free=True) for y in range(-1, -7, -1)]
    run(f2, 400)
    assert sum(len(b.items) for b in branch) > 0 and sum(len(b.items) for b in ahead) > 0
    assert a.out_sides == (1 << E) | (1 << N)
    assert [o[2] for o in a.outputs] == [E, N]
    # ordering: both branches are downstream of the junction
    assert f2.belts_ordered.index(a) > f2.belts_ordered.index(ahead[0])
    assert f2.belts_ordered.index(a) > f2.belts_ordered.index(branch[0])


def test_only_miners_on_deposits():
    class T:
        def deposit_at(self, tx, ty):
            return 3 if (tx, ty) in ((2, 2), (3, 2)) else 0

        def buildable(self, tx, ty):
            return True
    f = Factory(seed=1, terrain=T(), balance=10 ** 6)
    assert f.can_place("belt", 2, 2, E) == (False, "only miners go on numbers")
    assert f.can_place("wall", 3, 2, E) == (False, "only miners go on numbers")
    assert f.can_place("miner", 2, 2, E)[0]
    assert f.can_place("belt", 4, 2, E)[0]


def test_items_remember_their_entry_side_for_rendering():
    """The third item field is the relative side it came in through
    (render-only): a corner entry draws the item sliding in from that edge."""
    f = factory()
    a = f.place("belt", 0, 0, E, free=True)
    corner = f.place("belt", 1, 0, S, free=True)          # E line turning south
    a.items.append([4, 0.9, BACK])
    run(f, 3)
    assert corner.items and corner.items[0][2] == RIGHT      # entered through its right (world W) side
    assert (corner.direction + corner.items[0][2]) % 4 == W
    m = f.place("miner", 2, 0, E, free=True, value=7)       # miner east of the S-facing corner: its LEFT side
    run(f, 41)
    sides = {it[2] for it in corner.items}
    assert LEFT in sides
    # round trip keeps the side; old two-field saves default to BACK
    d = corner.to_dict()
    assert all(len(it) == 3 for it in d["items"])
    from sim.structures import Belt
    again = Belt.from_dict(d)
    assert [it[2] for it in again.items] == [it[2] for it in corner.items]
    old = Belt.from_dict({"x": 0, "y": 0, "dir": E, "items": [[5, 0.25]]})
    assert old.items == [[5, 0.25, BACK]]


def test_parallel_line_corner_does_not_split_its_neighbour():
    """John: two parallel E lines; turning one belt of the lower line south
    must not turn the belt above it into a T splitter. Only a belt that
    starts beside a line (nothing feeding it) is a branch."""
    f = factory()
    top = [f.place("belt", x, 0, E, free=True) for x in range(0, 4)]
    bottom = [f.place("belt", x, 1, E, free=True) for x in range(0, 4)]
    f.rotate(1, 1)                                   # bottom[1] now faces S: a corner
    assert bottom[1].direction == S
    f.rebuild_links()
    assert [o[2] for o in top[1].outputs] == [E]     # no side output into the corner
    assert top[1].out_sides == 1 << E
    assert bottom[1].in_sides == 1 << W and bottom[1].outputs == []
    # a fresh belt started beside the top line with nothing feeding it is still a branch
    f.place("belt", 2, -1, N, free=True)
    f.rebuild_links()
    assert [o[2] for o in top[2].outputs] == [E, N]
