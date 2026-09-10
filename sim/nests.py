"""Enemy nests: a deterministic region grid (docs/PLAN.md section 3.6).

nest_at(seed, rx, ry) is PURE: the same (seed, region) always yields the same
NestSpec (or None). The generator stamps nest tiles from it; combat reads the
same function. Destruction is recorded in NestRegistry, never in terrain.

Determinism note: random.Random is seeded with a STRING, not a tuple hash.
hash(("x", 1)) is salted per process (PYTHONHASHSEED), str seeds are not.
"""
import random
from collections import namedtuple
from functools import lru_cache

from settings import (CHUNK_SIZE, NEST_REGION, SAFE_REGIONS,
                      NEST_CHANCE_PER_REGION, NEST_CHANCE_MAX)

NEST_RADIUS = 2   # footprint = (2r+1)^2 NEST_GROUND tiles with NEST_CORE centred
NEST_BASE_HP = 500

# tx, ty: world tile of the core. tier: 1 = nearest possible ring, growing outward.
NestSpec = namedtuple("NestSpec", "rx ry tx ty tier")


def region_of_chunk(cx, cy):
    return cx // NEST_REGION, cy // NEST_REGION


def region_of_tile(tx, ty):
    return tx // (NEST_REGION * CHUNK_SIZE), ty // (NEST_REGION * CHUNK_SIZE)


@lru_cache(maxsize=4096)
def nest_at(seed, rx, ry):
    """NestSpec for region (rx, ry) or None. Regions within SAFE_REGIONS
    (Chebyshev) of the origin never hold a nest."""
    dist = max(abs(rx), abs(ry))
    if dist <= SAFE_REGIONS:
        return None
    rng = random.Random(f"{seed}:{rx}:{ry}:nest")
    chance = min(NEST_CHANCE_MAX, NEST_CHANCE_PER_REGION * (dist - SAFE_REGIONS))
    if rng.random() >= chance:
        return None
    cx = rx * NEST_REGION + rng.randrange(NEST_REGION)
    cy = ry * NEST_REGION + rng.randrange(NEST_REGION)
    # keep the whole footprint inside one chunk so generation stays chunk-pure
    lx = rng.randrange(NEST_RADIUS, CHUNK_SIZE - NEST_RADIUS)
    ly = rng.randrange(NEST_RADIUS, CHUNK_SIZE - NEST_RADIUS)
    return NestSpec(rx, ry, cx * CHUNK_SIZE + lx, cy * CHUNK_SIZE + ly,
                    dist - SAFE_REGIONS)


def nest_in_chunk(seed, cx, cy):
    """The nest whose footprint lies in chunk (cx, cy), if any."""
    spec = nest_at(seed, *region_of_chunk(cx, cy))
    if spec is None:
        return None
    if (spec.tx // CHUNK_SIZE, spec.ty // CHUNK_SIZE) != (cx, cy):
        return None
    return spec


def nest_max_hp(spec):
    return NEST_BASE_HP * spec.tier


class NestRegistry:
    """Authoritative mutable nest state: which nests are destroyed / damaged.
    Saved in enemies.json; terrain files are never modified."""

    def __init__(self):
        self.destroyed = set()      # {(rx, ry)}
        self.damage = {}            # (rx, ry) -> hp lost so far

    def is_destroyed(self, rx, ry):
        return (rx, ry) in self.destroyed

    def hp(self, spec):
        return nest_max_hp(spec) - self.damage.get((spec.rx, spec.ry), 0)

    def hit(self, spec, dmg):
        """Apply damage; returns True when the nest just died."""
        key = (spec.rx, spec.ry)
        if key in self.destroyed:
            return False
        self.damage[key] = self.damage.get(key, 0) + dmg
        if self.hp(spec) <= 0:
            self.destroyed.add(key)
            self.damage.pop(key, None)
            return True
        return False

    def to_dict(self):
        return {"nests_destroyed": sorted(list(k) for k in self.destroyed),
                "nests_damaged": {f"{k[0]},{k[1]}": v
                                  for k, v in sorted(self.damage.items())}}

    @classmethod
    def from_dict(cls, d):
        reg = cls()
        for rx, ry in d.get("nests_destroyed", []):
            reg.destroyed.add((int(rx), int(ry)))
        for key, v in d.get("nests_damaged", {}).items():
            rx, ry = key.split(",")
            reg.damage[(int(rx), int(ry))] = v
        return reg
