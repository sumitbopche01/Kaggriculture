"""Tests for map archetype classification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain.map import classify_archetype


class MapArchetypeTests(unittest.TestCase):
    def test_early_berry_by_first_shop_day(self):
        track = {"first_berry_day": 3}
        s = {"day": 8, "shops": ["SMOOTHIE_SHOP"]}
        params = {
            "map_early_berry_day_max": 8,
            "map_late_berry_day_min": 12,
            "land2_empty_max": 4,
            "late_ramp_land_empty_max": 24,
        }
        self.assertEqual(
            classify_archetype(
                s,
                track,
                params,
                berry_shops=frozenset({"SMOOTHIE_SHOP", "BRUNCH_SPOT"}),
                milk_shops=frozenset({"PIZZA_SHOP"}),
            ),
            "EARLY_BERRY",
        )

    def test_late_berry_bakery_before_berries(self):
        track = {"first_berry_day": None}
        s = {"day": 8, "shops": ["BAKERY"]}
        params = {
            "map_early_berry_day_max": 8,
            "map_late_berry_day_min": 12,
            "land2_empty_max": 4,
            "late_ramp_land_empty_max": 24,
        }
        self.assertEqual(
            classify_archetype(
                s,
                track,
                params,
                berry_shops=frozenset({"SMOOTHIE_SHOP"}),
                milk_shops=frozenset({"PIZZA_SHOP"}),
            ),
            "LATE_BERRY",
        )

    def test_milk_stack_two_milk_shops(self):
        track = {"first_berry_day": 10}
        s = {"day": 8, "shops": ["PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"]}
        params = {
            "map_early_berry_day_max": 8,
            "map_late_berry_day_min": 12,
            "land2_empty_max": 4,
            "late_ramp_land_empty_max": 24,
        }
        self.assertEqual(
            classify_archetype(
                s,
                track,
                params,
                berry_shops=frozenset({"SMOOTHIE_SHOP"}),
                milk_shops=frozenset({"PIZZA_SHOP", "ICE_CREAM_SHOP"}),
            ),
            "MILK_STACK",
        )


if __name__ == "__main__":
    unittest.main()
