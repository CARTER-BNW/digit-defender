"""Test Lab: a hand-built layout showing every part and junction type around
the HQ, for manual bug hunting (John) and scripted checks
(tests/test_testworld.py). Launch: `python main.py --testworld` or the menu
entry "Test lab". Everything is placed with free=True (no cost; miners get
fixed digits, so the lab does not depend on deposits).

Legend (x grows east, y grows south; the HQ covers -3..2):
  WEST ROW y=-2 into the HQ's west edge, fed by miner 3 at (-24,-6) through two corners:
    (-20,-6) forced X split [T]: short dead-end stubs north and south (they fill, then stall)
    (-14,-2) forced T split [T] into a fed side belt: line north into tower A (-14,-7); miner 7 beside it
    (-12,-2) merge T: the miner-2 line comes down from the north
    (-11,-2) BRIDGE: the miner-6 line crosses the row from north to south without mixing, then runs
             east along y=5 and north into the HQ's south edge at (0,3)
    (-9,-2)  cross merge: miner 4 from the north and miner 5 from the south join the row
    (-6,-2)  auto branch: an unfed belt starting beside the row -> line north into tower B (-6,-5)
    (-16,-2) is a level-3 belt (badge, faster)
  NORTH into the HQ's north edge: adder (-1,-8) fed from behind (miner 2) and from its left (miner 3);
    multiplier (2,-8) fed from behind by one miner-3 line (pairs 3s -> 9);
    subtractor (-6,-9): 9 (north) - 4 (south) = 5, routed to (-3,-4); divider (5,-9): 8 // 2 = 4,
    routed round to the HQ's east edge at (3,0)
  EAST: tower C (9,-4) stocked by miner 1 (10,-4) beside it; tower D (9,4) empty (red frame)
  SOUTH-EAST: spawners ranged (6,6), melee (8,6), heavy (10,6), repair (12,6); two units queued each
  SOUTH-WEST: wall line y=8 from -12..-4 with a corner up at x=-12; levels 1 / 2 / 3;
    (-8,8) starts damaged (repair units head for it once trained)
"""
from sim.structures import N, E, S, W

NAME = "Test Lab"
SEED = 1337


def _line(f, x0, y0, x1, y1, d):
    out = []
    x, y = x0, y0
    while True:
        out.append(f.place("belt", x, y, d, free=True))
        if (x, y) == (x1, y1):
            break
        x += (x1 > x) - (x1 < x)
        y += (y1 > y) - (y1 < y)
    return out


def is_empty(factory):
    """True when only the HQ stands (a fresh world)."""
    return factory.count() <= 1


def top_up(f):
    """Add parts the legend gained after a lab was first built (the lab is
    saved like any world, so an older save keeps its layout). Returns what
    was added."""
    added = []
    if not any(s.KIND == "spawner_repair" for s in f.spawners) and f.structure_at(12, 6) is None:
        sp = f.place("spawner_repair", 12, 6, S, free=True)
        for _ in range(2):
            sp.enqueue(f)
        added.append(sp)
    return added


