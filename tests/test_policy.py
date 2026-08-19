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

    def test_rest_of_day_zero_is_idle(self):
        s = make_s(
            day=0,
            hour=7,
            money=2000,
            shed={"FERTILIZER": 6, "WOOL": 4, "WHEAT": 0},
        )
        market = M.market_for(s, "ENGINE")
        self.assertEqual(market, [])


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

    @unittest.skip("surplus wheat sell to bakery not in P1/P2 scope")
    def test_bakery_sells_surplus_wheat(self):
        s = make_s(
            hour=5,
            cows=2,
            sheep=2,
            shops=["BAKERY"],
            shed={"WHEAT": 20, "FERTILIZER": 0, "MILK": 0, "WOOL": 0},
        )
        market: list = []
        M._sell_goods(market, s, dict(s["shed"]), max_actions=4)
        wheat_sells = [a for a in market if a[0] == "SELL" and a[1] == "WHEAT"]
        self.assertTrue(wheat_sells)
        self.assertGreater(wheat_sells[0][2], 0)

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

    @unittest.skip("herd_can_expand not in P1/P2 scope")
    def test_herd_blocked_without_wheat_buffer(self):
        s = make_s(
            n_quads=2,
            cows=4,
            sheep=2,
            shops=["PIZZA_SHOP", "SMOOTHIE_SHOP"],
            crops={"WHEAT": 5},
            shed={"WHEAT": 1},
        )
        self.assertFalse(M.herd_can_expand(s))
        self.assertEqual(M.want_cows(s), 4)

    @unittest.skip("want_geese not in P1/P2 scope")
    def test_bakery_wants_geese(self):
        s = make_s(
            n_quads=2,
            day=8,
            cows=2,
            sheep=2,
            geese=0,
            crops={"WHEAT": 8},
            shed={"WHEAT": 6},
            shops=["BAKERY"],
        )
        self.assertGreaterEqual(M.want_geese(s), 1)


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

    def test_tomatoes_capped_when_berry_and_pizza_shops(self):
        s = make_s(n_quads=2, shops=["PIZZA_SHOP", "FARMERS_MARKET"])
        plan = M.crop_plan(s)
        self.assertLessEqual(plan["TOMATO"], 4)
        self.assertGreaterEqual(plan["STRAWBERRY"], 16)

    def test_no_filler_melon_after_berry_shop_opens(self):
        s = make_s(
            day=8,
            n_quads=1,
            cows=2,
            sheep=2,
            shops=["SMOOTHIE_SHOP"],
            empty=10,
            scores={**{c: 10.0 for c in M.SEED_COST}, "MELON": 40.0, "WHEAT": 8.0},
        )
        self.assertEqual(M.crop_plan(s)["MELON"], 0)

    @unittest.skip("filler wheat/melon not in P1/P2 scope")
    def test_pizza_only_still_allows_filler_before_berries(self):
        s = make_s(
            day=5,
            n_quads=1,
            cows=2,
            sheep=2,
            shops=["PIZZA_SHOP"],
            empty=15,
            scores={**{c: 10.0 for c in M.SEED_COST}, "MELON": 40.0, "WHEAT": 8.0},
        )
        plan = M.crop_plan(s)
        self.assertGreater(plan["MELON"] + max(0, plan["WHEAT"] - 6), 0)

    def test_tomatoes_ok_on_pizza_without_berries(self):
        s = make_s(n_quads=1, shops=["PIZZA_SHOP"])
        self.assertGreater(M.crop_plan(s)["TOMATO"], 0)

    @unittest.skip("filler wheat/melon not in P1/P2 scope")
    def test_bakery_only_fills_leftover_tiles(self):
        s = make_s(
            day=5,
            n_quads=1,
            cows=2,
            sheep=2,
            shops=["BAKERY"],
            empty=15,
            scores={**{c: 10.0 for c in M.SEED_COST}, "MELON": 40.0, "WHEAT": 8.0},
        )
        plan = M.crop_plan(s)
        self.assertEqual(plan["STRAWBERRY"], 0)
        self.assertLessEqual(plan["MELON"], 4)
        self.assertGreater(plan["WHEAT"], 6)
        self.assertLess(plan["WHEAT"] + plan["MELON"], 21)

    @unittest.skip("filler wheat/melon not in P1/P2 scope")
    def test_two_quad_bakery_may_plant_melon_filler(self):
        s = make_s(
            day=5,
            n_quads=2,
            cows=2,
            sheep=2,
            shops=["BAKERY"],
            empty=20,
            scores={**{c: 10.0 for c in M.SEED_COST}, "MELON": 40.0, "WHEAT": 8.0},
        )
        self.assertGreater(M.crop_plan(s)["MELON"], 0)

    @unittest.skip("filler wheat/melon not in P1/P2 scope")
    def test_bakery_only_extra_wheat_when_melon_is_worse(self):
        s = make_s(day=5, n_quads=1, cows=2, sheep=2, shops=["BAKERY"], empty=15)
        plan = M.crop_plan(s)
        self.assertEqual(plan["STRAWBERRY"], 0)
        self.assertGreater(plan["WHEAT"], 6)

    def test_berry_maps_still_prefer_strawberries_over_filler(self):
        s = make_s(n_quads=2, shops=["FARMERS_MARKET"], cows=2, sheep=2)
        plan = M.crop_plan(s)
        self.assertGreaterEqual(plan["STRAWBERRY"], 16)
        self.assertEqual(plan["MELON"], 0)
        self.assertEqual(plan["WHEAT"], 6)

    def test_pick_crop_plants_berries_before_extra_wheat(self):
        s = make_s(
            n_quads=2,
            cows=2,
            sheep=2,
            shops=["FARMERS_MARKET"],
            crops={"WHEAT": 6, "STRAWBERRY": 4},
            seeds={"WHEAT": 8, "STRAWBERRY": 8},
        )
        self.assertEqual(M.pick_crop(s, dict(s["seeds"])), "STRAWBERRY")


