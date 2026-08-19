"""Policy unit tests for the Kaggriculture agent.

These lock the manure opening, feed rules, and shop-gated crop plans so
later agility tweaks cannot silently revive land-on-hour-0 or shop-wheat
groceries.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as M


def make_s(**kwargs) -> dict:
    crops = {c: 0 for c in M.SEED_COST}
    seeds = {c: 0 for c in M.SEED_COST}
    shops = list(kwargs.pop("shops", []))
    s: dict = {
        "day": 10,
        "hour": 1,
        "money": 2500,
        "n_quads": 1,
        "workers": 6,
        "hires_today": 0,
        "crops": crops,
        "empty": 15,
        "animals": {"COW": 2, "SHEEP": 2, "GOOSE": 0},
        "cows": 2,
        "geese": 0,
        "sheep": 2,
        "empty_struct": {"COOP": 0, "PASTURE": 0},
        "hungry": 0,
        "fert_ready": 0,
        "unwatered": 0,
        "at_risk": 0,
        "load": 4,
        "seeds": seeds,
        "shed": {"WHEAT": 4},
        "prices": dict(M.BASE_PRICE),
        "inventory": {},
        "scores": {c: 10.0 for c in M.SEED_COST},
        "a_scores": {a: 10.0 for a in M.ANIMAL_COST},
        "best_crop": "WHEAT",
        "shops": shops,
        "demand": M.shop_demand(shops),
        "milk_sink": 0,
        "berry_sink": 0,
    }
    s.update(kwargs)
    s["demand"] = M.shop_demand(s["shops"])
    s["milk_sink"] = sum(1 for shop in s["shops"] if shop in M.MILK_SHOPS)
    s["berry_sink"] = sum(1 for shop in s["shops"] if shop in M.BERRY_SHOPS)
    if "crops" in kwargs:
        s["crops"] = {c: 0 for c in M.SEED_COST}
        s["crops"].update(kwargs["crops"])
    if "seeds" in kwargs:
        s["seeds"] = {c: 0 for c in M.SEED_COST}
        s["seeds"].update(kwargs["seeds"])
    if "shed" in kwargs:
        s["shed"] = dict(kwargs["shed"])
    return s


class OpeningTests(unittest.TestCase):
    def test_hour_zero_is_manure_opening(self):
        s = make_s(day=0, hour=0)
        self.assertEqual(M.market_for(s, "ENGINE"), M.OPENING_MARKET)

    def test_hour_zero_does_not_buy_land(self):
        s = make_s(day=0, hour=0, money=3000)
        market = M.market_for(s, "ENGINE")
        self.assertFalse(any(a and a[0] == "BUY_LAND" for a in market))

    def test_rest_of_day_zero_skips_market(self):
        s = make_s(day=0, hour=7, money=2000)
        self.assertEqual(M.market_for(s, "ENGINE"), [])


class FeedAndWheatTests(unittest.TestCase):
    def test_shop_wheat_only_hour_zero_or_cheap(self):
        s = make_s(hour=5, cows=2, sheep=2, shed={"WHEAT": 0}, prices={**M.BASE_PRICE, "WHEAT": 40})
        market: list = []
        M._buy_feed_wheat(market, 2000, s)
        self.assertEqual(market, [])

        s["hour"] = 0
        market = []
        M._buy_feed_wheat(market, 2000, s)
        self.assertTrue(any(a[0] == "BUY_PRODUCT" and a[1] == "WHEAT" for a in market))

        s["hour"] = 5
        s["prices"]["WHEAT"] = 10
        market = []
        M._buy_feed_wheat(market, 2000, s)
        self.assertTrue(any(a[0] == "BUY_PRODUCT" and a[1] == "WHEAT" for a in market))

    def test_wheat_tiles_cover_mouths(self):
        s = make_s(cows=8, sheep=2, n_quads=2, shops=["PIZZA_SHOP"])
        _tiles, _room, wheat = M.tile_budget(s)
        self.assertGreaterEqual(wheat, M.mouths_of(s))
        self.assertGreaterEqual(wheat, 6)

    def test_no_cow_expand_when_wheat_short(self):
        s = make_s(
            n_quads=2,
            cows=2,
            sheep=2,
            shops=["PIZZA_SHOP"],
            crops={"WHEAT": 4, "STRAWBERRY": 8},
            prices={**M.BASE_PRICE, "MILK": 160},
        )
        self.assertEqual(M.want_cows(s), 2)

    def test_one_quad_does_not_expand_cows(self):
        s = make_s(
            n_quads=1,
            cows=2,
            shops=["PIZZA_SHOP", "SMOOTHIE_SHOP"],
            crops={"WHEAT": 8},
            prices={**M.BASE_PRICE, "MILK": 160},
        )
        self.assertEqual(M.want_cows(s), 2)


class CropPlanTests(unittest.TestCase):
    def test_one_quad_farmers_market_prefers_berries_over_carrots(self):
        s = make_s(day=6, n_quads=1, cows=2, sheep=2, shops=["FARMERS_MARKET"], empty=0)
        plan = M.crop_plan(s)
        self.assertGreaterEqual(plan["STRAWBERRY"], 8)
        self.assertLessEqual(plan["CARROT"], 2)

    def test_berry_cap_scales_with_land(self):
        s1 = make_s(n_quads=1, shops=["SMOOTHIE_SHOP"])
        s2 = make_s(n_quads=2, shops=["SMOOTHIE_SHOP", "FARMERS_MARKET"])
        s3 = make_s(n_quads=3, shops=["SMOOTHIE_SHOP", "FARMERS_MARKET"])
        self.assertEqual(M.berry_tile_cap(s1), 8)
        self.assertEqual(M.berry_tile_cap(s2), 28)
        self.assertEqual(M.berry_tile_cap(s3), 48)
        self.assertGreater(M.crop_plan(s2)["STRAWBERRY"], M.crop_plan(s1)["STRAWBERRY"])
        self.assertGreater(M.crop_plan(s3)["STRAWBERRY"], 16)

    def test_no_berries_without_berry_shop(self):
        s = make_s(n_quads=2, shops=["BAKERY", "YARN_STORE"])
        self.assertEqual(M.crop_plan(s)["STRAWBERRY"], 0)

    def test_pick_crop_replants_strawberry_before_melon(self):
        s = make_s(
            n_quads=2,
            shops=["FARMERS_MARKET"],
            crops={"WHEAT": 6, "STRAWBERRY": 4, "MELON": 0},
            seeds={"STRAWBERRY": 4, "MELON": 4},
            scores={"STRAWBERRY": 20.0, "MELON": 99.0, "WHEAT": 5.0, "CARROT": 1.0, "TOMATO": 1.0},
        )
        self.assertEqual(M.pick_crop(s, dict(s["seeds"])), "STRAWBERRY")

    def test_pick_crop_keeps_wheat_floor_before_cash(self):
        s = make_s(
            n_quads=1,
            cows=2,
            sheep=2,
            shops=["FARMERS_MARKET"],
            crops={"WHEAT": 2, "STRAWBERRY": 0},
            seeds={"WHEAT": 5, "STRAWBERRY": 8},
        )
        self.assertEqual(M.pick_crop(s, dict(s["seeds"])), "WHEAT")

    def test_no_tomatoes_when_berry_shop_exists(self):
        s = make_s(n_quads=2, shops=["PIZZA_SHOP", "FARMERS_MARKET"])
        self.assertEqual(M.crop_plan(s)["TOMATO"], 0)

    def test_tomatoes_ok_on_pizza_without_berries(self):
        s = make_s(n_quads=1, shops=["PIZZA_SHOP"])
        self.assertGreater(M.crop_plan(s)["TOMATO"], 0)


class CrewTests(unittest.TestCase):
    def test_day_zero_stays_five_hires(self):
        s = make_s(day=0, n_quads=1, cows=2, sheep=2)
        self.assertEqual(M.want_hands(s), 5)

    def test_two_quads_want_full_crew(self):
        s = make_s(day=8, n_quads=2, cows=2, sheep=2, shops=["FARMERS_MARKET"])
        self.assertEqual(M.want_hands(s), 12)

    def test_one_quad_with_herd_wants_eight(self):
        s = make_s(day=3, n_quads=1, cows=2, sheep=2)
        self.assertEqual(M.want_hands(s), 8)


class LandGuardTests(unittest.TestCase):
    def test_no_land_before_day_4(self):
        s = make_s(day=2, n_quads=1, empty=0, money=4000, shops=["FARMERS_MARKET"])
        self.assertFalse(M.need_land(s))

    def test_no_land_when_one_quad_still_has_empty_tiles(self):
        s = make_s(day=8, n_quads=1, empty=18, money=4000, shops=["FARMERS_MARKET"])
        self.assertFalse(M.need_land(s))


if __name__ == "__main__":
    unittest.main()