def build(f):
    """Place the lab in factory f (which already has its HQ). Returns the
    named parts for scripted checks."""
    lab = {}
    f.balance = max(f.balance, 5000)
    # ---- west row -------------------------------------------------------------
    lab["miner3"] = f.place("miner", -24, -6, E, free=True, value=3)
    top = _line(f, -23, -6, -18, -6, E)
    xsplit = f.structure_at(-20, -6)
    xsplit.split = True
    lab["xsplit"] = xsplit
    lab["stub_n"] = _line(f, -20, -7, -20, -9, N)
    lab["stub_s"] = _line(f, -20, -5, -20, -4, S)
    f.place("belt", -17, -6, S, free=True)                 # corner
    _line(f, -17, -5, -17, -3, S)
    f.place("belt", -17, -2, E, free=True)                 # corner
    row = _line(f, -16, -2, -12, -2, E)
    lab["bridge"] = f.place("bridge", -11, -2, N, free=True)
    row += _line(f, -10, -2, -4, -2, E)
    lab["row"] = row
    row[0].invested = 225                                  # (-16,-2): level 3
    split = f.structure_at(-14, -2)
    split.split = True
    lab["split"] = split
    lab["side_fed"] = _line(f, -14, -3, -14, -6, N)
    lab["miner7"] = f.place("miner", -15, -3, E, free=True, value=7)   # feeds the side belt (and the row)
    lab["towerA"] = f.place("tower", -14, -7, N, free=True)
    lab["miner2"] = f.place("miner", -12, -9, S, free=True, value=2)
    _line(f, -12, -8, -12, -3, S)
    lab["miner6"] = f.place("miner", -11, -9, S, free=True, value=6)
    lab["over"] = _line(f, -11, -8, -11, -3, S)
    lab["under"] = _line(f, -11, -1, -11, 4, S)
    f.place("belt", -11, 5, E, free=True)
    lab["south_run"] = _line(f, -10, 5, -1, 5, E)
    f.place("belt", 0, 5, N, free=True)
    lab["south_in"] = _line(f, 0, 4, 0, 3, N)
    lab["miner4"] = f.place("miner", -9, -8, S, free=True, value=4)
    _line(f, -9, -7, -9, -3, S)
    lab["miner5"] = f.place("miner", -9, 2, N, free=True, value=5)
    _line(f, -9, 1, -9, -1, N)
    lab["auto"] = _line(f, -6, -3, -6, -4, N)
    lab["towerB"] = f.place("tower", -6, -5, N, free=True)
    # ---- north: machines ----------------------------------------------------------
    lab["adder"] = f.place("adder", -1, -8, S, free=True)
    f.place("miner", -1, -12, S, free=True, value=2)
    _line(f, -1, -11, -1, -9, S)
    f.place("miner", 0, -8, W, free=True, value=3)         # the adder's left side (A)
    lab["adder_out"] = _line(f, -1, -7, -1, -4, S)
    lab["mul"] = f.place("multiplier", 2, -8, S, free=True)
    f.place("miner", 2, -12, S, free=True, value=3)
    _line(f, 2, -11, 2, -9, S)
    lab["mul_out"] = _line(f, 2, -7, 2, -4, S)
    lab["sub"] = f.place("subtractor", -6, -9, E, free=True)
    f.place("miner", -6, -10, S, free=True, value=9)       # A (north = its left)
    f.place("miner", -6, -8, N, free=True, value=4)        # B (south = its right)
    _line(f, -5, -9, -4, -9, E)
    f.place("belt", -3, -9, S, free=True)
    lab["sub_out"] = _line(f, -3, -8, -3, -4, S)
    lab["div"] = f.place("divider", 5, -9, E, free=True)
    f.place("miner", 5, -10, S, free=True, value=8)
    f.place("miner", 5, -8, N, free=True, value=2)
    f.place("belt", 6, -9, E, free=True)
    f.place("belt", 7, -9, S, free=True)
    _line(f, 7, -8, 7, -1, S)
    f.place("belt", 7, 0, W, free=True)
    lab["div_out"] = _line(f, 6, 0, 3, 0, W)
    # ---- east: towers -------------------------------------------------------------
    lab["towerC"] = f.place("tower", 9, -4, N, free=True)
    f.place("miner", 10, -4, W, free=True, value=1)
    lab["towerD"] = f.place("tower", 9, 4, N, free=True)
    # ---- south-east: spawners -------------------------------------------------------
    lab["spawners"] = [f.place(kind, x, 6, S, free=True)
                       for kind, x in (("spawner_ranged", 6), ("spawner_melee", 8), ("spawner_heavy", 10),
                                       ("spawner_repair", 12))]
    for sp in lab["spawners"]:
        for _ in range(2):
            sp.enqueue(f)
    # ---- south-west: walls ------------------------------------------------------------
    walls = [f.place("wall", x, 8, N, free=True) for x in range(-12, -3)]
    walls += [f.place("wall", -12, y, N, free=True) for y in (7, 6)]
    walls[4].invested = 100                                 # (-8,8): level 2
    walls[-1].invested = 225                                # (-12,6): level 3
    f.damage(walls[4], 150)                                 # something for the repair units to fix
    lab["walls"] = walls
    f.rebuild_links()
    return lab
