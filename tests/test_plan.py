"""Tests for unified turn planning (brain/plan.py)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as M
from brain.plan import TurnFlags, phase_profile, resolve_market_route


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
        "seeds": seeds,
        "shed": {},
        "shops": shops,
        "demand": M.shop_demand(shops),
        "prices": dict(M.BASE_PRICE),
        "price_ma": {},
        "delta": {},
        "hungry": 0,
        "fert_ready": 0,
        "unwatered": 0,
        "at_risk": 0,
        "load": 0,
        "scores": {},
        "a_scores": {},
        "best_crop": None,
        "berry_sink": sum(1 for sh in shops if sh in M.BERRY_SHOPS),
        "milk_sink": sum(1 for sh in shops if sh in M.MILK_SHOPS),
    }
    s["crops"].update(kwargs.pop("crops", {}))
    s["seeds"].update(kwargs.pop("seeds", {}))
    s["shed"].update(kwargs.pop("shed", {}))
    s.update(kwargs)
    M.refresh_planning_scores(s)
    return s


class TurnPlanTests(unittest.TestCase):
    def test_plan_turn_sets_regime_and_crops(self):
        s = make_s(day=10, shops=["FARMERS_MARKET"], crops={"WHEAT": 6, "STRAWBERRY": 8})
        tp = M.plan_turn(s)
        self.assertIs(s["turn_plan"], tp)
        self.assertEqual(s["regime"]["phase"], tp.phase)
        self.assertEqual(M.crop_plan(s), tp.crops)

    def test_endgame_skips_animal_care(self):
        s = make_s(day=27, shops=["FARMERS_MARKET"], crops={"WHEAT": 6})
        tp = M.plan_turn(s)
        self.assertEqual(tp.phase, "ENDGAME")
        self.assertTrue(tp.harvest_focus)
        self.assertTrue(tp.profile.skip_animal_care)

    def test_late_sprint_market_route(self):
        M._LATE_SHOP_SPRINT["until_day"] = 20
        try:
            s = make_s(day=16, shops=["SMOOTHIE_SHOP"], empty=10, n_quads=2)
            tp = M.plan_turn(s)
            self.assertEqual(tp.market_route, "late_sprint")
            self.assertEqual(tp.profile.field_priority, "fill")
        finally:
            M._LATE_SHOP_SPRINT["until_day"] = -1

    def test_phase_profile_spike_sell_bump(self):
        prof = phase_profile("SPIKE", M.PARAMS)
        self.assertTrue(prof.spike_sell_bump)

    def test_resolve_market_route_berry_prep(self):
        flags = TurnFlags(
            late_shop_sprint=False,
            berry_prep=True,
            plant_sprint=False,
            berry_ramp=False,
            seed_fill_push=False,
            berry_replant_push=False,
            in_late_ramp=False,
            land_ramp_relax=False,
            need_land=False,
            berry_ok=False,
            liquidity_stress=False,
            late_ongoing=False,
            demand_stack=False,
            price_spike={},
        )
        self.assertEqual(
            resolve_market_route("ENGINE", flags, mode="ENGINE"), "berry_prep"
        )


if __name__ == "__main__":
    unittest.main()
