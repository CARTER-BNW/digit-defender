"""Balance helpers and hub targets (John, 2026-09-11 design).

TARGET_COUNT slots, each with its own level. A target wants `amount`
deliveries of its `value`; when the amount is reached the bonus is paid and
the slot moves to its next level. Level 1 numbers are distinct picks from
TARGET_LEVEL1_RANGE with TARGET_BASE_AMOUNT deliveries; every level after
grows the number and the amount each by a random share in TARGET_GROWTH
(25-75%). Growth is rolled from a string-seeded RNG keyed by (world seed,
slot, level), so a world always climbs the same ladder: no unseeded
randomness inside the sim.
"""
import random

from settings import (COSTS, DEMOLISH_REFUND, TARGET_COUNT, TARGET_LEVEL1_RANGE, TARGET_BASE_AMOUNT,
                      TARGET_GROWTH, TARGET_REWARD_MULT, TARGET_REWARD_FLAT)


class Target:
    __slots__ = ("slot", "level", "value", "amount", "delivered", "reward")

    def __init__(self, slot, level, value, amount, delivered=0, reward=None):
        self.slot = slot
        self.level = level
        self.value = value
        self.amount = amount
        self.delivered = delivered
        self.reward = target_reward(value, amount) if reward is None else reward

    @property
    def done(self):
        return self.delivered >= self.amount

    def to_dict(self):
        return {"slot": self.slot, "level": self.level, "value": self.value, "amount": self.amount,
                "delivered": self.delivered, "reward": self.reward}

    @classmethod
    def from_dict(cls, d, slot=0):
        """Also reads the old {value, reward} records (as level-1 targets)."""
        return cls(int(d.get("slot", slot)), int(d.get("level", 1)), int(d["value"]),
                   int(d.get("amount", TARGET_BASE_AMOUNT)), int(d.get("delivered", 0)),
                   int(d["reward"]) if "reward" in d else None)

    def __repr__(self):
        return f"Target(slot {self.slot} Lv{self.level}: {self.amount} x {self.value} -> +{self.reward})"


def target_reward(value, amount, mult=None):
    """Bonus for delivering `amount` of `value`: 10-20x what was delivered
    (the multiplier is rolled per target; the midpoint when none is given)."""
    lo, hi = TARGET_REWARD_MULT
    if mult is None:
        mult = (lo + hi) / 2
    return int(round(value * amount * mult)) + TARGET_REWARD_FLAT


def _roll_mult(rng):
    lo, hi = TARGET_REWARD_MULT
    return rng.uniform(lo, hi)


def _grow(rng, n):
    """n grown by a random 25-75% (always at least +1)."""
    lo, hi = TARGET_GROWTH
    return max(n + 1, int(round(n * (1 + rng.uniform(lo, hi)))))


def initial_targets(seed, count=TARGET_COUNT):
    """Level-1 targets: distinct numbers from TARGET_LEVEL1_RANGE (the range
    widens upward if there are more slots than numbers)."""
    rng = random.Random(f"{seed}:targets:init")
    lo, hi = TARGET_LEVEL1_RANGE
    pool = list(range(lo, max(hi, lo + count - 1) + 1))
    values = rng.sample(pool, count)
    return [Target(i, 1, v, TARGET_BASE_AMOUNT, reward=target_reward(v, TARGET_BASE_AMOUNT, _roll_mult(rng)))
            for i, v in enumerate(values)]


def next_level(seed, target, taken=()):
    """The slot's next level: number and amount each grow by a random 25-75%;
    the number is bumped past any value another slot uses, so one delivery
    never counts for two targets."""
    rng = random.Random(f"{seed}:target:{target.slot}:{target.level + 1}")
    value = _grow(rng, target.value)
    amount = _grow(rng, target.amount)
    mult = _roll_mult(rng)
    taken = set(taken)
    while value in taken:
        value += 1
    return Target(target.slot, target.level + 1, value, amount, reward=target_reward(value, amount, mult))


def top_up(seed, targets, count=TARGET_COUNT):
    """Fill missing slots (older saves had fewer) with level-1 targets whose
    numbers avoid the ones already in play."""
    taken = {t.value for t in targets}
    for fresh in initial_targets(seed, count)[len(targets):]:
        while fresh.value in taken:
            fresh.value += 1
        fresh.reward = target_reward(fresh.value, fresh.amount)
        taken.add(fresh.value)
        targets.append(fresh)
    return targets


def build_cost(kind):
    return COSTS.get(kind, 0)


def demolish_refund(kind):
    return int(build_cost(kind) * DEMOLISH_REFUND)
