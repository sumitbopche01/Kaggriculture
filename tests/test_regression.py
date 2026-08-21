"""Episode regression tests.

Floors track the current ~80k densify band so CI catches real regressions,
not only mathematician-style sub-15k collapses.
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

from tune.evaluate import (
    HOLDOUT_SEEDS,
    MEAN_SEEDS_15,
    MEAN_SEEDS_30,
    dawn_step,
    path_metrics_from_env,
)

# Keep in sync with recent healthy local runs (~85k densify mean15).
SCORE_FLOORS = {
    2063069147: 45000,
    195016893: 40000,
    42: 78000,
    89: 85000,
    7: 75000,
    55: 75000,
    458695376: 50000,
    827875246: 55000,
    1827862996: 65000,
}

MEAN_SEEDS = list(MEAN_SEEDS_15)
MEAN_FLOOR = 78000
MEAN30_FLOOR = 72000

SPRINT_FLOORS = {
    993781610: 70000,
    89: 85000,
    3141: 65000,
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
EXTRA_FLOOR = 50000

HOLDOUT_FLOOR = 60000


def run_vs_starter(seed: int):
    agent = str(ROOT / "main.py")
    env = make(
        "kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=False
    )
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
    return list(
        env.steps[step_i][0]["observation"].get("town", {}).get("unlocked_shops") or []
    )


BERRY_SHOPS = {"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"}


def berry_shop_open(env, step_i: int) -> bool:
    return any(name in BERRY_SHOPS for name in shops_at(env, step_i))


def empty_at_step(env, step_i: int) -> int:
    me = env.steps[step_i][0]["observation"]["farms"][0]
    return sum(1 for row in me["tiles"] for t in row if t is None)


class KeySeedRegression(unittest.TestCase):
    def test_fail_map_stays_well_above_old_26k(self):
        env, us, _starter = run_vs_starter(2063069147)
        self.assertGreaterEqual(
            us, SCORE_FLOORS[2063069147], f"fail-map collapsed to {us}"
        )
        self.assertNotIn(0, land_bought_days(env))

    def test_pizza_map_does_not_regress_to_sub_20k(self):
        env, us, _starter = run_vs_starter(195016893)
        self.assertGreaterEqual(
            us, SCORE_FLOORS[195016893], f"pizza/smoothie map collapsed to {us}"
        )
        self.assertEqual(shop_wheat_off_hour(env), 0)

    def test_seed_42_floor(self):
        _env, us, starter = run_vs_starter(42)
        self.assertGreaterEqual(us, SCORE_FLOORS[42], f"seed 42 collapsed to {us}")
        self.assertGreater(us, starter)

    def test_seed_89_densify_floor(self):
        _env, us, starter = run_vs_starter(89)
        self.assertGreaterEqual(us, SCORE_FLOORS[89], f"seed 89 collapsed to {us}")
        self.assertGreater(us, starter)

    def test_holdout_1827862996_floor(self):
        env, us, starter = run_vs_starter(1827862996)
        self.assertGreaterEqual(
            us, SCORE_FLOORS[1827862996], f"holdout collapsed to {us}"
        )
        self.assertGreater(us, starter)
        path = path_metrics_from_env(env, 1827862996, us, starter)
        self.assertGreaterEqual(path.cows_d10, 2)

    def test_berry_dream_map_fills_land_and_beats_floor(self):
        env, us, _starter = run_vs_starter(458695376)
        self.assertGreaterEqual(
            us, SCORE_FLOORS[458695376], f"berry map collapsed to {us}"
        )
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
        self.assertLess(
            empty20, 30, f"day-20 empty {empty20}; extra land should not stay mostly unused"
        )
        dawn_animals = animal_count(env, 144)
        self.assertGreaterEqual(dawn_animals.get("COW", 0), 2)
        self.assertGreaterEqual(dawn_animals.get("SHEEP", 0), 2)
        self.assertEqual(shop_wheat_off_hour(env), 0)
        self.assertNotIn(0, land_bought_days(env))


class LandSprintRegression(unittest.TestCase):
    def test_worst_seeds_fill_boards_and_replant_berries(self):
        for seed, floor in SPRINT_FLOORS.items():
            env, us, starter = run_vs_starter(seed)
            self.assertGreaterEqual(us, floor, f"seed {seed} collapsed to {us}")
            self.assertGreater(us, starter)
            d16 = dawn_step(16)
            quads = len(
                env.steps[d16][0]["observation"]["farms"][0]["unlocked_quadrants"]
            )
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
    def test_fifteen_seed_densify_mean_stays_in_80k_band(self):
        scores = []
        for seed in MEAN_SEEDS:
            _env, us, _starter = run_vs_starter(seed)
            scores.append(us)
            self.assertGreater(us, 40000, f"seed {seed} blew up to {us}")
        mean = sum(scores) / len(scores)
        self.assertGreaterEqual(
            mean,
            MEAN_FLOOR,
            f"15-seed densify mean {mean:.0f} dropped below {MEAN_FLOOR}; scores={scores}",
        )

    def test_mean30_diverse_panel_floor(self):
        self.assertEqual(len(MEAN_SEEDS_30), 30)
        self.assertEqual(len(set(MEAN_SEEDS_30)), 30)
        self.assertTrue(set(MEAN_SEEDS_15).issubset(set(MEAN_SEEDS_30)))
        scores = []
        for seed in MEAN_SEEDS_30:
            _env, us, _starter = run_vs_starter(seed)
            scores.append(us)
            self.assertGreater(us, 25000, f"mean30 seed {seed} collapsed to {us}")
        mean = sum(scores) / len(scores)
        self.assertGreaterEqual(
            mean,
            MEAN30_FLOOR,
            f"mean30 {mean:.0f} dropped below {MEAN30_FLOOR}; scores={scores}",
        )


class HoldoutRegression(unittest.TestCase):
    def test_holdout_panel_mean_floor(self):
        holdout = [s for s in HOLDOUT_SEEDS if s not in MEAN_SEEDS_30][:8]
        scores = []
        for seed in holdout:
            _env, us, _starter = run_vs_starter(seed)
            scores.append(us)
            self.assertGreater(us, 25000, f"holdout seed {seed} collapsed to {us}")
        mean = sum(scores) / len(scores)
        self.assertGreaterEqual(
            mean,
            HOLDOUT_FLOOR,
            f"holdout mean {mean:.0f} dropped below {HOLDOUT_FLOOR}; scores={scores}",
        )


class ExtraSeedBoard(unittest.TestCase):
    def test_extra_seeds_do_not_collapse(self):
        scores = []
        for seed in EXTRA_SEEDS:
            env, us, starter = run_vs_starter(seed)
            scores.append((seed, us, starter))
            self.assertGreaterEqual(
                us, EXTRA_FLOOR, f"seed {seed} collapsed to {us}"
            )
            self.assertGreater(
                us, starter, f"seed {seed} lost to starter {us} vs {starter}"
            )
            self.assertEqual(
                shop_wheat_off_hour(env), 0, f"seed {seed} bought off-hour shop wheat"
            )
            self.assertNotIn(
                0, land_bought_days(env), f"seed {seed} bought land on day 0"
            )
        print("extra-seed scores", scores)


if __name__ == "__main__":
    unittest.main()
