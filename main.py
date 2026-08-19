"""Kaggriculture agent — manure core + gated shop spends.

Kaggle calls the last function. obs.day is 0-indexed (0–29).
Opening is hour 0: 5 hires, 2 cows, 2 sheep, wheat. No land, no melons.
PriceBook and shop demand gate land, berries, and herd — they do not
outrank feed, hires, or leftover operating cash.
"""

from __future__ import annotations

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
        item: (sum(series[-72:]) / len(series[-72:])) if series else float(prices.get(item, 0))
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


def crop_score(crop: str, price: int, day: int, demand: dict[str, int] | None = None) -> float:
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
    wheat_tiles = max(6, mouths) if mouths else 4
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
    """How many tiles of each crop to hold. Shops first, leftover melons only."""
    _, room, wheat_tiles = tile_budget(s)
    plan = {c: 0 for c in SEED_COST}
    plan["WHEAT"] = wheat_tiles
    leftover = room
    demand = s.get("demand") or {}

    def take(crop: str, cap: int) -> None:
        nonlocal leftover
        if leftover <= 0 or cap <= 0:
            return
        n = min(leftover, cap)
        plan[crop] = n
        leftover -= n

    if demand.get("STRAWBERRY", 0) >= 1 and s["day"] <= 26:
        take("STRAWBERRY", berry_tile_cap(s))
    if demand.get("CARROT", 0) >= 1 and s["day"] <= 26:
        carrot_cap = 2 if berry_sink(s) else 8
        take("CARROT", carrot_cap)
    if demand.get("TOMATO", 0) >= 1 and s["day"] <= 24 and berry_sink(s) == 0:
        tomato_cap = 4 if s["n_quads"] == 1 else 8
        take("TOMATO", tomato_cap)
    if leftover >= 8 and s["n_quads"] >= 3 and s["day"] <= 16 and live_ev(s, "MELON") > live_ev(s, "WHEAT"):
        take("MELON", min(8, leftover))
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
    if s["day"] > 22 or milk_px(s) < 60:
        return s["cows"]
    floor = 2 if s["day"] <= 20 else 0
    if s["cows"] < floor:
        return floor
    if milk_sink(s) == 0:
        return s["cows"]
    if s["n_quads"] == 1:
        return s["cows"]
    if s["crops"].get("WHEAT", 0) < mouths_of(s) + 1:
        return s["cows"]
    cap = 6 if s["n_quads"] == 2 else 8
    return min(s["cows"] + 1, cap)


def want_sheep(s: dict[str, Any]) -> int:
    if s["day"] > 22 or wool_px(s) < 80:
        return s["sheep"]
    floor = 2 if s["day"] <= 20 else 0
    if s["sheep"] < floor:
        return floor
    if s["demand"].get("WOOL", 0) <= 0:
        return s["sheep"]
    if s["n_quads"] == 1:
        return s["sheep"]
    if s["crops"].get("WHEAT", 0) < mouths_of(s) + 1:
        return s["sheep"]
    cap = 4 if s["n_quads"] == 2 else 6
    return min(s["sheep"] + 1, cap)


def need_land(s: dict[str, Any]) -> bool:
    if s["day"] < 4 or s["day"] >= 24 or s["n_quads"] >= 4:
        return False
    if s["n_quads"] == 1 and s["empty"] > 10:
        return False
    _, cash_room, _ = tile_budget(s)
    if s["n_quads"] == 1:
        if s["empty"] > 10:
            return False
        if s["empty"] <= 8:
            return True
        if cash_room <= 4 and cash_shop(s):
            return True
        if s["seeds"].get("STRAWBERRY", 0) >= 4 and s["empty"] <= 10:
            return True
        return False
    if s["n_quads"] == 2:
        if int(s["money"]) < 3000:
            return False
        if s["empty"] <= 8:
            return True
        if berry_ok(s) and s["crops"]["STRAWBERRY"] >= 12 and s["empty"] <= 14:
            return True
        return False
    if s["n_quads"] >= 3:
        return s["empty"] <= 4 and s["day"] <= 18 and int(s["money"]) >= 5000
    if s["empty"] <= 6:
        return True
    bcap, ccap = cash_caps(s)
    have = s["crops"]["STRAWBERRY"] + s["crops"]["CARROT"]
    return (berry_ok(s) or carrot_ok(s)) and have >= max(4, bcap + ccap) and s["empty"] <= 10