class SprintAndReplantTests(unittest.TestCase):
    def test_plant_sprint_after_land_buy(self):
        M._LAND_SPRINT["until_day"] = 10
        s = make_s(day=9, n_quads=2, empty=14, shops=["FARMERS_MARKET"])
        self.assertTrue(M.plant_sprint(s))
        s2 = make_s(day=11, n_quads=2, empty=14, shops=["FARMERS_MARKET"])
        self.assertFalse(M.plant_sprint(s2))

    def test_plant_sprint_not_from_empty_tiles_alone(self):
        s = make_s(
            day=12,
            n_quads=3,
            empty=14,
            shops=["FARMERS_MARKET"],
            crops={"WHEAT": 6, "STRAWBERRY": 20},
            seeds={"STRAWBERRY": 8},
        )
        self.assertFalse(M.plant_sprint(s))

    def test_berry_replant_pick_after_plan_filled(self):
        s = make_s(
            day=18,
            n_quads=2,
            shops=["FARMERS_MARKET"],
            crops={"WHEAT": 6, "STRAWBERRY": 20, "MELON": 0},
            seeds={"STRAWBERRY": 4, "WHEAT": 4},
        )
        self.assertGreater(M.berry_gap(s), 0)
        self.assertEqual(M.pick_crop(s, dict(s["seeds"])), "STRAWBERRY")

    def test_land_prep_buys_berries_before_land(self):
        s = make_s(
            day=10,
            hour=1,
            n_quads=1,
            empty=4,
            money=4500,
            workers=6,
            hires_today=0,
            shops=["FARMERS_MARKET"],
            crops={"WHEAT": 6, "STRAWBERRY": 8},
            seeds={"STRAWBERRY": 0},
        )
        market = M.market_for(s, "ENGINE")
        land_i = next(i for i, a in enumerate(market) if a and a[0] == "BUY_LAND")
        berry_before = any(
            a and a[0] == "BUY_SEED" and a[1] == "STRAWBERRY" for a in market[:land_i]
        )
        self.assertTrue(berry_before, f"market order should seed berries before land: {market}")
        hires_before = sum(1 for a in market[:land_i] if a and a[0] == "HIRE")
        self.assertGreaterEqual(hires_before, 1)

    def test_berry_push_blocks_animals_when_gap_large(self):
        s = make_s(
            day=18,
            n_quads=2,
            cows=4,
            sheep=2,
            money=5000,
            shops=["FARMERS_MARKET"],
            crops={"WHEAT": 8, "STRAWBERRY": 4},
            seeds={"STRAWBERRY": 0},
            shed={"COW": 0, "SHEEP": 0, "GOOSE": 0},
        )
        self.assertGreaterEqual(M.berry_gap(s), 6)
        market: list = []
        M._buy_animals(market, 5000, s)
        self.assertFalse(any(a and a[0] == "BUY_ANIMAL" for a in market))


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

    @unittest.skip("8-berry land gate not in P1/P2 scope")
    def test_no_land_until_first_berry_wave_is_in(self):
        s = make_s(
            day=8,
            n_quads=1,
            empty=4,
            money=4000,
            shops=["SMOOTHIE_SHOP"],
            crops={"WHEAT": 6, "STRAWBERRY": 2},
        )
        self.assertFalse(M.need_land(s))

    def test_no_land_when_bank_cannot_cover_cost_reserve(self):
        s = make_s(
            day=8,
            hour=5,
            n_quads=1,
            empty=4,
            money=252,
            cows=2,
            sheep=2,
            shops=["SMOOTHIE_SHOP"],
            crops={"WHEAT": 6, "STRAWBERRY": 8},
        )
        market = M.market_for(s, "ENGINE")
        self.assertFalse(any(a and a[0] == "BUY_LAND" for a in market))

    @unittest.skip("low-keep berry buys before day 12 not in P1/P2 scope")
    def test_one_quad_buys_berries_when_cash_is_tight(self):
        s = make_s(
            day=6,
            hour=1,
            n_quads=1,
            money=700,
            cows=2,
            sheep=2,
            shops=["SMOOTHIE_SHOP"],
            crops={"WHEAT": 6},
            empty=15,
        )
        market = M.market_for(s, "ENGINE")
        self.assertTrue(any(a and a[0] == "BUY_SEED" and a[1] == "STRAWBERRY" for a in market))

    @unittest.skip("stricter 2-quad land gate not in P1/P2 scope")
    def test_no_third_land_while_broke_on_late_berries(self):
        s = make_s(
            day=11,
            n_quads=2,
            money=3500,
            empty=13,
            cows=2,
            sheep=2,
            shops=["BRUNCH_SPOT"],
            crops={"WHEAT": 6, "STRAWBERRY": 12},
        )
        self.assertFalse(M.need_land(s))

    def test_third_land_ok_when_berries_filled_and_cash_healthy(self):
        s = make_s(
            day=14,
            n_quads=2,
            money=6000,
            empty=5,
            cows=2,
            sheep=2,
            shops=["BRUNCH_SPOT", "FARMERS_MARKET"],
            crops={"WHEAT": 6, "STRAWBERRY": 24},
        )
        self.assertTrue(M.need_land(s))


if __name__ == "__main__":
    unittest.main()
