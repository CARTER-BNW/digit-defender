"""World generation: purity/determinism, negative coords, deposits, spawn
clearing + near-spawn guarantee, nest safe zone."""
import random

from settings import CHUNK_SIZE, SPAWN_CLEAR_RADIUS, SAFE_REGIONS, NEST_REGION
from world.generator import generate_chunk, in_spawn_clearing
from world.terrain import Terrain
from world import tiles
from sim import nests

SEED = 1337


def test_deterministic_same_args():
    for cx, cy in ((0, 0), (-1, -1), (7, -3), (-40, 25)):
        assert generate_chunk(SEED, cx, cy) == generate_chunk(SEED, cx, cy)


def test_visit_order_independent():
    coords = [(x, y) for x in range(-3, 4) for y in range(-3, 4)]
    a = Terrain(SEED)
    b = Terrain(SEED)
    for c in coords:
        a.get_chunk(*c)
    for c in reversed(coords):
        b.get_chunk(*c)
    for c in coords:
        assert a.get_chunk(*c).tiles == b.get_chunk(*c).tiles


def test_seed_changes_terrain():
    assert generate_chunk(SEED, 3, 3) != generate_chunk(SEED + 1, 3, 3)


def test_tile_ids_valid_and_checker_parity():
    for cx, cy in ((0, 0), (-1, 0), (0, -1), (-5, 9)):
        t = generate_chunk(SEED, cx, cy)
        assert len(t) == CHUNK_SIZE * CHUNK_SIZE
        for i, tile in enumerate(t):
            tx, ty = cx * CHUNK_SIZE + i % CHUNK_SIZE, cy * CHUNK_SIZE + i // CHUNK_SIZE
            if tiles.is_ground(tile):
                assert tile & 1 == (tx + ty) & 1      # global parity -> seamless checker
            else:
                assert tiles.deposit_value(tile) in range(1, 10) or tiles.is_nest(tile)


def test_negative_coords_and_borders():
    t = Terrain(SEED)
    # tile -1 lives in chunk -1 at local 15; tile 16 in chunk 1 at local 0
    assert t.get_tile(-1, -1) == generate_chunk(SEED, -1, -1)[15 * CHUNK_SIZE + 15]
    assert t.get_tile(0, 0) == generate_chunk(SEED, 0, 0)[0]
    assert t.get_tile(15, 3) == generate_chunk(SEED, 0, 0)[3 * CHUNK_SIZE + 15]
    assert t.get_tile(16, 3) == generate_chunk(SEED, 1, 0)[3 * CHUNK_SIZE + 0]
    assert t.get_tile(-17, 40) == generate_chunk(SEED, -2, 2)[8 * CHUNK_SIZE + 15]
    assert set(t.chunks) == {(-1, -1), (0, 0), (1, 0), (-2, 2)}


def test_spawn_clearing_is_ground():
    t = Terrain(SEED)
    r = SPAWN_CLEAR_RADIUS
    for tx in range(-r, r + 1):
        for ty in range(-r, r + 1):
            assert in_spawn_clearing(tx, ty)
            assert tiles.is_ground(t.get_tile(tx, ty)), (tx, ty)
    assert not in_spawn_clearing(r + 1, 0)


def test_near_spawn_guarantee_every_seed():
    """Chunks within radius 2 of the origin always contain a 1, a 2 and a 3
    deposit, whatever the seed."""
    for seed in (SEED, 0, 1, 42, 99999, 2 ** 31 - 1):
        found = set()
        for cx in range(-2, 3):
            for cy in range(-2, 3):
                for tile in generate_chunk(seed, cx, cy):
                    d = tiles.deposit_value(tile)
                    if d:
                        found.add(d)
        assert {1, 2, 3} <= found, (seed, found)


def test_deposit_values_and_blob_coherence():
    """Every deposit tile holds 1..9 and belongs to a same-digit blob."""
    t = Terrain(SEED)
    rng = random.Random(1)
    for _ in range(40):
        cx, cy = rng.randint(-30, 30), rng.randint(-30, 30)
        chunk = t.get_chunk(cx, cy)
        for i, tile in enumerate(chunk.tiles):
            d = tiles.deposit_value(tile)
            if not d:
                continue
            assert 1 <= d <= 9
            lx, ly = i % CHUNK_SIZE, i // CHUNK_SIZE
            neighbours = [chunk.get(lx + dx, ly + dy)
                          for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                          if 0 <= lx + dx < CHUNK_SIZE and 0 <= ly + dy < CHUNK_SIZE]
            # a blob has >= 3 tiles, so every deposit tile has a same-digit neighbour
            assert tile in neighbours, (cx, cy, lx, ly)


def test_high_digits_rarer_near_origin():
    def high_share(radius_lo, radius_hi):
        hi = lo = 0
        for cx in range(-radius_hi, radius_hi + 1):
            for cy in range(-radius_hi, radius_hi + 1):
                if max(abs(cx), abs(cy)) < radius_lo:
                    continue
                for tile in generate_chunk(SEED, cx, cy):
                    d = tiles.deposit_value(tile)
                    if d >= 6:
                        hi += 1
                    elif d:
                        lo += 1
        return hi / max(1, hi + lo)
    assert high_share(0, 4) < high_share(30, 34)


def test_nest_safe_zone_and_stamping():
    for rx in range(-SAFE_REGIONS, SAFE_REGIONS + 1):
        for ry in range(-SAFE_REGIONS, SAFE_REGIONS + 1):
            assert nests.nest_at(SEED, rx, ry) is None
    # find a nest somewhere and verify the generator stamps it exactly once
    found = None
    for rx in range(-8, 9):
        for ry in range(-8, 9):
            spec = nests.nest_at(SEED, rx, ry)
            if spec is not None:
                found = spec
                break
        if found:
            break
    assert found is not None, "expected at least one nest within 8 regions"
    assert found.tier >= 1
    t = Terrain(SEED)
    assert t.get_tile(found.tx, found.ty) == tiles.NEST_CORE
    assert t.get_tile(found.tx + 1, found.ty) == tiles.NEST_GROUND
    assert t.get_tile(found.tx + nests.NEST_RADIUS + 1, found.ty) != tiles.NEST_GROUND
    core_count = sum(1 for tile in t.get_chunk(found.tx // CHUNK_SIZE, found.ty // CHUNK_SIZE).tiles
                     if tile == tiles.NEST_CORE)
    assert core_count == 1
    # region maths
    assert nests.region_of_chunk(found.tx // CHUNK_SIZE, found.ty // CHUNK_SIZE) == (found.rx, found.ry)
    assert nests.region_of_tile(-1, -1) == (-1, -1)
    assert nests.region_of_tile(NEST_REGION * CHUNK_SIZE, 0) == (1, 0)


def test_nest_registry_roundtrip():
    spec = nests.NestSpec(3, 0, 600, 40, 2)
    reg = nests.NestRegistry()
    assert reg.hp(spec) == nests.nest_max_hp(spec)
    assert not reg.hit(spec, 10)
    assert reg.hit(spec, 10 ** 9)
    assert reg.is_destroyed(3, 0)
    reg2 = nests.NestRegistry.from_dict(reg.to_dict())
    assert reg2.destroyed == {(3, 0)} and reg2.damage == {}