def want_hands(s: dict[str, Any]) -> int:
    """Leaders rehire a full crew every morning. Day 0 stays the 5-hire opening."""
    if s["day"] == 0:
        return 5
    if s["n_quads"] >= 2 or s["unwatered"] >= 8:
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
        c: crop_score(c, int(prices.get(c, BASE_PRICE[c])), day, demand) for c in SEED_COST
    }
    a_scores = {
        a: animal_score(a, int(prices.get(ANIMAL_PRODUCT[a], BASE_PRICE[ANIMAL_PRODUCT[a]])), day)
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
    if s["day"] >= 27:
        return "LIQUIDATE"
    return "ENGINE"


def cash_waiting(s: dict[str, Any], seeds: dict[str, int] | None = None) -> bool:
    seeds = seeds if seeds is not None else s["seeds"]
    plan = crop_plan(s)
    return any(
        seeds.get(crop, 0) > 0 and s["crops"][crop] < plan.get(crop, 0) for crop in CASH_PLANT
    )


def wheat_waiting(s: dict[str, Any], seeds: dict[str, int] | None = None) -> bool:
    seeds = seeds if seeds is not None else s["seeds"]
    mouths = mouths_of(s)
    floor = max(4, crop_plan(s)["WHEAT"]) if mouths > 0 else 0
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
        if "STRAWBERRY" in cash:
            return "STRAWBERRY"
        return max(cash, key=lambda c: s["scores"].get(c, 0.0))
    if (
        berry_ok(s)
        and s["day"] <= 26
        and seeds.get("STRAWBERRY", 0) > 0
        and berry_gap(s) > 0
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
                    priority = 0
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
                elif ctx["carried"] and ANIMAL_STRUCT.get(ctx["carried"]) == t.get("kind"):
                    priority = 2
            elif isinstance(t, dict) and t.get("kind") == "WEED":
                if ctx.get("plant_sprint") and hungry == 0:
                    priority = 0
                    urgency = 8
            elif t is None:
                waiting_plant = ctx.get("cash_waiting") or ctx.get("wheat_waiting")
                if ctx.get("plant_sprint") and hungry == 0 and has_seeds and waiting_plant:
                    priority = 0
                    urgency = 10
                elif (ctx.get("need_pasture") or ctx.get("need_coop")) and not waiting_plant:
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
        if tile is None and ANIMAL_STRUCT[carried] == "PASTURE" and s["empty_struct"]["PASTURE"] <= 0:
            s["empty_struct"]["PASTURE"] += 1
            claimed.add((x, y))
            return ["BUILD_PASTURE"], seeds
        if tile is None and ANIMAL_STRUCT[carried] == "COOP" and s["empty_struct"]["COOP"] <= 0:
            s["empty_struct"]["COOP"] += 1
            claimed.add((x, y))
            return ["BUILD_COOP"], seeds

    if isinstance(tile, dict) and tile.get("kind") == "WEED":
        claimed.add((x, y))
        return ["DIG"], seeds

    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        if crop_ready(tile, day, ctx.get("early_wheat", False)):
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
    if (
        ctx.get("use_fert")
        and inv.get("FERTILIZER", 0) > 0
        and s.get("hour", 0) < 22
    ):
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
        reserve = waiting_past + waiting_coop - s["empty_struct"]["PASTURE"] - s["empty_struct"]["COOP"]
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

    if s["hungry"] and not has_wheat and shed.get("WHEAT", 0) > 0 and (x, y) not in SHED_TILES:
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


def _buy_wheat_seeds(market: list, afford: int, s: dict[str, Any], seeds: dict[str, int]) -> int:
    _, _, wheat_tiles = tile_budget(s)
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


def _hire_up_to(market: list, afford: int, s: dict[str, Any]) -> int:
    want = want_hands(s)
    n_hire = min(HIRES_PER_TURN, max(0, want - s["hires_today"]))
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
    cap_n = 8 if berry_sink(s) else 4
    if s["n_quads"] >= 2 and afford >= 1600:
        cap_n = 12
    if s["n_quads"] >= 3 and afford >= 2000:
        cap_n = 16
    if berry_replant_push(s):
        cap_n = max(cap_n, 16)
    order = [c for c in ("STRAWBERRY", "CARROT", "TOMATO", "MELON") if plan.get(c, 0) > 0]
    if berry_only:
        order = [c for c in order if c == "STRAWBERRY"]
    for crop in order:
        have = s["crops"][crop] + seeds.get(crop, 0)
        need = plan[crop] - have
        if crop == "STRAWBERRY":
            if berry_replant_push(s) or s["day"] >= 20:
                keep = 80
            else:
                keep = 400 if s["n_quads"] >= 2 else 800
            if berry_only:
                need = max(need, min(12, max(6, berry_gap(s) + 4)))
        else:
            keep = 800
        if need > 0:
            n_before = len(market)
            afford = _append_seed(market, afford, crop, min(need, cap_n), keep=keep)
            if len(market) > n_before:
                seeds[crop] = seeds.get(crop, 0) + int(market[-1][2])
    return afford


def _buy_animals(market: list, afford: int, s: dict[str, Any]) -> int:
    below_floor = s["cows"] < 2 or s["sheep"] < 2
    if s["day"] < 3 and not below_floor:
        return afford
    if s["shed"].get("COW", 0) or s["shed"].get("SHEEP", 0) or s["shed"].get("GOOSE", 0):
        return afford
    if s["crops"]["WHEAT"] < 4:
        return afford
    if not below_floor and mouths_of(s) >= s["crops"]["WHEAT"]:
        return afford
    _, cash_room, _ = tile_budget(s)
    mouth_cap = 6 if s["n_quads"] == 1 else (10 if s["n_quads"] == 2 else 12)
    if mouths_of(s) >= mouth_cap:
        return afford
    if s["n_quads"] == 1 and cash_shop(s) and cash_room < 6 and not below_floor:
        return afford
    plan = crop_plan(s)
    berry_gap = max(
        0, plan.get("STRAWBERRY", 0) - s["crops"]["STRAWBERRY"] - s["seeds"].get("STRAWBERRY", 0)
    )
    reserve = min(900, berry_gap * SEED_COST["STRAWBERRY"])
    if below_floor:
        reserve = min(reserve, 200)
    if afford - ANIMAL_COST["COW"] < max(reserve, 1200) and not below_floor:
        return afford
    for kind, want, have in (
        ("COW", want_cows(s), s["cows"]),
        ("SHEEP", want_sheep(s), s["sheep"]),
    ):
        need = want - have
        unit = ANIMAL_COST[kind]
        if need <= 0 or afford < unit or s["empty"] < 2:
            continue
        if mouths_of(s) + 1 > mouth_cap:
            continue
        n = min(need, 1, afford // unit)
        if n <= 0:
            continue
        market.append(["BUY_ANIMAL", kind, n])
        afford -= n * unit
        if kind == "COW":
            s["cows"] += n
        else:
            s["sheep"] += n
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


def _sell_goods(market: list, s: dict[str, Any], shed: dict, max_actions: int = 4) -> int:
    proceeds = 0
    keep_fert = _keep_fert(s)
    ranked: list[tuple[int, str, int]] = []
    for item in ("FERTILIZER", "MELON", "MILK", "WOOL", "STRAWBERRY", "CARROT", "EGG", "TOMATO"):
        keep = keep_fert if item == "FERTILIZER" else 0
        n = sell_qty(shed.get(item, 0), keep)
        if n > 0:
            ranked.append((n * px(s, item), item, n))
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
    s2["seeds"] = dict(s["seeds"])
    s2["shed"] = dict(s["shed"])
    s2["crops"] = dict(s["crops"])
    return s2


def _start_market(s: dict[str, Any], mode: str) -> tuple[list, int, dict[str, Any]]:
    s2 = _fork_signals(s)
    market: list = []
    shed = s2["shed"]
    sell_n = 8 if mode == "LIQUIDATE" else 3
    proceeds = _sell_goods(market, s2, shed, max_actions=sell_n)
    wheat = shed.get("WHEAT", 0)
    if (mode == "LIQUIDATE" or s2["day"] >= 27) and wheat > 0:
        market.append(["SELL", "WHEAT", wheat])
        proceeds += wheat * px(s2, "WHEAT")
        shed["WHEAT"] = 0
    afford = int(s["money"]) + proceeds
    return market, afford, s2


def _pack_market(market: list, limit: int = 10) -> list:
    """Keep feed, land, hires, then wheat seeds if we overflow the 10-action cap."""

    def rank(act: list) -> tuple[int, int]:
        if not act:
            return (9, 0)
        op = act[0]
        if op == "SELL":
            return (0, 0)
        if op == "BUY_LAND":
            return (1, 0)
        if op == "HIRE":
            return (2, 0)
        if op == "BUY_SEED" and act[1] == "WHEAT":
            return (3, 0)
        if op == "BUY_SEED":
            return (4, 0)
        if op == "BUY_PRODUCT":
            return (5, 0)
        if op == "BUY_ANIMAL":
            return (6, 0)
        return (9, 0)

    if len(market) <= limit:
        return market
    ordered = sorted(enumerate(market), key=lambda iv: (rank(iv[1]), iv[0]))
    keep = {i for i, _ in ordered[:limit]}
    return [act for i, act in enumerate(market) if i in keep]


def market_for(s: dict[str, Any], mode: str) -> list:
    day = s["day"]
    hour = s["hour"]

    if day == 0 and hour == 0:
        return [list(act) for act in OPENING_MARKET]

    if day == 0:
        return []

    market, afford, s2 = _start_market(s, mode)
    if mode == "LIQUIDATE":
        afford = _hire_up_to(market, afford, s2)
        return _pack_market(market)

    prep_land = _will_buy_land(s2, afford) and berry_ok(s2)
    if prep_land:
        afford = _hire_up_to(market, afford, s2)
        afford = _buy_planned_seeds(market, afford, s2, s2["seeds"], berry_only=True)
        afford = _maybe_buy_land(market, afford, s2)
    else:
        afford = _maybe_buy_land(market, afford, s2)
        afford = _hire_up_to(market, afford, s2)
    afford = _buy_wheat_seeds(market, afford, s2, s2["seeds"])
    afford = _buy_planned_seeds(market, afford, s2, s2["seeds"])
    if afford >= 1200:
        _buy_animals(market, afford, s2)
    _buy_feed_wheat(market, afford, s2)
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
    }
    me = obs["farms"][obs["player"]]
    private = obs["private"]
    fx, fy = me["farmer"]
    farmer, seeds = action_for(
        me["tiles"], fx, fy, s["day"], seeds, claimed, s,
        private["inventories"][0], ctx,
    )
    hands = []
    for i, (hx, hy) in enumerate(me["hands"]):
        action, seeds = action_for(
            me["tiles"], hx, hy, s["day"], seeds, claimed, s,
            private["inventories"][i + 1], ctx,
        )
        hands.append(action)
    return {"farmer": farmer, "hands": hands, "market": market}
