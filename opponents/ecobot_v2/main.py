"""EcoBot v2 — High-performance economics-driven Kaggriculture agent.

Key Strategy Pillars:
1. Day 0 All-In: 2 cows + 2 sheep + 11 melons + 6 wheat + 5 hires.
2. Compact central pasture cluster around shed at (4,4), (4,3), (3,4), (3,3), etc.
3. Daily animal cycle: FEED -> CARE -> COLLECT_FERTILIZER, selling fertilizer daily for cashflow.
4. Quadrant scaling: Day 5 unlock NE ($1k), Day 9 unlock SW ($2k). Never buy SE (75 tiles is optimal for 13 units).
5. 8-Phase Crop Lifecycle:
   - Days 0-4: 11 Melons + 6-10 Wheat + 4 Animals (NW)
   - Days 5-8: 11 Melons + 16-24 Strawberries + 14 Wheat + 7 Animals (NW+NE)
   - Day 9: Expansion to SW + 8 Animals (6 Cows + 2 Sheep)
   - Day 10: First Melon Harvest (66 units -> $16.5k+) -> scale to 12 hires daily
   - Days 11-20: 12 Melons (Wave 2) + 24 Strawberries + 28 Wheat + 8 Animals
   - Day 21: Second Melon Harvest (72 units)
   - Days 22-26: Dig expired strawberries -> plant 55-65 Wheat (100% field coverage)
   - Days 27-29: Massive Wheat Harvest & Liquidation (hundreds of wheat sold)
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

# ---------------------------------------------------------------------------
# Game Constants
# ---------------------------------------------------------------------------

TOTAL_DAYS: int = 30
TURNS_PER_DAY: int = 24
SHED_CAPACITY: int = 100
MAX_MARKET_ORDERS: int = 10
BOARD_SIZE: int = 10
I0: int = 10_000

# Central pasture cluster positions around the center shed tiles (4,4)..(5,5)
PASTURE_CLUSTER: list[tuple[int, int]] = [
    (4, 4), (4, 3), (3, 4), (3, 3),
    (5, 3), (6, 3), (5, 4), (6, 4),
]

SHED_TILES: list[tuple[int, int]] = [(4, 4), (5, 4), (4, 5), (5, 5)]

# Fixed animal-care crew size. The eco2 strategy targets a fixed 8-animal
# cluster, so a dynamic formula would be speculative (YAGNI) — 2 shepherds
# is what the swarm-diagnosis in the replay analysis converged on.
N_SHEPHERDS: int = 2

# Adaptive-market thresholds. Kept as a single price-floor + shed-pressure
# valve rather than a full demand model — bounded, explicit, easy to retune.
SELL_FLOOR_PCT: float = 0.30      # don't dump into a crashed price...
SHED_SELL_PRESSURE: int = 85      # ...unless the shed risks overflow discard
LIQUIDATION_DAY: int = 28         # ...or the season is ending (unsold = 0 anyway)
SEED_BUY_FLOOR_PCT: float = 0.50  # stop topping up a crop whose price already crashed
MAX_PASTURE_ANIMALS: int = 8

CROPS: dict[str, dict[str, Any]] = {
    "WHEAT": {
        "seed_cost": 10, "base_price": 25,
        "first_yield_day": 2, "max_yield_day": 4,
        "max_units_base": 4, "max_units_fert": 6,
        "bonus_start_day": 2, "is_ongoing": False,
    },
    "CARROT": {
        "seed_cost": 20, "base_price": 35,
        "first_yield_day": 2, "max_yield_day": 3,
        "max_units_base": 3, "max_units_fert": 4,
        "bonus_start_day": 2, "is_ongoing": False,
    },
    "TOMATO": {
        "seed_cost": 50, "base_price": 60,
        "first_yield_day": 8, "max_yield_day": 11,
        "is_ongoing": True,
        "bonus_start_day": 8, "yield_days": [8, 9, 10, 11],
    },
    "STRAWBERRY": {
        "seed_cost": 100, "base_price": 120,
        "first_yield_day": 10, "max_yield_day": 16,
        "is_ongoing": True,
        "bonus_start_day": 10, "yield_days": [10, 12, 14, 16],
    },
    "MELON": {
        "seed_cost": 80, "base_price": 250,
        "first_yield_day": 10, "max_yield_day": 10,
        "is_ongoing": False,
        "bonus_start_day": 6, "max_units_base": 6, "max_units_fert": 6,
    },
}

ANIMALS: dict[str, dict[str, Any]] = {
    "GOOSE": {"cost": 300, "base_price": 50, "structure": "COOP", "first_yield_day": 4, "interval": 1, "product": "EGG"},
    "COW":   {"cost": 400, "base_price": 160, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "product": "MILK"},
    "SHEEP": {"cost": 500, "base_price": 200, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "product": "WOOL"},
}

MARKET_PARAMS: dict[str, dict[str, Any]] = {
    "WHEAT":       {"base": 25,  "T": 400, "below_func": "sqrt",  "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":      {"base": 35,  "T": 450, "below_func": "hinge", "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":      {"base": 60,  "T": 200, "below_func": "hinge", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY":  {"base": 120, "T": 100, "below_func": "sqrt",  "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":       {"base": 250, "T": 300, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":         {"base": 50,  "T": 332, "below_func": "hinge", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":        {"base": 160, "T": 122, "below_func": "sqrt",  "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":        {"base": 200, "T": 105, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER":  {"base": 100, "T": 200, "below_func": "linear","below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

_FIB: list[int] = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]


def fib_cost(n: int) -> int:
    if n < len(_FIB):
        return _FIB[n]
    a, b = _FIB[-2], _FIB[-1]
    for _ in range(n - len(_FIB) + 1):
        a, b = b, a + b
    return b


def total_hire_cost(count: int, already_hired: int) -> int:
    return sum(fib_cost(already_hired + i) for i in range(count))


# ---------------------------------------------------------------------------
# Market Pricing
# ---------------------------------------------------------------------------


def _shape(func: str, x: float, t: float) -> float:
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(max(0.0, x))
    if func == "log":
        return math.log(1.0 + max(0.0, x))
    if func == "hinge":
        u = x / max(1.0, t)
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def market_price(item: str, inv: int) -> int:
    p = MARKET_PARAMS[item]
    base = float(p["base"])
    t = float(p["T"])
    if inv == I0:
        return int(round(base))
    if inv < I0:
        x = float(I0 - inv)
        denom = _shape(p["below_func"], t, t)
        amp = (p["below_target"] * base) / denom if denom > 0 else 0.0
        return max(1, int(round(base + amp * _shape(p["below_func"], x, t))))
    x = float(inv - I0)
    denom = _shape(p["above_func"], t, t)
    amp = (p["above_target"] * base) / denom if denom > 0 else 0.0
    return max(1, int(round(base - amp * _shape(p["above_func"], x, t))))


def _price_ratio(item: str, market_inv: dict[str, int]) -> float:
    return market_price(item, market_inv.get(item, I0)) / MARKET_PARAMS[item]["base"]


def _should_sell(item: str, market_inv: dict[str, int], shed_total: int, day: int) -> bool:
    """Avoid dumping stock into a crashed price; force-sell only when the
    season is ending or the shed risks overflow (discard beats a bad price)."""
    if day >= LIQUIDATION_DAY or shed_total >= SHED_SELL_PRESSURE:
        return True
    return _price_ratio(item, market_inv) >= SELL_FLOOR_PCT


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

_DIRS = ((0, -1, "NORTH"), (0, 1, "SOUTH"), (1, 0, "EAST"), (-1, 0, "WEST"))


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def is_shed_adj(pos: tuple[int, int]) -> bool:
    return pos in {(4, 4), (5, 4), (4, 5), (5, 5)}


def closest_shed_pos(pos: tuple[int, int]) -> tuple[int, int]:
    return min(SHED_TILES, key=lambda s: manhattan(pos, s))


def bfs_step(start: tuple[int, int], goal: tuple[int, int]) -> str | None:
    if start == goal:
        return None
    visited: set[tuple[int, int]] = {start}
    q: deque[tuple[tuple[int, int], str]] = deque()
    for dx, dy, move in _DIRS:
        nx, ny = start[0] + dx, start[1] + dy
        if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
            if (nx, ny) == goal:
                return move
            visited.add((nx, ny))
            q.append(((nx, ny), move))
    while q:
        (cx, cy), first = q.popleft()
        for dx, dy, _ in _DIRS:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE and (nx, ny) not in visited:
                if (nx, ny) == goal:
                    return first
                visited.add((nx, ny))
                q.append(((nx, ny), first))
    return None


# ---------------------------------------------------------------------------
# Farm State Analysis
# ---------------------------------------------------------------------------


def parse_farm_state(tiles: list[list[Any]], day: int) -> dict[str, Any]:
    state: dict[str, Any] = {
        "animals": [],          # list of dicts: {pos, animal, fed, cared, fert, yu}
        "empty_pastures": [],   # (x, y) empty pasture tiles
        "plants": [],           # list of dicts: {pos, crop, age, watered, yu, fert_due, is_expired}
        "weeds": [],            # (x, y) weed positions
        "empty_tiles": [],      # (x, y) empty unlocked tiles
        "unlocked_count": 0,
    }

    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            tile = tiles[y][x]
            pos = (x, y)

            if tile == "LOCKED":
                continue
            state["unlocked_count"] += 1

            if tile is None:
                state["empty_tiles"].append(pos)
                continue

            if not isinstance(tile, dict):
                continue

            kind = tile.get("kind")
            if kind == "WEED":
                state["weeds"].append(pos)
            elif kind == "PASTURE" or kind == "COOP":
                animal = tile.get("animal")
                if animal is None:
                    state["empty_pastures"].append(pos)
                else:
                    state["animals"].append({
                        "pos": pos,
                        "animal": animal,
                        "fed_today": tile.get("fed_today", False),
                        "cared_today": tile.get("cared_today", False),
                        "fertilizer_available": tile.get("fertilizer_available", False),
                        "yield_units": tile.get("yield_units", 0),
                    })
            elif kind == "PLANT":
                crop = tile.get("crop", "WHEAT")
                planted_day = tile.get("planted_day", day)
                age = day - planted_day
                spec = CROPS.get(crop, CROPS["WHEAT"])
                yu = tile.get("yield_units", 0)
                watered = tile.get("watered_today", False)
                fert_until = tile.get("fertilized_until_day", -1)

                # Decay starts one day after the plant's last productive day:
                # max_yield_day for one-time crops, the final scheduled
                # yield_days entry for ongoing crops. A flat cutoff (e.g. a
                # hardcoded age) is wrong for TOMATO (should decay at 12,
                # not 18) and STRAWBERRY (17, not 18), and leaving it
                # unchecked leaves the crew watering dead plants for days
                # with zero benefit instead of doing useful work elsewhere.
                is_expired = False
                if spec["is_ongoing"]:
                    last_yield_age = spec["yield_days"][-1]
                    if age >= last_yield_age + 1:
                        is_expired = True

                fert_due = (
                    not spec["is_ongoing"]
                    and spec["bonus_start_day"] <= age <= spec["max_yield_day"]
                    and fert_until < day
                )

                state["plants"].append({
                    "pos": pos,
                    "crop": crop,
                    "age": age,
                    "watered_today": watered,
                    "yield_units": yu,
                    "fertilize_due": fert_due,
                    "is_expired": is_expired,
                    "is_ongoing": spec["is_ongoing"],
                    "first_yield_day": spec["first_yield_day"],
                })

    return state


# ---------------------------------------------------------------------------
# Market Strategy
# ---------------------------------------------------------------------------


def get_desired_hires(day: int) -> int:
    if day == 0:
        return 5
    if day in (1, 2):
        return 2
    if day in (3, 4):
        return 4
    if day in (5, 6):
        return 7
    if day in (7, 8):
        return 9
    if day == 9:
        return 10
    if 10 <= day <= 27:
        return 12
    if day == 28:
        return 9
    return 8


def _plan_seed_topup(
    crop: str, empty_count: int, curr_seeds: int, budget: float
) -> tuple[list[Any] | None, float]:
    """Buy enough `crop` seed to cover every empty tile, budget permitting."""
    seed_cost = CROPS[crop]["seed_cost"]
    need = max(0, empty_count - curr_seeds)
    if need <= 0 or budget < need * seed_cost:
        return None, budget
    return ["BUY_SEED", crop, need], budget - need * seed_cost


def plan_market_orders(
    step: int,
    day: int,
    hour: int,
    money: float,
    shed: dict[str, int],
    seeds: dict[str, int],
    market_inv: dict[str, int],
    unlocked_quads: list[str],
    farm_state: dict[str, Any],
    hires_today: int,
) -> list[list[Any]]:
    orders: list[list[Any]] = []
    budget = money

    # === DAY 0 SPECIAL OPENING (Exact replica of winning game) ===
    if day == 0 and hour <= 1:
        if hires_today < 5:
            for _ in range(5 - hires_today):
                orders.append(["HIRE"])
        if shed.get("SHEEP", 0) == 0 and len(farm_state["animals"]) == 0:
            orders.append(["BUY_ANIMAL", "SHEEP", 2])
            orders.append(["BUY_ANIMAL", "COW", 2])
            orders.append(["BUY_SEED", "MELON", 11])
            orders.append(["BUY_SEED", "WHEAT", 6])
            orders.append(["BUY_PRODUCT", "WHEAT", 4])
        return orders[:MAX_MARKET_ORDERS]

    # === SELLS ===
    shed_total = sum(shed.values())

    # 1. Fertilizer: reserve exactly what today's melon fertilizing needs, sell the rest
    melon_fert_due = sum(
        1 for p in farm_state["plants"] if p["crop"] == "MELON" and p["fertilize_due"]
    )
    fert_in_shed = shed.get("FERTILIZER", 0)
    fert_to_sell = max(0, fert_in_shed - melon_fert_due)
    if fert_to_sell > 0 and _should_sell("FERTILIZER", market_inv, shed_total, day):
        orders.append(["SELL", "FERTILIZER", fert_to_sell])
        budget += fert_to_sell * market_price("FERTILIZER", market_inv.get("FERTILIZER", I0))

    # 2. Everything else: hold if price crashed, unless shed pressure or endgame forces it
    for item in ("MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "CARROT", "TOMATO"):
        qty = shed.get(item, 0)
        if qty > 0 and _should_sell(item, market_inv, shed_total, day):
            p = market_price(item, market_inv.get(item, I0))
            orders.append(["SELL", item, qty])
            budget += qty * p

    # 3. Wheat: keep enough for animal feed (at least 2 days reserve), sell excess.
    # The reserve applies for the whole season, including the days-27-29
    # liquidation push — zeroing it out there used to let the SELL order
    # drain the shed before shepherds could pick up feed, risking starving
    # (and losing) animals right before the season ends.
    wheat_in_shed = shed.get("WHEAT", 0)
    n_animals = len(farm_state["animals"]) + shed.get("COW", 0) + shed.get("SHEEP", 0)
    feed_buffer = max(4, n_animals * 2)
    if wheat_in_shed > feed_buffer and day > 0:
        excess_wheat = wheat_in_shed - feed_buffer
        if _should_sell("WHEAT", market_inv, shed_total, day):
            orders.append(["SELL", "WHEAT", excess_wheat])
            budget += excess_wheat * market_price("WHEAT", market_inv.get("WHEAT", I0))

    # === HIRES ===
    desired_hires = get_desired_hires(day)
    new_hires = max(0, desired_hires - hires_today)
    if new_hires > 0:
        cost = total_hire_cost(new_hires, hires_today)
        if budget >= cost + 50 or day <= 10:
            for _ in range(new_hires):
                orders.append(["HIRE"])
            budget -= cost

    # === LAND EXPANSION ===
    # Day 5: Buy NE ($1000)
    if "NE" not in unlocked_quads and day >= 5 and budget >= 1000 + 100:
        orders.append(["BUY_LAND"])
        budget -= 1000

    # Day 9: Buy SW ($2000)
    if "SW" not in unlocked_quads and "NE" in unlocked_quads and day >= 9 and budget >= 2000 + 200:
        orders.append(["BUY_LAND"])
        budget -= 2000

    # === ANIMAL EXPANSION ===
    # Days 7-12: fill remaining pasture slots (cap MAX_PASTURE_ANIMALS) with
    # whichever of COW/SHEEP currently prices better relative to its own
    # base — reacts to shop-driven spikes (e.g. Yarn Store pushing wool up).
    total_animals = (
        sum(1 for a in farm_state["animals"] if a["animal"] in ("COW", "SHEEP"))
        + shed.get("COW", 0) + shed.get("SHEEP", 0)
    )
    if 7 <= day <= 12 and total_animals < MAX_PASTURE_ANIMALS:
        preferred = "SHEEP" if _price_ratio("WOOL", market_inv) > _price_ratio("MILK", market_inv) else "COW"
        cost = ANIMALS[preferred]["cost"]
        want = min(2, MAX_PASTURE_ANIMALS - total_animals)
        if want > 0 and budget >= want * cost + 100:
            orders.append(["BUY_ANIMAL", preferred, want])
            budget -= want * cost

    # === FEED (WHEAT PRODUCT) ===
    if wheat_in_shed < n_animals * 2:
        wp = market_price("WHEAT", market_inv.get("WHEAT", I0))
        buy_wheat_n = min(15, max(4, n_animals * 2 - wheat_in_shed))
        cost_wheat = wp * buy_wheat_n
        if budget >= cost_wheat + 50:
            orders.append(["BUY_PRODUCT", "WHEAT", buy_wheat_n])
            budget -= cost_wheat

    # === SEED PURCHASES BY PHASE ===
    empty_count = len(farm_state["empty_tiles"])

    # Phase 7 & 8: Days 22-26 -> Massive WHEAT planting to cover the whole farm
    if 22 <= day <= 26:
        curr_wheat_seeds = seeds.get("WHEAT", 0)
        need_seeds = max(0, empty_count + 20 - curr_wheat_seeds)
        if need_seeds > 0 and budget >= need_seeds * 10:
            orders.append(["BUY_SEED", "WHEAT", need_seeds])
            budget -= need_seeds * 10

    # Phase 5: Day 11 -> Buy Wave 2 Melons (12)
    elif day == 11 and seeds.get("MELON", 0) < 12 and budget >= 12 * 80:
        buy_m = 12 - seeds.get("MELON", 0)
        orders.append(["BUY_SEED", "MELON", buy_m])
        budget -= buy_m * 80

    # Phase 2 & 3: Days 5-10 -> Strawberries for NE/SW expansion, gated by
    # price so we stop buying into an already-crashed strawberry market
    elif 5 <= day <= 10:
        curr_straw = seeds.get("STRAWBERRY", 0)
        total_straw = sum(1 for p in farm_state["plants"] if p["crop"] == "STRAWBERRY") + curr_straw
        if total_straw < empty_count and _price_ratio("STRAWBERRY", market_inv) >= SEED_BUY_FLOOR_PCT:
            buy_s = min(empty_count - total_straw, int(budget // 100))
            if buy_s > 0:
                orders.append(["BUY_SEED", "STRAWBERRY", buy_s])
                budget -= buy_s * 100

        order, budget = _plan_seed_topup("WHEAT", empty_count, seeds.get("WHEAT", 0), budget)
        if order:
            orders.append(order)

    # Phase 5 & 6: Days 12-21 -> Full scale wheat production
    elif 12 <= day <= 21:
        order, budget = _plan_seed_topup("WHEAT", empty_count, seeds.get("WHEAT", 0), budget)
        if order:
            orders.append(order)

    # Phase 1: Days 1-4 -> Buy Wheat seeds to cycle through
    elif 1 <= day <= 4:
        order, budget = _plan_seed_topup("WHEAT", empty_count, seeds.get("WHEAT", 0), budget)
        if order:
            orders.append(order)

    return orders[:MAX_MARKET_ORDERS]


# ---------------------------------------------------------------------------
# Unit Dispatcher
# ---------------------------------------------------------------------------


def dispatch_units(
    all_units: list[tuple[tuple[int, int], dict[str, int]]],
    farm_state: dict[str, Any],
    shed: dict[str, int],
    seeds: dict[str, int],
    day: int,
    hour: int,
) -> list[list[Any]]:
    actions: list[list[Any]] = []
    claimed_targets: set[tuple[int, int]] = set()
    fert_pickup_claimed = False  # cap fertilizer fetch-trips to one dispatch per turn

    seeds_stock = dict(seeds)

    if 22 <= day <= 26:
        target_crop = "WHEAT"
    elif seeds_stock.get("MELON", 0) > 0:
        target_crop = "MELON"
    elif seeds_stock.get("STRAWBERRY", 0) > 0:
        target_crop = "STRAWBERRY"
    else:
        target_crop = "WHEAT"

    needed_pastures: list[tuple[int, int]] = []
    n_animals_total = len(farm_state["animals"]) + shed.get("COW", 0) + shed.get("SHEEP", 0)
    for p_pos in PASTURE_CLUSTER:
        current_pastures_count = len(needed_pastures) + len(farm_state["animals"]) + len(farm_state["empty_pastures"])
        if current_pastures_count < n_animals_total:
            if p_pos in farm_state["empty_tiles"]:
                needed_pastures.append(p_pos)

    melon_fert_due: list[tuple[int, int]] = [
        p["pos"] for p in farm_state["plants"] if p["crop"] == "MELON" and p["fertilize_due"]
    ]

    for unit_idx, (pos, inv) in enumerate(all_units):
        is_shepherd = unit_idx < N_SHEPHERDS
        inv_total = sum(inv.values())
        has_wheat = inv.get("WHEAT", 0) > 0
        has_fert = inv.get("FERTILIZER", 0) > 0
        has_cow = inv.get("COW", 0) > 0
        has_sheep = inv.get("SHEEP", 0) > 0
        sp = closest_shed_pos(pos)

        def _step_to(target: tuple[int, int]) -> list[Any]:
            st = bfs_step(pos, target)
            return [st or "PASS"]

        act: list[Any] | None = None

        # ---------------------------------------------------------------
        # 1-3. ANIMAL CARE / CONSTRUCTION / FEEDING — shepherds only.
        # Previously every unit checked the animal queues each morning,
        # so the whole crew marched to the pasture cluster instead of
        # planting/watering (see replay diagnosis: swarm effect).
        # ---------------------------------------------------------------
        if is_shepherd:
            standing_animal = next((a for a in farm_state["animals"] if a["pos"] == pos), None)
            if standing_animal is not None:
                if not standing_animal["fed_today"] and has_wheat:
                    act = ["FEED"]
                elif not standing_animal["cared_today"]:
                    act = ["CARE"]
                elif standing_animal["fertilizer_available"]:
                    act = ["COLLECT_FERTILIZER"]
                elif standing_animal["yield_units"] > 0:
                    act = ["HARVEST"]

            if act is None:
                if (has_cow or has_sheep) and farm_state["empty_pastures"]:
                    avail_pastures = [p for p in farm_state["empty_pastures"] if p not in claimed_targets]
                    if avail_pastures:
                        target = min(avail_pastures, key=lambda p: manhattan(pos, p))
                        claimed_targets.add(target)
                        if pos == target:
                            animal_to_place = "COW" if has_cow else "SHEEP"
                            act = ["PLACE", animal_to_place]
                        else:
                            act = _step_to(target)

                elif (shed.get("COW", 0) > 0 or shed.get("SHEEP", 0) > 0) and farm_state["empty_pastures"] and not (has_cow or has_sheep):
                    aname = "COW" if shed.get("COW", 0) > 0 else "SHEEP"
                    if is_shed_adj(pos):
                        act = ["PICKUP", aname, 1]
                    else:
                        act = _step_to(sp)

                elif needed_pastures:
                    avail_builds = [p for p in needed_pastures if p not in claimed_targets]
                    if avail_builds:
                        target = min(avail_builds, key=lambda p: manhattan(pos, p))
                        claimed_targets.add(target)
                        if pos == target:
                            act = ["BUILD_PASTURE"]
                        else:
                            act = _step_to(target)

            if act is None:
                unfed_animals = [
                    a["pos"] for a in farm_state["animals"]
                    if not a["fed_today"] and a["pos"] not in claimed_targets
                ]
                if unfed_animals:
                    if has_wheat:
                        target = min(unfed_animals, key=lambda p: manhattan(pos, p))
                        claimed_targets.add(target)
                        if pos == target:
                            act = ["FEED"]
                        else:
                            act = _step_to(target)
                    elif shed.get("WHEAT", 0) > 0:
                        if is_shed_adj(pos):
                            act = ["PICKUP", "WHEAT", min(4, shed.get("WHEAT", 0))]
                        else:
                            act = _step_to(sp)

        # ---------------------------------------------------------------
        # 4. FIELD OPERATIONS: WATER > HARVEST > FERTILIZE(melon) > DIG > PLANT
        # Open to every unit, including shepherds once chores are clear.
        # ---------------------------------------------------------------
        if act is None:
            unwatered = [
                p["pos"] for p in farm_state["plants"]
                if not p["watered_today"] and not p["is_expired"] and p["pos"] not in claimed_targets
            ]
            if unwatered:
                target = min(unwatered, key=lambda p: manhattan(pos, p))
                claimed_targets.add(target)
                act = ["WATER"] if pos == target else _step_to(target)

        if act is None:
            harvestable = [
                p["pos"] for p in farm_state["plants"]
                if p["yield_units"] > 0 and (p["is_ongoing"] or p["age"] >= p["first_yield_day"]) and p["pos"] not in claimed_targets
            ]
            if harvestable:
                target = min(harvestable, key=lambda p: manhattan(pos, p))
                claimed_targets.add(target)
                act = ["HARVEST"] if pos == target else _step_to(target)

        if act is None:
            due = [p for p in melon_fert_due if p not in claimed_targets]
            if due:
                if has_fert:
                    target = min(due, key=lambda p: manhattan(pos, p))
                    claimed_targets.add(target)
                    act = ["FERTILIZE"] if pos == target else _step_to(target)
                elif not fert_pickup_claimed and shed.get("FERTILIZER", 0) > 0:
                    fert_pickup_claimed = True
                    if is_shed_adj(pos):
                        act = ["PICKUP", "FERTILIZER", min(4, shed.get("FERTILIZER", 0))]
                    else:
                        act = _step_to(sp)

        if act is None:
            dig_targets: list[tuple[int, int]] = [w for w in farm_state["weeds"] if w not in claimed_targets]
            if day >= 22:
                for p in farm_state["plants"]:
                    if p["crop"] == "STRAWBERRY" and p["pos"] not in claimed_targets:
                        dig_targets.append(p["pos"])
            if dig_targets:
                target = min(dig_targets, key=lambda p: manhattan(pos, p))
                claimed_targets.add(target)
                act = ["DIG"] if pos == target else _step_to(target)

        if act is None:
            active_seed = target_crop if seeds_stock.get(target_crop, 0) > 0 else "WHEAT"
            if seeds_stock.get(active_seed, 0) > 0 and farm_state["empty_tiles"]:
                avail_empty = [
                    p for p in farm_state["empty_tiles"]
                    if p not in claimed_targets and p not in PASTURE_CLUSTER[:n_animals_total]
                ]
                if avail_empty:
                    target = min(avail_empty, key=lambda p: manhattan(pos, p))
                    claimed_targets.add(target)
                    if pos == target:
                        act = ["PLANT", active_seed]
                        seeds_stock[active_seed] -= 1
                    else:
                        act = _step_to(target)

        # ---------------------------------------------------------------
        # 5. LOGISTICS & DROP
        # ---------------------------------------------------------------
        if act is None:
            if inv_total > 0:
                carrying_feed_only = has_wheat and inv_total == inv.get("WHEAT", 0)
                if not (carrying_feed_only and any(not a["fed_today"] for a in farm_state["animals"])):
                    act = ["DROP"] if is_shed_adj(pos) else _step_to(sp)

        if act is None:
            act = ["PASS"]

        actions.append(act)

    return actions


# ---------------------------------------------------------------------------
# Main Agent Entry Point
# ---------------------------------------------------------------------------


def agent(obs: dict[str, Any]) -> dict[str, Any]:
    player = obs["player"]
    step = obs.get("step", 0)
    day = obs["day"]
    hour = obs["hour"]

    me = obs["farms"][player]
    private = obs["private"]
    mkt = obs["market"]

    money = float(me["money"])
    tiles = me["tiles"]
    unlocked_quads = me.get("unlocked_quadrants", ["NW"])
    shed = private.get("shed", {})
    seeds = private.get("seeds", {})
    market_inv = mkt.get("inventory", {})
    inventories = private.get("inventories", [{}])
    hires_today = me.get("hires_today", 0)

    # 1. Parse current farm grid
    farm_state = parse_farm_state(tiles, day)

    # 2. Plan Market Orders
    market_orders = plan_market_orders(
        step, day, hour, money, shed, seeds, market_inv,
        unlocked_quads, farm_state, hires_today,
    )

    # 3. Assemble all units (Farmer + Hired Hands)
    farmer_pos = (me["farmer"][0], me["farmer"][1])
    hands_pos = [(h[0], h[1]) for h in me.get("hands", [])]

    all_units: list[tuple[tuple[int, int], dict[str, int]]] = []
    all_units.append((farmer_pos, inventories[0] if inventories else {}))
    for idx, hp in enumerate(hands_pos):
        h_inv = inventories[idx + 1] if idx + 1 < len(inventories) else {}
        all_units.append((hp, h_inv))

    # 4. Dispatch unit actions
    unit_actions = dispatch_units(all_units, farm_state, shed, seeds, day, hour)

    farmer_act = unit_actions[0] if unit_actions else ["PASS"]
    hands_acts = unit_actions[1:] if len(unit_actions) > 1 else []

    return {
        "farmer": farmer_act,
        "hands": hands_acts,
        "market": market_orders,
    }