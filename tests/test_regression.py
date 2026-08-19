"""Episode regression tests.

Score floors are below the last known-good local runs so a seed RNG wobble
does not fail CI, but they still catch the mathematician-style collapses
(sub-15k means, 26k fail-map, starving pizza maps).
"""

from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaggle_environments import make

# Last known-good local vs starter after berry-scale (2026-08-19):
# 2063069147 53007, 195016893 51934, 42 44448, 458695376 44717.
SCORE_FLOORS = {
    2063069147: 35000,
    195016893: 28000,
    42: 25000,
    458695376: 38000,
    827875246: 50000,
}

MEAN_SEEDS = [42, 7, 13, 21, 33, 55, 89, 99, 123, 256, 777, 1024, 2024, 3141, 993781610]
MEAN_FLOOR = 45000

SPRINT_FLOORS = {
    993781610: 50000,
    89: 40000,
    3141: 42000,
}

EXTRA_SEEDS = [
    1,
    2,
    100,
    500,
    1000,
    2025,
    9999,
    12345,
    54321,
    111111,
    1918864023,
    458695376,
    827875246,
]
EXTRA_FLOOR = 15000


def run_vs_starter(seed: int):
    agent = str(ROOT / "main.py")
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=False)
    env.run([agent, "starter"])
    return env, int(env.steps[-1][0]["reward"]), int(env.steps[-1][1]["reward"])


