"""Unit tests for brain/v2 lines + budget (target agent design)."""

from __future__ import annotations

import unittest

from brain.v2.budget import build_crop_plan
from brain.v2.lines import apply_lock, lock_pair_for_shop, resolve_lock


class TestLines(unittest.TestCase):
    def test_ice_cream_slice1_pets(self):
        crop, herd = lock_pair_for_shop("ICE_CREAM_SHOP", scale_berry_opener=False)
        self.assertEqual(crop, "STRAWBERRY")
        self.assertEqual(herd, "PETS")

    def test_ice_cream_hypothesis_scale(self):
        crop, herd = lock_pair_for_shop("ICE_CREAM_SHOP", scale_berry_opener=True)
        self.assertEqual((crop, herd), ("STRAWBERRY", "SCALE"))

    def test_pizza_scale(self):
        self.assertEqual(
            lock_pair_for_shop("PIZZA_SHOP"),
            ("TOMATO", "SCALE"),
        )

    def test_pet_cafe_no_lock(self):
        self.assertIsNone(lock_pair_for_shop("PET_CAFE"))

    def test_same_day_ice_cream_beats_pizza(self):
        crop, herd, shop = resolve_lock(
            ["ICE_CREAM_SHOP", "PIZZA_SHOP"],
            first_berry_day=3,
            first_milk_day=3,
            first_pizza_day=3,
            scale_berry_opener=False,
        )
        self.assertEqual(crop, "STRAWBERRY")
        self.assertEqual(herd, "PETS")
        self.assertEqual(shop, "ICE_CREAM_SHOP")

    def test_pizza_before_berry(self):
        crop, herd, shop = resolve_lock(
            ["PIZZA_SHOP", "SMOOTHIE_SHOP"],
            first_berry_day=9,
            first_milk_day=4,
            first_pizza_day=4,
            scale_berry_opener=False,
        )
        self.assertEqual((crop, herd, shop), ("TOMATO", "SCALE", "PIZZA_SHOP"))

    def test_bakery_only(self):
        crop, herd, shop = resolve_lock(
            ["BAKERY", "BAKERY"],
            first_berry_day=None,
            first_milk_day=None,
            first_bakery_day=2,
        )
        self.assertEqual((crop, herd), ("FEED", "PETS"))

    def test_lock_once_tomato_hard(self):
        state: dict = {}
        apply_lock(
            state,
            ["PIZZA_SHOP"],
            first_pizza_day=4,
            first_berry_day=None,
            first_milk_day=4,
        )
        self.assertEqual(state["crop_line"], "TOMATO")
        apply_lock(
            state,
            ["PIZZA_SHOP", "SMOOTHIE_SHOP"],
            first_pizza_day=4,
            first_berry_day=9,
            first_milk_day=4,
        )
        self.assertEqual(state["crop_line"], "TOMATO")
        self.assertEqual(state["herd_line"], "SCALE")

    def test_feed_upgrades_to_strawberry_pets(self):
        state: dict = {}
        apply_lock(
            state,
            ["BAKERY"],
            first_bakery_day=2,
            first_berry_day=None,
            first_milk_day=None,
        )
        self.assertEqual(state["crop_line"], "FEED")
        apply_lock(
            state,
            ["BAKERY", "SMOOTHIE_SHOP"],
            first_bakery_day=2,
            first_berry_day=9,
            first_milk_day=9,
        )
        self.assertEqual(state["crop_line"], "STRAWBERRY")
        self.assertEqual(state["herd_line"], "PETS")

    def test_feed_upgrades_to_tomato_scale(self):
        state: dict = {}
        apply_lock(
            state,
            ["BAKERY"],
            first_bakery_day=2,
            first_berry_day=None,
            first_milk_day=None,
        )
        apply_lock(
            state,
            ["BAKERY", "PIZZA_SHOP"],
            first_bakery_day=2,
            first_berry_day=None,
            first_milk_day=8,
            first_pizza_day=8,
        )
        self.assertEqual(state["crop_line"], "TOMATO")
        self.assertEqual(state["herd_line"], "SCALE")


