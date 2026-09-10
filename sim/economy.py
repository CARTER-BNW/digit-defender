"""Balance helpers and hub target numbers. Targets are generated from a
string-seeded RNG keyed by (world seed, ordinal) so a world always rolls the
same sequence: no unseeded randomness inside the sim tick.
"""
import random

from settings import (COSTS, DEMOLISH_REFUND, TARGET_BASE, TARGET_GROWTH,
                      TARGET_REWARD_MULT, TARGET_REWARD_FLAT)


class Target:
    __slots__ = ("value", "reward")

    def __init__(self, value, reward):
        self.value = value
        self.reward = reward

    def to_dict(self):
        return {"value": self.value, "reward": self.reward}

    @classmethod
    def from_dict(cls, d):
        return cls(int(d["value"]), int(d["reward"]))

    def __repr__(self):
        return f"Target({self.value} -> +{self.reward})"


def target_range(n_completed):
    lo = int(TARGET_BASE * TARGET_GROWTH ** n_completed)
    return lo, lo * 3


def target_reward(value):
    return value * TARGET_REWARD_MULT + TARGET_REWARD_FLAT


def make_target(seed, ordinal, n_completed):
    rng = random.Random(f"{seed}:target:{ordinal}")
    lo, hi = target_range(n_completed)
    value = rng.randint(lo, hi)
    return Target(value, target_reward(value))


def build_cost(kind):
    return COSTS.get(kind, 0)


def demolish_refund(kind):
    return int(build_cost(kind) * DEMOLISH_REFUND)