def crop_count(env, step_i: int, crop: str) -> int:
    me = env.steps[step_i][0]["observation"]["farms"][0]
    n = 0
    for row in me["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("crop") == crop:
                n += 1
    return n


def animal_count(env, step_i: int) -> dict[str, int]:
    me = env.steps[step_i][0]["observation"]["farms"][0]
    counts: Counter[str] = Counter()
    for row in me["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("animal"):
                counts[t["animal"]] += 1
    return dict(counts)


def land_bought_days(env) -> list[int]:
    days = []
    for i, step in enumerate(env.steps[:-1]):
        acts = (env.steps[i + 1][0].get("action") or {}).get("market") or []
        if any(a and a[0] == "BUY_LAND" for a in acts):
            days.append(step[0]["observation"]["day"])
    return days


def shop_wheat_off_hour(env) -> int:
    n = 0
    for i, step in enumerate(env.steps[:-1]):
        obs = step[0]["observation"]
        if obs["hour"] == 0:
            continue
        px = int(obs["market"]["prices"].get("WHEAT", 99))
        if px <= 12:
            continue
        acts = (env.steps[i + 1][0].get("action") or {}).get("market") or []
        for a in acts:
            if a and a[0] == "BUY_PRODUCT" and a[1] == "WHEAT":
                n += a[2]
    return n


def shops_at(env, step_i: int) -> list:
    return list(env.steps[step_i][0]["observation"].get("town", {}).get("unlocked_shops") or [])


BERRY_SHOPS = {"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"}


def berry_shop_open(env, step_i: int) -> bool:
    return any(name in BERRY_SHOPS for name in shops_at(env, step_i))


def empty_at_step(env, step_i: int) -> int:
    me = env.steps[step_i][0]["observation"]["farms"][0]
    return sum(1 for row in me["tiles"] for t in row if t is None)


def dawn_step(day: int) -> int:
    return day * 24


class KeySeedRegression(unittest.TestCase):
    def test_fail_map_stays_well_above_old_26k(self):
        env, us, _starter = run_vs_starter(2063069147)
        self.assertGreaterEqual(us, SCORE_FLOORS[2063069147], f"fail-map collapsed to {us}")
        self.assertNotIn(0, land_bought_days(env))

    def test_pizza_map_does_not_regress_to_sub_20k(self):
        env, us, _starter = run_vs_starter(195016893)
        self.assertGreaterEqual(us, SCORE_FLOORS[195016893], f"pizza/smoothie map collapsed to {us}")
        self.assertEqual(shop_wheat_off_hour(env), 0)

    def test_seed_42_floor(self):
        _env, us, starter = run_vs_starter(42)
        self.assertGreaterEqual(us, SCORE_FLOORS[42], f"seed 42 collapsed to {us}")
        self.assertGreater(us, starter)

    def test_berry_dream_map_fills_land_and_beats_floor(self):
        env, us, _starter = run_vs_starter(458695376)
        self.assertGreaterEqual(us, SCORE_FLOORS[458695376], f"berry map collapsed to {us}")
        if berry_shop_open(env, dawn_step(8)):
            berries_d12 = crop_count(env, 288, "STRAWBERRY")
            self.assertGreaterEqual(
                berries_d12,
                16,
                f"day-12 strawberries {berries_d12}; a berry shop was already open",
            )
        berries_d20 = crop_count(env, 480, "STRAWBERRY")
        me20 = env.steps[480][0]["observation"]["farms"][0]
        empty20 = sum(1 for row in me20["tiles"] for t in row if t is None)
        if berry_shop_open(env, dawn_step(8)):
            self.assertGreaterEqual(
                berries_d20,
                12,
                f"day-20 strawberries {berries_d20} died and were not replanted",
            )
        elif berry_shop_open(env, dawn_step(12)):
            self.assertGreaterEqual(
                berries_d20,
                4,
                f"day-20 strawberries {berries_d20}; berry shop opened midgame and was ignored",
            )
        self.assertLess(empty20, 30, f"day-20 empty {empty20}; extra land should not stay mostly unused")
        dawn_animals = animal_count(env, 144)
        self.assertGreaterEqual(dawn_animals.get("COW", 0), 2)
        self.assertGreaterEqual(dawn_animals.get("SHEEP", 0), 2)
        self.assertEqual(shop_wheat_off_hour(env), 0)
        self.assertNotIn(0, land_bought_days(env))


class LateBerryBakeryMap(unittest.TestCase):
    """Seed 827875246.

    Sitting on 15 empty tiles scored ~46k and also rerolled the town shop
    stream (weed RNG is mixed into shop draws). Fill leftover wheat/melon,
    never buy land on an empty wallet, and plant berries once a berry shop
    actually exists.
    """

class LandSprintRegression(unittest.TestCase):
    def test_worst_seeds_fill_boards_and_replant_berries(self):
        for seed, floor in SPRINT_FLOORS.items():
            env, us, starter = run_vs_starter(seed)
            self.assertGreaterEqual(us, floor, f"seed {seed} collapsed to {us}")
            self.assertGreater(us, starter)
            d16 = dawn_step(16)
            quads = len(env.steps[d16][0]["observation"]["farms"][0]["unlocked_quadrants"])
            if quads >= 3 and berry_shop_open(env, d16):
                empty16 = empty_at_step(env, d16)
                self.assertLessEqual(
                    empty16,
                    24,
                    f"seed {seed} day-16 empty {empty16} on {quads} quads",
                )
            if berry_shop_open(env, dawn_step(8)):
                self.assertGreaterEqual(
                    crop_count(env, dawn_step(20), "STRAWBERRY"),
                    20,
                    f"seed {seed} day-20 berry replant too low",
                )


class MeanRegression(unittest.TestCase):
    def test_fifteen_seed_mean_stays_in_40k_band(self):
        scores = []
        for seed in MEAN_SEEDS:
            _env, us, _starter = run_vs_starter(seed)
            scores.append(us)
            self.assertGreater(us, 8000, f"seed {seed} blew up to {us}")
        mean = sum(scores) / len(scores)
        self.assertGreaterEqual(
            mean,
            MEAN_FLOOR,
            f"15-seed mean {mean:.0f} dropped below {MEAN_FLOOR}; scores={scores}",
        )


class ExtraSeedBoard(unittest.TestCase):
    def test_extra_seeds_do_not_collapse(self):
        scores = []
        for seed in EXTRA_SEEDS:
            env, us, starter = run_vs_starter(seed)
            scores.append((seed, us, starter))
            self.assertGreaterEqual(us, EXTRA_FLOOR, f"seed {seed} collapsed to {us}")
            self.assertGreater(us, starter, f"seed {seed} lost to starter {us} vs {starter}")
            self.assertEqual(shop_wheat_off_hour(env), 0, f"seed {seed} bought off-hour shop wheat")
            self.assertNotIn(0, land_bought_days(env), f"seed {seed} bought land on day 0")
        print("extra-seed scores", scores)


if __name__ == "__main__":
    unittest.main()