class TestBudget(unittest.TestCase):
    def test_open_wheat_fills_board(self):
        s = {
            "crop_line": "OPEN",
            "herd_line": "PETS",
            "n_quads": 1,
            "cows": 2,
            "sheep": 2,
            "geese": 0,
            "demand": {},
        }
        plan = build_crop_plan(s)
        self.assertEqual(plan["STRAWBERRY"], 0)
        self.assertEqual(plan["TOMATO"], 0)
        # mouths=4, wheat_min=6 → fill leftover to full board (bakery bait).
        self.assertEqual(plan["WHEAT"], 25)

    def test_feed_fills_leftover_wheat(self):
        s = {
            "crop_line": "FEED",
            "herd_line": "PETS",
            "n_quads": 1,
            "cows": 2,
            "sheep": 2,
            "geese": 0,
            "demand": {},
        }
        plan = build_crop_plan(s)
        self.assertEqual(plan["WHEAT"], 25)

    def test_strawberry_glut_holds_not_expands(self):
        s = {
            "crop_line": "STRAWBERRY",
            "herd_line": "PETS",
            "n_quads": 2,
            "cows": 2,
            "sheep": 2,
            "geese": 0,
            "demand": {"STRAWBERRY": 1},
            "crops": {"STRAWBERRY": 10},
            "seeds": {"STRAWBERRY": 2},
            "strawberry_ok": False,
        }
        plan = build_crop_plan(s, wheat_override=6)
        self.assertEqual(plan["STRAWBERRY"], 12)
        self.assertEqual(plan["WHEAT"], 6)

    def test_strawberry_leftover_empty(self):
        s = {
            "crop_line": "STRAWBERRY",
            "herd_line": "PETS",
            "n_quads": 2,
            "cows": 2,
            "sheep": 2,
            "geese": 0,
            "demand": {"STRAWBERRY": 1},
        }
        plan = build_crop_plan(s, wheat_override=6)
        self.assertEqual(plan["STRAWBERRY"], 28)
        self.assertEqual(plan["WHEAT"], 6)
        # 50 - 6 - 28 = 16 empty (not forced into wheat)
        self.assertEqual(plan["WHEAT"] + plan["STRAWBERRY"], 34)

    def test_tomato_scale_wheat_ahead(self):
        s = {
            "crop_line": "TOMATO",
            "herd_line": "SCALE",
            "n_quads": 2,
            "cows": 4,
            "sheep": 2,
            "geese": 0,
            "demand": {"TOMATO": 2},
        }
        plan = build_crop_plan(s)
        mouths = 6
        self.assertGreaterEqual(plan["WHEAT"], mouths + 2)
        self.assertGreater(plan["TOMATO"], 0)

    def test_tomato_reserves_late_berry_garnish(self):
        s = {
            "crop_line": "TOMATO",
            "herd_line": "SCALE",
            "n_quads": 2,
            "cows": 4,
            "sheep": 2,
            "geese": 0,
            "demand": {"TOMATO": 2, "STRAWBERRY": 1, "CARROT": 1},
            "strawberry_ok": True,
            "tomato_ok": True,
            "prices": {"STRAWBERRY": 200, "TOMATO": 70},
            "crops": {},
            "seeds": {},
        }
        plan = build_crop_plan(s, wheat_override=10)
        self.assertEqual(plan["STRAWBERRY"], 8)
        self.assertGreaterEqual(plan["TOMATO"], 16)
        self.assertLessEqual(plan["TOMATO"] + plan["STRAWBERRY"] + plan["WHEAT"], 50)

    def test_tomato_holds_berries_when_ev_gates(self):
        s = {
            "crop_line": "TOMATO",
            "herd_line": "SCALE",
            "n_quads": 2,
            "cows": 4,
            "sheep": 2,
            "geese": 0,
            "demand": {"TOMATO": 1, "STRAWBERRY": 1},
            "strawberry_ok": False,
            "tomato_ok": True,
            "prices": {"STRAWBERRY": 190, "TOMATO": 64},
            "crops": {"STRAWBERRY": 6},
            "seeds": {"STRAWBERRY": 2},
        }
        plan = build_crop_plan(s, wheat_override=10)
        self.assertEqual(plan["STRAWBERRY"], 8)


if __name__ == "__main__":
    unittest.main()
