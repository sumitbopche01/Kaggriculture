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
MAX_HANDS = 12
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
    ["BUY_SEED", "WHEAT", 7],
    ["BUY_PRODUCT", "WHEAT", 6],
]

DEFAULT_PARAMS: dict[str, int | float] = {
    # Slice A wheat engine
    "wheat_engine_day_max": 20,
    "wheat_buffer_add": 2,
    "wheat_min_tiles": 6,
    "wheat_no_mouth_tiles": 4,
    "wheat_filler_day_max": 20,
    "late_wheat_seed_buffer_day_min": 16,
    "late_wheat_seed_buffer": 2,
    # Melon filler (only when berries exist)
    "melon_leftover_min": 8,
    "melon_n_quads_min": 3,
    "melon_day_max": 16,
    # Herd ramp gates
    "cow_day_max": 20,
    "cow_milk_px_min": 80,
    "cow_floor_day_max": 20,
    "cow_floor": 2,
    "cow_expand_cap": 10,
    "sheep_day_max": 20,
    "sheep_wool_px_min": 80,
    "sheep_floor_day_max": 20,
    "sheep_floor": 2,
    "sheep_expand_cap": 4,
    # Land timing / guards
    "land_day_min": 6,
    "land_day_max": 22,
    "max_quads_for_land": 3,
    "land2_day_min": 11,
    "land2_day_max": 22,
    "land2_money_min": 4000,
    "land2_empty_max": 4,
    "land2_strawberry_min": 16,
    # Sell-hold heuristic
    "sell_hold_price_factor": 0.82,
    "sell_hold_days_left_min": 7,  # days_left(day) > 6
    # Animal buy caps
    "animal_buy_day_max": 20,
    "animal_buy_day_min": 3,
    "mouth_cap_1q": 6,
    "mouth_cap_2qplus": 14,
    "animal_cash_floor_2qplus": 400,
    "animal_cash_floor_1q": 1200,
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
    s["mean3"] = {
        item: (
            (sum(series[-72:]) / len(series[-72:]))
            if series
            else float(prices.get(item, 0))
        )
        for item, series in hist.items()
    }


def milk_sink(s: dict[str, Any]) -> int:
    return sum(1 for shop in s.get("shops") or [] if shop in MILK_SHOPS)


def berry_sink(s: dict[str, Any]) -> int:
    return sum(1 for shop in s.get("shops") or [] if shop in BERRY_SHOPS)


_LAND_SPRINT: dict[str, int] = {"until_day": -1}


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
    if s["day"] > 22:
        return False
    return _LAND_SPRINT.get("until_day", -1) >= s["day"]


def berry_replant_push(s: dict[str, Any]) -> bool:
    return 12 <= s["day"] <= 26 and berry_ok(s) and berry_gap(s) > 0


def seed_fill_push(s: dict[str, Any]) -> bool:
    """Buy/plant aggressively after land buys or when many tiles sit empty."""
    if s["day"] > 22:
        return False
    # Slightly lower threshold to reduce idle tiles earlier.
    return plant_sprint(s) or s["empty"] >= 8


def berry_ramp(s: dict[str, Any]) -> bool:
    """Berry shop open midgame with room to plant — ramp through day 16."""
    # Start the ramp slightly earlier so strawberries can mature by day 16.
    if not berry_ok(s) or s["day"] < 7 or s["day"] > 16:
        return False
    if s["empty"] < 2:
        return False
    target = crop_plan(s).get("STRAWBERRY", 0)
    if target <= 0:
        return False
    have = s["crops"].get("STRAWBERRY", 0) + s["seeds"].get("STRAWBERRY", 0)
    if have >= target:
        return False
    if s["n_quads"] == 1 and have >= 8:
        return False
    return berry_gap(s) >= 3


def berry_seed_push(s: dict[str, Any]) -> bool:
    return berry_replant_push(s) or berry_ramp(s)


def land_bundle_cost(s: dict[str, Any]) -> int:
    if s["n_quads"] >= 4:
        return 0
    return LAND_COST[s["n_quads"] - 1] + 800


def _will_buy_land(s: dict[str, Any], afford: int) -> bool:
    if not need_land(s) or s["n_quads"] >= 4:
        return False
    cost = LAND_COST[s["n_quads"] - 1]
    if int(s["money"]) < land_bundle_cost(s):
        return False
    if afford < cost + 800:
        return False
    if s["n_quads"] >= 2 and afford - cost < 1500:
        return False
    if not cash_shop(s):
        best_ev = max(s["scores"].values()) if s["scores"] else 0.0
        if best_ev * 25 * max(3, days_left(s["day"]) // 2) < cost:
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
    mouths = mouths_of(s)
    if mouths <= 0:
        return True
    if s["crops"].get("WHEAT", 0) < mouths + 1:
        return False
    if wheat_stock(s) < mouths + 2:
        return False
    return True


def egg_sink(s: dict[str, Any]) -> int:
    return sum(1 for shop in s.get("shops") or [] if shop in ("BAKERY", "BRUNCH_SPOT"))


def crop_score(
    crop: str, price: int, day: int, demand: dict[str, int] | None = None
) -> float:
    """Expected coins per tile-day at the live price. Shops only boost slightly."""
    left = days_left(day)
    demand = demand or {}
    price = max(1, price)
    boost = 1.0 + 0.05 * demand.get(crop, 0)
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
            return 0.0
        n = min(4, left - 7)
        return boost * (n * price - 50) / min(12.0, left)
    if crop == "STRAWBERRY":
        if left < 8:
            return 0.0
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


def tile_budget(s: dict[str, Any]) -> tuple[int, int, int]:
    tiles = s["n_quads"] * 25
    mouths = mouths_of(s)
    # Slice A: keep wheat ahead of mouths (`mouths + 2`) early on
    # so `herd_can_expand()` can flip once the 2nd land buys land/animals.
    if mouths and s["day"] <= PARAMS["wheat_engine_day_max"]:
        wheat_tiles = max(
            PARAMS["wheat_min_tiles"], mouths + PARAMS["wheat_buffer_add"]
        )
    else:
        wheat_tiles = (
            max(PARAMS["wheat_min_tiles"], mouths)
            if mouths
            else PARAMS["wheat_no_mouth_tiles"]
        )
    cash_room = max(0, tiles - mouths - wheat_tiles)
    return tiles, cash_room, wheat_tiles


def berry_tile_cap(s: dict[str, Any]) -> int:
    """Strawberries scale with land. A hard 16 left extra quadrants empty."""
    if s["n_quads"] <= 1:
        return 8
    if s["n_quads"] == 2:
        return 28
    if s["n_quads"] == 3:
        return 48
    return 60


def crop_plan(s: dict[str, Any]) -> dict[str, int]:
    """How many tiles of each crop to hold.

    Allocate cash tiles to the most profitable cash crops available from the
    currently open shops (and melon as an EV-based fallback).
    """
    _, room, wheat_tiles = tile_budget(s)
    plan = {c: 0 for c in SEED_COST}
    plan["WHEAT"] = wheat_tiles
    leftover = room
    demand = s.get("demand") or {}
    # Early-game melon is a small EV cash-cycle starter while there is
    # no STRAWBERRY demand yet. (Using `demand` avoids mismatches where
    # some berry shops contribute to strawberry demand but aren't counted
    # by `berry_sink`.)
    melon_early = demand.get("STRAWBERRY", 0) == 0 and s["day"] <= 6

    def take(crop: str, cap: int) -> None:
        nonlocal leftover
        if leftover <= 0 or cap <= 0:
            return
        n = min(leftover, cap)
        plan[crop] = n
        leftover -= n

    candidates: list[str] = []
    if demand.get("STRAWBERRY", 0) >= 1 and crop_score("STRAWBERRY", px(s, "STRAWBERRY"), s["day"], demand) > 0:
        candidates.append("STRAWBERRY")
    if demand.get("CARROT", 0) >= 1 and crop_score("CARROT", px(s, "CARROT"), s["day"], demand) > 0:
        candidates.append("CARROT")
    if demand.get("TOMATO", 0) >= 1 and crop_score("TOMATO", px(s, "TOMATO"), s["day"], demand) > 0:
        candidates.append("TOMATO")
    if (
        leftover >= PARAMS["melon_leftover_min"]
        and (s["n_quads"] >= PARAMS["melon_n_quads_min"] or melon_early)
        and s["day"] <= PARAMS["melon_day_max"]
        and live_ev(s, "MELON") > live_ev(s, "WHEAT")
    ):
        candidates.append("MELON")

    # EV-driven allocator: increment one cash tile at a time, choosing the
    # crop with best EV per seed-cost. This replaces fixed per-crop caps.
    def tile_marginal_score(crop: str) -> float:
        price = px(s, crop)
        ev = float(s["scores"].get(crop, 0.0) or 0.0)
        cost = float(SEED_COST.get(crop, 1))
        # Mild momentum tilt so the allocator prefers uptrends.
        delta = (s.get("delta") or {}).get(crop, 0)
        momentum = 1.0 + max(-0.2, min(0.2, float(delta) / 200.0))
        return ev

    # Keep allocation stable by using the candidate set as the search space.
    # (We already gated candidates with crop_score > 0.)
    cap_map: dict[str, int] = {}
    for c in candidates:
        if c == "STRAWBERRY":
            cap_map[c] = berry_tile_cap(s)
        elif c == "CARROT":
            cap_map[c] = 4 if s["n_quads"] == 1 else 8
        elif c == "TOMATO":
            cap_map[c] = 4 if s["n_quads"] == 1 else 8
        elif c == "MELON":
            cap_map[c] = min(3 if melon_early else 8, leftover)
        else:
            cap_map[c] = 0

    while leftover > 0:
        remaining = [c for c in candidates if plan[c] < cap_map.get(c, 0)]
        if not remaining:
            break
        best = max(remaining, key=tile_marginal_score)
        if tile_marginal_score(best) <= 0:
            break
        plan[best] += 1
        leftover -= 1

    # Slice A wheat filler: only when there is no berry shop demand yet.
    # (This keeps `pick_crop`/plant scheduling aligned with `_buy_wheat_seeds()`.)
    if (
        berry_sink(s) == 0
        and s["day"] <= PARAMS["wheat_filler_day_max"]
        and leftover > 0
    ):
        plan["WHEAT"] += leftover
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
    if s["day"] > PARAMS["cow_day_max"] or milk_px(s) < PARAMS["cow_milk_px_min"]:
        return s["cows"]
    floor = PARAMS["cow_floor"] if s["day"] <= PARAMS["cow_floor_day_max"] else 0
    if s["cows"] < floor:
        return floor
    if milk_sink(s) == 0:
        return s["cows"]
    if s["n_quads"] == 1:
        return s["cows"]
    if not herd_can_expand(s):
        return s["cows"]
    return min(s["cows"] + 1, PARAMS["cow_expand_cap"])


def want_sheep(s: dict[str, Any]) -> int:
    if s["day"] > PARAMS["sheep_day_max"] or wool_px(s) < PARAMS["sheep_wool_px_min"]:
        return s["sheep"]
    floor = PARAMS["sheep_floor"] if s["day"] <= PARAMS["sheep_floor_day_max"] else 0
    if s["sheep"] < floor:
        return floor
    if s["demand"].get("WOOL", 0) <= 0:
        return s["sheep"]
    if s["n_quads"] == 1:
        return s["sheep"]
    if not herd_can_expand(s):
        return s["sheep"]
    return min(s["sheep"] + 1, PARAMS["sheep_expand_cap"])


def want_geese(s: dict[str, Any]) -> int:
    if s["day"] > 20 or egg_sink(s) == 0:
        return s["geese"]
    egg_px = px(s, "EGG")
    goose_ev = animal_score("GOOSE", egg_px, s["day"])
    # Saturated egg-shop maps (2× bakery + brunch) need cash for berries, not geese.
    if egg_sink(s) >= 3 and egg_px < 80:
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
    return min(s["geese"] + 1, max_geese)


def need_land(s: dict[str, Any]) -> bool:
    if (
        s["day"] < PARAMS["land_day_min"]
        or s["n_quads"] >= PARAMS["max_quads_for_land"]
    ):
        return False
    if s["n_quads"] == 1 and s["day"] >= PARAMS["land_day_max"]:
        return False
    if s["n_quads"] == 2 and s["day"] >= PARAMS["land2_day_max"]:
        return False
    if s["n_quads"] == 1 and s["empty"] > 10:
        return False
    _, cash_room, _ = tile_budget(s)
    if s["n_quads"] == 1:
        # Winners often buy land slightly before the board is fully filled,
        # as long as there is cash-shop demand to fund the next reinvest.
        if s["empty"] > 11:
            return False
        if s["empty"] <= 8:
            return True
        if s["empty"] <= 11 and cash_shop(s) and s["day"] <= 7:
            return True
        if cash_room <= 4 and cash_shop(s):
            return True
        if s["seeds"].get("STRAWBERRY", 0) >= 4 and s["empty"] <= 10:
            return True
        return False
    if s["n_quads"] == 2:
        if s["day"] < PARAMS["land2_day_min"]:
            return False
        if int(s["money"]) < PARAMS["land2_money_min"]:
            return False
        if s["empty"] > PARAMS["land2_empty_max"]:
            return False
        if berry_ok(s) and s["crops"]["STRAWBERRY"] < PARAMS["land2_strawberry_min"]:
            return False
        return True
    return False


def want_hands(s: dict[str, Any]) -> int:
    """Leaders rehire a full crew every morning. Day 0 stays the 5-hire opening."""
    if s["day"] == 0:
        return 5
    if s["n_quads"] >= 2 or mouths_of(s) >= 8:
        return 12
    if mouths_of(s) >= 1 or berry_ok(s):
        return 8
    return 5


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
    if s["day"] >= 28:
        return "LIQUIDATE"
    return "ENGINE"


def cash_waiting(s: dict[str, Any], seeds: dict[str, int] | None = None) -> bool:
    seeds = seeds if seeds is not None else s["seeds"]
    plan = crop_plan(s)
    return any(
        seeds.get(crop, 0) > 0 and s["crops"][crop] < plan.get(crop, 0)
        for crop in CASH_PLANT
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
    wheat_floor = max(4, plan.get("WHEAT", 0) if mouths else 0)
    if s["crops"]["WHEAT"] < wheat_floor and seeds.get("WHEAT", 0) > 0:
        return "WHEAT"
    if s["crops"]["WHEAT"] == 0 and shed_w == 0 and seeds.get("WHEAT", 0) > 0:
        return "WHEAT"
    cash = [
        crop
        for crop in CASH_PLANT
        if seeds.get(crop, 0) > 0 and s["crops"][crop] < plan.get(crop, 0)
    ]
    if cash:
        return max(cash, key=lambda c: s["scores"].get(c, 0.0))
    if (
        berry_ok(s)
        and s["day"] <= 26
        and seeds.get("STRAWBERRY", 0) > 0
        and berry_gap(s) > 0
        and (s["day"] >= 12 or berry_ramp(s))
    ):
        return "STRAWBERRY"
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
                    priority = 0
                    # `candidate` tuple sorts ascending, so negate the score.
                    urgency = -(ev_score + inv_score)
                elif not t["watered_today"] and t.get("consecutive_unwatered", 0) >= 1:
                    priority = 0
                    urgency = -5
                elif not t["watered_today"] and (hungry == 0 or not has_wheat):
                    cash = t.get("crop") in CASH_CROPS
                    if fert_ready == 0 or ctx.get("use_fert") or cash or not has_wheat:
                        priority = 2 if ctx.get("use_fert") else 4
                elif (
                    has_fertilizer
                    and t.get("crop") in CASH_CROPS
                    and ctx.get("use_fert")
                    and t.get("fertilized_until_day", -1) < day
                    and hungry == 0
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
                    elif t.get("fertilizer_available"):
                        if hungry == 0 or not has_wheat:
                            priority = 0
                            urgency = -15
                    elif (
                        not t.get("cared_today")
                        and t.get("fed_today")
                        and hungry == 0
                        and fert_ready == 0
                        and not ctx.get("skip_care")
                        and not ctx.get("plant_sprint")
                    ):
                        priority = 3
                elif ctx["carried"] and ANIMAL_STRUCT.get(ctx["carried"]) == t.get(
                    "kind"
                ):
                    priority = 2
            elif isinstance(t, dict) and t.get("kind") == "WEED":
                if hungry == 0:
                    if ctx.get("plant_sprint") or ctx.get("berry_ramp"):
                        priority = 0
                        urgency = 8
                    elif ctx.get("cash_waiting"):
                        priority = 1
                        urgency = 3
                    else:
                        priority = 2
                        urgency = 2
            elif t is None:
                waiting_plant = ctx.get("cash_waiting") or ctx.get("wheat_waiting")
                waiting_berry = ctx.get("berry_waiting")
                if (
                    (ctx.get("plant_sprint") or ctx.get("berry_ramp"))
                    and hungry == 0
                    and has_seeds
                    and (waiting_plant or waiting_berry)
                ):
                    priority = 0
                    urgency = 10
                elif (
                    ctx.get("need_pasture") or ctx.get("need_coop")
                ) and not waiting_plant:
                    priority = 1
                elif hungry == 0 and has_seeds:
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
    ctx["need_pasture"] = need_pasture
    ctx["need_coop"] = need_coop
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
        if crop_ready(tile, day, ctx.get("early_wheat", False)):
            crop = tile.get("crop")
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
        ):
            claimed.add((x, y))
            return ["FERTILIZE"], seeds
        at_risk_tile = tile.get("consecutive_unwatered", 0) >= 1
        if not tile["watered_today"] and not is_feeder:
            claimed.add((x, y))
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
    for _ in range(n_hire):
        cost = fib_hire_cost(s["hires_today"])
        if afford < cost + (40 if mouths_of(s) > 0 else 0):
            break
        market.append(["HIRE"])
        afford -= cost
        s["hires_today"] += 1
    return afford


def _maybe_buy_land(market: list, afford: int, s: dict[str, Any]) -> int:
    if not _will_buy_land(s, afford):
        return afford
    cost = LAND_COST[s["n_quads"] - 1]
    market.append(["BUY_LAND"])
    # Land buy should trigger a short, aggressive replant window so the
    # board fills quickly enough for later land upgrades.
    _LAND_SPRINT["until_day"] = s["day"] + 2
    return afford - cost


def _buy_planned_seeds(
    market: list,
    afford: int,
    s: dict[str, Any],
    seeds: dict[str, int],
    *,
    berry_only: bool = False,
) -> int:
    plan = crop_plan(s)
    cash_planned = any(plan.get(c, 0) > 0 for c in CASH_PLANT)
    cap_n = 8 if cash_planned else 4
    if s["n_quads"] >= 2 and afford >= 1600:
        cap_n = 12
    if s["n_quads"] >= 3 and afford >= 2000:
        cap_n = 16
    if berry_replant_push(s):
        cap_n = max(cap_n, 16)
    elif berry_ramp(s):
        cap_n = max(cap_n, 8)
    if seed_fill_push(s):
        cap_n = max(cap_n, min(16, s["empty"]))
    order = [c for c in CASH_PLANT if plan.get(c, 0) > 0]

    # "Stock market" style ranking: prefer crops where we still need tiles,
    # with highest EV, boosted slightly by upward price momentum.
    def marginal_score(c: str) -> float:
        have = s["crops"][c] + seeds.get(c, 0)
        need_tiles = plan[c] - have
        if need_tiles <= 0:
            return -1e9
        ev = float(s["scores"].get(c, 0.0))
        delta = (s.get("delta") or {}).get(c, 0)
        # Symmetric momentum: reward uptrend, penalize downtrend.
        momentum = 1.0 + max(-0.2, min(0.2, float(delta) / 200.0))
        cost = float(SEED_COST.get(c, 1))
        return (need_tiles * ev * max(0.6, momentum)) / max(1.0, cost)

    order.sort(key=marginal_score, reverse=True)
    fill_push = seed_fill_push(s)
    if berry_only:
        # Conservative mode: one crop unless land-sprint fill needs diversity.
        if plan.get("STRAWBERRY", 0) > 0:
            order = ["STRAWBERRY"]
        else:
            order = order[: 2 if plant_sprint(s) else 1]
    remaining = list(order)
    while remaining and afford > 0 and len(market) < MARKET_LIMIT:
        remaining.sort(key=marginal_score, reverse=True)
        crop = remaining[0]
        have = s["crops"][crop] + seeds.get(crop, 0)
        need = plan[crop] - have
        if need <= 0:
            remaining.pop(0)
            continue

        if crop == "STRAWBERRY":
            if berry_replant_push(s):
                keep = 80
            elif berry_ramp(s):
                keep = 200
            else:
                keep = 400 if s["n_quads"] >= 2 else 800
            if plant_sprint(s):
                keep = min(keep, 200)
            elif s["empty"] >= 12:
                keep = min(keep, 120)
            if berry_only:
                need = max(need, min(8, max(4, berry_gap(s) + 2)))
        else:
            keep = 200 if plant_sprint(s) else 800

        # Safety clamp: never reserve more cash than we currently have.
        keep = max(0, min(afford - 1, keep))

        if not berry_only and crop != "STRAWBERRY" and len(market) >= MARKET_LIMIT:
            break

        n_before = len(market)
        afford = _append_seed(market, afford, crop, min(need, cap_n), keep=keep)
        if len(market) > n_before:
            seeds[crop] = seeds.get(crop, 0) + int(market[-1][2])
        else:
            break
    return afford


def _buy_animals(market: list, afford: int, s: dict[str, Any]) -> int:
    below_floor = s["cows"] < 2 or s["sheep"] < 2
    if s["hour"] != 0 and not below_floor:
        return afford
    if s["day"] >= PARAMS["animal_buy_day_max"] and not below_floor:
        return afford
    if s["day"] < PARAMS["animal_buy_day_min"] and not below_floor:
        return afford
    if (
        s["shed"].get("COW", 0)
        or s["shed"].get("SHEEP", 0)
        or s["shed"].get("GOOSE", 0)
    ):
        return afford
    if s["crops"]["WHEAT"] < 4:
        return afford
    if not below_floor and not herd_can_expand(s):
        return afford
    if not below_floor and mouths_of(s) >= s["crops"]["WHEAT"]:
        return afford
    _, cash_room, _ = tile_budget(s)
    mouth_cap = (
        PARAMS["mouth_cap_1q"] if s["n_quads"] == 1 else PARAMS["mouth_cap_2qplus"]
    )
    if mouths_of(s) >= mouth_cap:
        return afford
    if s["n_quads"] == 1 and cash_shop(s) and cash_room < 6 and not below_floor:
        return afford
    seed_gap = berry_gap(s)
    reserve = min(900, seed_gap * SEED_COST["STRAWBERRY"])
    if below_floor:
        reserve = min(reserve, 200)
    cash_floor = (
        PARAMS["animal_cash_floor_2qplus"]
        if s["n_quads"] >= 2
        else PARAMS["animal_cash_floor_1q"]
    )
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
    price = px(s, item)
    # Winners liquidate strawberries aggressively once the berry-shop mix is
    # strong (multiple berry sinks open). Don't let the generic hold heuristic
    # block cash-out in that midgame window.
    if item == "STRAWBERRY" and s.get("berry_sink", 0) >= 2:
        return n * price
    if (
        item in ("STRAWBERRY", "MELON", "MILK", "WOOL")
        and days_left(s["day"]) >= PARAMS["sell_hold_days_left_min"]
    ):
        hist = float(s.get("mean3", {}).get(item, price) or price)
        if hist > 0 and price < hist * PARAMS["sell_hold_price_factor"]:
            # If the market is moving up (positive delta), sell instead of
            # holding through a likely bounce.
            delta = int(s.get("delta", {}).get(item, 0) or 0)
            days_left_v = days_left(s["day"])
            if not (delta > 0 and days_left_v <= PARAMS["sell_hold_days_left_min"] + 3):
                threshold = hist * float(PARAMS["sell_hold_price_factor"])
                ratio = (price / threshold) if threshold > 0 else 0.0
                hold_cutoff = 0.85
                if ratio < hold_cutoff:
                    return 0
                # Near-threshold smoothing: allow selling but with a reduced
                # score so it only triggers when we're close to the hold boundary.
                t = (ratio - hold_cutoff) / max(1e-9, (1.0 - hold_cutoff))
                t = max(0.0, min(1.0, t))
                scale = 0.15 + 0.85 * t
                return int(n * price * scale)
    return n * price


def _sell_goods(
    market: list, s: dict[str, Any], shed: dict, max_actions: int = 4
) -> int:
    proceeds = 0
    keep_fert = _keep_fert(s)
    # Inventory floor: keep enough inventory to match the harvest model's
    # near-term target, scaled by liquidation capacity (`max_actions`).
    plan = crop_plan(s)
    sell_scale = max_actions / 3.0
    inv_keep: dict[str, int] = {}
    for c in CASH_CROPS:
        base = max(2, min(10, int(plan.get(c, 0)) // 3))
        keep = int(round(base * sell_scale))
        # Make the keep-floor adaptive, but only when `mean3` exists.
        # (If mean3 is missing we avoid guessing and keep the original floor.)
        price = float(px(s, c))
        mean3 = s.get("mean3") or {}
        hist = float(mean3.get(c, 0) or 0)
        if hist > 0:
            threshold = hist * float(PARAMS["sell_hold_price_factor"])
            ratio = (price / threshold) if threshold > 0 else 1.0
            sell_pressure = max(0.0, min(1.0, (ratio - 1.0) / 0.5))  # 1.0->0, 1.5+->1
        else:
            sell_pressure = 0.0
        ongoing_mult = 1.15 if c in ONGOING else 1.0
        keep = int(round(keep * ongoing_mult * (1.0 - 0.25 * sell_pressure)))
        inv_keep[c] = max(1, min(12, keep))
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
                # Stock-like tilt: if price is trending up, slightly
                # prioritize liquidation earlier. Bound adjustment to
                # prevent overreacting to noisy deltas.
                delta = (s.get("delta") or {}).get(item, 0)
                momentum = 1.0 + max(-0.2, min(0.2, float(delta) / 200.0))
                ranked.append((int(score * momentum), item, n))
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
    return s2


def _start_market(s: dict[str, Any], mode: str) -> tuple[list, int, dict[str, Any]]:
    s2 = _fork_signals(s)
    market: list = []
    shed = s2["shed"]
    if mode == "LIQUIDATE":
        sell_n = 8
    elif (berry_ok(s2) and berry_gap(s2) > 0) or need_land(s2):
        sell_n = 2
    else:
        sell_n = 3

    # Liquidity pressure: if we’re short on cash for the next planned
    # seed expansion, sell more aggressively (still filtered by
    # `_sell_score()` so we only liquidate when it’s economically sound).
    plan = crop_plan(s2)
    planned_seed_spend = 0
    for c in CASH_PLANT:
        target = plan.get(c, 0)
        have = s2["crops"].get(c, 0) + s2["seeds"].get(c, 0)
        need = max(0, target - have)
        planned_seed_spend += need * SEED_COST[c]
    cash_deficit = max(0, planned_seed_spend - float(s2.get("money", 0)))
    if mode != "LIQUIDATE" and cash_deficit >= 1200:
        sell_n = max(sell_n, 4)

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


def _hire_budget(s: dict[str, Any], market: list, *, reserve_land: bool) -> int:
    """Leave slots for land, berries, wheat seeds, and emergency feed."""
    reserved = 0
    if reserve_land:
        reserved += 1
    if berry_ok(s) and berry_gap(s) > 0:
        reserved += 1
    _, _, wheat_tiles = tile_budget(s)
    if s["crops"]["WHEAT"] + s["seeds"].get("WHEAT", 0) < wheat_tiles:
        reserved += 1
    if _feed_crisis(s):
        reserved += 1
    # When the board is still very sparse, spending the full 5 hire slots
    # often crowds out seed buys. Reserve one extra slot for planting.
    if s["empty"] >= 12 and s["day"] <= 18:
        reserved += 1
    left = max(0, MARKET_LIMIT - len(market) - reserved)
    return min(HIRES_PER_TURN, left)


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
        if op == "BUY_SEED" and act[1] in CASH_PLANT:
            return (3, 0)
        if op == "HIRE":
            return (4, 0)
        if op == "BUY_SEED" and act[1] == "WHEAT":
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
    return [act for i, act in enumerate(market) if i in keep]


def market_for(s: dict[str, Any], mode: str) -> list:
    day = s["day"]
    hour = s["hour"]

    if day == 0 and hour == 0:
        return [list(act) for act in OPENING_MARKET]

    if day == 0:
        return []

    market, afford, s2 = _start_market(s, mode)
    berry_gap_start = berry_gap(s)
    if mode == "LIQUIDATE":
        afford = _hire_up_to(market, afford, s2)
        return _pack_market(market)

    can_land = _will_buy_land(s2, afford)
    prep_land = can_land and cash_shop(s2)
    if prep_land:
        hire_n = _hire_budget(s2, market, reserve_land=True)
        afford = _hire_up_to(market, afford, s2, hire_n)
        afford = _buy_planned_seeds(market, afford, s2, s2["seeds"], berry_only=True)
        afford = _maybe_buy_land(market, afford, s2)
    else:
        afford = _maybe_buy_land(market, afford, s2)
        hire_n = _hire_budget(s2, market, reserve_land=False)
        afford = _hire_up_to(market, afford, s2, hire_n)
        if berry_ramp(s2):
            ramp_conservative = not seed_fill_push(s2)
            afford = _buy_planned_seeds(
                market, afford, s2, s2["seeds"], berry_only=ramp_conservative
            )
    afford = _buy_wheat_seeds(market, afford, s2, s2["seeds"])
    afford = _buy_planned_seeds(market, afford, s2, s2["seeds"])
    afford = _buy_feed_wheat(market, afford, s2)
    defer_animals = s2["empty"] >= 12 and 12 <= s2["day"] <= 18 and berry_gap_start > 0
    if afford >= 1200 and len(market) < MARKET_LIMIT and not defer_animals:
        _buy_animals(market, afford, s2)
    return _pack_market(market)


def agent(obs: dict[str, Any]) -> dict[str, Any]:
    s = read_signals(obs)
    update_price_book(s)
    mode = pick_mode(s)
    market = market_for(s, mode)
    seeds = dict(s["seeds"])
    claimed = set()
    n_feeders = min(s["workers"], s["hungry"]) if s["hungry"] else 0
    early_wheat = s["hungry"] > 0 and s["shed"].get("WHEAT", 0) == 0
    sprint = plant_sprint(s)
    ramp = berry_ramp(s)
    plan = crop_plan(s)
    # Sell-horizon aware inventory targets for harvest prioritization.
    # Approximate liquidation capacity with the same `sell_n` logic used in
    # `_start_market()`, including the liquidity bump.
    sell_n_est = (
        8
        if mode == "LIQUIDATE"
        else (2 if ((berry_ok(s) and berry_gap(s) > 0) or need_land(s)) else 3)
    )
    planned_seed_spend = 0
    for c in CASH_PLANT:
        target = plan.get(c, 0)
        have = s["crops"].get(c, 0) + s["seeds"].get(c, 0)
        need = max(0, target - have)
        planned_seed_spend += need * SEED_COST[c]
    cash_deficit = max(0, planned_seed_spend - float(s.get("money", 0)))
    if mode != "LIQUIDATE" and cash_deficit >= 1200:
        sell_n_est = max(sell_n_est, 4)

    inventory_target: dict[str, float] = {}
    inventory_stock: dict[str, float] = {}
    for c in CASH_CROPS:
        base = max(2.0, min(10.0, float(plan.get(c, 0)) / 3.0))
        scaled = base * (sell_n_est / 3.0)
        inv_target = max(1.0, min(12.0, scaled))
        inventory_target[c] = inv_target
        inventory_stock[c] = float(s["shed"].get(c, 0))
    ctx = {
        "feeder": [max(1, n_feeders)],
        "is_feeder": False,
        "at_risk": s["at_risk"],
        "hungry": s["hungry"],
        "fert_ready": s["fert_ready"],
        "unwatered": s["unwatered"],
        "carried": None,
        "has_wheat": False,
        "early_wheat": early_wheat,
        "plant_sprint": sprint,
        "berry_ramp": ramp,
        "berry_waiting": (
            seeds.get("STRAWBERRY", 0) > 0 and berry_ok(s) and berry_gap(s) > 0
        ),
        "cash_seeds": (
            seeds.get("STRAWBERRY", 0) > 0
            or seeds.get("CARROT", 0) > 0
            or seeds.get("MELON", 0) > 0
            or seeds.get("TOMATO", 0) > 0
        ),
        "cash_waiting": cash_waiting(s, seeds),
        "wheat_waiting": wheat_waiting(s, seeds),
        "use_fert": _keep_fert(s) > 0,
        "skip_care": milk_px(s) < 40,
        # Harvest priority signals (explicitly decoupled from sell-now rules).
        "crop_ev_score": {c: s["scores"].get(c, 0.0) for c in CASH_CROPS},
        "inventory_target": inventory_target,
        "inventory_stock": inventory_stock,
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
    return {"farmer": farmer, "hands": hands, "market": market}
