"""Kaggriculture agent — manure core + gated shop spends.

Kaggle calls the last function. obs.day is 0-indexed (0–29).
Opening is hour 0: 5 hires, 2 cows, 2 sheep, wheat. No land, no melons.
PriceBook and shop demand gate land, berries, and herd — they do not
outrank feed, hires, or leftover operating cash.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from brain.plan import TurnFlags, TurnPlan, build_turn_plan, compute_sell_n
from brain.board import (
    board_fill_land_empty_cap,
    board_fill_pressure,
    land_blocked_by_board_fill,
)
from brain.map import (
    MapStrategy,
    classify_archetype,
    land_ramp_relax_active,
    maybe_reclassify_archetype,
    resolve_strategy,
    softfloor_mode_active,
    strategy_allows_berry_prep,
    strategy_land_empty_cap,
    strategy_quad1_empty_cap,
)
from brain.playbook import (
    ENGINE_REPLANT_DAY_MAX,
    cash_tile_cap,
    cow_target,
    crop_gap,
    crop_is_ramping,
    crop_is_replanting,
    engine_of,
    herd_tile_reserve,
    map_engine,
    plant_gap,
    primary_cash_crop,
    skip_berry_prep_for_sinks,
)
from brain.dynamics import crew_live_cap, water_stress
from brain.lookahead import rank_projects
from brain.long_term import (
    LongTermStreams,
    best_animal_horizon_ev,
    build_streams,
)
from brain.market import keep_qty as market_keep_qty
from brain.market import market_inventory, sale_score
from brain.turn_budget import (
    TurnBudget,
    choose_project,
    compute_turn_budget,
    cow_beats_seeds,
    cow_project_ev,
    expand_vs_stay_advantage,
    hire_project_ev,
    hollow_expand_window,
    land_fillable_tiles,
    live_tiles_for_hollow_expand,
    post_land_seed_cap,
    seed_project_ev,
)

HARVEST_AGE = {"WHEAT": 4, "CARROT": 3, "MELON": 10}
YIELD_CAP = {"WHEAT": 4, "CARROT": 3, "MELON": 6}
ONGOING = {"TOMATO", "STRAWBERRY"}
SEED_COST = {
    "WHEAT": 10,
    "CARROT": 20,
    "TOMATO": 50,
    "STRAWBERRY": 100,
    "MELON": 80,
}
BASE_PRICE = {
    "WHEAT": 25,
    "CARROT": 35,
    "TOMATO": 60,
    "STRAWBERRY": 120,
    "MELON": 250,
    "EGG": 50,
    "MILK": 160,
    "WOOL": 200,
    "FERTILIZER": 100,
}
ANIMAL_COST = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_STRUCT = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
ANIMAL_FIRST = {"GOOSE": 4, "COW": 8, "SHEEP": 6}
ANIMAL_INTERVAL = {"GOOSE": 1, "COW": 2, "SHEEP": 3}
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
SHED_TILES = ((4, 4), (5, 4), (4, 5), (5, 5))
LAND_COST = (1000, 2000, 4000)
MAX_HANDS = 13  # softfloor median peak ~13; frontier spikes to 14 on land2 day
HIRES_PER_TURN = 5
MARKET_LIMIT = 10
DROP_ITEMS = ("FERTILIZER", "WOOL", "MILK", "MELON")
CASH_CROPS = ("STRAWBERRY", "CARROT")
SHOP_PRODUCTS = {
    "BAKERY": ["EGG", "WHEAT"],
    "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE": ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE": ["CARROT"],
    "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
MILK_SHOPS = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
BERRY_SHOPS = ("SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET")
CASH_PLANT = ("STRAWBERRY", "CARROT", "TOMATO", "MELON")
OPENING_MARKET = [
    ["HIRE"],
    ["HIRE"],
    ["HIRE"],
    ["HIRE"],
    ["HIRE"],
    ["BUY_ANIMAL", "COW", 2],
    ["BUY_ANIMAL", "SHEEP", 2],
    # EcoBot / elite ladder: day-0 melon all-in beats wheat-only openers
    # under shared-market H2H (first melon cash spike ~day 10).
    ["BUY_SEED", "MELON", 11],
    ["BUY_SEED", "WHEAT", 6],
    ["BUY_PRODUCT", "WHEAT", 4],
]

DEFAULT_PARAMS: dict[str, int | float] = {
    # Slice A wheat engine
    "wheat_engine_day_max": 24,
    "wheat_buffer_add": 2,
    "wheat_min_tiles": 6,
    "wheat_no_mouth_tiles": 4,
    "wheat_filler_day_max": 20,
    "late_wheat_seed_buffer_day_min": 16,
    "late_wheat_seed_buffer": 2,
    # Melon filler — bakery/yarn boards before berry demand.
    "melon_leftover_min": 4,
    "melon_n_quads_min": 1,
    "melon_day_max": 16,
    "melon_cap": 12,
    "melon_bridge_cow_day_max": 12,
    "melon_bridge_cow_cap": 8,
    "berry_melon_bridge_cow_cap": 8,
    "melon_bridge_melon_min": 6,
    # Herd ramp gates
    "cow_day_max": 24,
    "cow_milk_px_min": 80,
    "cow_floor_day_max": 20,
    "cow_floor": 2,
    "cow_expand_cap": 10,
    "cow_stack_cap": 12,
    "sheep_day_max": 20,
    "sheep_wool_px_min": 80,
    "sheep_floor_day_max": 20,
    "sheep_floor": 2,
    "sheep_expand_cap": 4,
    # Land timing / guards (EcoBot + elite: first plot as early as day 5)
    "land_day_min": 5,
    "land_day_max": 22,
    "max_quads_for_land": 3,
    "land3_day_min": 13,
    "land3_day_max": 20,
    "land3_money_min": 5500,
    "land_horizon_day_max": 28,
    "land2_day_min": 9,
    "land2_day_max": 22,
    "land2_money_min": 2800,
    "land2_empty_max": 4,
    # Replay winners buy plot-3 near day 11 with ~10–12 berries, not 16.
    "land2_strawberry_min": 10,
    "land2_tomato_min": 12,
    "land2_schedule_cow_min": 6,
    # Softfloor bots buy plot-3 ~d10–12 with empty still ~40–60 (then fill).
    "land2_schedule_empty_max": 55,
    "land2_schedule_empty_min": 12,
    "land2_schedule_plantable_min": 10,
    "land2_schedule_berry_min": 16,
    "land2_packed_empty_max": 6,
    "land2_dense_money_min": 2500,
    "land2_dense_empty_max": 8,
    "berry_milk_cow_cap": 10,
    "berry_milk_cow_extra": 4,
    "berry_herd_mouth_cap": 12,
    "berry_animal_buy_day_max": 18,
    "berry_cow_hard_cap": 10,
    "late_berry_tomato_cap": 24,
    "land2_sprint_strawberry_min": 24,
    "sell_n_pre_dump": 7,
    "liquidate_day_min": 25,
    # Sell-hold heuristic
    "sell_hold_price_factor": 0.82,
    "sell_hold_days_left_min": 7,  # days_left(day) > 6
    # P0 regime: ongoing late-game + spike sell + soft cap override
    "ongoing_min_days_left": 3,
    "ongoing_spike_price_factor": 2.5,
    "spike_sell_n_min": 4,
    "spike_sell_base_mult": 3.0,
    "spike_sell_ma_mult": 1.5,
    # Sell-slot budget (phase profiles read these)
    "sell_n_base": 3,
    "sell_n_build": 2,
    "sell_n_liquidate": 8,
    "sell_n_endgame": 5,
    "sell_n_rescue": 5,
    "sell_n_cash_deficit_bump": 4,
    "sell_n_late_ongoing_bump": 4,
    "sell_n_cash_deficit_min": 1200,
    "land_cash_buffer_default": 800,
    "land_post_floor_default": 1500,
    # Map archetype router (locked at map_archetype_lock_day)
    "map_archetype_lock_day": 8,
    "map_early_berry_day_max": 8,
    "map_late_berry_day_min": 12,
    "map_early_spike_day_max": 12,
    "map_early_spike_berry_sink_max": 2,
    "map_provisional_day_min": 5,
    "map_land_relax_empty_max": 12,
    "map_land_sprint_relax_empty_max": 14,
    "map_land1_empty_max": 11,
    "map_land1_seed_empty_max": 10,
    "map_milk_stack_pure_min": 1,
    "map_milk_stack_dual_min": 1,
    "map_milk_defer_milk_sink_min": 2,
    "map_milk_defer_empty_max": 14,
    "map_milk_sprint_defer_empty_max": 12,
    # Softfloor: hire-aware multi-dawn. Packed printers (empty ≤8) keep
    # two-dawn residual so fat stands score ~0 (seed 89 densify path).
    "land_hollow_soft_cap": 14,
    "land_hollow_penalty_k": 4.0,
    "land_stand_ready_min": 10,
    "land2_tomato_soft_min": 8,
    "land2_hollow_empty_max": 45,
    "land_npv_realize": 0.7,
    "land_expand_margin": 0.0,
    "land2_packed_stand_min": 24,
    "berry_cow_hard_cap": 10,
    # Multi-stream long-term (crops + milk/egg/wool)
    "lt_secondary_weight": 0.25,
    "lt_animal_realize": 0.7,
    "lt_land_animal_realize": 0.45,
    "lt_land_animal_scale": 0.1,
    "lt_animal_project_scale": 0.15,
    "lt_pasture_frac": 0.28,
    "lt_inventory_realize": 0.15,
    # Herd-with-land expand-while-hollow (softfloor ~d10 plot-3)
    "hollow_live_cap_factor": 1.25,
    "hollow_live_empty_min": 20,
    "hollow_land_day_max": 12,
    "hollow_herd_push": 0,
    "hollow_herd_deep_empty": 20,
    "lt_hollow_berry_animal_scale": 0.12,
    "hollow_seed_hold_factor": 0.35,
    "hollow_seed_early_factor": 0.6,
    "hollow_land_priority_boost": 1.0,
    "hollow_land_npv_min": 5000,
    "hollow_preserve_empty_pad": 2,
    "hollow_preland_stand_cap": 20,
    # Softfloor herd burst: mined curve in brain.schedules.softfloor_cow_target_day.
    # Global day_max stays -1; softfloor_mode router enables via softfloor_herd_day_max.
    "land2_hollow_cow_min": 4,
    "post_land2_cow_burst": 2,
    "post_land2_cow_day_max": -1,
    "softfloor_herd_enabled": 1,
    "softfloor_herd_day_max": 10,
    "softfloor_herd_empty_min": 16,
    "softfloor_herd_day_min": 7,
    "softfloor_fill_empty_min": 16,
    "hollow_plot3_fill_frac": 0.35,
    # Post-plot-3 crew spike (frontier ~14 hires on land2 day)
    "land2_hire_target": 13,
    "land2_hire_burst": 12,
    "land2_hire_empty_min": 12,
    "land2_post_seed_keep": 200,
    # Densify-3 fill package (elite post-plot3): berry + hire, not tomato.
    "densify3_fill_enabled": 1,
    "densify3_day_max": 15,
    "densify3_empty_min": 12,
    "densify3_berry_target": 34,
    "densify3_hire_target": 13,
    "densify3_hire_burst": 12,
    "densify3_seed_keep": 150,
    "densify3_seed_stockpile": 16,
    "nonberry_secondary_cap": 16,
    "capital_followup": 1,
    # Board-fill pressure (plant priority); land ban demoted to NPV hollow pen
    "board_fill_land_empty_max_1q": 10,
    "board_fill_land_empty_max_2q": 8,
    "board_fill_land_empty_max_3q": 6,
    "board_fill_late_berry_cap_2q": 8,
    "board_fill_milk_stack_cap_2q": 10,
    "board_fill_early_berry_cap_2q": 10,
    "board_fill_berry_gap_min": 3,
    "board_fill_berry_target_min": 8,
    "board_fill_pressure_empty": 6,
    "board_fill_no_berry_cap_1q": 12,
    "board_fill_no_berry_cap_2q": 18,
    "board_fill_no_berry_cap_3q": 14,
    "board_fill_berry_met_cap_2q": 12,
    "board_fill_late_preberry_pressure_empty": 16,
    "cap_override_ev_mult": 2.0,
    "cap_override_bonus_max": 4,
    "cap_override_price_factor": 2.0,
    # P1: duplicate-shop demand scaling
    "demand_boost_linear": 0.08,
    "demand_boost_stack": 0.04,
    "demand_cap_step_berry": 4,
    "demand_cap_step_crop": 2,
    "milk_herd_base": 2,
    "wool_herd_base": 2,
    # P2: phase system + late shop sprint + extended windows
    # Replay dump median ~d27; EcoBot-style earlier liquidation helps H2H.
    "liquidate_day_min": 25,
    "engine_replant_day_max": ENGINE_REPLANT_DAY_MAX,
    "liquidity_rescue_day_max": 26,
    "seed_fill_day_max": 22,
    "endgame_days_left": 4,
    "late_shop_day_min": 12,
    "late_shop_sprint_days": 6,
    "late_shop_sprint_cutoff_day": 24,
    "late_ramp_land_empty_max": 24,
    "late_ramp_hire_cap": 3,
    "late_ramp_land_cash_buffer": 400,
    "late_ramp_skip_strawberry_min": 1,
    # P3/P7: stockpile and plant strawberries before a late first berry shop.
    "berry_prep_enabled": 1,
    "berry_prep_day_min": 11,
    "berry_prep_day_max": 14,
    "berry_prep_empty_min": 10,
    "berry_prep_money_min": 3500,
    "berry_prep_seed_tiles": 10,
    "berry_prep_cash_keep": 800,
    "berry_prep_max_seed_spend": 1200,
    # Softfloor elites plant berry from ~d6 on pizza/bakery before berry shops.
    # Gated by softfloor_router (EARLY_BERRY densify stays off).
    "softfloor_router_enabled": 1,
    "softfloor_router_day_min": 6,
    "softfloor_router_day_max": 18,
    "softfloor_speculative_berry": 1,
    "softfloor_berry_day_min": 6,
    "softfloor_berry_day_max": 18,
    "softfloor_berry_money_min": 600,
    "softfloor_berry_cap": 36,
    "softfloor_berry_seed_tiles": 24,
    # P3: market intelligence
    "glut_block_threshold": 0.35,
    "spike_harvest_mult": 1.35,
    "frontrun_uptrend_hours": 3,
    "frontrun_score_mult": 1.2,
    "frontrun_cap_bonus": 4,
    "animal_buy_day_max": 24,
    "animal_buy_day_min": 3,
    "mouth_cap_1q": 6,
    "mouth_cap_2qplus": 14,
    "animal_cash_floor_2qplus": 400,
    "animal_cash_floor_1q": 1200,
    # Softfloor shed-busy cow catch-up (never densify — gated by _softfloor_mode).
    "softfloor_shed_busy_cow_buy": 1,
    "shed_busy_empty_min": 2,
    "plot3_cal_day_min": 9,
    "plot3_cal_day_max": 11,
    "plot3_cal_cash_reserve": 500,
    "plot3_hands_soft_min": 8,
    "plot3_packed_berry_min": 16,
    "plot3_packed_cow_min": 4,
    "lane_b_berry_steer": 1,
    "lane_b_berry_day_min": 6,
    "lane_b_berry_day_max": 10,
    "lane_b_berry_target": 20,
    "lane_b_cow_floor": 4,
    # Pasture bind: shed animals with no empty pasture tile.
    "pasture_bind_fix": 1,
    "pasture_bind_hour_max": 4,
    "pasture_bind_max": 1,
    # Pre-calendar pack: fill hollow boards to empty≤4 by d10.
    "pre_calendar_pack": 1,
    "pre_pack_day_min": 6,
    "pre_pack_day_max": 10,
    "pre_pack_empty_min": 12,
    "pre_pack_early_berry_empty_min": 14,
    "pre_pack_berry_target": 20,
    # Cash-hollow phase-2 (off until pack/pasture eval passes).
    "plot3_cash_hollow": 0,
    "plot3_hollow_empty_min": 8,
    "plot3_hollow_empty_max": 12,
    "plot3_hollow_berry_min": 11,
    "plot3_hollow_cow_min": 6,
    "plot3_hollow_fill_per_empty": 400,
    # 2–5 day capital look-ahead (land vs cow vs seed)
    "lookahead_days": 3,
    "lookahead_actions_per_worker_day": 8,
    "lookahead_shadow": 0,
    "lookahead_min_day": 1,
    "lookahead_max_day": 24,
}


def _load_params() -> dict[str, int | float]:
    """
    Load tuning params from either:
      - $KAGGRICULTURE_PARAMS_PATH (explicit), or
      - ./tune/params.json (default; optional)
    """
    params = dict(DEFAULT_PARAMS)
    try:
        path = os.getenv("KAGGRICULTURE_PARAMS_PATH") or str(
            Path(__file__).resolve().parent / "tune" / "params.json"
        )
        if os.path.exists(path):
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            for k, v in raw.items():
                if k in params:
                    params[k] = v
    except Exception:
        # Tuning is optional; if loading fails we keep defaults.
        pass
    return params


PARAMS: dict[str, int | float] = _load_params()

_PRICE_BOOK: dict[str, Any] = {"prev": {}, "delta": {}, "hist": {}}


def days_left(day: int) -> int:
    return max(0, 29 - day)


def fib_hire_cost(already: int) -> int:
    a, b = 1, 1
    for _ in range(already):
        a, b = b, a + b
    return a


def px(s: dict[str, Any], item: str) -> int:
    return int(s["prices"].get(item, BASE_PRICE.get(item, 1)))


def milk_px(s: dict[str, Any]) -> int:
    return px(s, "MILK")


def wool_px(s: dict[str, Any]) -> int:
    return px(s, "WOOL")


def glut(s: dict[str, Any], item: str) -> float:
    """Positive = oversupply (price pressure down). Inventory starts at 10_000."""
    inv = int(s.get("inventory", {}).get(item, 10000))
    return (inv - 10000) / 10000.0


def update_price_book(s: dict[str, Any]) -> None:
    """Persist prices across turns in one episode. Reset at day 0 hour 0."""
    global _PRICE_BOOK
    if s["day"] == 0 and s["hour"] == 0:
        _PRICE_BOOK = {"prev": {}, "delta": {}, "hist": {}}
        _LAND_SPRINT["until_day"] = -1
        _LATE_SHOP_SPRINT["until_day"] = -1
        _SHOP_TRACK["prev_shops"] = set()
        _UPTREND_HOURS.clear()
    prices = {k: int(v) for k, v in s["prices"].items()}
    prev = _PRICE_BOOK.get("prev") or {}
    delta: dict[str, int] = {}
    hist: dict[str, list[int]] = _PRICE_BOOK.get("hist") or {}
    for item, p in prices.items():
        old = int(prev.get(item, p))
        delta[item] = p - old
        series = hist.setdefault(item, [])
        series.append(p)
        if len(series) > 72:
            del series[0]
    _PRICE_BOOK = {"prev": prices, "delta": delta, "hist": hist}
    s["delta"] = delta
    s["price_ma"] = {
        item: (
            (sum(series[-72:]) / len(series[-72:]))
            if series
            else float(prices.get(item, 0))
        )
        for item, series in hist.items()
    }


def price_momentum(s: dict[str, Any], item: str) -> float:
    """Hourly price trend tilt: ±20% max from last-step delta."""
    delta = (s.get("delta") or {}).get(item, 0)
    return 1.0 + max(-0.2, min(0.2, float(delta) / 200.0))


def planning_ev(s: dict[str, Any], crop: str) -> float:
    """EV for plant/buy/harvest: glut-adjusted score × hourly momentum."""
    return live_ev(s, crop) * price_momentum(s, crop)


def refresh_planning_scores(s: dict[str, Any]) -> None:
    """Recompute planning EV after hourly price book update."""
    scores = s.get("scores") or {}
    s["plan_scores"] = {c: planning_ev(s, c) for c in scores}


def plan_ev(s: dict[str, Any], crop: str) -> float:
    """Cached planning EV when available, else compute on the fly."""
    ps = s.get("plan_scores")
    if ps is not None and crop in ps:
        return float(ps[crop])
    return planning_ev(s, crop)


def plan_viable(s: dict[str, Any], crop: str) -> bool:
    """Glut-aware gate: skip flooded markets unless price is spiking."""
    if plan_ev(s, crop) <= 0:
        return False
    glut_level = glut(s, crop)
    if glut_level > float(PARAMS["glut_block_threshold"]) and not price_spike(s, crop):
        return False
    return True


def _hold_engine_crop(s: dict[str, Any], crop: str) -> bool:
    """Keep the opener's tile plan after new-plant EV hits zero.

    `ongoing_crop_score` requires a 2.5× spike once days_left < 8. That is a
    gate for *new* plantings, not a reason to drop a live strawberry field.
    """
    if not engine_replant_open(s):
        return False
    if int((s.get("demand") or {}).get(crop, 0) or 0) < 1:
        return False
    glut_level = glut(s, crop)
    if glut_level > float(PARAMS["glut_block_threshold"]) and not price_spike(s, crop):
        return False
    return _primary_cash(s) == crop


def update_uptrend_tracking(s: dict[str, Any]) -> None:
    """Count consecutive uptrend hours for high-demand crops."""
    global _UPTREND_HOURS
    demand = s.get("demand") or {}
    delta = s.get("delta") or {}
    for crop in CASH_PLANT:
        d = int(demand.get(crop, 0))
        uptick = int(delta.get(crop, 0) or 0) > 0
        if d >= 2 and uptick:
            _UPTREND_HOURS[crop] = _UPTREND_HOURS.get(crop, 0) + 1
        else:
            _UPTREND_HOURS[crop] = 0


def uptrend_frontrun(s: dict[str, Any], crop: str) -> bool:
    """Pre-emptive buy when price has risen for several hours under shop stack."""
    need = int(PARAMS["frontrun_uptrend_hours"])
    return _UPTREND_HOURS.get(crop, 0) >= need


def harvest_ev_score(s: dict[str, Any], crop: str) -> float:
    """Harvest priority EV with spike boost independent of inventory plan."""
    ev = plan_ev(s, crop)
    if price_spike(s, crop):
        return ev * float(PARAMS["spike_harvest_mult"])
    spikes = (s.get("regime") or {}).get("price_spike") or {}
    if spikes.get(crop):
        return ev * float(PARAMS["spike_harvest_mult"])
    return ev


def milk_sink(s: dict[str, Any]) -> int:
    return sum(1 for shop in s.get("shops") or [] if shop in MILK_SHOPS)


def berry_sink(s: dict[str, Any]) -> int:
    return sum(1 for shop in s.get("shops") or [] if shop in BERRY_SHOPS)


_LAND_SPRINT: dict[str, int] = {"until_day": -1}
_LATE_SHOP_SPRINT: dict[str, int] = {"until_day": -1}
_SHOP_TRACK: dict[str, Any] = {"prev_shops": set()}
_UPTREND_HOURS: dict[str, int] = {}


def update_shop_tracking(s: dict[str, Any]) -> None:
    """Track shop unlocks; trigger a berry sprint when a berry shop opens late."""
    global _SHOP_TRACK, _LATE_SHOP_SPRINT
    shops = set(s.get("shops") or [])
    prev = set(_SHOP_TRACK.get("prev_shops") or set())
    new_berry = [sh for sh in shops if sh in BERRY_SHOPS and sh not in prev]
    if new_berry and _SHOP_TRACK.get("first_berry_day") is None:
        _SHOP_TRACK["first_berry_day"] = s["day"]
    new_milk = [sh for sh in shops if sh in MILK_SHOPS and sh not in prev]
    if new_milk and _SHOP_TRACK.get("first_milk_day") is None:
        _SHOP_TRACK["first_milk_day"] = s["day"]
    first_late_berry = new_berry and not (prev & set(BERRY_SHOPS))
    if first_late_berry and s["day"] >= int(PARAMS["late_shop_day_min"]):
        until = s["day"] + int(PARAMS["late_shop_sprint_days"])
        _LATE_SHOP_SPRINT["until_day"] = max(
            _LATE_SHOP_SPRINT.get("until_day", -1), until
        )
    _SHOP_TRACK["prev_shops"] = shops
    _maybe_lock_archetype(s)
    maybe_reclassify_archetype(
        s,
        _SHOP_TRACK,
        PARAMS,
        berry_shops=frozenset(BERRY_SHOPS),
        milk_shops=frozenset(MILK_SHOPS),
        new_berry_today=bool(new_berry),
    )


def _maybe_lock_archetype(s: dict[str, Any]) -> None:
    """Lock map archetype once at map_archetype_lock_day (default day 8)."""
    if _SHOP_TRACK.get("archetype_locked"):
        return
    lock_day = int(PARAMS["map_archetype_lock_day"])
    if s["day"] < lock_day:
        return
    arch = classify_archetype(
        s,
        _SHOP_TRACK,
        PARAMS,
        berry_shops=frozenset(BERRY_SHOPS),
        milk_shops=frozenset(MILK_SHOPS),
    )
    _SHOP_TRACK["archetype"] = arch
    _SHOP_TRACK["archetype_locked"] = True


def map_strategy(s: dict[str, Any]) -> MapStrategy:
    tp = s.get("turn_plan")
    if tp is not None and tp.strategy != "UNKNOWN":
        return tp.strategy
    return resolve_strategy(
        s,
        _SHOP_TRACK,
        PARAMS,
        berry_shops=frozenset(BERRY_SHOPS),
        milk_shops=frozenset(MILK_SHOPS),
    )


def late_shop_sprint(s: dict[str, Any]) -> bool:
    """Aggressive berry/land fill for a few days after a late berry-shop unlock."""
    if s["day"] > int(PARAMS["late_shop_sprint_cutoff_day"]):
        return False
    return _LATE_SHOP_SPRINT.get("until_day", -1) >= s["day"]


def in_late_ramp(s: dict[str, Any]) -> bool:
    """Active post-unlock berry sprint (may overlap ENDGAME)."""
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.flags.in_late_ramp
    return late_shop_sprint(s)


def land_ramp_relax(s: dict[str, Any]) -> bool:
    """Relax land empty caps only while sprinting to fill a moderate berry gap."""
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.flags.land_ramp_relax
    strat = map_strategy(s)
    berry_gap_n = max(
        0,
        crop_plan(s).get("STRAWBERRY", 0)
        - s["crops"].get("STRAWBERRY", 0)
        - int(s["seeds"].get("STRAWBERRY", 0)),
    )
    return land_ramp_relax_active(
        strat,
        s,
        PARAMS,
        late_shop_sprint=late_shop_sprint(s),
        berry_gap=berry_gap_n,
        n_quads=int(s.get("n_quads", 1)),
    )


def _compute_land_ramp_relax(
    s: dict[str, Any], *, strategy: MapStrategy, berry_gap: int, lshop: bool
) -> bool:
    """Uncached land_ramp_relax for plan_turn flag collection."""
    return land_ramp_relax_active(
        strategy,
        s,
        PARAMS,
        late_shop_sprint=lshop,
        berry_gap=berry_gap,
        n_quads=int(s.get("n_quads", 1)),
    )


def _cash_deficit(s: dict[str, Any]) -> float:
    plan = crop_plan(s)
    planned_seed_spend = 0
    for c in CASH_PLANT:
        target = plan.get(c, 0)
        have = s["crops"].get(c, 0) + s["seeds"].get(c, 0)
        need = max(0, target - have)
        planned_seed_spend += need * SEED_COST[c]
    return max(0.0, planned_seed_spend - float(s.get("money", 0)))


def _softfloor_mode(s: dict[str, Any]) -> bool:
    """True when map router allows softfloor schedule priors.

    Adds a labor gate on top of softfloor_mode_active so densify boards that
    briefly look hollow (high day_plantable) stay on densify priorities.
    Deep hollow (empty ≥ hollow_herd_deep_empty) always qualifies.
    """
    if not softfloor_mode_active(s, map_strategy(s), PARAMS):
        return False
    empty = int(s.get("empty") or 0)
    if empty >= int(PARAMS.get("hollow_herd_deep_empty", 20)):
        return True
    return _hollow_plot3_labor_ok(s)


def _softfloor_speculative_berry(s: dict[str, Any]) -> bool:
    """Plant strawberries before berry shops — softfloor elite schedule.

    Live H2H on seed 33: structured/frontier plant berry from d6 with only
    pizza/bakery unlocked and score 135k–172k; we wait for berry shops, plant
    tomato, and stall hollow (~64k). Shop unlock order is path-dependent, so
    speculative berry also steers unlocks toward FM/smoothie.
    """
    if int(PARAMS.get("softfloor_speculative_berry", 1)) != 1:
        return False
    if not _softfloor_mode(s):
        return False
    if berry_sink(s) > 0:
        return False
    day = int(s.get("day") or 0)
    if day < int(PARAMS.get("softfloor_berry_day_min", 6)):
        return False
    if day > int(PARAMS.get("softfloor_berry_day_max", 18)):
        return False
    if float(s.get("money", 0)) < float(PARAMS.get("softfloor_berry_money_min", 600)):
        return False
    shops = set(s.get("shops") or [])
    # Require pizza — bakery-only LATE_BERRY densify must not use this path.
    return "PIZZA_SHOP" in shops


def _lane_b_berry_steer(s: dict[str, Any]) -> bool:
    """Package B: pizza→berry on Lane B (never EARLY_BERRY densify printers).

    Elites reach berry≈17–20 by land2 dawn; we plant tomato and stall. Steer
    strawberry through d6–10 on softfloor hollow / UNKNOWN even after berry
    shops open (tomato must not own leftover). 2q only — 1q tomato towns
    must keep densify-safe openers.
    """
    if int(PARAMS.get("lane_b_berry_steer", 1)) != 1:
        return False
    if map_strategy(s) == "EARLY_BERRY":
        return False
    if "PIZZA_SHOP" not in set(s.get("shops") or []):
        return False
    day = int(s.get("day") or 0)
    if day < int(PARAMS.get("lane_b_berry_day_min", 6)):
        return False
    if day > int(PARAMS.get("lane_b_berry_day_max", 10)):
        return False
    if int(s.get("n_quads") or 0) < 2:
        return False
    if _softfloor_mode(s):
        return True
    if softfloor_mode_active(s, map_strategy(s), PARAMS):
        return True
    return int(s.get("empty") or 0) >= int(PARAMS.get("softfloor_fill_empty_min", 16))


def _pre_calendar_pack_active(s: dict[str, Any]) -> bool:
    """Fill hollow boards toward empty≤4 before calendar land2 window.

    Softfloor_mode only — LATE_BERRY/UNKNOWN hollow without the labor gate
    (seed 33) crashed when berry pack stole the tomato/cash path (−10k+).
    """
    if int(PARAMS.get("pre_calendar_pack", 1)) != 1:
        return False
    if not _softfloor_mode(s):
        return False
    day = int(s.get("day") or 0)
    if day < int(PARAMS.get("pre_pack_day_min", 6)):
        return False
    if day > int(PARAMS.get("pre_pack_day_max", 10)):
        return False
    if int(s.get("n_quads") or 0) < 2:
        return False
    empty = int(s.get("empty") or 0)
    if empty <= int(PARAMS.get("land2_empty_max", 4)):
        return False
    if empty < int(PARAMS.get("pre_pack_empty_min", 12)):
        return False
    shops = set(s.get("shops") or [])
    if "PIZZA_SHOP" not in shops and berry_sink(s) <= 0:
        return False
    return True


def _pack_berry_active(s: dict[str, Any]) -> bool:
    """Berry owns leftover when packing toward calendar readiness."""
    return _lane_b_berry_steer(s) or _pre_calendar_pack_active(s)


def _lane_b_berry_gap(s: dict[str, Any]) -> int:
    """How many strawberry plant tiles still needed before land2 dawn."""
    if not (
        _pack_berry_active(s)
        or _softfloor_speculative_berry(s)
        or _softfloor_mode(s)
    ):
        return 0
    # EARLY_BERRY densify printers: only via pre_calendar_pack hollow gate.
    if map_strategy(s) == "EARLY_BERRY" and not _pre_calendar_pack_active(s):
        return 0
    have = int((s.get("crops") or {}).get("STRAWBERRY", 0) or 0)
    seed = int((s.get("seeds") or {}).get("STRAWBERRY", 0) or 0)
    target = int(PARAMS.get("pre_pack_berry_target", PARAMS.get("lane_b_berry_target", 20)))
    gap = max(0, target - have - seed)
    # Only chase empty≤4 when pre-calendar pack is explicitly on.
    if _pre_calendar_pack_active(s):
        empty = int(s.get("empty") or 0)
        pack_need = max(0, empty - int(PARAMS.get("land2_empty_max", 4)))
        gap = max(gap, max(0, pack_need - seed))
    return gap


def _pasture_bind_active(s: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    """Shed cows/sheep with zero empty pastures — build before cash plant.

    Softfloor_mode only — densify printers are EARLY_BERRY but start as
    UNKNOWN; binding pastures then stole melon plant hours (−12–28k).
    """
    if int(PARAMS.get("pasture_bind_fix", 1)) != 1:
        return False
    if not _softfloor_mode(s):
        return False
    if int(s.get("hour") or 0) > int(PARAMS.get("pasture_bind_hour_max", 4)):
        return False
    if int(s.get("at_risk") or 0) > 0:
        return False
    shed = s.get("shed") or {}
    waiting = int(shed.get("COW", 0) or 0) + int(shed.get("SHEEP", 0) or 0)
    if waiting <= 0:
        return False
    if int((s.get("empty_struct") or {}).get("PASTURE", 0) or 0) > 0:
        return False
    if ctx is not None:
        built = int(ctx.get("pasture_bind_builds", 0) or 0)
        if built >= int(PARAMS.get("pasture_bind_max", 1)):
            return False
    return True


def _softfloor_berry_plant_push(s: dict[str, Any], seeds: dict[str, int]) -> bool:
    """Plant held strawberry seeds on routed softfloor hollow boards."""
    if seeds.get("STRAWBERRY", 0) <= 0:
        return False
    if _pack_berry_active(s):
        return True
    if berry_sink(s) > 0:
        return False
    if not softfloor_mode_active(s, map_strategy(s), PARAMS):
        return False
    if int(s.get("empty") or 0) < int(PARAMS.get("softfloor_fill_empty_min", 16)):
        return False
    if int(s.get("day") or 0) > int(PARAMS.get("softfloor_berry_day_max", 18)):
        return False
    return "PIZZA_SHOP" in set(s.get("shops") or [])


def _berry_prep_window(s: dict[str, Any]) -> bool:
    """Day/shop/land gates for berry steering. Does not read crop_plan."""
    if int(PARAMS["berry_prep_enabled"]) != 1:
        return False
    if _softfloor_speculative_berry(s):
        return True
    strat = map_strategy(s)
    if strat != "UNKNOWN" and not strategy_allows_berry_prep(strat):
        return False
    if berry_sink(s) > 0 or skip_berry_prep_for_sinks(
        s,
        first_berry_day=_SHOP_TRACK.get("first_berry_day"),
        first_milk_day=_SHOP_TRACK.get("first_milk_day"),
    ):
        return False
    day = s["day"]
    if day < int(PARAMS["berry_prep_day_min"]) or day > int(PARAMS["berry_prep_day_max"]):
        return False
    if float(s.get("money", 0)) < float(PARAMS["berry_prep_money_min"]):
        return False
    if int(s["empty"]) < int(PARAMS["berry_prep_empty_min"]):
        return False
    if s["n_quads"] >= 2 and int(s["empty"]) > 12:
        return False
    if s["n_quads"] == 1 and int(s["empty"]) > 8:
        return False
    return True


def berry_prep_active(s: dict[str, Any]) -> bool:
    """Reserve land/cash for strawberries when no berry shop is open yet."""
    if not _berry_prep_window(s):
        return False
    if _softfloor_speculative_berry(s):
        return True
    if _cash_deficit(s) >= 900:
        return False
    return True


def berry_prep_seed_need(
    s: dict[str, Any], seeds: dict[str, int] | None = None
) -> int:
    """Strawberry seeds to stockpile before the first berry shop opens."""
    if not berry_prep_active(s):
        return 0
    seeds = seeds if seeds is not None else s.get("seeds") or {}
    have = s["crops"].get("STRAWBERRY", 0) + int(seeds.get("STRAWBERRY", 0))
    tiles = int(PARAMS["berry_prep_seed_tiles"])
    if _softfloor_speculative_berry(s):
        tiles = int(PARAMS.get("softfloor_berry_seed_tiles", 24))
    target = min(int(s["empty"]), tiles)
    return max(0, target - have)


def detect_regime(s: dict[str, Any]) -> dict[str, Any]:
    """Classify the current turn — delegates to unified plan_turn()."""
    return plan_turn(s).regime


def berry_gap(s: dict[str, Any]) -> int:
    plan = crop_plan(s)
    return max(
        0,
        plan.get("STRAWBERRY", 0)
        - s["crops"].get("STRAWBERRY", 0)
        - s["seeds"].get("STRAWBERRY", 0),
    )


def plant_sprint(s: dict[str, Any]) -> bool:
    """Fill empty tiles aggressively for two days after buying land."""
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.flags.plant_sprint
    if s["day"] > int(PARAMS["seed_fill_day_max"]):
        return False
    return _LAND_SPRINT.get("until_day", -1) >= s["day"]


def engine_replant_open(s: dict[str, Any]) -> bool:
    """Plant the engine crop through ENDGAME; stop on LIQUIDATE."""
    return int(s.get("day", 0)) <= int(PARAMS["engine_replant_day_max"])


def berry_replant_push(s: dict[str, Any]) -> bool:
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.flags.berry_replant_push
    if not engine_replant_open(s):
        return False
    if not (berry_ok(s) and berry_gap(s) > 0):
        return False
    if in_late_ramp(s):
        return True
    return s["day"] >= 12


def seed_fill_push(s: dict[str, Any]) -> bool:
    """Buy/plant aggressively after land buys or when many tiles sit empty."""
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.flags.seed_fill_push
    if in_late_ramp(s):
        if s["day"] > int(PARAMS["late_shop_sprint_cutoff_day"]):
            return False
        return plant_sprint(s) or s["empty"] >= 8
    if s["day"] > int(PARAMS["seed_fill_day_max"]):
        return False
    if plant_sprint(s) or s["empty"] >= 8:
        return True
    strat = map_strategy(s)
    cap = board_fill_land_empty_cap(
        int(s.get("n_quads", 1)), PARAMS, strategy=strat
    )
    return int(s.get("empty", 0)) > cap


def berry_ramp(s: dict[str, Any]) -> bool:
    """Berry shop open midgame with room to plant — ramp through day 16 (or late sprint)."""
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.flags.berry_ramp
    late = in_late_ramp(s)
    plan = crop_plan(s)
    return crop_is_ramping(s, "STRAWBERRY", plan, late=late)


def cash_ramp(s: dict[str, Any]) -> bool:
    """Ramp the dominant shop crop (berries, tomatoes, or carrots)."""
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.flags.cash_ramp
    late = in_late_ramp(s)
    plan = crop_plan(s)
    primary = _primary_cash(s)
    if primary == "STRAWBERRY":
        return crop_is_ramping(s, "STRAWBERRY", plan, late=late)
    return crop_is_ramping(s, primary, plan, late=late)


def berry_seed_push(s: dict[str, Any]) -> bool:
    return berry_replant_push(s) or berry_ramp(s)


def land_bundle_cost(s: dict[str, Any]) -> int:
    if s["n_quads"] >= 4:
        return 0
    return LAND_COST[s["n_quads"] - 1] + 800


def _productive_days(s: dict[str, Any], *, for_land: bool = False) -> int:
    """Horizon for NPV. Land uses replant cutoff; herd/seed may use late dump."""
    day = int(s.get("day") or 0)
    end = int(PARAMS.get("engine_replant_day_max", 27))
    if not for_land:
        end = max(end, int(PARAMS.get("land_horizon_day_max", 28)))
    return max(0, end - day)


def _turn_budget(s: dict[str, Any]) -> TurnBudget:
    tp = s.get("turn_plan")
    if tp is not None and tp.budget is not None:
        return tp.budget
    primary = _primary_cash(s)
    tile_ev = plan_ev(s, primary) if primary else 0.0
    return compute_turn_budget(
        s, cash_crop=primary or "", tile_ev=tile_ev, productive_days=_productive_days(s)
    )


def _stand_factor(s: dict[str, Any]) -> float:
    """0–1.5 readiness from live cash stand (soft; not a hard land veto)."""
    berries = int(s["crops"].get("STRAWBERRY", 0) or 0)
    tomatoes = int(s["crops"].get("TOMATO", 0) or 0)
    melons = int(s["crops"].get("MELON", 0) or 0)
    carrots = int(s["crops"].get("CARROT", 0) or 0)
    stand = max(berries, tomatoes, melons, carrots)
    ready = max(1, int(PARAMS.get("land_stand_ready_min", 6)))
    return max(0.35, min(1.5, float(stand) / float(ready)))


def _sheep_horizon_target(s: dict[str, Any]) -> int:
    wool_d = int((s.get("demand") or {}).get("WOOL", 0) or 0)
    if wool_d <= 0:
        return int(s.get("sheep") or 0)
    floor = int(PARAMS["sheep_floor"]) if int(s["day"]) <= int(PARAMS["sheep_floor_day_max"]) else 0
    return min(
        int(PARAMS["sheep_expand_cap"]),
        max(floor, int(PARAMS.get("wool_herd_base", 2)) + wool_d),
    )


def _goose_horizon_target(s: dict[str, Any]) -> int:
    sinks = egg_sink(s)
    if sinks <= 0 or int(s["day"]) > 20:
        return int(s.get("geese") or 0)
    max_geese = 1 if int(s.get("n_quads") or 1) <= 2 else 2
    egg_target = max_geese
    if sinks >= 2 and px(s, "EGG") >= 65:
        egg_target = min(max_geese, 1 + (sinks - 1) // 2)
    return max(int(s.get("geese") or 0), egg_target)


def _long_term_streams(s: dict[str, Any]) -> LongTermStreams:
    """Crops + milk/egg/wool (+ light inventory) for horizon planning."""
    cached = s.get("_lt_streams")
    day = int(s.get("day") or 0)
    hour = int(s.get("hour") or 0)
    if cached is not None and cached[0] == day and cached[1] == hour:
        return cached[2]
    primary = _primary_cash(s)
    days = _productive_days(s)
    primary_ev = plan_ev(s, primary) if primary else 0.0
    shed = s.get("shed") or {}
    crops = s.get("crops") or {}
    carrot_sinks = sum(
        1 for sh in (s.get("shops") or []) if sh in ("PET_CAFE", "FARMERS_MARKET")
    )
    streams = build_streams(
        productive_days=days,
        primary_ev=primary_ev,
        berry_ev=plan_ev(s, "STRAWBERRY"),
        tomato_ev=plan_ev(s, "TOMATO"),
        carrot_ev=plan_ev(s, "CARROT"),
        melon_ev=plan_ev(s, "MELON"),
        berry_sinks=berry_sink(s),
        milk_sinks=milk_sink(s),
        carrot_sinks=carrot_sinks,
        egg_sinks=egg_sink(s),
        wool_demand=int((s.get("demand") or {}).get("WOOL", 0) or 0),
        milk_px=float(milk_px(s)),
        egg_px=float(px(s, "EGG")),
        wool_px=float(wool_px(s)),
        cows=int(s.get("cows") or 0),
        sheep=int(s.get("sheep") or 0),
        geese=int(s.get("geese") or 0),
        cow_target=max(int(s.get("cows") or 0), int(cow_target(s, PARAMS))),
        sheep_target=_sheep_horizon_target(s),
        goose_target=_goose_horizon_target(s),
        cow_interval=int(ANIMAL_INTERVAL["COW"]),
        sheep_interval=int(ANIMAL_INTERVAL["SHEEP"]),
        goose_interval=int(ANIMAL_INTERVAL["GOOSE"]),
        cow_cost=int(ANIMAL_COST["COW"]),
        sheep_cost=int(ANIMAL_COST["SHEEP"]),
        goose_cost=int(ANIMAL_COST["GOOSE"]),
        shed_berries=int(shed.get("STRAWBERRY", 0) or 0),
        shed_milk=int(shed.get("MILK", 0) or 0),
        shed_eggs=int(shed.get("EGG", 0) or 0),
        shed_wool=int(shed.get("WOOL", 0) or 0),
        shed_melons=int(shed.get("MELON", 0) or 0),
        berry_px=float(px(s, "STRAWBERRY")),
        melon_px=float(px(s, "MELON")),
        secondary_weight=float(PARAMS.get("lt_secondary_weight", 0.25)),
        animal_realize=float(PARAMS.get("lt_animal_realize", 0.7)),
        land_animal_realize=float(PARAMS.get("lt_land_animal_realize", 0.45)),
        pasture_frac=float(PARAMS.get("lt_pasture_frac", 0.28)),
        inventory_realize=float(PARAMS.get("lt_inventory_realize", 0.15)),
    )
    s["_lt_streams"] = (day, hour, streams)
    return streams


def _hollow_expand_window(s: dict[str, Any]) -> bool:
    """True in softfloor plot-3 window: 2q, mid-hollow, milk/berry path, land2 days."""
    if not hollow_expand_window(
        n_quads=int(s.get("n_quads") or 0),
        empty=int(s.get("empty") or 0),
        soft_cap=int(PARAMS.get("land_hollow_soft_cap", 14)),
        hollow_max=int(PARAMS.get("land2_hollow_empty_max", 45)),
    ):
        return False
    day = int(s.get("day") or 0)
    if day < int(PARAMS["land2_day_min"]) - 1:
        return False
    if day > int(PARAMS.get("land2_day_max", 22)):
        return False
    if milk_sink(s) >= 1:
        return True
    # Berry softfloor: deep hollow only (empty >= deep). Densify printers
    # drop below deep empty quickly; softfloor stays hollow through ~d10.
    if berry_sink(s) >= 1:
        if egg_sink(s) >= 1:
            return False
        return int(s.get("empty") or 0) >= int(
            PARAMS.get("hollow_herd_deep_empty", 20)
        )
    return False


def _post_land2_herd_burst(s: dict[str, Any]) -> bool:
    """Dawn multi-cow to catch softfloor post-land1 ramp (3→6→8 by d9).

    Only via softfloor_mode router — global post_land2_cow_day_max stays -1 so
    densify EARLY_BERRY never bursts.
    """
    if int(PARAMS.get("softfloor_herd_enabled", 1)) != 1:
        return False
    if not _softfloor_mode(s):
        return False
    if int(s.get("hour") or 0) != 0:
        return False
    day = int(s.get("day") or 0)
    day_max = int(PARAMS.get("post_land2_cow_day_max", -1))
    if day_max < 0:
        day_max = int(PARAMS.get("softfloor_herd_day_max", 10))
    if day > day_max:
        return False
    if day < int(PARAMS.get("softfloor_herd_day_min", 7)):
        return False
    from brain.schedules import softfloor_cow_target_day

    target = softfloor_cow_target_day(
        day, cap=int(PARAMS.get("berry_melon_bridge_cow_cap", 8))
    )
    cows = int(s.get("cows") or 0)
    if cows >= target:
        return False
    crops = s.get("crops") or {}
    stand_ok = (
        int(crops.get("STRAWBERRY", 0) or 0) >= 4
        or int(crops.get("MELON", 0) or 0) >= 4
        or int(crops.get("TOMATO", 0) or 0) >= 4
        or milk_sink(s) >= 1
        or berry_sink(s) >= 1
    )
    return stand_ok


def _softfloor_schedule_cow_want(s: dict[str, Any]) -> int | None:
    """If softfloor herd window is open, return schedule cow want; else None."""
    if int(PARAMS.get("softfloor_herd_enabled", 1)) != 1:
        return None
    if not _softfloor_mode(s):
        return None
    day = int(s.get("day") or 0)
    if day < int(PARAMS.get("softfloor_herd_day_min", 7)):
        return None
    day_max = int(PARAMS.get("post_land2_cow_day_max", -1))
    if day_max < 0:
        day_max = int(PARAMS.get("softfloor_herd_day_max", 10))
    if day > day_max:
        return None
    if not herd_can_expand(s):
        return None
    from brain.schedules import softfloor_cow_target_day

    target = softfloor_cow_target_day(
        day, cap=int(PARAMS.get("berry_melon_bridge_cow_cap", 8))
    )
    cows = int(s.get("cows") or 0)
    if cows >= target:
        return None
    return min(cows + 1, target)


def _hollow_plot3_labor_ok(s: dict[str, Any]) -> bool:
    """True when remaining empties exceed near-term plant capacity (softfloor)."""
    empty = int(s.get("empty") or 0)
    if empty <= int(PARAMS.get("land2_empty_max", 4)):
        return True
    bud = _turn_budget(s)
    frac = float(PARAMS.get("hollow_plot3_fill_frac", 0.45))
    return bud.day_plantable < empty * frac


def _land_cow_min(s: dict[str, Any]) -> int:
    """Softer cow gate only on softfloor hollow (never densify printers)."""
    cow_min = int(PARAMS.get("land2_schedule_cow_min", 6))
    if not _softfloor_mode(s):
        return cow_min
    deep = int(PARAMS.get("softfloor_fill_empty_min", 16))
    hi = int(PARAMS.get("land2_hollow_empty_max", 45))
    empty = int(s.get("empty") or 0)
    if (
        int(s.get("n_quads") or 0) == 2
        and deep <= empty <= hi
        and int(s.get("day") or 0) <= int(PARAMS.get("hollow_land_day_max", 12))
        and _hollow_plot3_labor_ok(s)
    ):
        return int(PARAMS.get("land2_hollow_cow_min", 4))
    return cow_min


def _plot3_packed_ready(s: dict[str, Any]) -> bool:
    """Calendar + packed readiness (elite majority path).

    day∈[9,11], empty≤4, berry≥16 (or melon≥8), cows≥4, money≥land+500.
    Densify printers still use wider need_land paths; force-buy is gated
    separately via _plot3_qualified_buy (never EARLY_BERRY).
    """
    if int(s.get("n_quads") or 0) != 2:
        return False
    day = int(s.get("day") or 0)
    if day < int(PARAMS.get("plot3_cal_day_min", 9)):
        return False
    if day > int(PARAMS.get("plot3_cal_day_max", 11)):
        return False
    if int(s.get("empty") or 0) > int(PARAMS.get("land2_empty_max", 4)):
        return False
    if int(s.get("cows") or 0) < int(PARAMS.get("plot3_packed_cow_min", 4)):
        return False
    crops = s.get("crops") or {}
    berries = int(crops.get("STRAWBERRY", 0) or 0)
    melons = int(crops.get("MELON", 0) or 0)
    if berries < int(PARAMS.get("plot3_packed_berry_min", 16)) and melons < 8:
        return False
    cost = LAND_COST[min(int(s.get("n_quads") or 2) - 1, 2)]
    reserve = int(PARAMS.get("plot3_cal_cash_reserve", 500))
    return int(s.get("money") or 0) >= cost + reserve


def _plot3_hollow_ready(s: dict[str, Any]) -> bool:
    """Cash-hollow phase-2: money ≥ land + k×empty (rare ladder path).

    Off by default (`plot3_cash_hollow=0`). Never EARLY_BERRY densify.
    """
    if int(PARAMS.get("plot3_cash_hollow", 0)) != 1:
        return False
    if map_strategy(s) == "EARLY_BERRY":
        return False
    if int(s.get("n_quads") or 0) != 2:
        return False
    day = int(s.get("day") or 0)
    if day < int(PARAMS.get("plot3_cal_day_min", 9)):
        return False
    if day > int(PARAMS.get("plot3_cal_day_max", 11)):
        return False
    empty = int(s.get("empty") or 0)
    lo = int(PARAMS.get("plot3_hollow_empty_min", 8))
    hi = int(PARAMS.get("plot3_hollow_empty_max", 12))
    if empty < lo or empty > hi:
        return False
    if int(s.get("cows") or 0) < int(PARAMS.get("plot3_hollow_cow_min", 6)):
        return False
    berries = int((s.get("crops") or {}).get("STRAWBERRY", 0) or 0)
    if berries < int(PARAMS.get("plot3_hollow_berry_min", 11)):
        return False
    cost = LAND_COST[min(int(s.get("n_quads") or 2) - 1, 2)]
    need = cost + int(PARAMS.get("plot3_hollow_fill_per_empty", 400)) * empty
    return int(s.get("money") or 0) >= need


def _plot3_qualified_buy(s: dict[str, Any]) -> bool:
    """Force plot-3: calendar+packed, optional cash-hollow; never EARLY_BERRY."""
    if map_strategy(s) == "EARLY_BERRY":
        return False
    if _plot3_packed_ready(s):
        return True
    return _plot3_hollow_ready(s)


def _softfloor_calendar_land_ready(s: dict[str, Any]) -> bool:
    """Compat alias — calendar packed qualification."""
    return _plot3_qualified_buy(s)


def _herd_ready_for_land(s: dict[str, Any]) -> bool:
    return int(s.get("cows") or 0) >= int(PARAMS.get("land2_schedule_cow_min", 6))


def _hold_densify_for_expand(s: dict[str, Any]) -> bool:
    """Hold densify while finishing herd, or when land NPV is strongly positive."""
    if not _hollow_expand_window(s):
        return False
    day = int(s.get("day") or 0)
    if day > int(PARAMS.get("hollow_land_day_max", 14)):
        return False
    cow_min = int(PARAMS.get("land2_schedule_cow_min", 6))
    cows = int(s.get("cows") or 0)
    # Softfloor path: reserve cash for the last cow(s) before plot-3.
    if cows >= max(0, cow_min - 1) and cows < cow_min:
        return True
    if cows < cow_min:
        return False
    cost = LAND_COST[min(int(s.get("n_quads") or 1) - 1, 2)]
    return _expansion_npv_score(s, land_cost=cost) >= float(
        PARAMS.get("hollow_land_npv_min", 5000)
    )


def _apply_hollow_capital_bias(
    s: dict[str, Any],
    *,
    land_npv: float,
    cow_ev: float,
    seed_ev: float,
    defer_animals: bool,
) -> tuple[float, float, float]:
    """Herd-with-land: cows first, then land only when NPV clears a hard floor."""
    if defer_animals or not _hollow_expand_window(s):
        return land_npv, cow_ev, seed_ev
    cow_min = int(PARAMS.get("land2_schedule_cow_min", 6))
    boost = float(PARAMS.get("hollow_land_priority_boost", 1.0))
    cows = int(s.get("cows") or 0)
    if cows < cow_min and cow_ev > 0:
        cow_ev = max(cow_ev, seed_ev + boost)
    elif (
        cows >= cow_min
        and land_npv >= float(PARAMS.get("hollow_land_npv_min", 5000))
    ):
        land_npv = max(land_npv, seed_ev + boost, cow_ev + 0.5)
    return land_npv, cow_ev, seed_ev


def _seed_allowed_during_hollow(s: dict[str, Any], *, land_npv: float, cow_ev: float, afford: int) -> bool:
    """False when cash should stay reserved for cows or plot-3."""
    # Package B: berry stand must form before herd eats every dollar.
    if _lane_b_berry_gap(s) > 0:
        return True
    if not _hold_densify_for_expand(s):
        return True
    if cow_ev > 0 and afford >= ANIMAL_COST["COW"] and not _herd_ready_for_land(s):
        return False
    if land_npv > 0 and _herd_ready_for_land(s) and _will_buy_land(s, afford):
        return False
    return True


def _expansion_npv_score(s: dict[str, Any], *, land_cost: int) -> float:
    """Expand vs stay — crop fill EV + gated milk/egg/wool land unlock."""
    primary = _primary_cash(s)
    budget = _turn_budget(s)
    streams = _long_term_streams(s)
    seed_c = int(SEED_COST.get(primary or "WHEAT", 10))
    primary_ev = plan_ev(s, primary) if primary else 0.0
    # When the primary printer is weak/missing, lean on blended crop streams
    # (carrot/tomato/melon towns). Berry printers keep primary EV.
    w = float(PARAMS.get("lt_secondary_weight", 0.25))
    if primary_ev <= 0:
        tile_ev = streams.fill_tile_ev
    elif primary in ("CARROT", "TOMATO") or berry_sink(s) == 0:
        tile_ev = (1.0 - w) * primary_ev + w * streams.fill_tile_ev
    else:
        tile_ev = primary_ev
    empty = int(s.get("empty") or 0)
    soft = int(PARAMS.get("land_hollow_soft_cap", 14))
    # Honest spare-labor NPV only — no animal unlock boost on berry hollow
    # (that pushed losing plot-3 on seeds 7/99/123).
    animal = 0.0
    if (
        empty > soft
        and primary != "STRAWBERRY"
        and (
            milk_sink(s) > 0
            or egg_sink(s) > 0
            or int((s.get("demand") or {}).get("WOOL", 0) or 0) > 0
        )
    ):
        animal = streams.land_animal_unlock_ev * float(
            PARAMS.get("lt_land_animal_scale", 0.1)
        )
    return expand_vs_stay_advantage(
        workers=budget.workers,
        hungry=budget.hungry,
        live_tiles=budget.live_tiles,
        productive_days=_productive_days(s, for_land=True),
        tile_ev=tile_ev,
        land_cost=land_cost,
        seed_cost=seed_c,
        empty=empty,
        stand_factor=_stand_factor(s),
        realize=float(PARAMS.get("land_npv_realize", 0.7)),
        margin=float(PARAMS.get("land_expand_margin", 0.0)),
        animal_unlock_ev=animal,
    )


def _will_buy_land(s: dict[str, Any], afford: int) -> bool:
    if not need_land(s) or s["n_quads"] >= 4:
        return False
    cost = LAND_COST[s["n_quads"] - 1]
    # Calendar + packed (or cash-hollow): sticker already gated in ready helpers.
    if _plot3_qualified_buy(s):
        return afford >= LAND_COST[s["n_quads"] - 1]
    tp = s.get("turn_plan")
    ramp = tp.flags.in_late_ramp if tp else in_late_ramp(s)
    prof = tp.profile if tp else None
    seed_buffer = (
        prof.land_cash_buffer
        if prof and ramp
        else (
            int(PARAMS["late_ramp_land_cash_buffer"])
            if ramp
            else int(PARAMS["land_cash_buffer_default"])
        )
    )
    post_land_floor = (
        prof.post_land_floor
        if prof and ramp
        else (
            int(PARAMS["late_ramp_land_cash_buffer"])
            if ramp
            else int(PARAMS["land_post_floor_default"])
        )
    )
    if ramp:
        if int(s["money"]) < cost + seed_buffer:
            return False
    elif int(s["money"]) < land_bundle_cost(s):
        return False
    if afford < cost + seed_buffer:
        return False
    if s["n_quads"] >= 2 and afford - cost < post_land_floor:
        return False
    if not cash_shop(s) and not ramp:
        best_ev = max((plan_ev(s, c) for c in s["scores"]), default=0.0)
        if best_ev * 25 * max(3, days_left(s["day"]) // 2) < cost:
            return False
    # Plot 3+: multi-dawn expansion NPV (fat stands no longer zero day_plantable).
    if s["n_quads"] >= 2:
        primary = _primary_cash(s)
        budget = _turn_budget(s)
        seed_c = int(SEED_COST.get(primary or "WHEAT", 10))
        npv = _expansion_npv_score(s, land_cost=cost)
        if npv <= 0:
            return False
        fill_n = land_fillable_tiles(
            workers=budget.workers,
            hungry=budget.hungry,
            live_tiles=budget.live_tiles,
            productive_days=budget.productive_days,
            new_empty=25,
            short_horizon=False,
        )
        # Seed a realistic first wave, not fantasy 25×seed in one market hour.
        fill_cost = min(fill_n, max(8, budget.workers)) * seed_c
        live_ops = max(int(post_land_floor), int(budget.live_tiles) * 10)
        live_ops = min(live_ops, int(post_land_floor) * 2)
        if afford < cost + fill_cost + live_ops:
            return False
    return True


def cash_shop(s: dict[str, Any]) -> bool:
    d = s.get("demand") or {}
    return berry_sink(s) > 0 or d.get("CARROT", 0) > 0 or d.get("TOMATO", 0) > 0


def mouths_of(s: dict[str, Any]) -> int:
    return s["cows"] + s["sheep"] + s["geese"]


def wheat_stock(s: dict[str, Any]) -> int:
    return s["crops"]["WHEAT"] + s["seeds"].get("WHEAT", 0) + s["shed"].get("WHEAT", 0)


def herd_can_expand(s: dict[str, Any]) -> bool:
    """Expand when planted + stock cover the herd (thicker on milk-led boards)."""
    mouths = mouths_of(s)
    if mouths <= 0:
        return True
    planted = int(s["crops"].get("WHEAT", 0) or 0)
    milk_led = milk_sink(s) >= 1 and berry_sink(s) == 0
    buffer = int(PARAMS["wheat_buffer_add"])
    if milk_led:
        if planted < mouths + 2:
            return False
        return wheat_stock(s) >= mouths + 2
    # Berry / ice cream garnish: mouths planted + stock for buffer.
    if planted < mouths:
        return False
    return wheat_stock(s) >= mouths + buffer


def egg_sink(s: dict[str, Any]) -> int:
    return sum(1 for shop in s.get("shops") or [] if shop in ("BAKERY", "BRUNCH_SPOT"))


def demand_boost(demand: dict[str, int] | None, crop: str) -> float:
    """Shop demand multiplier — duplicate shops stack in `shop_demand()`."""
    d = int((demand or {}).get(crop, 0))
    linear = float(PARAMS["demand_boost_linear"])
    stack = float(PARAMS["demand_boost_stack"])
    return 1.0 + linear * d + stack * max(0, d - 2)


def demand_scaled_cap(base: int, demand_count: int, *, step: int) -> int:
    """Raise soft tile caps when multiple shops want the same product."""
    d = max(0, int(demand_count))
    if d <= 1:
        return base
    return base + step * (d - 1)


def ongoing_crop_score(crop: str, price: int, left: int, boost: float) -> float:
    """EV for mature ongoing crops after the standard plant window closes."""
    if crop not in ONGOING:
        return 0.0
    if left < int(PARAMS["ongoing_min_days_left"]):
        return 0.0
    base = int(BASE_PRICE.get(crop, price))
    if base <= 0 or price < base * float(PARAMS["ongoing_spike_price_factor"]):
        return 0.0
    cost = float(SEED_COST[crop])
    harvests = max(1, left // 2)
    return boost * (harvests * price - cost) / max(1.0, float(left))


def price_spike(s: dict[str, Any], item: str) -> bool:
    """True when the market price signals a demand-spike regime."""
    price = px(s, item)
    base = int(BASE_PRICE.get(item, 0))
    if base > 0 and price >= base * float(PARAMS["spike_sell_base_mult"]):
        return True
    # MA spike: only in the late window where hold logic would block sells.
    if days_left(s["day"]) > int(PARAMS["sell_hold_days_left_min"]) + 2:
        return False
    hist = float((s.get("price_ma") or {}).get(item, 0) or 0)
    delta = int((s.get("delta") or {}).get(item, 0) or 0)
    if hist > 0 and delta > 0 and price >= hist * float(PARAMS["spike_sell_ma_mult"]):
        return True
    return False


def _median_plan_ev(s: dict[str, Any], crops: list[str]) -> float:
    vals = sorted(plan_ev(s, c) for c in crops if plan_ev(s, c) > 0)
    if not vals:
        return 0.0
    mid = len(vals) // 2
    if len(vals) % 2:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def crop_score(
    crop: str, price: int, day: int, demand: dict[str, int] | None = None
) -> float:
    """Expected coins per tile-day at the live price. Shops boost via demand."""
    left = days_left(day)
    demand = demand or {}
    price = max(1, price)
    boost = demand_boost(demand, crop)
    if crop == "WHEAT":
        if left < 3:
            return 0.0
        return boost * (4 * price - 10) / 4.0
    if crop == "CARROT":
        if left < 3:
            return 0.0
        return boost * (3 * price - 20) / 3.0
    if crop == "MELON":
        if left < 10:
            return 0.0
        return boost * (6 * price - 80) / 10.0
    if crop == "TOMATO":
        if left < 8:
            return ongoing_crop_score("TOMATO", price, left, boost)
        n = min(4, left - 7)
        return boost * (n * price - 50) / min(12.0, left)
    if crop == "STRAWBERRY":
        if left < 8:
            return ongoing_crop_score("STRAWBERRY", price, left, boost)
        n = min(5, 1 + max(0, left - 8) // 2)
        return boost * (n * price - 100) / min(17.0, left)
    return 0.0


def animal_score(kind: str, price: int, day: int) -> float:
    left = days_left(day)
    first = ANIMAL_FIRST[kind]
    if left < first:
        return 0.0
    n = 1 + (left - first) // ANIMAL_INTERVAL[kind]
    feed = left * 10
    return (n * price - ANIMAL_COST[kind] - feed) / float(left)


def live_ev(s: dict[str, Any], crop: str) -> float:
    ev = s["scores"].get(crop, 0.0)
    g = glut(s, crop)
    if g > 0:
        ev *= max(0.4, 1.0 - 0.5 * g)
    elif g < 0:
        ev *= 1.0 + min(0.2, -g)
    return ev


def current_engine(s: dict[str, Any]) -> str:
    """BERRY / MILK / EGG — gates milk-only wheat, cow, and market rules."""
    if s.get("first_berry_day") is None:
        s["first_berry_day"] = _SHOP_TRACK.get("first_berry_day")
    if s.get("first_milk_day") is None:
        s["first_milk_day"] = _SHOP_TRACK.get("first_milk_day")
    s["engine"] = map_engine(
        milk_n=milk_sink(s),
        egg_n=egg_sink(s),
        first_berry_day=s.get("first_berry_day"),
        first_milk_day=s.get("first_milk_day"),
    )
    return s["engine"]


def tile_budget(s: dict[str, Any]) -> tuple[int, int, int]:
    tiles = s["n_quads"] * 25
    mouths = mouths_of(s)
    # Two bakeries also list WHEAT. Only a milk engine should keep feed
    # tiles ahead of mouths after wheat_engine_day_max (pizza starve fix).
    shop_wheat = (
        int((s.get("demand") or {}).get("WHEAT", 0) or 0) >= 2
        and current_engine(s) == "MILK"
    )
    keep_ahead = mouths and (
        s["day"] <= PARAMS["wheat_engine_day_max"] or shop_wheat
    )
    # Pizza/ice cream list WHEAT as a product; keep feed tiles ahead of mouths
    # or the extra cows starve (761083594: 6 cows → 2).
    if keep_ahead:
        wheat_tiles = max(
            PARAMS["wheat_min_tiles"], mouths + PARAMS["wheat_buffer_add"]
        )
    else:
        wheat_tiles = (
            max(PARAMS["wheat_min_tiles"], mouths)
            if mouths
            else PARAMS["wheat_no_mouth_tiles"]
        )
    # Berry ice-cream garnish still needs a feed floor even when leftover
    # strawberries own the cash room.
    if mouths and current_engine(s) == "BERRY":
        wheat_tiles = max(
            int(wheat_tiles), mouths + int(PARAMS["wheat_buffer_add"])
        )
    cash_room = max(0, tiles - mouths - wheat_tiles)
    return tiles, cash_room, wheat_tiles


def berry_tile_cap(s: dict[str, Any]) -> int:
    """Strawberries scale with land and stacked berry-shop demand."""
    berry_d = int((s.get("demand") or {}).get("STRAWBERRY", 0))
    step = int(PARAMS["demand_cap_step_berry"])
    return cash_tile_cap(
        int(s["n_quads"]), berry_d, primary=True, step=step, crop="STRAWBERRY"
    )


def _primary_cash(s: dict[str, Any]) -> str | None:
    return primary_cash_crop(
        s.get("demand"),
        viable={
            "STRAWBERRY": plan_viable(s, "STRAWBERRY"),
            "TOMATO": plan_viable(s, "TOMATO"),
            "CARROT": plan_viable(s, "CARROT"),
        },
        milk_n=milk_sink(s),
        first_berry_day=_SHOP_TRACK.get("first_berry_day"),
        first_milk_day=_SHOP_TRACK.get("first_milk_day"),
    )


def crop_plan(s: dict[str, Any]) -> dict[str, int]:
    """How many tiles of each crop to hold.

    Fill the engine cash crop to its cap. Leftover tiles become wheat on
    milk/egg maps (feed). They do not go to carrot/tomato EV — that is
    how farmers market leftover turned a berry town into a carrot field.
    """
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.crops
    _, room, wheat_tiles = tile_budget(s)
    plan = {c: 0 for c in SEED_COST}
    plan["WHEAT"] = wheat_tiles
    leftover = max(0, room - herd_tile_reserve(s, PARAMS))
    cap_bonus = min(int(PARAMS["cap_override_bonus_max"]), leftover)
    demand = s.get("demand") or {}

    def take(crop: str, cap: int) -> None:
        nonlocal leftover
        if leftover <= 0 or cap <= 0:
            return
        n = min(leftover, cap)
        plan[crop] = n
        leftover -= n

    candidates: list[str] = []
    if demand.get("STRAWBERRY", 0) >= 1 and (
        plan_viable(s, "STRAWBERRY") or _hold_engine_crop(s, "STRAWBERRY")
    ):
        candidates.append("STRAWBERRY")
    if demand.get("CARROT", 0) >= 1 and plan_viable(s, "CARROT"):
        candidates.append("CARROT")
    if demand.get("TOMATO", 0) >= 1 and (
        plan_viable(s, "TOMATO") or _hold_engine_crop(s, "TOMATO")
    ):
        candidates.append("TOMATO")

    cap_step = int(PARAMS["demand_cap_step_crop"])
    berry_step = int(PARAMS["demand_cap_step_berry"])
    primary = _primary_cash(s)
    cap_map: dict[str, int] = {}
    for c in candidates:
        is_primary = c == primary
        step = berry_step if c == "STRAWBERRY" else cap_step
        cap_map[c] = cash_tile_cap(
            int(s["n_quads"]),
            int(demand.get(c, 0)),
            primary=is_primary,
            step=step,
            crop=c,
        )

    med_ev = _median_plan_ev(s, candidates)
    override_mult = float(PARAMS["cap_override_ev_mult"])
    price_factor = float(PARAMS["cap_override_price_factor"])
    if med_ev > 0 and cap_bonus > 0:
        for c in candidates:
            base_px = int(BASE_PRICE.get(c, 0))
            px_now = px(s, c)
            if base_px <= 0 or px_now < base_px * price_factor:
                continue
            if plan_ev(s, c) > override_mult * med_ev:
                cap_map[c] = cap_map.get(c, 0) + cap_bonus

    # Softfloor speculative berry BEFORE primary tomato densify. Elites plant
    # berry from d6 on pizza/bakery; taking tomato first left strawberry plan=0
    # while seeds sat in inventory (seed 33).
    if leftover > 0 and _softfloor_speculative_berry(s):
        take(
            "STRAWBERRY",
            min(leftover, int(PARAMS.get("softfloor_berry_cap", 36))),
        )
    # Pre-calendar / Lane B pack: strawberry owns leftover until berry target
    # or empty approaches ≤4.
    if leftover > 0 and _pack_berry_active(s):
        have_b = int(s["crops"].get("STRAWBERRY", 0) or 0)
        target = int(PARAMS.get("pre_pack_berry_target", 20))
        empty = int(s.get("empty") or 0)
        pack_need = max(0, empty - int(PARAMS.get("land2_empty_max", 4)))
        need_b = max(0, target - have_b, pack_need)
        if need_b > 0:
            take("STRAWBERRY", min(leftover, need_b))
    # Densify-3 (elite): strawberry owns leftover until ~34 tiles — tomato
    # leftover was leaving empty@d16≈20 on seeds that already bought plot3.
    if leftover > 0 and _densify3_fill_active(s):
        have_b = int(s["crops"].get("STRAWBERRY", 0) or 0)
        target = int(PARAMS.get("densify3_berry_target", 34))
        need_b = max(0, target - have_b)
        if need_b > 0:
            take("STRAWBERRY", min(leftover, need_b))

    if primary and primary in cap_map:
        want = cap_map[primary]
        have = int(s["crops"].get(primary, 0) or 0)
        # Pack path: do not let tomato eat leftover before berry target.
        if (
            _pack_berry_active(s)
            and primary != "STRAWBERRY"
            and int(s["crops"].get("STRAWBERRY", 0) or 0)
            < int(PARAMS.get("pre_pack_berry_target", 20))
        ):
            want = min(want, have)
        # Berry engine with live EV owns leftover cash room (3q hole was
        # PRIMARY_TILE_BASE[3]=48 leaving ~15 tiles empty). Pizza leftover
        # still goes tomato-then-wheat below, not this branch.
        elif (
            berry_sink(s) > 0
            and primary == "STRAWBERRY"
            and plan_viable(s, "STRAWBERRY")
        ):
            want = leftover
        elif berry_sink(s) > 0 and primary == "STRAWBERRY":
            want = max(want, have)
        take(primary, want)

    # Pizza-first towns still plant berries when a berry shop opens later.
    # Carrots never get leftover — that was the old carrot bug.
    if primary != "STRAWBERRY" and "STRAWBERRY" in cap_map:
        take("STRAWBERRY", cap_map["STRAWBERRY"])

    # Milk-led leftover densifies primary a little, then wheat.
    milk_led = milk_sink(s) >= 1 and berry_sink(s) == 0
    if leftover > 0 and milk_led and primary and plan_viable(s, primary):
        extra = min(leftover, 8)
        plan[primary] = int(plan.get(primary, 0) or 0) + extra
        leftover -= extra

    # Melon filler before berry demand — bakery schedules from replays.
    # Day-0 opener is required for mean; do not globally defer melon for pizza.
    if (
        leftover >= int(PARAMS["melon_leftover_min"])
        and int(s["day"]) <= int(PARAMS["melon_day_max"])
        and int(s["n_quads"]) >= int(PARAMS["melon_n_quads_min"])
        and int(demand.get("STRAWBERRY", 0) or 0) == 0
        and live_ev(s, "MELON") > live_ev(s, "WHEAT")
    ):
        take("MELON", min(int(PARAMS["melon_cap"]), leftover))

    # Non-berry engines: leftover becomes tomato/carrot cash, not only wheat.
    # Berry maps still refuse a second cash crop (the old carrot leftover).
    if leftover > 0 and berry_sink(s) == 0:
        sec_cap = int(PARAMS.get("nonberry_secondary_cap", 20))
        for crop in ("TOMATO", "CARROT"):
            if leftover <= 0:
                break
            if crop == primary:
                continue
            if int(demand.get(crop, 0) or 0) < 1:
                continue
            if not (plan_viable(s, crop) or _hold_engine_crop(s, crop)):
                continue
            have = int(plan.get(crop, 0) or 0)
            room_c = max(0, sec_cap - have)
            if room_c <= 0:
                continue
            take(crop, room_c)

    # Feed leftover. Berry maps leave the hole empty rather than flooding
    # wheat over strawberries; only top up wheat when feed floor is short.
    if leftover > 0 and (
        milk_led or int(demand.get("STRAWBERRY", 0) or 0) == 0
    ):
        plan["WHEAT"] += leftover
    elif leftover > 0:
        mouths = mouths_of(s)
        feed_floor = mouths + int(PARAMS["wheat_buffer_add"]) if mouths else 0
        wheat_have = int(s["crops"].get("WHEAT", 0) or 0) + int(
            s["seeds"].get("WHEAT", 0) or 0
        )
        short = max(0, feed_floor - wheat_have - int(plan["WHEAT"]))
        plan["WHEAT"] += min(leftover, short)

    # Tomato densify only — berry engines keep their plan. Caps the stand to
    # what the crew can water after wheat + live/planned berries.
    tom_plan = int(plan.get("TOMATO", 0) or 0)
    if tom_plan > 0:
        hands = max(want_hands(s), int(s.get("workers") or 1))
        clearing = max(
            8,
            int(0.5 * crew_live_cap(workers=hands, mouths=mouths_of(s))),
        )
        wheat_n = int(plan.get("WHEAT", 0) or 0)
        berry_n = max(
            int(plan.get("STRAWBERRY", 0) or 0),
            int(s["crops"].get("STRAWBERRY", 0) or 0),
        )
        room = max(8, clearing - wheat_n - berry_n)
        # Waiting on the first berry shop: keep a modest tomato printer, leave
        # empty for the strawberry pivot (do not cap after berries exist).
        if (
            berry_sink(s) == 0
            and milk_sink(s) >= 1
            and int(s.get("day", 0)) >= int(PARAMS.get("berry_prep_day_min", 11))
        ):
            room = min(room, int(PARAMS.get("late_berry_tomato_cap", 12)))
        have_t = int(s["crops"].get("TOMATO", 0) or 0)
        if int(s.get("unwatered") or 0) > hands or int(s.get("at_risk") or 0) > 0:
            room = min(room, have_t)
        plan["TOMATO"] = min(tom_plan, room)
    return plan


def berry_ok(s: dict[str, Any]) -> bool:
    return crop_plan(s).get("STRAWBERRY", 0) > 0


def carrot_ok(s: dict[str, Any]) -> bool:
    return crop_plan(s).get("CARROT", 0) > 0


def melon_ok(s: dict[str, Any]) -> bool:
    return crop_plan(s).get("MELON", 0) > 0


def cash_caps(s: dict[str, Any]) -> tuple[int, int]:
    plan = crop_plan(s)
    return plan["STRAWBERRY"], plan["CARROT"]


def want_cows(s: dict[str, Any]) -> int:
    """Expand cows from shop target; berry path uses cow-vs-seed EV."""
    schedule_want = _softfloor_schedule_cow_want(s)
    if schedule_want is not None:
        return schedule_want
    target = cow_target(s, PARAMS)
    floor = int(PARAMS["cow_floor"]) if s["day"] <= PARAMS["cow_floor_day_max"] else 0
    if s["cows"] < floor:
        return min(s["cows"] + 1, max(target, floor))
    # Milk-led = pizza densify (milk shops, no berry). Else ice-cream garnish.
    milk_led = milk_sink(s) >= 1 and berry_sink(s) == 0
    if not milk_led:
        # Melon→cow bridge before berry EV clears. Softfloor/meta elites stock
        # ~8–10 cows by d10 on berry opens (not only ice/smoothie dual shops).
        # Keep bridging after melons clear so harvest does not stall the herd.
        melons = int(s["crops"].get("MELON", 0) or 0)
        berry_open = berry_sink(s) >= 1
        dual = sum(
            1
            for sh in (s.get("shops") or [])
            if sh in ("ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
        )
        bridge_cap = int(PARAMS.get("melon_bridge_cow_cap", 5))
        if berry_open:
            bridge_cap = max(
                bridge_cap, int(PARAMS.get("berry_melon_bridge_cow_cap", 8))
            )
        melon_min = int(PARAMS.get("melon_bridge_melon_min", 6))
        bridge_fuel = melons >= melon_min or (
            berry_open and int(s["cows"]) >= int(PARAMS.get("cow_floor", 2))
        )
        if (
            int(s["day"]) <= int(PARAMS.get("melon_bridge_cow_day_max", 12))
            and s["n_quads"] >= 2
            and (dual >= 1 or berry_open)
            and bridge_fuel
            and herd_can_expand(s)
            and s["cows"] < bridge_cap
        ):
            return min(s["cows"] + 1, bridge_cap)
        if target > s["cows"] and s["n_quads"] >= 2 and herd_can_expand(s):
            primary = _primary_cash(s)
            budget = _turn_budget(s)
            seed_c = int(SEED_COST.get(primary or "STRAWBERRY", 100))
            # Schedule herd: keep ramping toward target without losing every
            # buy to strawberry seed EV (opp ran 10 cows on 1286627911).
            schedule_herd = (
                berry_open
                and int(s["day"]) <= 16
                and int(s["cows"])
                < min(target, int(PARAMS.get("berry_melon_bridge_cow_cap", 8)))
            )
            if schedule_herd or cow_beats_seeds(
                cow_ev=animal_score("COW", milk_px(s), s["day"]),
                tile_ev=budget.tile_ev,
                cow_cost=int(ANIMAL_COST["COW"]),
                seed_cost=seed_c,
                plantable=budget.plantable,
                empty=int(s.get("empty") or 0),
                buy_gap=crop_gap(crop_plan(s), s, primary) if primary else 0,
            ):
                return min(s["cows"] + 1, target)
        return s["cows"]
    pizza_1q = s["n_quads"] == 1 and milk_sink(s) >= 2
    if s["n_quads"] == 1 and not pizza_1q:
        return s["cows"]
    if not herd_can_expand(s):
        return s["cows"]
    cap = int(PARAMS["cow_expand_cap"])
    if milk_sink(s) >= 3:
        cap = max(cap, int(PARAMS["cow_stack_cap"]))
    mouth_cap = (
        int(PARAMS["mouth_cap_1q"]) if s["n_quads"] == 1 else int(PARAMS["mouth_cap_2qplus"])
    )
    cap = min(cap, max(0, mouth_cap - s["sheep"] - s["geese"]))
    goal = min(target, cap)
    if s["cows"] < goal:
        return min(s["cows"] + 1, goal)
    return s["cows"]


def want_sheep(s: dict[str, Any]) -> int:
    if s["day"] > PARAMS["sheep_day_max"] or wool_px(s) < PARAMS["sheep_wool_px_min"]:
        return s["sheep"]
    floor = PARAMS["sheep_floor"] if s["day"] <= PARAMS["sheep_floor_day_max"] else 0
    if s["sheep"] < floor:
        return floor
    wool_d = int(s["demand"].get("WOOL", 0))
    # No wool demand → don't expand (pasture and water would compete).
    if wool_d <= 0:
        return s["sheep"]
    # Yarn-stacked 1-quad towns still need wool mouths; waiting for land2
    # left seed 99 on 2 sheep while two yarn stores printed demand.
    if s["n_quads"] == 1 and wool_d < 2:
        return s["sheep"]
    if not herd_can_expand(s):
        return s["sheep"]
    wool_target = min(
        int(PARAMS["sheep_expand_cap"]),
        max(int(floor), int(PARAMS["wool_herd_base"]) + wool_d),
    )
    if s["sheep"] < wool_target:
        return min(s["sheep"] + 1, wool_target)
    return min(s["sheep"] + 1, int(PARAMS["sheep_expand_cap"]))


def want_geese(s: dict[str, Any]) -> int:
    if s["day"] > 20 or egg_sink(s) == 0:
        return s["geese"]
    egg_px = px(s, "EGG")
    goose_ev = animal_score("GOOSE", egg_px, s["day"])
    sinks = egg_sink(s)
    # Saturated egg-shop maps (2× bakery + brunch) need cash for berries, not geese.
    if sinks >= 3 and egg_px < 80:
        return s["geese"]
    if egg_px < 55 or goose_ev <= 12:
        return s["geese"]
    if egg_px < 80 and goose_ev <= 15:
        return s["geese"]
    max_geese = 1 if s["n_quads"] <= 2 else 2
    if s["geese"] >= max_geese:
        return s["geese"]
    if s["n_quads"] == 1 and mouths_of(s) >= 4:
        return s["geese"]
    if not herd_can_expand(s):
        return s["geese"]
    # Scale goose target with egg-shop count when eggs are priced well.
    egg_target = max_geese
    if sinks >= 2 and egg_px >= 65:
        egg_target = min(max_geese, 1 + (sinks - 1) // 2)
    if s["geese"] < egg_target:
        return min(s["geese"] + 1, egg_target)
    return min(s["geese"] + 1, max_geese)


def need_land(s: dict[str, Any]) -> bool:
    """Safety + readiness gates; expansion NPV decides affordability/score."""
    ramp = in_late_ramp(s)
    if (
        s["day"] < PARAMS["land_day_min"]
        or s["n_quads"] >= PARAMS["max_quads_for_land"]
    ):
        return False
    if s["n_quads"] == 1 and s["day"] >= PARAMS["land_day_max"]:
        return False
    if s["n_quads"] == 2 and s["day"] >= PARAMS["land2_day_max"]:
        return False
    strat = map_strategy(s)
    gap = berry_gap(s)
    bok = berry_ok(s)
    lshop = late_shop_sprint(s)
    ramp_active = berry_ramp(s) if not s.get("turn_plan") else False
    tp = s.get("turn_plan")
    if tp is not None:
        ramp_active = tp.flags.berry_ramp
        lshop = tp.flags.late_shop_sprint
        bok = tp.flags.berry_ok
        gap = tp.berry_gap
    # Calendar packed: bypass densify board-fill when ready.
    if land_blocked_by_board_fill(
        s,
        PARAMS,
        berry_gap=gap,
        berry_ok=bok,
        late_shop_sprint=lshop,
        berry_ramp=ramp_active,
        strategy=strat,
    ) and not _plot3_qualified_buy(s):
        return False
    relax = land_ramp_relax(s)
    if s["n_quads"] == 1 and s["empty"] > strategy_quad1_empty_cap(
        strat, PARAMS, relax=relax
    ):
        return False
    _, cash_room, _ = tile_budget(s)
    if s["n_quads"] == 1:
        empty_max = strategy_quad1_empty_cap(strat, PARAMS, relax=relax)
        if s["empty"] > empty_max:
            return False
        if s["empty"] <= 8:
            return True
        if s["empty"] <= empty_max and cash_shop(s) and s["day"] <= 7:
            return True
        if cash_room <= 4 and cash_shop(s):
            return True
        if s["seeds"].get("STRAWBERRY", 0) >= 4 and s["empty"] <= strategy_quad1_empty_cap(
            strat, PARAMS, relax=relax, seed_buy=True
        ):
            return True
        return False
    if s["n_quads"] == 2:
        # Calendar + packed readiness; densify keeps stand_ok path below.
        berries = int(s["crops"].get("STRAWBERRY", 0) or 0)
        melons = int(s["crops"].get("MELON", 0) or 0)
        tomatoes = int(s["crops"].get("TOMATO", 0) or 0)
        milk_only = (milk_sink(s) >= 1 and berry_sink(s) == 0) or strat == "MILK_STACK"
        if strat == "LAND_SPRINT" and berries < int(
            PARAMS.get("land2_sprint_strawberry_min", 24)
        ):
            return False
        from brain.schedules import berry_land2_day, berry_land2_strawberry_floor

        land2_day = berry_land2_day(int(PARAMS["land2_day_min"]))
        if int(s["day"]) < max(int(PARAMS["land2_day_min"]), land2_day - 1):
            return False
        if int(s["day"]) > int(PARAMS.get("land2_day_max", 22)):
            return False
        # Softfloor: only calendar+packed (no broke mid-empty expands).
        if _softfloor_mode(s):
            return _plot3_qualified_buy(s)
        money_min = int(PARAMS["land2_money_min"])
        cow_min = _land_cow_min(s)
        full_cow_min = int(PARAMS.get("land2_schedule_cow_min", 6))
        packed = _plot3_packed_ready(s)
        if packed:
            money_min = min(money_min, int(PARAMS.get("land2_dense_money_min", 2500)))
        if berries >= 16 and int(s["cows"]) >= full_cow_min:
            money_min = min(money_min, int(PARAMS.get("land2_dense_money_min", 2500)))
        if (
            milk_sink(s) >= 1
            and int(s["cows"]) >= full_cow_min
            and int(PARAMS.get("land_hollow_soft_cap", 14))
            < int(s["empty"])
            <= int(PARAMS.get("land2_hollow_empty_max", 45))
        ):
            money_min = min(money_min, int(PARAMS.get("land2_dense_money_min", 2500)))
        if int(s["money"]) < money_min:
            return False
        empty_max = int(PARAMS["land2_empty_max"])
        stand_ok = berries >= 12 or melons >= 6 or (
            milk_only and tomatoes >= int(PARAMS.get("land2_tomato_min", 12))
        )
        if int(s["cows"]) >= cow_min and stand_ok and (
            packed or (_softfloor_mode(s) and _hollow_plot3_labor_ok(s))
        ):
            empty_max = max(
                empty_max, int(PARAMS.get("land2_schedule_empty_max", 55))
            )
        if berries >= 16 and int(s["cows"]) >= full_cow_min:
            empty_max = max(empty_max, int(PARAMS.get("land2_dense_empty_max", 8)))
        # Non-densify: no late mid-empty expand past elite calendar window.
        if (
            map_strategy(s) != "EARLY_BERRY"
            and int(s["empty"]) > int(PARAMS["land2_empty_max"])
            and int(s["day"]) > int(PARAMS.get("plot3_cal_day_max", 11))
        ):
            return False
        if s["empty"] > empty_max:
            return False
        if int(s["cows"]) < cow_min:
            return False
        if packed:
            return True
        if milk_only and not stand_ok:
            return False
        if berry_sink(s) > 0 and not milk_only:
            berry_min = berry_land2_strawberry_floor(int(PARAMS["land2_strawberry_min"]))
            if berries < berry_min and melons < 6:
                return False
        elif not milk_only and berry_sink(s) == 0 and milk_sink(s) == 0:
            return False
        return stand_ok or (
            berry_sink(s) > 0 and berries >= int(PARAMS["land2_strawberry_min"])
        )
    if s["n_quads"] == 3:
        # Plot 4 — softfloor/elite tails; NPV still decides after readiness.
        if int(s["day"]) < int(PARAMS.get("land3_day_min", 13)):
            return False
        if int(s["day"]) > int(PARAMS.get("land3_day_max", 20)):
            return False
        if int(s["money"]) < int(PARAMS.get("land3_money_min", 4500)):
            return False
        if int(s["cows"]) < int(PARAMS.get("land2_schedule_cow_min", 6)):
            return False
        if berry_sink(s) == 0 and milk_sink(s) == 0 and egg_sink(s) == 0:
            return False
        berries = int(s["crops"].get("STRAWBERRY", 0) or 0)
        tomatoes = int(s["crops"].get("TOMATO", 0) or 0)
        return max(berries, tomatoes) >= int(PARAMS.get("land_stand_ready_min", 10))
    return False


def plan_turn(s: dict[str, Any]) -> TurnPlan:
    """Single planning pass: crop targets, regime phase, market route, field mode."""
    crops = crop_plan(s)
    primary = _primary_cash(s)
    berry_gap_n = crop_gap(crops, s, "STRAWBERRY")
    cash_gap_n = crop_gap(crops, s, primary)
    left = days_left(s["day"])
    demand = s.get("demand") or {}
    # Stacked shops raise tile caps. They are not a sell-mode switch.
    # Two bakeries used to flip SPIKE for the rest of seed 42.
    demand_stack = any(
        int(demand.get(c, 0)) >= 2
        for c in ("TOMATO", "STRAWBERRY", "CARROT", "EGG")
    )
    spikes = {item: price_spike(s, item) for item in BASE_PRICE}
    late_ongoing = left < 8 and any(
        px(s, c) >= int(BASE_PRICE[c]) * float(PARAMS["ongoing_spike_price_factor"])
        for c in ONGOING
    )
    lshop = late_shop_sprint(s)
    prep = berry_prep_active(s)
    cash_deficit = _cash_deficit(s)
    liquidity_stress = cash_deficit >= 900
    from brain.schedules import late_dump_day

    dump_day = late_dump_day(int(PARAMS["liquidate_day_min"]))
    endgame = left <= int(PARAMS["endgame_days_left"]) or s["day"] >= dump_day
    bok = crops.get("STRAWBERRY", 0) > 0
    strat = map_strategy(s)
    cash_ramp_n = crop_is_ramping(s, primary, crops, late=lshop)
    berry_ramp_n = crop_is_ramping(s, "STRAWBERRY", crops, late=lshop)
    # Collect flags before turn_plan exists (helpers fall through to live compute).
    fill_pressure = board_fill_pressure(
        s,
        PARAMS,
        berry_gap=max(berry_gap_n, cash_gap_n),
        berry_ok=bok or cash_gap_n > 0,
        late_shop_sprint=lshop,
        berry_ramp=berry_ramp_n or cash_ramp_n,
        plant_sprint=plant_sprint(s),
        strategy=strat,
    )
    cash_crop = primary or ""
    field_target = int(crops.get(cash_crop, 0) or 0) if cash_crop else 0
    field_short = (
        field_target > 0
        and plant_gap(crops, s, cash_crop) > 0
        and int(s.get("empty", 0) or 0) > 0
        and engine_replant_open(s)
    )
    flags = TurnFlags(
        late_shop_sprint=lshop,
        berry_prep=prep,
        plant_sprint=plant_sprint(s),
        berry_ramp=berry_ramp_n,
        seed_fill_push=seed_fill_push(s),
        berry_replant_push=berry_replant_push(s),
        in_late_ramp=lshop,
        land_ramp_relax=_compute_land_ramp_relax(
            s, strategy=strat, berry_gap=max(berry_gap_n, cash_gap_n), lshop=lshop
        ),
        board_fill_pressure=fill_pressure,
        need_land=need_land(s),
        berry_ok=bok,
        liquidity_stress=liquidity_stress,
        late_ongoing=late_ongoing,
        demand_stack=demand_stack,
        price_spike=spikes,
        cash_ramp=cash_ramp_n,
        field_short=field_short,
    )
    tp = build_turn_plan(
        s,
        PARAMS,
        crops=crops,
        berry_gap=berry_gap_n,
        flags=flags,
        cash_deficit=cash_deficit,
        days_left=left,
        endgame=endgame,
        strategy=strat,
    )
    tp.cash_crop = primary or ""
    tp.cash_gap = cash_gap_n
    tile_ev = plan_ev(s, primary) if primary else 0.0
    prod_days = _productive_days(s)
    tp.budget = compute_turn_budget(
        s, cash_crop=tp.cash_crop, tile_ev=tile_ev, productive_days=prod_days
    )
    # Multi-stream snapshot for land/animal decisions this hour.
    s["lt_streams"] = _long_term_streams(s)
    s["turn_plan"] = tp
    s["regime"] = tp.regime
    return tp


def _land2_crew_spike(s: dict[str, Any]) -> bool:
    """Frontier-style hire spike after plot-3: fill the new 25 empties.

    Softfloor winners jump to ~12–14 hands on land2 day; we were buying
    plot-3 then sitting on empty@d16≈29 (seed 33). Only fire post-buy —
    pre-buy spikes spent cash and blocked land.
    """
    day = int(s.get("day") or 0)
    empty = int(s.get("empty") or 0)
    n_quads = int(s.get("n_quads") or 0)
    empty_min = int(PARAMS.get("land2_hire_empty_min", 16))
    if n_quads < 3 or empty < empty_min:
        return False
    if day <= int(PARAMS.get("hollow_land_day_max", 12)) + 3:
        return True
    return int(_LAND_SPRINT.get("until_day", -1)) >= day


def _densify3_fill_active(s: dict[str, Any]) -> bool:
    """Elite densify-3: after plot-3, pack empties with berry (not tomato).

    Live elite decode (structured/frontier/boatlee/top10/hamburger × softfloor):
    land2 day hire median 12–14; berry +16 in 2d; empty back toward 2–4.
    Us on 3141/993781610: hire ok but berry +9 and empty stays ~20.
    """
    if int(PARAMS.get("densify3_fill_enabled", 1)) != 1:
        return False
    if int(s.get("n_quads") or 0) < 3:
        return False
    day = int(s.get("day") or 0)
    if day > int(PARAMS.get("densify3_day_max", 15)):
        return False
    empty = int(s.get("empty") or 0)
    if empty < int(PARAMS.get("densify3_empty_min", 12)):
        return False
    # Densify printers stay packed on 2q — never empty≥12 on 3q. Softfloor
    # EARLY_BERRY 3q hollow still gets the fill (berry boards).
    if berry_sink(s) > 0:
        return True
    if "PIZZA_SHOP" in set(s.get("shops") or []):
        return True
    return _softfloor_mode(s) or int(_LAND_SPRINT.get("until_day", -1)) >= day


def want_hands(s: dict[str, Any]) -> int:
    """Rehire every morning sized to water debt + herd, not only quads."""
    if s["day"] == 0:
        return 5
    # Clear dry tiles by dusk with ~55% pathing efficiency (see water_risk).
    debt = max(int(s.get("unwatered") or 0), int(s.get("at_risk") or 0))
    live = 0
    crops = s.get("crops") or {}
    for c in ("TOMATO", "STRAWBERRY", "CARROT", "MELON", "WHEAT"):
        live += int(crops.get(c, 0) or 0)
    water_load = max(debt, live)
    # Full crew after dawn hire lag ≈ 10 useful hours × 0.55 ≈ 5.5 tiles/worker.
    cover = (water_load + 4) // 5
    base = 5
    if s["n_quads"] >= 2 or mouths_of(s) >= 8:
        base = 12
    elif mouths_of(s) >= 1 or berry_ok(s):
        base = 8
    # Feeders share the crew — leave room above pure water cover.
    need = cover + max(0, mouths_of(s) // 3)
    # Follow the elite hire curve (ladder $85k+ winners hit ~9–10 hands by d6–8).
    if int(s["day"]) <= 15 and (berry_sink(s) > 0 or engine_of(s) == "BERRY"):
        from brain.schedules import hire_target_day

        need = max(need, hire_target_day(int(s["day"]), default=base))
    # Softfloor router: top-corpus crew (≥10 by d7–8) while hollow.
    if _softfloor_mode(s) and int(s["day"]) <= 12:
        from brain.schedules import softfloor_hire_target_day

        need = max(need, softfloor_hire_target_day(int(s["day"]), default=9))
    if _land2_crew_spike(s) or _densify3_fill_active(s):
        need = max(need, int(PARAMS.get("land2_hire_target", 13)))
        need = max(need, int(PARAMS.get("densify3_hire_target", 13)))
    return min(MAX_HANDS, max(base, need))


def hire_burst_cap(s: dict[str, Any]) -> int:
    """Dawn hire burst when water debt outruns the default 5."""
    hour = int(s.get("hour") or 0)
    if hour > 2:
        return HIRES_PER_TURN
    if _land2_crew_spike(s) or _densify3_fill_active(s):
        return min(
            MAX_HANDS,
            int(PARAMS.get("densify3_hire_burst", PARAMS.get("land2_hire_burst", 12))),
        )
    if hire_water_pressure(s):
        return min(MAX_HANDS, 9)
    return HIRES_PER_TURN


def _hire_budget(s: dict[str, Any], market: list, *, reserve_land: bool) -> int:
    """Leave slots for land, berries, wheat seeds, and emergency feed."""
    reserved = 0
    hour = int(s.get("hour") or 0)
    # Dawn crew first when true water pressure — skip densify/land reserves.
    # Softfloor land2: same — fill crew before seed stockpile eats the 10-cap.
    crew_first = hour <= 2 and (
        hire_water_pressure(s) or _land2_crew_spike(s) or _densify3_fill_active(s)
    )
    if not crew_first:
        if reserve_land:
            reserved += 1
        if berry_ok(s) and berry_gap(s) > 0:
            reserved += 1
        elif (s.get("turn_plan") and int(getattr(s["turn_plan"], "cash_gap", 0) or 0) > 0):
            reserved += 1
        elif crop_gap(crop_plan(s), s, _primary_cash(s)) > 0:
            reserved += 1
        _, _, wheat_tiles = tile_budget(s)
        if s["crops"]["WHEAT"] + s["seeds"].get("WHEAT", 0) < wheat_tiles:
            reserved += 1
        if _feed_crisis(s):
            reserved += 1
        if s["empty"] >= 12 and s["day"] <= 18 and int(s.get("unwatered") or 0) == 0:
            reserved += 1
    elif _feed_crisis(s):
        reserved = 1
    left = max(0, MARKET_LIMIT - len(market) - reserved)
    return min(hire_burst_cap(s), left)


def shop_demand(shops: list | None) -> dict[str, int]:
    demand = {k: 0 for k in BASE_PRICE}
    for name in shops or []:
        products = SHOP_PRODUCTS.get(name, [])
        mult = 2 if len(products) == 1 else 1
        for item in products:
            demand[item] = demand.get(item, 0) + mult
    return demand


def crop_ready(tile, day, early_wheat: bool = False):
    crop = tile.get("crop")
    if crop in ONGOING:
        return tile.get("yield_units", 0) > 0
    yield_u = tile.get("yield_units", 0)
    fert = tile.get("fertilized_until_day", -1)
    cap = YIELD_CAP.get(crop, 4)
    if fert >= 0 and crop == "WHEAT":
        cap = 6
    if fert >= 0 and crop == "CARROT":
        cap = 4
    if yield_u >= cap:
        return True
    age = day - tile["planted_day"]
    if crop == "WHEAT" and early_wheat and yield_u > 0 and age >= 2:
        return True
    return age >= HARVEST_AGE.get(crop, 4)


def tile_census(tiles):
    crops = {k: 0 for k in SEED_COST}
    empty = 0
    animals = {k: 0 for k in ANIMAL_COST}
    empty_struct = {"COOP": 0, "PASTURE": 0}
    hungry = 0
    fert_ready = 0
    unwatered = 0
    at_risk = 0
    load = 0
    for row in tiles:
        for t in row:
            if t is None:
                empty += 1
            elif not isinstance(t, dict):
                continue
            elif t.get("kind") == "PLANT":
                crop = t.get("crop")
                if crop in crops:
                    crops[crop] += 1
                load += 1
                if not t.get("watered_today"):
                    unwatered += 1
                    if t.get("consecutive_unwatered", 0) >= 1:
                        at_risk += 1
            elif t.get("kind") in ("COOP", "PASTURE"):
                animal = t.get("animal")
                if animal in animals:
                    animals[animal] += 1
                    load += 1
                    if not t.get("fed_today"):
                        hungry += 1
                    if t.get("fertilizer_available"):
                        fert_ready += 1
                else:
                    empty_struct[t["kind"]] += 1
    return {
        "crops": crops,
        "empty": empty,
        "animals": animals,
        "empty_struct": empty_struct,
        "hungry": hungry,
        "fert_ready": fert_ready,
        "unwatered": unwatered,
        "at_risk": at_risk,
        "load": load,
    }


def read_signals(obs: dict[str, Any]) -> dict[str, Any]:
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    census = tile_census(me["tiles"])
    prices = obs["market"]["prices"]
    day = obs["day"]
    shops = list(obs.get("town", {}).get("unlocked_shops", []))
    demand = shop_demand(shops)
    scores = {
        c: crop_score(c, int(prices.get(c, BASE_PRICE[c])), day, demand)
        for c in SEED_COST
    }
    a_scores = {
        a: animal_score(
            a, int(prices.get(ANIMAL_PRODUCT[a], BASE_PRICE[ANIMAL_PRODUCT[a]])), day
        )
        for a in ANIMAL_COST
    }
    best_crop = max(scores, key=lambda c: scores[c])
    return {
        "day": day,
        "hour": obs["hour"],
        "money": me["money"],
        "n_quads": len(me["unlocked_quadrants"]),
        "workers": 1 + len(me["hands"]),
        "hires_today": me["hires_today"],
        "crops": census["crops"],
        "empty": census["empty"],
        "animals": census["animals"],
        "cows": census["animals"]["COW"] + private["shed"].get("COW", 0),
        "geese": census["animals"]["GOOSE"] + private["shed"].get("GOOSE", 0),
        "sheep": census["animals"]["SHEEP"] + private["shed"].get("SHEEP", 0),
        "empty_struct": census["empty_struct"],
        "hungry": census["hungry"],
        "fert_ready": census["fert_ready"],
        "unwatered": census["unwatered"],
        "at_risk": census["at_risk"],
        "load": census["load"],
        "seeds": {c: private["seeds"].get(c, 0) for c in SEED_COST},
        "shed": private["shed"],
        "prices": prices,
        "inventory": dict(obs.get("market", {}).get("inventory") or {}),
        "scores": scores,
        "a_scores": a_scores,
        "best_crop": best_crop,
        "shops": shops,
        "demand": demand,
        "milk_sink": sum(1 for shop in shops if shop in MILK_SHOPS),
        "berry_sink": sum(1 for shop in shops if shop in BERRY_SHOPS),
    }


def pick_mode(s: dict[str, Any]) -> str:
    tp = s.get("turn_plan")
    if tp is not None:
        return tp.mode
    from brain.schedules import late_dump_day

    dump = late_dump_day(int(PARAMS["liquidate_day_min"]))
    if s["day"] >= dump:
        return "LIQUIDATE"
    return "ENGINE"


def field_water_stress(s: dict[str, Any]) -> bool:
    """Crew–tile risk: dry field outruns remaining hands before dusk."""
    hour = int(s.get("hour") or 0)
    workers = max(1, int(s.get("workers") or 1))
    # Hands clear overnight — size morning risk to the hire target, not roster=1.
    if hour <= 2:
        workers = max(workers, min(MAX_HANDS, want_hands(s)))
    return water_stress(
        unwatered=int(s.get("unwatered") or 0),
        at_risk=int(s.get("at_risk") or 0),
        workers=workers,
        hour=hour,
    )


def hire_water_pressure(s: dict[str, Any]) -> bool:
    """Market hire urgency — ignore dawn workers=1 false alarm (hands clear overnight)."""
    if int(s.get("at_risk") or 0) > 0:
        return True
    crops = s.get("crops") or {}
    ongoing = int(crops.get("TOMATO", 0) or 0) + int(crops.get("STRAWBERRY", 0) or 0)
    live = ongoing
    for c in ("CARROT", "MELON", "WHEAT"):
        live += int(crops.get(c, 0) or 0)
    if live < 12:
        return False
    hour = int(s.get("hour") or 0)
    # Dense ongoing stands need a dawn burst — wheat filler does not.
    if hour <= 2 and ongoing >= 20:
        return True
    return water_stress(
        unwatered=max(int(s.get("unwatered") or 0), live),
        at_risk=int(s.get("at_risk") or 0),
        workers=MAX_HANDS,
        hour=max(2, hour),
    )


def cash_waiting(s: dict[str, Any], seeds: dict[str, int] | None = None) -> bool:
    # Late-day water crisis / at-risk: don't densify over saving tiles.
    if int(s.get("at_risk") or 0) > 0:
        return False
    if int(s.get("hour") or 0) >= 6 and field_water_stress(s):
        return False
    seeds = seeds if seeds is not None else s["seeds"]
    plan = crop_plan(s)
    if any(
        seeds.get(crop, 0) > 0 and s["crops"][crop] < plan.get(crop, 0)
        for crop in CASH_PLANT
    ):
        return True
    # Sunk engine seeds: inventory is a buy-side budget, not a plant stop.
    primary = _primary_cash(s)
    return bool(
        primary
        and seeds.get(primary, 0) > 0
        and int(s.get("empty") or 0) > 0
        and engine_replant_open(s)
        and (plan.get(primary, 0) > 0 or _hold_engine_crop(s, primary))
    )


def wheat_waiting(s: dict[str, Any], seeds: dict[str, int] | None = None) -> bool:
    seeds = seeds if seeds is not None else s["seeds"]
    mouths = mouths_of(s)
    # Slice A: `crop_plan(s)["WHEAT"]` may include filler wheat. We only
    # want BUILD_PASTURE to wait for the `mouths + 2` wheat floor.
    _, _, wheat_tiles = tile_budget(s)
    floor = max(4, wheat_tiles) if mouths > 0 else 0
    if mouths > 0 and s["crops"]["WHEAT"] == 0 and seeds.get("WHEAT", 0) > 0:
        return True
    return seeds.get("WHEAT", 0) > 0 and s["crops"]["WHEAT"] < floor


def pick_crop(s: dict[str, Any], seeds: dict[str, int]) -> str | None:
    plan = crop_plan(s)
    shed_w = s["shed"].get("WHEAT", 0)
    mouths = mouths_of(s)
    # Feed floor is tile_budget, not leftover wheat in the plan. Otherwise
    # milk leftover wheat plants before the primary cash crop.
    _, _, feed_wheat = tile_budget(s)
    wheat_floor = max(4, feed_wheat if mouths else 0)
    if mouths:
        wheat_floor = max(wheat_floor, mouths + int(PARAMS["wheat_buffer_add"]))
    if s["crops"]["WHEAT"] < wheat_floor and seeds.get("WHEAT", 0) > 0:
        return "WHEAT"
    if s["crops"]["WHEAT"] == 0 and shed_w == 0 and seeds.get("WHEAT", 0) > 0:
        return "WHEAT"
    cash = [
        crop
        for crop in CASH_PLANT
        if seeds.get(crop, 0) > 0 and s["crops"][crop] < plan.get(crop, 0)
    ]
    primary = _primary_cash(s) or "STRAWBERRY"
    # Softfloor router: plant held strawberry seeds on hollow pizza/bakery boards.
    if _softfloor_berry_plant_push(s, seeds):
        return "STRAWBERRY"
    if cash:
        if primary in cash:
            return primary
        if "STRAWBERRY" in cash and _softfloor_speculative_berry(s):
            return "STRAWBERRY"
        return max(cash, key=lambda c: plan_ev(s, c))
    primary_gap = plant_gap(plan, s, primary)
    if (
        in_late_ramp(s)
        and engine_replant_open(s)
        and seeds.get(primary, 0) > 0
        and s["empty"] >= 2
        and (primary_gap > 0 or plan.get(primary, 0) > 0)
    ):
        return primary
    if (
        plan.get(primary, 0) > 0
        and engine_replant_open(s)
        and seeds.get(primary, 0) > 0
        and primary_gap > 0
        and (s["day"] >= 12 or cash_ramp(s) or berry_ramp(s))
    ):
        return primary
    if (
        primary
        and seeds.get(primary, 0) > 0
        and int(s.get("empty") or 0) > 0
        and engine_replant_open(s)
        and (plan.get(primary, 0) > 0 or _hold_engine_crop(s, primary))
    ):
        return primary
    if s["crops"]["WHEAT"] < plan["WHEAT"] and seeds.get("WHEAT", 0) > 0:
        return "WHEAT"
    return None


def step_toward(fx, fy, tx, ty):
    if tx < fx:
        return ["WEST"]
    if tx > fx:
        return ["EAST"]
    if ty < fy:
        return ["NORTH"]
    if ty > fy:
        return ["SOUTH"]
    return ["PASS"]


def nearest_job(tiles, fx, fy, day, claimed, has_seeds, has_fertilizer, has_wheat, ctx):
    best = None
    hungry = ctx["hungry"]
    fert_ready = ctx.get("fert_ready", 0)
    stress = bool(ctx.get("water_stress"))
    live_dry = int(ctx.get("unwatered") or 0)
    for y, row in enumerate(tiles):
        for x, t in enumerate(row):
            if t == "LOCKED" or (x, y) in claimed:
                continue
            priority = None
            urgency = 0
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                if crop_ready(t, day, ctx.get("early_wheat", False)):
                    crop = t.get("crop")
                    # Position-aware harvest priority:
                    # - EV is the base signal.
                    # - Inventory pressure boosts crops where shed stock is low
                    #   relative to near-term target and penalizes overstock.
                    # This is intentionally decoupled from "sell now" logic.
                    ev_score = ctx.get("crop_ev_score", {}).get(crop, 0.0)
                    inv_target = (ctx.get("inventory_target") or {}).get(crop, 0.0)
                    inv_stock = (ctx.get("inventory_stock") or {}).get(crop, 0.0)
                    gap = inv_target - inv_stock
                    if gap >= 0:
                        inv_score = 0.25 * float(gap)
                    else:
                        inv_score = -0.15 * float(-gap)
                    # Ongoing harvest must not outrun dry-tile watering when
                    # debt exceeds this hour's crew (overnight weed risk).
                    if (
                        live_dry > max(1, int(ctx.get("workers") or 1))
                        or stress
                    ) and crop in ONGOING:
                        priority = 1
                    else:
                        priority = 0
                    # `candidate` tuple sorts ascending, so negate the score.
                    urgency = -(ev_score + inv_score)
                elif not t["watered_today"] and t.get("consecutive_unwatered", 0) >= 1:
                    priority = 0
                    tile_ev = float(ctx.get("tile_ev") or 0.0)
                    days = max(1, int(ctx.get("productive_days") or 1))
                    urgency = -(max(tile_ev, 1.0) * days)
                elif not t["watered_today"] and (hungry == 0 or not has_wheat):
                    crop = t.get("crop")
                    cash = crop in CASH_CROPS
                    engine = (
                        not ctx.get("harvest_focus")
                        and crop == ctx.get("cash_crop")
                        and crop in CASH_CROPS
                    )
                    if (
                        fert_ready == 0
                        or ctx.get("use_fert")
                        or cash
                        or not has_wheat
                        or engine
                        or stress
                    ):
                        if cash or engine or stress:
                            # Dry cash tiles beat densify plant (priority 1).
                            priority = 0
                            urgency = -max(float(ctx.get("tile_ev") or 0.0), 1.0)
                            if cash:
                                urgency -= 1.0
                        elif ctx.get("use_fert"):
                            priority = 2
                        else:
                            priority = 4
                elif (
                    has_fertilizer
                    and t.get("crop") in CASH_CROPS
                    and ctx.get("use_fert")
                    and t.get("fertilized_until_day", -1) < day
                    and hungry == 0
                    and not stress
                ):
                    priority = 2
            elif isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE"):
                animal = t.get("animal")
                if animal:
                    if t.get("yield_units", 0) > 0:
                        priority = 0
                    elif not t.get("fed_today") and has_wheat:
                        priority = 0
                        urgency = -30
                    elif t.get("fertilizer_available") and not stress:
                        if hungry == 0 or not has_wheat:
                            priority = 0
                            urgency = -15
                    elif (
                        not t.get("cared_today")
                        and t.get("fed_today")
                        and hungry == 0
                        and fert_ready == 0
                        and not ctx.get("skip_care")
                        and not ctx.get("fill_board")
                        and not stress
                    ):
                        priority = 3
                elif ctx["carried"] and ANIMAL_STRUCT.get(ctx["carried"]) == t.get(
                    "kind"
                ):
                    priority = 2
            elif isinstance(t, dict) and t.get("kind") == "WEED":
                if hungry == 0 and not stress:
                    if ctx.get("cash_waiting"):
                        priority = 1
                        urgency = 3
                    else:
                        priority = 2
                        urgency = 2
            elif t is None:
                waiting_plant = ctx.get("cash_waiting") or ctx.get("wheat_waiting")
                waiting_berry = ctx.get("berry_waiting")
                # Pasture bind: walk to empty tile to BUILD before cash plant race.
                if ctx.get("pasture_bind") and hungry == 0 and not stress:
                    priority = 0
                    urgency = -50
                elif (
                    hungry == 0
                    and has_seeds
                    and (waiting_plant or waiting_berry)
                    and not stress
                ):
                    tile_ev = float(ctx.get("tile_ev") or 0.0)
                    days = max(1, int(ctx.get("productive_days") or 1))
                    # After live plants are watered this hour, leftover seeds
                    # share priority 0 with water (post-land fill).
                    if live_dry == 0 and (
                        ctx.get("plant_sprint")
                        or int(ctx.get("empty") or 0) > int(ctx.get("workers") or 0)
                    ):
                        priority = 0
                        urgency = -(max(tile_ev, 1.0) * days)
                    else:
                        priority = 1
                        urgency = -(max(tile_ev, 1.0) * days)
                elif (
                    (ctx.get("need_pasture") or ctx.get("need_coop"))
                    and not waiting_plant
                    and not stress
                ):
                    priority = 1
                elif hungry == 0 and has_seeds and not stress:
                    priority = 1 if waiting_plant else 4
            if priority is None:
                continue
            dist = abs(x - fx) + abs(y - fy)
            candidate = (priority, urgency, dist, x, y)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return None
    return (best[3], best[4])


def action_for(tiles, x, y, day, seeds, claimed, s, inv, ctx):
    tile = tiles[y][x]
    has_fertilizer = inv.get("FERTILIZER", 0) > 0
    has_wheat = inv.get("WHEAT", 0) > 0
    ctx["has_wheat"] = has_wheat
    is_feeder = has_wheat and s["hungry"] > 0 and ctx["feeder"][0] > 0
    if is_feeder:
        ctx["feeder"][0] -= 1
    ctx["is_feeder"] = is_feeder
    carried = next((a for a in ANIMAL_COST if inv.get(a, 0) > 0), None)
    ctx["carried"] = carried
    shed = s["shed"]
    waiting_coop = shed.get("GOOSE", 0) + (1 if carried == "GOOSE" else 0)
    waiting_past = (
        shed.get("COW", 0)
        + shed.get("SHEEP", 0)
        + (1 if carried in ("COW", "SHEEP") else 0)
    )
    need_coop = waiting_coop > s["empty_struct"]["COOP"]
    need_pasture = waiting_past > s["empty_struct"]["PASTURE"]
    # Shed bind: animals waiting with zero pastures — force need even if counts tie.
    if _pasture_bind_active(s, ctx):
        need_pasture = True
    ctx["need_pasture"] = need_pasture
    ctx["need_coop"] = need_coop
    ctx["pasture_bind"] = _pasture_bind_active(s, ctx)
    ctx["cash_waiting"] = cash_waiting(s, seeds)
    ctx["wheat_waiting"] = wheat_waiting(s, seeds)

    if carried:
        if (
            isinstance(tile, dict)
            and tile.get("kind") in ("COOP", "PASTURE")
            and not tile.get("animal")
            and ANIMAL_STRUCT[carried] == tile.get("kind")
        ):
            claimed.add((x, y))
            return ["PLACE", carried], seeds
        if (
            tile is None
            and ANIMAL_STRUCT[carried] == "PASTURE"
            and s["empty_struct"]["PASTURE"] <= 0
        ):
            s["empty_struct"]["PASTURE"] += 1
            claimed.add((x, y))
            return ["BUILD_PASTURE"], seeds
        if (
            tile is None
            and ANIMAL_STRUCT[carried] == "COOP"
            and s["empty_struct"]["COOP"] <= 0
        ):
            s["empty_struct"]["COOP"] += 1
            claimed.add((x, y))
            return ["BUILD_COOP"], seeds

    if isinstance(tile, dict) and tile.get("kind") == "WEED":
        claimed.add((x, y))
        return ["DIG"], seeds

    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        at_risk_tile = tile.get("consecutive_unwatered", 0) >= 1
        dry = not tile["watered_today"] and not is_feeder
        # Water before harvest when dry cash/risk — yield skim must not kill tiles.
        if dry and (
            at_risk_tile
            or ctx.get("water_stress")
            or tile.get("crop") in CASH_CROPS
            or int(ctx.get("unwatered") or 0) > max(1, int(ctx.get("workers") or 1))
        ):
            claimed.add((x, y))
            s["unwatered"] = max(0, int(s.get("unwatered") or 0) - 1)
            ctx["unwatered"] = s["unwatered"]
            if at_risk_tile:
                s["at_risk"] = max(0, int(s.get("at_risk") or 0) - 1)
                ctx["at_risk"] = s["at_risk"]
            ctx["water_stress"] = field_water_stress(s)
            return ["WATER"], seeds
        if crop_ready(tile, day, ctx.get("early_wheat", False)):
            crop = tile.get("crop")
            # Track all harvested crops for in-turn shed projection
            # (WHEAT, MILK/WOOl cashflow, etc).
            if crop:
                shed_delta = ctx.setdefault("shed_delta", {})
                shed_delta[crop] = shed_delta.get(crop, 0) + 1
            # Position throttling is for "clearing" crops. For ONGOING crops
            # (e.g. TOMATO/STRAWBERRY), the tile remains and we don't want to
            # artificially suppress repeated harvests within the sell window.
            if crop in CASH_PLANT:
                inv_stock = ctx.setdefault("inventory_stock", {})
                inv_stock[crop] = inv_stock.get(crop, 0) + 1
            if crop and crop not in ONGOING:
                s["crops"][crop] = max(0, s["crops"].get(crop, 0) - 1)
                s["empty"] += 1
            claimed.add((x, y))
            return ["HARVEST"], seeds
        if (
            has_fertilizer
            and ctx.get("use_fert")
            and tile.get("crop") in CASH_CROPS
            and tile.get("fertilized_until_day", -1) < day
            and not is_feeder
            and not ctx.get("water_stress")
        ):
            claimed.add((x, y))
            return ["FERTILIZE"], seeds
        if dry:
            claimed.add((x, y))
            s["unwatered"] = max(0, int(s.get("unwatered") or 0) - 1)
            ctx["unwatered"] = s["unwatered"]
            ctx["water_stress"] = field_water_stress(s)
            return ["WATER"], seeds

    if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE"):
        animal = tile.get("animal")
        if animal:
            if tile.get("yield_units", 0) > 0:
                claimed.add((x, y))
                return ["HARVEST"], seeds
            if not tile.get("fed_today") and has_wheat:
                claimed.add((x, y))
                s["hungry"] = max(0, s["hungry"] - 1)
                ctx["hungry"] = s["hungry"]
                return ["FEED"], seeds
            if tile.get("fertilizer_available"):
                claimed.add((x, y))
                s["fert_ready"] = max(0, s["fert_ready"] - 1)
                ctx["fert_ready"] = s["fert_ready"]
                return ["COLLECT_FERTILIZER"], seeds
            if (
                not tile.get("cared_today")
                and tile.get("fed_today")
                and not ctx.get("skip_care")
                and not ctx.get("plant_sprint")
            ):
                claimed.add((x, y))
                return ["CARE"], seeds
        elif carried and ANIMAL_STRUCT[carried] == tile.get("kind"):
            claimed.add((x, y))
            return ["PLACE", carried], seeds

    drop_items = DROP_ITEMS
    if ctx.get("use_fert") and inv.get("FERTILIZER", 0) > 0 and s.get("hour", 0) < 22:
        drop_items = tuple(i for i in DROP_ITEMS if i != "FERTILIZER")
    to_drop = any(inv.get(i, 0) > 0 for i in drop_items)
    if (
        to_drop
        and not is_feeder
        and s["at_risk"] == 0
        and s["hungry"] == 0
        and not ctx.get("plant_sprint")
    ):
        if (x, y) in SHED_TILES:
            claimed.add((x, y))
            return ["DROP"], seeds
        return step_toward(x, y, 4, 4), seeds

    if tile is None:
        waiting_cash = ctx.get("cash_waiting")
        waiting_wheat = ctx.get("wheat_waiting")
        sprint = ctx.get("plant_sprint")
        struct_block = sprint and waiting_past <= 0 and waiting_coop <= 0
        # Pasture bind beats cash plant: shed animals with nowhere to place.
        if (
            ctx.get("pasture_bind")
            and s["at_risk"] == 0
            and tile is None
        ):
            ctx["pasture_bind_builds"] = int(ctx.get("pasture_bind_builds", 0) or 0) + 1
            s["empty_struct"]["PASTURE"] += 1
            claimed.add((x, y))
            return ["BUILD_PASTURE"], seeds
        if (
            need_pasture
            and s["at_risk"] == 0
            and not struct_block
            and not waiting_cash
            and not waiting_wheat
        ):
            s["empty_struct"]["PASTURE"] += 1
            claimed.add((x, y))
            return ["BUILD_PASTURE"], seeds
        if (
            need_coop
            and s["at_risk"] == 0
            and not struct_block
            and not waiting_cash
            and not waiting_wheat
        ):
            s["empty_struct"]["COOP"] += 1
            claimed.add((x, y))
            return ["BUILD_COOP"], seeds
        feeding = is_feeder
        reserve = (
            waiting_past
            + waiting_coop
            - s["empty_struct"]["PASTURE"]
            - s["empty_struct"]["COOP"]
        )
        reserve = max(0, reserve)
        if s["day"] <= 1:
            reserve = max(reserve, 2)
        if (
            current_engine(s) == "MILK"
            and milk_sink(s) >= 1
            and s["n_quads"] >= 2
            and want_cows(s) > s["cows"]
            and s["day"] <= int(PARAMS["animal_buy_day_max"])
        ):
            reserve = max(reserve, 2)
        if (not feeding) and not carried and s["empty"] > reserve:
            crop = pick_crop(s, seeds)
            if crop is not None:
                seeds[crop] -= 1
                s["crops"][crop] += 1
                s["empty"] -= 1
                claimed.add((x, y))
                return ["PLANT", crop], seeds

    if (x, y) in SHED_TILES:
        for animal in ("COW", "SHEEP", "GOOSE"):
            if shed.get(animal, 0) > 0 and not carried:
                shed[animal] -= 1
                claimed.add((x, y))
                return ["PICKUP", animal, 1], seeds
        if s["hungry"] and not has_wheat and shed.get("WHEAT", 0) > 0:
            n = min(4, shed.get("WHEAT", 0))
            shed["WHEAT"] -= n
            claimed.add((x, y))
            return ["PICKUP", "WHEAT", n], seeds
        if to_drop:
            claimed.add((x, y))
            return ["DROP"], seeds

    if (
        s["hungry"]
        and not has_wheat
        and shed.get("WHEAT", 0) > 0
        and (x, y) not in SHED_TILES
    ):
        return step_toward(x, y, 4, 4), seeds

    waiting = next((a for a in ("COW", "SHEEP", "GOOSE") if shed.get(a, 0) > 0), None)
    if waiting and not carried and s["at_risk"] <= 2:
        if (x, y) not in SHED_TILES:
            return step_toward(x, y, 4, 4), seeds

    has_seeds = any(seeds.get(c, 0) > 0 for c in SEED_COST)
    target = nearest_job(
        tiles, x, y, day, claimed, has_seeds, has_fertilizer, has_wheat, ctx
    )
    if target is not None:
        claimed.add(target)
        return step_toward(x, y, target[0], target[1]), seeds
    return ["PASS"], seeds


def sell_qty(stock: int, keep: int = 0) -> int:
    if stock <= keep:
        return 0
    return stock - keep


def _append_seed(market: list, money: int, crop: str, n: int, keep: int = 400) -> int:
    if n <= 0:
        return money
    cost = SEED_COST[crop]
    n = min(n, max(0, money - keep) // cost)
    if n <= 0:
        return money
    market.append(["BUY_SEED", crop, n])
    return money - n * cost


def _feed_crisis(s: dict[str, Any]) -> bool:
    mouths = mouths_of(s)
    if mouths <= 0:
        return False
    stock = s["crops"]["WHEAT"] + s["seeds"].get("WHEAT", 0) + s["shed"].get("WHEAT", 0)
    return stock < mouths


def _buy_feed_wheat(market: list, afford: int, s: dict[str, Any]) -> int:
    """Shop wheat is usually worse than $10 seeds. Buy only to avoid a missed feed day."""
    mouths = s["cows"] + s["sheep"] + s["geese"]
    shed_w = s["shed"].get("WHEAT", 0)
    wheat_px = max(1, px(s, "WHEAT"))
    if mouths <= 0:
        return afford
    if wheat_px <= 12:
        need = max(0, mouths - shed_w)
        n = min(need, afford // wheat_px, 9)
    elif s["hour"] == 0 and shed_w < mouths:
        n = min(max(0, mouths - shed_w), afford // wheat_px, 4)
    else:
        return afford
    if n > 0:
        market.append(["BUY_PRODUCT", "WHEAT", n])
        afford -= n * wheat_px
    return afford


def _buy_wheat_seeds(
    market: list, afford: int, s: dict[str, Any], seeds: dict[str, int]
) -> int:
    _, _, wheat_tiles = tile_budget(s)
    # Keep a small wheat seed buffer for late-game days so harvested wheat
    # gets replanted before the next morning market decisions.
    buffer = (
        PARAMS["late_wheat_seed_buffer"]
        if s["day"] >= PARAMS["late_wheat_seed_buffer_day_min"] and mouths_of(s) > 0
        else 0
    )
    wheat_tiles += buffer
    mouths = mouths_of(s)
    if mouths >= 4:
        wheat_tiles += 2
    have_w = s["crops"]["WHEAT"] + seeds.get("WHEAT", 0)
    if have_w >= wheat_tiles:
        return afford
    n = min(wheat_tiles - have_w, max(1, afford // 10), 12)
    keep = 0 if _feed_crisis(s) else 80
    n_before = len(market)
    afford = _append_seed(market, afford, "WHEAT", n, keep=keep)
    bought = 0
    if len(market) > n_before:
        bought = int(market[-1][2])
    seeds["WHEAT"] = seeds.get("WHEAT", 0) + bought
    return afford


def _hire_up_to(
    market: list, afford: int, s: dict[str, Any], max_hires: int | None = None
) -> int:
    cap = HIRES_PER_TURN if max_hires is None else max(0, max_hires)
    want = want_hands(s)
    n_hire = min(cap, max(0, want - s["hires_today"]))
    hired = 0
    for _ in range(n_hire):
        cost = fib_hire_cost(s["hires_today"])
        if afford < cost + (40 if mouths_of(s) > 0 else 0):
            break
        market.append(["HIRE"])
        afford -= cost
        s["hires_today"] += 1
        hired += 1
    if hired:
        # Hands join next step, but day-capacity planning must see the crew
        # we just paid for (else land/seed NPV use a stale TurnBudget).
        s["workers"] = int(s.get("workers") or 0) + hired
        tp = s.get("turn_plan")
        if tp is not None:
            tp.budget = None
    return afford


def _maybe_buy_land(market: list, afford: int, s: dict[str, Any]) -> int:
    if not _will_buy_land(s, afford):
        return afford
    cost = LAND_COST[s["n_quads"] - 1]
    market.append(["BUY_LAND"])
    # Same-hour seed buys must see the new plot. Seed 42 bought 12 berries
    # against the old 4 empty tiles, then sat on 27 empty the next dawn.
    s["n_quads"] = int(s["n_quads"]) + 1
    s["empty"] = int(s["empty"]) + 25
    sprint_days = 4 if s["n_quads"] >= 3 else 2
    _LAND_SPRINT["until_day"] = s["day"] + sprint_days
    s.pop("turn_plan", None)
    plan_turn(s)
    return afford - cost


def _buy_berry_prep_seeds(
    market: list,
    afford: int,
    s: dict[str, Any],
    seeds: dict[str, int],
) -> int:
    """Stockpile strawberry seeds before the first berry shop opens."""
    need = berry_prep_seed_need(s, seeds)
    if need <= 0 or afford <= 0 or len(market) >= MARKET_LIMIT:
        return afford
    keep = int(PARAMS["berry_prep_cash_keep"])
    max_n = max(1, int(PARAMS["berry_prep_max_seed_spend"]) // SEED_COST["STRAWBERRY"])
    n_before = len(market)
    afford = _append_seed(market, afford, "STRAWBERRY", min(need, max_n), keep=keep)
    if len(market) > n_before:
        seeds["STRAWBERRY"] = seeds.get("STRAWBERRY", 0) + int(market[-1][2])
    return afford


def _buy_planned_seeds(
    market: list,
    afford: int,
    s: dict[str, Any],
    seeds: dict[str, int],
    *,
    berry_only: bool = False,
    after_land: bool = False,
) -> int:
    if s.get("_seeds_bought_this_market"):
        return afford
    plan = crop_plan(s)
    rescue = bool(s.get("liquidity_rescue", False))
    budget = _turn_budget(s)
    if after_land:
        cap_n = post_land_seed_cap(
            workers=budget.workers,
            hungry=budget.hungry,
            live_tiles=budget.live_tiles,
            empty=int(s.get("empty") or 0),
        )
        # Elite densify-3: stockpile berry seeds beyond this-hour plantable —
        # hire lag means dawn after land2 plants 10–16 tiles (us was +9/2d).
        if _densify3_fill_active(s):
            empty = int(s.get("empty") or 0)
            stock = int(PARAMS.get("densify3_seed_stockpile", 16))
            cap_n = max(cap_n, min(empty, stock))
    else:
        # This hour only — do not stockpile beyond plantable hands.
        cap_n = max(0, min(int(budget.plantable), int(s.get("empty") or 0)))
    if cap_n <= 0:
        return afford
    order = [c for c in CASH_PLANT if plan.get(c, 0) > 0]

    def marginal_score(c: str) -> float:
        have = s["crops"][c] + seeds.get(c, 0)
        need_tiles = plan[c] - have
        if need_tiles <= 0:
            return -1e9
        ev = plan_ev(s, c)
        cost = float(SEED_COST.get(c, 1))
        score = (need_tiles * ev) / max(1.0, cost)
        if uptrend_frontrun(s, c):
            score *= float(PARAMS["frontrun_score_mult"])
        if rescue:
            payback_days = {"STRAWBERRY": 5.0, "CARROT": 3.0, "TOMATO": 4.0, "MELON": 10.0}.get(c, 6.0)
            score *= (6.0 / payback_days)
        return score

    order.sort(key=marginal_score, reverse=True)
    primary = _primary_cash(s)
    # Densify-3 / Lane B: elites plant berry not tomato on softfloor expand.
    if (_densify3_fill_active(s) or _pack_berry_active(s)) and (
        berry_sink(s) > 0 or "STRAWBERRY" in plan or _pack_berry_active(s)
    ):
        order = ["STRAWBERRY"] + [c for c in order if c != "STRAWBERRY"]
    if berry_only:
        if primary and plan.get(primary, 0) > 0:
            order = [primary]
        elif plan.get("STRAWBERRY", 0) > 0:
            order = ["STRAWBERRY"]
        else:
            order = order[: 2 if plant_sprint(s) else 1]
    remaining = list(order)
    bought_any = False
    while remaining and afford > 0 and len(market) < MARKET_LIMIT:
        remaining.sort(key=marginal_score, reverse=True)
        crop = remaining[0]
        have = s["crops"][crop] + seeds.get(crop, 0)
        need = plan[crop] - have
        empty_n = max(0, int(s.get("empty", 0)))
        need = min(need, empty_n, cap_n)
        if need <= 0:
            remaining.pop(0)
            continue

        tp = s.get("turn_plan")
        if crop == "STRAWBERRY" or crop == primary:
            keep = (
                int(tp.profile.post_land_floor)
                if tp is not None
                else int(PARAMS["land_post_floor_default"])
            )
            if s["n_quads"] < 2:
                keep = max(keep, 400)
        else:
            keep = 400

        if rescue:
            keep = int(keep * 0.6)
        if after_land and (_land2_crew_spike(s) or _densify3_fill_active(s)):
            keep = min(keep, int(PARAMS.get("land2_post_seed_keep", 200)))
        if _densify3_fill_active(s) and crop == "STRAWBERRY":
            keep = min(keep, int(PARAMS.get("densify3_seed_keep", 150)))
        keep = max(0, min(afford - 1, keep))

        if not berry_only and crop != "STRAWBERRY" and crop != primary and len(market) >= MARKET_LIMIT:
            break

        n_before = len(market)
        afford = _append_seed(market, afford, crop, min(need, cap_n), keep=keep)
        if len(market) > n_before:
            bought = int(market[-1][2])
            seeds[crop] = seeds.get(crop, 0) + bought
            cap_n = max(0, cap_n - bought)
            bought_any = True
            if cap_n <= 0:
                break
        else:
            break
    if bought_any:
        s["_seeds_bought_this_market"] = True
    return afford


def _land_project_npv(s: dict[str, Any], afford: int) -> float:
    if not need_land(s) or s["n_quads"] >= 4:
        return 0.0
    if not _will_buy_land(s, afford):
        return 0.0
    if s["n_quads"] == 1:
        # 1→2 survival unlock — keep a positive score when gates say buy.
        return 1.0
    if _plot3_qualified_buy(s):
        return 1.0
    cost = LAND_COST[s["n_quads"] - 1]
    return _expansion_npv_score(s, land_cost=cost)


def _hire_project_score(s: dict[str, Any], afford: int) -> float:
    """Hire only when it lifts expand-vs-stay advantage (crew-gated expand)."""
    if int(s.get("n_quads") or 0) < 2 or not need_land(s):
        return 0.0
    empty = int(s.get("empty") or 0)
    soft_cap = int(PARAMS.get("land_hollow_soft_cap", 14))
    hollow_max = int(PARAMS.get("land2_hollow_empty_max", 45))
    # Crew-gated expansion on softfloor hollow boards (not packed printers).
    if not (soft_cap < empty <= hollow_max):
        return 0.0
    cost = fib_hire_cost(int(s.get("hires_today") or 0))
    if afford < cost + 40:
        return 0.0
    budget = _turn_budget(s)
    streams = _long_term_streams(s)
    primary = _primary_cash(s)
    land_cost = LAND_COST[s["n_quads"] - 1]
    seed_c = int(SEED_COST.get(primary or "WHEAT", 10))
    primary_ev = plan_ev(s, primary) if primary else budget.tile_ev
    animal = 0.0
    if _primary_cash(s) != "STRAWBERRY":
        animal = streams.land_animal_unlock_ev * float(
            PARAMS.get("lt_land_animal_scale", 0.1)
        )
    common = dict(
        workers=budget.workers,
        hungry=budget.hungry,
        live_tiles=budget.live_tiles,
        productive_days=budget.productive_days,
        tile_ev=primary_ev,
        land_cost=land_cost,
        seed_cost=seed_c,
        empty=empty,
        stand_factor=_stand_factor(s),
        realize=float(PARAMS.get("land_npv_realize", 0.7)),
        margin=float(PARAMS.get("land_expand_margin", 0.0)),
        animal_unlock_ev=animal,
    )
    npv0 = expand_vs_stay_advantage(**common)
    npv1 = expand_vs_stay_advantage(**common, hire_n=1, hire_cost_total=cost)
    lift = npv1 - npv0
    if lift <= 0:
        return 0.0
    base = hire_project_ev(
        tile_ev=primary_ev,
        productive_days=budget.productive_days,
        hire_cost=cost,
        empty=empty,
        workers=budget.workers,
        hungry=budget.hungry,
        unwatered=budget.unwatered,
        live_tiles=budget.live_tiles,
    )
    return max(base, lift)


def _seed_project_score(s: dict[str, Any]) -> tuple[float, int]:
    primary = _primary_cash(s)
    if not primary:
        return 0.0, 0
    plan = crop_plan(s)
    budget = _turn_budget(s)
    need = max(
        0,
        int(plan.get(primary, 0) or 0)
        - int(s["crops"].get(primary, 0) or 0)
        - int(s["seeds"].get(primary, 0) or 0),
    )
    n = min(need, int(s.get("empty") or 0), int(budget.plantable))
    if n <= 0:
        return 0.0, 0
    ev = seed_project_ev(
        tile_ev=budget.tile_ev,
        productive_days=budget.productive_days,
        n_seeds=n,
        seed_cost=int(SEED_COST.get(primary, 100)),
    )
    if _hollow_expand_window(s):
        if _hold_densify_for_expand(s):
            ev *= float(PARAMS.get("hollow_seed_hold_factor", 0.3))
        elif not _herd_ready_for_land(s):
            ev *= float(PARAMS.get("hollow_seed_early_factor", 0.55))
    return ev, n


def _cow_project_score(s: dict[str, Any]) -> float:
    """Milk floor + light wool/egg horizon when those sinks dominate."""
    budget = _turn_budget(s)
    legacy = 0.0
    if want_cows(s) > int(s.get("cows") or 0):
        per_day = cow_project_ev(
            cow_ev=animal_score("COW", milk_px(s), s["day"]),
            cow_cost=int(ANIMAL_COST["COW"]),
        )
        legacy = per_day * max(1, int(budget.productive_days))
    streams = _long_term_streams(s)
    scale = float(PARAMS.get("lt_animal_project_scale", 0.35))
    # Only boost non-milk animals when berry is not the printer.
    if berry_sink(s) > 0 and _primary_cash(s) == "STRAWBERRY":
        return legacy
    multi = scale * best_animal_horizon_ev(
        productive_days=budget.productive_days,
        milk_day=streams.milk_day,
        wool_day=streams.wool_day,
        egg_day=streams.egg_day,
        want_cow=want_cows(s) > int(s.get("cows") or 0),
        want_sheep=want_sheep(s) > int(s.get("sheep") or 0),
        want_goose=want_geese(s) > int(s.get("geese") or 0),
        cow_cost=int(ANIMAL_COST["COW"]),
        sheep_cost=int(ANIMAL_COST["SHEEP"]),
        goose_cost=int(ANIMAL_COST["GOOSE"]),
    )
    return max(legacy, multi)

def _lookahead_project_scores(
    s: dict[str, Any],
    afford: int,
    *,
    can_land: bool,
    can_cow: bool,
    can_seed: bool,
    n_seeds: int,
) -> dict[str, float] | None:
    """Bucket look-ahead scores, or None outside the active day window / on error."""
    day = int(s.get("day") or 0)
    if day < int(PARAMS["lookahead_min_day"]) or day > int(PARAMS["lookahead_max_day"]):
        return None
    primary = _primary_cash(s) or "STRAWBERRY"
    try:
        return rank_projects(
            s,
            days=int(PARAMS["lookahead_days"]),
            actions_per_worker_day=int(PARAMS["lookahead_actions_per_worker_day"]),
            primary=primary,
            n_seeds=max(0, int(n_seeds)),
            can_land=can_land,
            can_cow=can_cow,
            can_seed=can_seed,
            land_cost_ok=afford >= LAND_COST[min(s["n_quads"] - 1, 2)],
        )
    except Exception:
        return None


def _capital_followup(
    market: list,
    afford: int,
    s: dict[str, Any],
    pick: str,
    *,
    defer_animals: bool,
) -> int:
    """Second capital action same hour — herd-with-land / land-then-herd."""
    if int(PARAMS.get("capital_followup", 1)) != 1:
        return afford
    if pick == "land" and not defer_animals and afford >= ANIMAL_COST["COW"]:
        if (
            want_cows(s) > int(s.get("cows") or 0)
            or want_sheep(s) > int(s.get("sheep") or 0)
            or want_geese(s) > int(s.get("geese") or 0)
        ):
            afford = _buy_animals(market, afford, s)
    elif pick == "cow" and need_land(s):
        cost = LAND_COST[min(int(s.get("n_quads") or 1) - 1, 2)]
        if _expansion_npv_score(s, land_cost=cost) >= float(
            PARAMS.get("hollow_land_npv_min", 5000)
        ) and _will_buy_land(s, afford):
            before = int(s.get("n_quads") or 0)
            afford = _maybe_buy_land(market, afford, s)
            if int(s.get("n_quads") or 0) > before:
                afford = _buy_planned_seeds(
                    market, afford, s, s["seeds"], berry_only=False, after_land=True
                )
    # Softfloor: second cow same dawn while still hollow after land2.
    if (
        pick == "cow"
        and not defer_animals
        and _post_land2_herd_burst(s)
        and want_cows(s) > int(s.get("cows") or 0)
        and afford >= ANIMAL_COST["COW"]
    ):
        afford = _buy_animals(market, afford, s)
    return afford


def _post_land_crew_fill(market: list, afford: int, s: dict[str, Any]) -> int:
    """Reserved: same-hour hire after land burned cash on seed 33.

    Crew spike is applied on following dawns via want_hands / hire_burst_cap
    while land-sprint empties remain. Land hour prioritizes seeds only.
    """
    return afford


def _execute_capital_pick(
    market: list,
    afford: int,
    s: dict[str, Any],
    pick: str,
    *,
    defer_animals: bool,
    berry_only_seeds: bool = False,
) -> int:
    if pick == "land":
        before = int(s.get("n_quads") or 0)
        afford = _maybe_buy_land(market, afford, s)
        if int(s.get("n_quads") or 0) > before:
            afford = _buy_planned_seeds(
                market,
                afford,
                s,
                s["seeds"],
                berry_only=False,
                after_land=True,
            )
        else:
            afford = _buy_planned_seeds(
                market,
                afford,
                s,
                s["seeds"],
                berry_only=True,
                after_land=True,
            )
    elif pick == "cow":
        afford = _buy_animals(market, afford, s)
        if not _hold_densify_for_expand(s):
            afford = _buy_planned_seeds(
                market, afford, s, s["seeds"], berry_only=berry_only_seeds
            )
    elif pick == "hire":
        afford = _hire_up_to(market, afford, s, 1)
        if not _hold_densify_for_expand(s):
            afford = _buy_planned_seeds(
                market, afford, s, s["seeds"], berry_only=berry_only_seeds
            )
    else:
        afford = _buy_planned_seeds(
            market, afford, s, s["seeds"], berry_only=berry_only_seeds
        )
    afford = _capital_followup(
        market, afford, s, pick, defer_animals=defer_animals
    )
    return afford


def _buy_animals(market: list, afford: int, s: dict[str, Any]) -> int:
    cow_floor = int(PARAMS.get("cow_floor", 2))
    sheep_floor = int(PARAMS.get("sheep_floor", 2))
    below_floor = s["cows"] < cow_floor or s["sheep"] < sheep_floor
    # Expansion is dawn-only except milk densify (pizza before berries),
    # which still needs mid-day garnish buys. Floor recovery may buy mid-day;
    # berry sheep-dip is species-gated in the candidate loop below.
    milk_led = milk_sink(s) >= 1 and berry_sink(s) == 0
    # Softfloor herd ramp: mid-day cows on non-berry hollow only.
    # Berry softfloor uses dawn capital bias (mid-day berry push wrecks densify).
    herd_push = (
        int(s.get("n_quads") or 0) >= 2
        and int(s.get("day") or 0) <= int(PARAMS.get("hollow_land_day_max", 14))
        and int(s.get("cows") or 0) < int(PARAMS.get("berry_melon_bridge_cow_cap", 8))
        and int(s.get("empty") or 0) > int(PARAMS.get("land_hollow_soft_cap", 14))
        and berry_sink(s) == 0
        and (
            milk_sink(s) >= 1
            or egg_sink(s) >= 1
            or int(s.get("empty") or 0) >= int(PARAMS.get("hollow_herd_deep_empty", 20))
        )
    )
    if int(s.get("hour") or 0) != 0 and not below_floor and not milk_led and not herd_push:
        return afford
    if s["day"] >= PARAMS["animal_buy_day_max"] and not below_floor:
        return afford
    # Berry engines stop expanding earlier so late water goes to the stand.
    if (
        not below_floor
        and engine_of(s) == "BERRY"
        and int(s["day"]) > int(PARAMS.get("berry_animal_buy_day_max", 18))
    ):
        return afford
    if s["day"] < PARAMS["animal_buy_day_min"] and not below_floor:
        return afford
    shed_busy = bool(
        s["shed"].get("COW", 0)
        or s["shed"].get("SHEEP", 0)
        or s["shed"].get("GOOSE", 0)
    )
    shed_buy_ok = (
        int(PARAMS.get("softfloor_shed_busy_cow_buy", 1)) == 1
        and shed_busy
        and _softfloor_mode(s)
        and int(s.get("hour") or 0) == 0
        and int(s.get("day") or 0) <= int(PARAMS.get("softfloor_herd_day_max", 10))
        and int(s.get("cows") or 0) < int(PARAMS.get("land2_schedule_cow_min", 6))
        and int(s.get("empty") or 0) >= int(PARAMS.get("shed_busy_empty_min", 2))
        and want_cows(s) > int(s.get("cows") or 0)
    )
    if shed_busy and not below_floor and not shed_buy_ok:
        return afford
    if s["crops"]["WHEAT"] < 4:
        return afford
    if _feed_crisis(s) and not below_floor:
        return afford
    if not below_floor and not herd_can_expand(s):
        return afford
    if not below_floor and mouths_of(s) >= s["crops"]["WHEAT"]:
        return afford
    _, cash_room, _ = tile_budget(s)
    mouth_cap = (
        PARAMS["mouth_cap_1q"] if s["n_quads"] == 1 else PARAMS["mouth_cap_2qplus"]
    )
    # Soft mouth cap on berry maps — pasture spam starves strawberry water.
    if engine_of(s) == "BERRY" and berry_sink(s) > 0:
        mouth_cap = min(
            int(mouth_cap), int(PARAMS.get("berry_herd_mouth_cap", 10))
        )
    if mouths_of(s) >= mouth_cap:
        return afford
    if s["n_quads"] == 1 and cash_shop(s) and cash_room < 6 and not below_floor:
        if milk_sink(s) < 2:
            return afford
    seed_gap = berry_gap(s)
    primary = _primary_cash(s)
    if primary and primary != "STRAWBERRY":
        seed_gap = max(seed_gap, crop_gap(crop_plan(s), s, primary))
    reserve = min(900, seed_gap * SEED_COST.get(primary or "STRAWBERRY", 100))
    # Milk-led densify frees animal cash once seeds aren't the only printer.
    if milk_sink(s) >= 1 and berry_sink(s) == 0:
        reserve = min(reserve, 200)
    if below_floor:
        reserve = min(reserve, 200)
    if shed_buy_ok:
        reserve = min(reserve, 200)
    cash_floor = (
        PARAMS["animal_cash_floor_2qplus"]
        if s["n_quads"] >= 2
        else PARAMS["animal_cash_floor_1q"]
    )
    if shed_buy_ok:
        cash_floor = min(int(cash_floor), 200)
    # When only diversification (e.g. GOOSE) is eligible, we should not
    # accidentally gate on cow-cost.
    need_kinds: list[str] = []
    if want_cows(s) > s["cows"]:
        need_kinds.append("COW")
    if want_sheep(s) > s["sheep"]:
        need_kinds.append("SHEEP")
    if want_geese(s) > s["geese"]:
        need_kinds.append("GOOSE")
    min_unit = min((ANIMAL_COST[k] for k in need_kinds), default=ANIMAL_COST["COW"])
    if afford - min_unit < max(reserve, cash_floor) and not below_floor:
        return afford
    # Buy the most valuable eligible animal first (milk/wool/egg).
    candidates: list[tuple[str, int, int]] = []
    for kind, want, have in (
        ("COW", want_cows(s), s["cows"]),
        ("SHEEP", want_sheep(s), s["sheep"]),
        ("GOOSE", want_geese(s), s["geese"]),
    ):
        # Berry sheep-dip trap: cows at floor + sheep under floor unlocked
        # all-day cow garnish while census lagged (seed 123).
        sheep_dip = (
            below_floor
            and engine_of(s) == "BERRY"
            and s["cows"] >= cow_floor
            and s["sheep"] < sheep_floor
        )
        if sheep_dip:
            if kind != "SHEEP":
                continue
            want = sheep_floor
        need = want - have
        if need <= 0 or afford < ANIMAL_COST[kind] or s["empty"] < 2:
            continue
        if kind == "GOOSE" and not herd_can_expand(s):
            # Geese are the highest-risk diversification; only buy them when
            # wheat reserves are healthy enough to expand herd feeding.
            continue
        out_item = {"COW": "MILK", "SHEEP": "WOOL", "GOOSE": "EGG"}[kind]
        candidates.append((kind, need, px(s, out_item)))

    # Sort by expected sell price so we diversify toward the best shop-map.
    candidates.sort(key=lambda t: t[2], reverse=True)
    for kind, want_need, _price in candidates:
        unit = ANIMAL_COST[kind]
        if mouths_of(s) + 1 > mouth_cap:
            continue
        if kind == "COW" and _post_land2_herd_burst(s) and want_need >= 1:
            burst = max(1, int(PARAMS.get("post_land2_cow_burst", 2)))
            wheat_head = max(0, int(s["crops"].get("WHEAT", 0) or 0) - mouths_of(s))
            mouth_head = max(0, mouth_cap - mouths_of(s))
            n = min(burst, afford // unit, mouth_head, max(1, wheat_head))
        else:
            n = min(want_need, 1, afford // unit)
        if n <= 0:
            continue
        market.append(["BUY_ANIMAL", kind, n])
        afford -= n * unit
        if kind == "COW":
            s["cows"] += n
        elif kind == "SHEEP":
            s["sheep"] += n
        else:
            s["geese"] += n
        break
    return afford


def _keep_fert(s: dict[str, Any]) -> int:
    if s["day"] >= 27:
        return 0
    fert_px = px(s, "FERTILIZER")
    berry_px = px(s, "STRAWBERRY")
    if berry_ok(s) and s["crops"].get("STRAWBERRY", 0) > 0 and fert_px < berry_px:
        return 8
    if carrot_ok(s) and s["crops"].get("CARROT", 0) > 0 and fert_px < 40:
        return 4
    return 0


def _sell_score(s: dict[str, Any], item: str, n: int) -> int:
    """Rank a sell lot via inventory–price surface (not spike-only)."""
    price = float(px(s, item))
    left = days_left(s["day"])
    liquidate = (s.get("turn_plan") and s["turn_plan"].mode == "LIQUIDATE") or left <= 2
    # Strong berry-shop mix: still cash out aggressively (legacy winner cue).
    berry_force = item == "STRAWBERRY" and int(s.get("berry_sink", 0) or 0) >= 2
    return sale_score(
        item=item,
        n=n,
        live_px=price,
        inventory=market_inventory(s, item),
        demand=s.get("demand") or {},
        days_left=left,
        price_ma=float((s.get("price_ma") or {}).get(item, 0) or 0) or None,
        spiked=price_spike(s, item) or berry_force,
        liquidate=bool(liquidate) or berry_force,
        momentum=price_momentum(s, item),
    )


def _sell_goods(
    market: list, s: dict[str, Any], shed: dict, max_actions: int = 4
) -> int:
    proceeds = 0
    keep_fert = _keep_fert(s)
    plan = crop_plan(s)
    sell_scale = max_actions / 3.0
    left = days_left(s["day"])
    liquidate = (s.get("turn_plan") and s["turn_plan"].mode == "LIQUIDATE") or left <= 2
    demand = s.get("demand") or {}
    price_ma = s.get("price_ma") or {}
    inv_keep: dict[str, int] = {}
    for c in CASH_CROPS:
        base = max(2, min(10, int(plan.get(c, 0)) // 3))
        base_keep = int(round(base * sell_scale))
        ongoing_mult = 1.15 if c in ONGOING else 1.0
        base_keep = int(round(base_keep * ongoing_mult))
        live = float(px(s, c))
        hist = float(price_ma.get(c, 0) or 0) or None
        inv_keep[c] = market_keep_qty(
            item=c,
            stock=int(shed.get(c, 0) or 0),
            base_keep=base_keep,
            live_px=live,
            inventory=market_inventory(s, c),
            demand=demand,
            days_left=left,
            price_ma=hist,
            spiked=price_spike(s, c),
            liquidate=bool(liquidate),
        )
    ranked: list[tuple[int, str, int]] = []
    for item in (
        "FERTILIZER",
        "MELON",
        "MILK",
        "WOOL",
        "STRAWBERRY",
        "CARROT",
        "EGG",
        "TOMATO",
    ):
        keep = keep_fert if item == "FERTILIZER" else inv_keep.get(item, 0)
        n = sell_qty(shed.get(item, 0), keep)
        if n > 0:
            score = _sell_score(s, item, n)
            if score > 0:
                ranked.append((score, item, n))
    ranked.sort(reverse=True)
    for _, item, n in ranked[:max_actions]:
        market.append(["SELL", item, n])
        proceeds += n * px(s, item)
        shed[item] = shed.get(item, 0) - n
    return proceeds


def _fork_signals(s: dict[str, Any]) -> dict[str, Any]:
    s2 = dict(s)
    s2["hires_today"] = s["hires_today"]
    s2["cows"] = s["cows"]
    s2["sheep"] = s["sheep"]
    s2["geese"] = s["geese"]
    s2["seeds"] = dict(s["seeds"])
    s2["shed"] = dict(s["shed"])
    s2["crops"] = dict(s["crops"])
    s2["regime"] = s.get("regime")
    s2["turn_plan"] = s.get("turn_plan")
    return s2


def _compute_sell_n(s: dict[str, Any], mode: str) -> int:
    """Unified sell-slot budget for market planning and harvest inventory targets."""
    tp = s.get("turn_plan")
    if tp is None:
        plan_turn(s)
        tp = s["turn_plan"]
    return compute_sell_n(
        tp,
        s,
        PARAMS,
        mode=mode,  # type: ignore[arg-type]
        base_prices=BASE_PRICE,
        px=px,
        ongoing_crops=ONGOING,
    )


def _start_market(s: dict[str, Any], mode: str) -> tuple[list, int, dict[str, Any]]:
    s2 = _fork_signals(s)
    market: list = []
    shed = s2["shed"]
    cash_deficit = float((s2.get("regime") or {}).get("cash_deficit", _cash_deficit(s2)))
    s2["liquidity_rescue"] = (
        mode != "LIQUIDATE"
        and s2.get("day", 0) <= int(PARAMS["liquidity_rescue_day_max"])
        and s2.get("empty", 0) >= 8
        and cash_deficit >= 900
    )
    sell_n = _compute_sell_n(s2, mode)

    proceeds = _sell_goods(market, s2, shed, max_actions=sell_n)
    wheat = shed.get("WHEAT", 0)
    if (mode == "LIQUIDATE" or s2["day"] >= 28) and wheat > 0:
        market.append(["SELL", "WHEAT", wheat])
        proceeds += wheat * px(s2, "WHEAT")
        shed["WHEAT"] = 0
    afford = int(s["money"]) + proceeds
    return market, afford, s2


def _coalesce_seed_buys(market: list) -> list:
    """Merge BUY_SEED of the same crop so berries do not spend two of the 10 slots."""
    merged: list = []
    seed_i: dict[str, int] = {}
    for act in market:
        if act and act[0] == "BUY_SEED" and len(act) >= 3:
            crop = act[1]
            if crop in seed_i:
                prev = merged[seed_i[crop]]
                merged[seed_i[crop]] = ["BUY_SEED", crop, int(prev[2]) + int(act[2])]
                continue
            seed_i[crop] = len(merged)
        merged.append(act)
    return merged


def _crew_hire_n(
    s: dict[str, Any],
    market: list,
    *,
    reserve_land: bool,
    hire_cap: int | None = None,
) -> int:
    """Hire count this market hour — phase cap yields to water-debt burst."""
    budget = _hire_budget(s, market, reserve_land=reserve_land)
    debt = int(s.get("unwatered") or 0)
    workers = max(1, int(s.get("workers") or 1))
    if debt > workers:
        return budget  # ignore phase hire_cap while drowning
    if hire_cap is None:
        return budget
    return min(budget, int(hire_cap))


def _pack_market(market: list, limit: int = MARKET_LIMIT) -> list:
    """Keep land, feed, berry seeds, then hires if we overflow the 10-action cap."""
    market = _coalesce_seed_buys(market)

    def rank(act: list) -> tuple[int, int]:
        if not act:
            return (9, 0)
        op = act[0]
        if op == "SELL":
            return (0, 0)
        if op == "BUY_LAND":
            return (1, 0)
        if op == "BUY_PRODUCT" and act[1] == "WHEAT":
            return (2, 0)
        if op == "BUY_SEED" and act[1] == "WHEAT":
            return (3, 0)
        if op == "BUY_SEED" and act[1] in CASH_PLANT:
            return (4, 0)
        if op == "HIRE":
            return (5, 0)
        if op == "BUY_SEED":
            return (6, 0)
        if op == "BUY_PRODUCT":
            return (7, 0)
        if op == "BUY_ANIMAL":
            return (8, 0)
        return (9, 0)

    if len(market) <= limit:
        return market
    ordered = sorted(enumerate(market), key=lambda iv: (rank(iv[1]), iv[0]))
    keep = {i for i, _ in ordered[:limit]}

    def force(pred) -> None:
        idx = next((i for i, a in enumerate(market) if pred(a)), None)
        if idx is None or idx in keep:
            return
        drop = max(keep, key=lambda i: (rank(market[i]), i))
        keep.remove(drop)
        keep.add(idx)

    force(lambda a: a and a[0] == "BUY_LAND")
    force(lambda a: a and a[0] == "BUY_PRODUCT" and a[1] == "WHEAT")
    force(lambda a: a and a[0] == "BUY_SEED" and a[1] in CASH_PLANT)
    force(lambda a: a and a[0] == "BUY_SEED" and a[1] == "WHEAT")
    force(lambda a: a and a[0] == "BUY_ANIMAL" and a[1] == "COW")
    return [act for i, act in enumerate(market) if i in keep]


def market_for(s: dict[str, Any], mode: str) -> list:
    day = s["day"]
    hour = s["hour"]

    if day == 0 and hour == 0:
        return [list(act) for act in OPENING_MARKET]

    if day == 0:
        return []

    if "turn_plan" not in s:
        plan_turn(s)
    tp = s["turn_plan"]

    market, afford, s2 = _start_market(s, mode)
    s2["_seeds_bought_this_market"] = False
    berry_gap_start = tp.berry_gap
    if mode == "LIQUIDATE":
        afford = _hire_up_to(market, afford, s2)
        return _pack_market(market)

    if tp.market_route == "late_sprint" and (
        s2["empty"] >= 8 or berry_gap_start > 0 or tp.cash_gap > 0
    ):
        hire_n = _crew_hire_n(
            s2, market, reserve_land=False, hire_cap=tp.profile.hire_cap
        )
        afford = _hire_up_to(market, afford, s2, hire_n)
        land_npv = _land_project_npv(s2, afford)
        cow_ev = _cow_project_score(s2) if not tp.defer_animals else 0.0
        seed_ev, n_seeds = _seed_project_score(s2)
        hire_ev = _hire_project_score(s2, afford)
        land_npv, cow_ev, seed_ev = _apply_hollow_capital_bias(
            s2,
            land_npv=land_npv,
            cow_ev=cow_ev,
            seed_ev=seed_ev,
            defer_animals=bool(tp.defer_animals),
        )
        can_land = land_npv > 0 or (s2["n_quads"] == 1 and _will_buy_land(s2, afford))
        if s2["n_quads"] == 1 and can_land and land_npv <= 0:
            land_npv = 1.0
        can_cow = cow_ev > 0 and afford >= ANIMAL_COST["COW"]
        can_seed = seed_ev > 0 and _seed_allowed_during_hollow(
            s2, land_npv=land_npv, cow_ev=cow_ev, afford=afford
        )
        can_hire = hire_ev > 0 and afford >= fib_hire_cost(int(s2.get("hires_today") or 0))
        la = _lookahead_project_scores(
            s2,
            afford,
            can_land=can_land,
            can_cow=can_cow,
            can_seed=can_seed,
            n_seeds=n_seeds,
        )
        if la is not None and int(PARAMS["lookahead_shadow"]) != 1:
            if la.get("land", 0.0) > 0 or la.get("cow", 0.0) > 0 or la.get("seed", 0.0) > 0:
                land_npv = float(la.get("land", 0.0))
                cow_ev = float(la.get("cow", 0.0)) if not tp.defer_animals else 0.0
                seed_ev = float(la.get("seed", 0.0))
                land_npv, cow_ev, seed_ev = _apply_hollow_capital_bias(
                    s2,
                    land_npv=land_npv,
                    cow_ev=cow_ev,
                    seed_ev=seed_ev,
                    defer_animals=bool(tp.defer_animals),
                )
                can_cow = cow_ev > 0 and afford >= ANIMAL_COST["COW"]
                can_seed = seed_ev > 0 and _seed_allowed_during_hollow(
                    s2, land_npv=land_npv, cow_ev=cow_ev, afford=afford
                )
                if s2["n_quads"] == 1 and can_land and land_npv <= 0:
                    land_npv = 1.0
        pick = choose_project(
            land_npv=land_npv,
            can_land=can_land,
            cow_ev=cow_ev,
            can_cow=can_cow,
            seed_ev=seed_ev,
            can_seed=can_seed,
            hire_ev=hire_ev,
            can_hire=can_hire,
        )
        afford = _execute_capital_pick(
            market,
            afford,
            s2,
            pick,
            defer_animals=bool(tp.defer_animals),
            berry_only_seeds=True,
        )
        afford = _buy_wheat_seeds(market, afford, s2, s2["seeds"])
        afford = _buy_feed_wheat(market, afford, s2)
        return _pack_market(market)

    if tp.market_route == "berry_prep":
        hire_n = _crew_hire_n(
            s2,
            market,
            reserve_land=need_land(s2),
            hire_cap=tp.profile.hire_cap,
        )
        afford = _hire_up_to(market, afford, s2, hire_n)
        # Allow land/cow NPV during prep so we do not skip expand-while-hollow.
        land_npv = _land_project_npv(s2, afford)
        cow_ev = 0.0 if tp.defer_animals else _cow_project_score(s2)
        seed_ev, _n = _seed_project_score(s2)
        land_npv, cow_ev, seed_ev = _apply_hollow_capital_bias(
            s2,
            land_npv=land_npv,
            cow_ev=cow_ev,
            seed_ev=seed_ev,
            defer_animals=bool(tp.defer_animals),
        )
        can_land = land_npv > 0 and _will_buy_land(s2, afford)
        can_cow = cow_ev > 0 and afford >= ANIMAL_COST["COW"]
        pick = choose_project(
            land_npv=land_npv,
            can_land=can_land,
            cow_ev=cow_ev,
            can_cow=can_cow,
            seed_ev=0.0,
            can_seed=False,
            hire_ev=0.0,
            can_hire=False,
        )
        if pick in ("land", "cow"):
            afford = _execute_capital_pick(
                market,
                afford,
                s2,
                pick,
                defer_animals=bool(tp.defer_animals),
                berry_only_seeds=True,
            )
        afford = _buy_berry_prep_seeds(market, afford, s2, s2["seeds"])
        afford = _buy_wheat_seeds(market, afford, s2, s2["seeds"])
        return _pack_market(market)

    # Hire first so expansion NPV sees the crew we can afford.
    hire_n = _crew_hire_n(s2, market, reserve_land=need_land(s2))
    afford = _hire_up_to(market, afford, s2, hire_n)

    land_npv = _land_project_npv(s2, afford)
    cow_ev = 0.0 if tp.defer_animals else _cow_project_score(s2)
    seed_ev, n_seeds = _seed_project_score(s2)
    hire_ev = _hire_project_score(s2, afford)
    # Pizza / milk stack: mouths outrank tomato seed stockpiles.
    if (
        current_engine(s2) == "MILK"
        and milk_sink(s2) >= 2
        and cow_ev > 0
        and not tp.defer_animals
    ):
        cow_ev = max(cow_ev, seed_ev + 1.0)
    if (
        cow_ev > 0
        and not tp.defer_animals
        and int(s2.get("n_quads") or 0) >= 2
        and int(s2.get("day") or 0) <= int(PARAMS.get("hollow_land_day_max", 14))
        and int(s2.get("cows") or 0) < int(PARAMS.get("berry_melon_bridge_cow_cap", 8))
        and int(s2.get("empty") or 0) > int(PARAMS.get("land_hollow_soft_cap", 14))
        and (
            int(s2.get("empty") or 0) >= int(PARAMS.get("hollow_herd_deep_empty", 20))
            or milk_sink(s2) >= 1
            or (egg_sink(s2) >= 1 and berry_sink(s2) == 0)
        )
    ):
        cow_ev = max(cow_ev, seed_ev + float(PARAMS.get("hollow_land_priority_boost", 1.0)))
    # Softfloor milk+berry herd: while still hollow, cows before densify seeds.
    if (
        milk_sink(s2) >= 1
        and berry_sink(s2) >= 1
        and int(s2.get("n_quads") or 0) >= 2
        and int(s2.get("day") or 0) <= 12
        and int(s2.get("cows") or 0) < int(PARAMS.get("berry_melon_bridge_cow_cap", 8))
        and int(s2.get("empty") or 0) > int(PARAMS.get("land_hollow_soft_cap", 14))
        and cow_ev > 0
        and not tp.defer_animals
        and _lane_b_berry_gap(s2) <= 0
    ):
        cow_ev = max(cow_ev, seed_ev + 1.0)
    # Package B Lane B: once herd is near ready, berry seeds beat extra cows.
    lane_gap = _lane_b_berry_gap(s2)
    if lane_gap > 0:
        # Speculative strawberry often scores seed_ev=0 without berry shops.
        seed_ev = max(seed_ev, float(lane_gap) * 2.0)
        cows = int(s2.get("cows") or 0)
        cow_floor = int(PARAMS.get("lane_b_cow_floor", 4))
        if cows >= cow_floor or cows >= int(PARAMS.get("land2_schedule_cow_min", 6)):
            seed_ev = max(seed_ev, cow_ev + 1.0)
        elif cows >= max(0, cow_floor - 1):
            seed_ev = max(seed_ev, cow_ev + 0.5)
    land_npv, cow_ev, seed_ev = _apply_hollow_capital_bias(
        s2,
        land_npv=land_npv,
        cow_ev=cow_ev,
        seed_ev=seed_ev,
        defer_animals=bool(tp.defer_animals),
    )
    # 1→2 land is survival; plot-3+ relies on expansion NPV.
    can_land = land_npv > 0 or (s2["n_quads"] == 1 and _will_buy_land(s2, afford))
    if can_land and land_npv <= 0 and s2["n_quads"] == 1:
        land_npv = 1.0
    can_cow = cow_ev > 0 and afford >= ANIMAL_COST["COW"]
    can_seed = seed_ev > 0 and _seed_allowed_during_hollow(
        s2, land_npv=land_npv, cow_ev=cow_ev, afford=afford
    )
    can_hire = hire_ev > 0 and afford >= fib_hire_cost(int(s2.get("hires_today") or 0))

    # 2–5 day bucket look-ahead for capital choice (shadow or live).
    la = _lookahead_project_scores(
        s2,
        afford,
        can_land=can_land,
        can_cow=can_cow and not tp.defer_animals,
        can_seed=can_seed,
        n_seeds=n_seeds,
    )
    shadow = int(PARAMS["lookahead_shadow"]) == 1
    if la is not None and not shadow:
        # Live: look-ahead $ deltas drive the chooser; closed-form is fallback
        # only when every project scores ≤ 0.
        if la.get("land", 0.0) > 0 or la.get("cow", 0.0) > 0 or la.get("seed", 0.0) > 0:
            land_npv = float(la.get("land", 0.0))
            cow_ev = float(la.get("cow", 0.0)) if not tp.defer_animals else 0.0
            seed_ev = float(la.get("seed", 0.0))
            land_npv, cow_ev, seed_ev = _apply_hollow_capital_bias(
                s2,
                land_npv=land_npv,
                cow_ev=cow_ev,
                seed_ev=seed_ev,
                defer_animals=bool(tp.defer_animals),
            )
            if lane_gap > 0 and seed_ev > 0:
                cows = int(s2.get("cows") or 0)
                if cows >= int(PARAMS.get("lane_b_cow_floor", 4)):
                    seed_ev = max(seed_ev, cow_ev + 1.0)
            if can_land and land_npv <= 0 and s2["n_quads"] == 1:
                land_npv = 1.0
            can_cow = cow_ev > 0 and afford >= ANIMAL_COST["COW"]
            can_seed = seed_ev > 0 and _seed_allowed_during_hollow(
                s2, land_npv=land_npv, cow_ev=cow_ev, afford=afford
            )
    # Shadow mode: still execute closed-form; look-ahead is computed for parity.

    pick = choose_project(
        land_npv=land_npv,
        can_land=can_land,
        cow_ev=cow_ev,
        can_cow=can_cow,
        seed_ev=seed_ev,
        can_seed=can_seed,
        hire_ev=hire_ev,
        can_hire=can_hire,
    )
    if pick != "land" and can_land and _plot3_qualified_buy(s2):
        pick = "land"
    if pick != "seed" and can_seed and lane_gap > 0 and pick == "cow":
        # Prefer berry seeds over the next cow once the herd floor is met.
        if int(s2.get("cows") or 0) >= int(PARAMS.get("lane_b_cow_floor", 4)):
            pick = "seed"

    afford = _execute_capital_pick(
        market,
        afford,
        s2,
        pick,
        defer_animals=bool(tp.defer_animals),
        berry_only_seeds=lane_gap > 0,
    )

    afford = _buy_wheat_seeds(market, afford, s2, s2["seeds"])
    afford = _buy_feed_wheat(market, afford, s2)
    # Leftover cow if seeds/land did not win and cash remains.
    if pick != "cow" and afford >= 1200 and len(market) < MARKET_LIMIT and not tp.defer_animals:
        _buy_animals(market, afford, s2)
    return _pack_market(market)


def agent(obs: dict[str, Any]) -> dict[str, Any]:
    global _LAND_SPRINT, _LATE_SHOP_SPRINT, _SHOP_TRACK, _UPTREND_HOURS
    if obs.get("day", 0) == 0 and (obs.get("hour") or 0) == 0:
        _LAND_SPRINT["until_day"] = -1
        _LATE_SHOP_SPRINT["until_day"] = -1
        _SHOP_TRACK["prev_shops"] = set()
        _SHOP_TRACK["first_berry_day"] = None
        _SHOP_TRACK["first_milk_day"] = None
        _SHOP_TRACK["archetype"] = "UNKNOWN"
        _SHOP_TRACK["archetype_locked"] = False
        _UPTREND_HOURS.clear()

    s = read_signals(obs)
    update_price_book(s)
    update_shop_tracking(s)
    update_uptrend_tracking(s)
    refresh_planning_scores(s)
    tp = plan_turn(s)
    mode = tp.mode
    market = []
    seeds = dict(s["seeds"])
    claimed = set()
    n_feeders = min(s["workers"], s["hungry"]) if s["hungry"] else 0
    early_wheat = s["hungry"] > 0 and s["shed"].get("WHEAT", 0) == 0
    sprint = tp.flags.plant_sprint
    densify3 = _densify3_fill_active(s)
    if densify3:
        sprint = True
    pack = _pack_berry_active(s)
    if pack:
        sprint = True
    ramp = tp.flags.berry_ramp or tp.flags.cash_ramp
    plan = tp.crops
    sell_n_est = _compute_sell_n(s, mode)

    inventory_target: dict[str, float] = {}
    inventory_stock: dict[str, float] = {}
    harvest_crops = ("STRAWBERRY", "CARROT", "TOMATO")
    for c in harvest_crops:
        base = max(2.0, min(10.0, float(plan.get(c, 0)) / 3.0))
        scaled = base * (sell_n_est / 3.0)
        inv_target = max(1.0, min(12.0, scaled))
        inventory_target[c] = inv_target
        inventory_stock[c] = float(s["shed"].get(c, 0))
    berry_waiting = (
        seeds.get("STRAWBERRY", 0) > 0
        and tp.flags.berry_ok
        and (
            tp.berry_gap > 0
            or (int(s.get("empty") or 0) > 0 and engine_replant_open(s))
        )
    ) or (
        bool(tp.cash_crop)
        and seeds.get(tp.cash_crop, 0) > 0
        and (
            tp.cash_gap > 0
            or (int(s.get("empty") or 0) > 0 and engine_replant_open(s))
        )
    )
    if densify3 and seeds.get("STRAWBERRY", 0) > 0:
        berry_waiting = True
    if pack and seeds.get("STRAWBERRY", 0) > 0:
        berry_waiting = True
    ctx = {
        "feeder": [max(1, n_feeders)],
        "is_feeder": False,
        "at_risk": s["at_risk"],
        "hungry": s["hungry"],
        "fert_ready": s["fert_ready"],
        "unwatered": s["unwatered"],
        "water_stress": field_water_stress(s),
        "carried": None,
        "has_wheat": False,
        "early_wheat": early_wheat,
        "plant_sprint": sprint,
        "berry_ramp": ramp,
        "fill_board": tp.fill_board or pack,
        "harvest_focus": tp.harvest_focus,
        "cash_crop": tp.cash_crop,
        "empty": s["empty"],
        "workers": int(s.get("workers") or 0),
        "tile_ev": float(tp.budget.tile_ev) if tp.budget else 0.0,
        "productive_days": int(tp.budget.productive_days) if tp.budget else 1,
        "plantable": int(tp.budget.plantable) if tp.budget else 0,
        "berry_waiting": berry_waiting,
        "pasture_bind_builds": 0,
        "cash_seeds": (
            seeds.get("STRAWBERRY", 0) > 0
            or seeds.get("CARROT", 0) > 0
            or seeds.get("MELON", 0) > 0
            or seeds.get("TOMATO", 0) > 0
        ),
        "cash_waiting": cash_waiting(s, seeds) or (
            (densify3 or pack) and seeds.get("STRAWBERRY", 0) > 0
        ),
        "wheat_waiting": wheat_waiting(s, seeds),
        "use_fert": _keep_fert(s) > 0,
        "skip_care": milk_px(s) < 40,
        # Harvest priority signals (explicitly decoupled from sell-now rules).
        "crop_ev_score": {c: harvest_ev_score(s, c) for c in CASH_PLANT},
        "inventory_target": inventory_target,
        "inventory_stock": inventory_stock,
        # Project harvested outputs for in-turn market planning. We already
        # model cash-crop inventory via `inventory_stock`; this tracks
        # everything else (e.g. WHEAT) without interfering with harvest
        # urgency.
        "shed_delta": {},
    }
    me = obs["farms"][obs["player"]]
    private = obs["private"]
    fx, fy = me["farmer"]
    farmer, seeds = action_for(
        me["tiles"],
        fx,
        fy,
        s["day"],
        seeds,
        claimed,
        s,
        private["inventories"][0],
        ctx,
    )
    hands = []
    for i, (hx, hy) in enumerate(me["hands"]):
        action, seeds = action_for(
            me["tiles"],
            hx,
            hy,
            s["day"],
            seeds,
            claimed,
            s,
            private["inventories"][i + 1],
            ctx,
        )
        hands.append(action)
    # Harvest-to-market projection: farmer actions are chosen before the
    # environment applies harvest outputs. Project harvested cash crops into
    # `shed` so `_sell_goods()` / `_start_market()` sees the correct inventory.
    inv_stock = ctx.get("inventory_stock") or {}
    for c, v in inv_stock.items():
        s["shed"][c] = int(v)
    shed_delta = ctx.get("shed_delta") or {}
    for c, d in shed_delta.items():
        # Cash crops are already projected via `inventory_stock`.
        if c not in inv_stock:
            s["shed"][c] = s["shed"].get(c, 0) + int(d)
    market = market_for(s, mode)
    return {"farmer": farmer, "hands": hands, "market": market}
