"""Shop-sink playbooks — tomatoes/carrots/milk get the berry loop."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as M
from brain.playbook import (
    ENGINE_REPLANT_DAY_MAX,
    berry_opened_first,
    cow_target,
    crop_is_replanting,
    map_engine,
    primary_cash_crop,
    skip_berry_prep_for_sinks,
)
from tests.test_policy import make_s


class PrimaryCropTests(unittest.TestCase):
    def test_berries_win_when_farmers_market_and_pizza_both_open(self):
        s = make_s(n_quads=2, shops=["PIZZA_SHOP", "FARMERS_MARKET"])
        self.assertEqual(M._primary_cash(s), "STRAWBERRY")
        plan = M.crop_plan(s)
        self.assertEqual(plan["TOMATO"], 0)
        self.assertGreaterEqual(plan["STRAWBERRY"], 16)

    def test_pizza_only_makes_tomato_primary_with_raised_cap(self):
        s = make_s(n_quads=2, shops=["PIZZA_SHOP", "PIZZA_SHOP", "PIZZA_SHOP"])
        self.assertEqual(M._primary_cash(s), "TOMATO")
        self.assertGreaterEqual(M.crop_plan(s)["TOMATO"], 16)
        self.assertEqual(M.crop_plan(s)["STRAWBERRY"], 0)

    def test_two_pizza_keeps_tomato_after_smoothie(self):
        s = make_s(
            n_quads=2,
            shops=["PIZZA_SHOP", "PIZZA_SHOP", "SMOOTHIE_SHOP"],
            first_berry_day=10,
            first_milk_day=3,
        )
        self.assertEqual(M._primary_cash(s), "TOMATO")
        self.assertGreaterEqual(M.crop_plan(s)["TOMATO"], 16)

    def test_ice_cream_then_pizza_stays_strawberry(self):
        s = make_s(
            n_quads=2,
            shops=["ICE_CREAM_SHOP", "PIZZA_SHOP"],
            first_berry_day=3,
            first_milk_day=3,
        )
        self.assertEqual(M._primary_cash(s), "STRAWBERRY")
        self.assertGreaterEqual(M.crop_plan(s)["STRAWBERRY"], 16)
        self.assertEqual(M.crop_plan(s)["TOMATO"], 0)

    def test_pet_cafe_makes_carrot_primary(self):
        s = make_s(n_quads=2, shops=["PET_CAFE"])
        self.assertEqual(M._primary_cash(s), "CARROT")
        plan = M.crop_plan(s)
        self.assertGreater(plan["CARROT"], 0)
        self.assertLessEqual(plan["CARROT"], 12)


class TomatoRampTests(unittest.TestCase):
    def test_tomato_ramps_on_pizza_midgame(self):
        s = make_s(
            day=8,
            n_quads=2,
            empty=12,
            shops=["PIZZA_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 6, "TOMATO": 4},
            seeds={"TOMATO": 0},
        )
        self.assertTrue(M.cash_ramp(s))
        self.assertFalse(M.berry_ramp(s))

    def test_berry_prep_skips_pizza_stack(self):
        s = make_s(
            day=11,
            n_quads=1,
            empty=10,
            money=4000,
            shops=["PIZZA_SHOP", "PIZZA_SHOP"],
        )
        self.assertTrue(skip_berry_prep_for_sinks(s))
        self.assertFalse(M.berry_prep_active(s))


class MilkHerdTests(unittest.TestCase):
    def test_cow_target_scales_with_pizza_stack(self):
        s = make_s(
            day=10,
            n_quads=2,
            cows=2,
            sheep=2,
            shops=["PIZZA_SHOP"] * 6,
            crops={"WHEAT": 8},
            prices={**M.BASE_PRICE, "MILK": 160},
        )
        self.assertGreaterEqual(cow_target(s, M.PARAMS), 8)
        self.assertGreater(M.want_cows(s), s["cows"])

    def test_ice_cream_then_pizza_keeps_cow_floor(self):
        s = make_s(
            day=10,
            n_quads=2,
            cows=2,
            sheep=2,
            shops=["ICE_CREAM_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 8},
            shed={"WHEAT": 4},
            prices={**M.BASE_PRICE, "MILK": 160},
            first_berry_day=3,
            first_milk_day=3,
        )
        self.assertEqual(M.current_engine(s), "BERRY")
        self.assertEqual(cow_target(s, M.PARAMS), 2)
        self.assertEqual(M.want_cows(s), 2)

    def test_pizza_then_ice_cream_still_scales_cows(self):
        s = make_s(
            day=10,
            n_quads=2,
            cows=2,
            sheep=2,
            shops=["ICE_CREAM_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 8},
            shed={"WHEAT": 4},
            prices={**M.BASE_PRICE, "MILK": 160},
            first_berry_day=10,
            first_milk_day=3,
        )
        self.assertEqual(M.current_engine(s), "MILK")
        self.assertEqual(cow_target(s, M.PARAMS), 6)
        self.assertEqual(M.want_cows(s), 3)

    def test_brunch_smoothie_does_not_ramp_cows(self):
        s = make_s(
            day=16,
            n_quads=2,
            cows=2,
            sheep=2,
            shops=["BAKERY", "BAKERY", "BRUNCH_SPOT", "SMOOTHIE_SHOP"],
            crops={"WHEAT": 8},
            shed={"WHEAT": 4},
            prices={**M.BASE_PRICE, "MILK": 160},
            first_berry_day=6,
            first_milk_day=15,
        )
        self.assertEqual(M.current_engine(s), "BERRY")
        self.assertEqual(cow_target(s, M.PARAMS), 2)
        self.assertEqual(M.want_cows(s), 2)

    def test_milk_engine_market_fronts_cows(self):
        s = make_s(
            day=10,
            hour=0,
            n_quads=2,
            money=8000,
            empty=8,
            cows=2,
            sheep=2,
            shops=["PIZZA_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 8, "TOMATO": 8},
            shed={"WHEAT": 6},
            prices={**M.BASE_PRICE, "MILK": 160},
            first_milk_day=3,
            first_berry_day=None,
        )
        market = M.market_for(s, "ENGINE")
        self.assertTrue(
            any(a and a[0] == "BUY_ANIMAL" and a[1] == "COW" for a in market)
        )

    def test_berry_engine_market_does_not_front_cows(self):
        s = make_s(
            day=10,
            hour=0,
            n_quads=2,
            money=8000,
            empty=8,
            cows=2,
            sheep=2,
            shops=["ICE_CREAM_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 8, "STRAWBERRY": 8},
            shed={"WHEAT": 6},
            prices={**M.BASE_PRICE, "MILK": 160},
            first_berry_day=3,
            first_milk_day=3,
        )
        market = M.market_for(s, "ENGINE")
        self.assertFalse(
            any(a and a[0] == "BUY_ANIMAL" and a[1] == "COW" for a in market)
        )

    def test_berry_engine_keeps_seed_reserve_despite_milk_shop(self):
        """Ice cream is BERRY. Do not shrink the animal cash reserve to 200."""
        s = make_s(
            day=10,
            hour=0,
            n_quads=2,
            money=1200,
            empty=8,
            cows=2,
            sheep=2,
            shops=["ICE_CREAM_SHOP", "YARN_STORE"],
            crops={"WHEAT": 8, "STRAWBERRY": 10},
            seeds={"STRAWBERRY": 0},
            shed={"WHEAT": 6},
            prices={**M.BASE_PRICE, "MILK": 160, "WOOL": 220},
            first_berry_day=3,
            first_milk_day=3,
        )
        self.assertEqual(M.current_engine(s), "BERRY")
        market: list = []
        M._buy_animals(market, 1200, s)
        self.assertFalse(any(a and a[0] == "BUY_ANIMAL" for a in market))

    def test_ice_cream_pizza_does_not_trip_milk_spike(self):
        s = make_s(
            day=10,
            n_quads=2,
            shops=["ICE_CREAM_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 6, "STRAWBERRY": 8},
            first_berry_day=3,
            first_milk_day=3,
        )
        M.detect_regime(s)
        self.assertEqual(s["regime"]["phase"], "ENGINE")
        self.assertFalse(s["regime"]["demand_stack"])

    def test_two_bakeries_do_not_trip_spike_phase(self):
        s = make_s(
            day=10,
            n_quads=2,
            shops=["BAKERY", "BAKERY"],
            crops={"WHEAT": 8},
        )
        M.detect_regime(s)
        self.assertTrue(s["regime"]["demand_stack"])
        self.assertEqual(s["regime"]["phase"], "ENGINE")

    def test_two_berry_shops_do_not_trip_spike_phase(self):
        s = make_s(
            day=10,
            n_quads=2,
            shops=["SMOOTHIE_SHOP", "BRUNCH_SPOT"],
            crops={"WHEAT": 6, "STRAWBERRY": 8},
        )
        M.detect_regime(s)
        self.assertTrue(s["regime"]["demand_stack"])
        self.assertEqual(s["regime"]["phase"], "ENGINE")

    def test_pizza_stack_does_not_buy_third_land(self):
        s = make_s(
            day=14,
            n_quads=2,
            money=6000,
            empty=4,
            shops=["PIZZA_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 8, "TOMATO": 20},
        )
        self.assertGreaterEqual(M.milk_sink(s), 2)
        self.assertFalse(M.need_land(s))

    def test_full_berry_board_buys_third_land(self):
        s = make_s(
            day=14,
            n_quads=2,
            money=8000,
            empty=2,
            shops=["ICE_CREAM_SHOP", "FARMERS_MARKET", "SMOOTHIE_SHOP"],
            crops={"WHEAT": 8, "STRAWBERRY": 30},
            first_berry_day=3,
            first_milk_day=3,
        )
        self.assertEqual(M.map_strategy(s), "EARLY_BERRY")
        self.assertTrue(M.need_land(s))


class MapEngineTests(unittest.TestCase):
    def test_two_bakeries_are_egg_engine(self):
        self.assertEqual(
            map_engine(milk_n=0, egg_n=2, first_berry_day=None, first_milk_day=None),
            "EGG",
        )

    def test_brunch_then_smoothie_stays_berry_engine(self):
        self.assertEqual(
            map_engine(milk_n=1, egg_n=2, first_berry_day=6, first_milk_day=15),
            "BERRY",
        )

    def test_pizza_before_berries_is_milk_engine(self):
        self.assertEqual(
            map_engine(milk_n=1, egg_n=0, first_berry_day=6, first_milk_day=3),
            "MILK",
        )

    def test_ice_cream_same_day_is_berry_engine(self):
        self.assertEqual(
            map_engine(milk_n=2, egg_n=0, first_berry_day=3, first_milk_day=3),
            "BERRY",
        )

    def test_bakery_stack_drops_wheat_ahead_after_engine_day(self):
        s = make_s(
            day=25,
            n_quads=2,
            cows=4,
            sheep=2,
            shops=["BAKERY", "BAKERY"],
            crops={"WHEAT": 10},
        )
        self.assertEqual(M.current_engine(s), "EGG")
        _tiles, _room, wheat = M.tile_budget(s)
        self.assertEqual(wheat, max(int(M.PARAMS["wheat_min_tiles"]), M.mouths_of(s)))

    def test_pizza_stack_keeps_wheat_ahead_after_engine_day(self):
        s = make_s(
            day=25,
            n_quads=2,
            cows=4,
            sheep=2,
            shops=["PIZZA_SHOP", "PIZZA_SHOP"],
            crops={"WHEAT": 10},
            first_milk_day=3,
            first_berry_day=None,
        )
        self.assertEqual(M.current_engine(s), "MILK")
        _tiles, _room, wheat = M.tile_budget(s)
        self.assertEqual(
            wheat,
            max(
                int(M.PARAMS["wheat_min_tiles"]),
                M.mouths_of(s) + int(M.PARAMS["wheat_buffer_add"]),
            ),
        )


class PrimaryHelperTests(unittest.TestCase):
    def test_primary_cash_crop_prefers_berries(self):
        self.assertEqual(
            primary_cash_crop(
                {"STRAWBERRY": 1, "TOMATO": 3},
                viable={"STRAWBERRY": True, "TOMATO": True, "CARROT": False},
            ),
            "STRAWBERRY",
        )
        self.assertEqual(
            primary_cash_crop(
                {"STRAWBERRY": 1, "TOMATO": 3},
                viable={"STRAWBERRY": True, "TOMATO": True, "CARROT": False},
                milk_n=2,
            ),
            "TOMATO",
        )
        self.assertEqual(
            primary_cash_crop(
                {"STRAWBERRY": 1, "TOMATO": 3},
                viable={"STRAWBERRY": True, "TOMATO": True, "CARROT": False},
                milk_n=2,
                first_berry_day=3,
                first_milk_day=3,
            ),
            "STRAWBERRY",
        )
        self.assertEqual(
            primary_cash_crop(
                {"STRAWBERRY": 1, "CARROT": 2},
                viable={"STRAWBERRY": False, "TOMATO": False, "CARROT": True},
                first_berry_day=3,
                first_milk_day=3,
            ),
            "STRAWBERRY",
        )
        self.assertTrue(berry_opened_first(3, 3))
        self.assertFalse(berry_opened_first(10, 3))
        self.assertEqual(
            primary_cash_crop(
                {"STRAWBERRY": 2, "TOMATO": 2},
                viable={"STRAWBERRY": True, "TOMATO": True, "CARROT": False},
                milk_n=2,
                first_berry_day=12,
                first_milk_day=3,
            ),
            "STRAWBERRY",
        )
        self.assertEqual(
            primary_cash_crop(
                {"TOMATO": 2},
                viable={"STRAWBERRY": False, "TOMATO": True, "CARROT": False},
            ),
            "TOMATO",
        )

    def test_ice_cream_stack_garnish_cows_after_berries_fill(self):
        s = make_s(
            day=12,
            n_quads=2,
            cows=2,
            sheep=2,
            empty=8,
            shops=["ICE_CREAM_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"],
            crops={"WHEAT": 8, "STRAWBERRY": 20},
            shed={"WHEAT": 4},
            prices={**M.BASE_PRICE, "MILK": 250},
            first_berry_day=3,
            first_milk_day=3,
        )
        self.assertEqual(M.current_engine(s), "BERRY")
        self.assertEqual(cow_target(s, M.PARAMS), 6)
        self.assertEqual(M.want_cows(s), 3)

    def test_crop_plan_keeps_engine_strawberry_when_late_ev_zero(self):
        s = make_s(
            day=22,
            n_quads=2,
            empty=2,
            shops=["ICE_CREAM_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"],
            crops={"WHEAT": 6, "STRAWBERRY": 32},
            seeds={"STRAWBERRY": 7},
            first_berry_day=3,
            first_milk_day=3,
            prices={**M.BASE_PRICE, "STRAWBERRY": 243},
        )
        s["scores"]["STRAWBERRY"] = M.crop_score(
            "STRAWBERRY", 243, 22, s["demand"]
        )
        M.refresh_planning_scores(s)
        self.assertEqual(s["scores"]["STRAWBERRY"], 0.0)
        self.assertFalse(M.plan_viable(s, "STRAWBERRY"))
        self.assertTrue(M._hold_engine_crop(s, "STRAWBERRY"))
        self.assertGreater(M.crop_plan(s)["STRAWBERRY"], 0)

    def test_crop_plan_does_not_expand_strawberry_into_glut(self):
        s = make_s(
            n_quads=2,
            shops=["ICE_CREAM_SHOP"],
            first_berry_day=3,
            first_milk_day=3,
            inventory={"STRAWBERRY": 20000},
        )
        self.assertFalse(M.plan_viable(s, "STRAWBERRY"))
        self.assertEqual(M._primary_cash(s), "STRAWBERRY")
        self.assertEqual(M.crop_plan(s)["STRAWBERRY"], 0)

    def test_crop_is_replanting_through_endgame_not_liquidate(self):
        plan = {"STRAWBERRY": 28}
        s27 = make_s(
            day=ENGINE_REPLANT_DAY_MAX,
            n_quads=2,
            empty=12,
            shops=["ICE_CREAM_SHOP"],
            first_berry_day=3,
            first_milk_day=3,
            crops={"STRAWBERRY": 10},
            seeds={"STRAWBERRY": 0},
        )
        s28 = make_s(
            day=ENGINE_REPLANT_DAY_MAX + 1,
            n_quads=2,
            empty=12,
            shops=["ICE_CREAM_SHOP"],
            first_berry_day=3,
            first_milk_day=3,
            crops={"STRAWBERRY": 10},
            seeds={"STRAWBERRY": 0},
        )
        self.assertTrue(crop_is_replanting(s27, "STRAWBERRY", plan, late=False))
        self.assertFalse(crop_is_replanting(s28, "STRAWBERRY", plan, late=False))
        self.assertTrue(crop_is_replanting(s27, "STRAWBERRY", plan, late=True))
        self.assertFalse(crop_is_replanting(s28, "STRAWBERRY", plan, late=True))
        self.assertEqual(
            primary_cash_crop(
                {"TOMATO": 2},
                viable={"STRAWBERRY": False, "TOMATO": True, "CARROT": False},
            ),
            "TOMATO",
        )


if __name__ == "__main__":
    unittest.main()
