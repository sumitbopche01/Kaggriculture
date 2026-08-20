"""Deterministic scenario-aware economic policy for Kaggriculture."""

from collections import deque
import math


# Domain constants

CROPS = {
    "WHEAT": {
        "seed": 10,
        "first": 2,
        "max_day": 4,
        "max_yield": 6,
        "ongoing": False,
        "ripe": 4,
        "last_plant": 24,
    },
    "CARROT": {
        "seed": 20,
        "first": 2,
        "max_day": 3,
        "max_yield": 4,
        "ongoing": False,
        "ripe": 3,
        "last_plant": 25,
    },
    "TOMATO": {
        "seed": 50,
        "first": 8,
        "max_day": 8,
        "max_yield": 4,
        "ongoing": True,
        "interval": 1,
        "ripe": 8,
        "last_plant": 19,
    },
    "STRAWBERRY": {
        "seed": 100,
        "first": 10,
        "max_day": 10,
        "max_yield": 4,
        "ongoing": True,
        "interval": 2,
        "ripe": 10,
        "last_plant": 18,
    },
    "MELON": {
        "seed": 80,
        "first": 10,
        "max_day": 12,
        "max_yield": 6,
        "ongoing": False,
        "ripe": 10,
        "last_plant": 18,
    },
}

ANIMALS = {
    "GOOSE": {
        "cost": 300,
        "structure": "COOP",
        "product": "EGG",
        "first": 4,
        "interval": 1,
        "max_held": 4,
    },
    "COW": {
        "cost": 400,
        "structure": "PASTURE",
        "product": "MILK",
        "first": 8,
        "interval": 2,
        "max_held": 6,
    },
    "SHEEP": {
        "cost": 500,
        "structure": "PASTURE",
        "product": "WOOL",
        "first": 6,
        "interval": 3,
        "max_held": 6,
    },
}

PRODUCTS = (
    "WHEAT",
    "CARROT",
    "TOMATO",
    "STRAWBERRY",
    "MELON",
    "EGG",
    "MILK",
    "WOOL",
    "FERTILIZER",
)

MARKET = {
    "WHEAT": (25, 400, "sqrt", 0.80, "log", 0.20),
    "CARROT": (35, 450, "hinge", 1.00, "sqrt", 0.70),
    "TOMATO": (60, 200, "hinge", 0.40, "sqrt", 0.60),
    "STRAWBERRY": (120, 100, "sqrt", 0.70, "linear", 1.60),
    "MELON": (250, 300, "log", 0.20, "sq", 3.60),
    "EGG": (50, 332, "hinge", 0.40, "log", 0.20),
    "MILK": (160, 122, "sqrt", 0.60, "linear", 1.60),
    "WOOL": (200, 105, "log", 0.20, "sq", 3.20),
    "FERTILIZER": (100, 200, "linear", 0.40, "linear", 0.40),
}

SHOPS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}

RESERVE_FRACTION = {
    "WHEAT": 0.68,
    "CARROT": 0.55,
    "TOMATO": 0.50,
    "STRAWBERRY": 0.48,
    "MELON": 0.58,
    "EGG": 0.65,
    "MILK": 0.42,
    "WOOL": 0.40,
    "FERTILIZER": 0.18,
}

MOVES = (
    ("NORTH", 0, -1),
    ("WEST", -1, 0),
    ("SOUTH", 0, 1),
    ("EAST", 1, 0),
)

LAND_PRICES = (1000, 2000, 4000)
MARKET_I0 = 10000
TOTAL_DAYS = 30
MAX_MARKET_ORDERS = 10
MAX_HANDS = 12
CORE_HERD_SEQUENCE = ("COW", "COW", "COW", "SHEEP")
CORE_HERD = len(CORE_HERD_SEQUENCE)
MID_HERD = 11
TARGET_HERD = 15
HERD_EXPANSION_DAY = 7
HERD_FINAL_DAY = 11
ANIMAL_PURCHASE_LAST_DAY = 18
ANIMAL_SLOTS = {"NW": 4, "NE": 7, "SW": 4, "SE": 0}
CROP_MIX = {
    "NW": {"MELON": 10, "WHEAT": 4, "CARROT": 2},
    "NE": {"WHEAT": 4, "CARROT": 1},
    "SW": {"WHEAT": 4, "CARROT": 1},
    "SE": {"WHEAT": 5, "CARROT": 2},
}
MELON_TILES_MIN = 8
MELON_TILES_BASE = 10
MELON_TILES_MAX = 12
MAX_EXTRA_LAND = 2
CASH_RESERVE = 250
LIQUIDATION_TURNS = 22
SHED_CAPACITY = 100
TRAVEL_COST = 8.0
FEED_STOCK_DAYS = 3
SCHEDULE_WHEAT_CAP = 100
LAND_OPEN_DAYS = (5, 9)
PRIORITY_BONUS = {
    -1: 120_000.0,
    0: 100_000.0,
    1: 1_500.0,
    2: 750.0,
    3: 250.0,
    4: 0.0,
    5: -100.0,
}

_SIGNATURE_LAST_STEP = -1
_SIGNATURE_ACTIVE = False
_SCHEDULE_WHEAT_REQUESTED = 0


# Configuration, pricing, and routing helpers

def _cfg(config, key, default):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


# "hinge" is flat-linear in x/T up to the knee at x == T and then a quadratic
# term takes over, so the price is calm until the resource is genuinely scarce
# and afterwards runs away. f(T) == 1 by construction, which keeps `target`
# meaning the same fraction of base it means for every other shape. Unlike the
# other shapes it is not scale-free, so it needs the throughput.
HINGE_GAIN = 8.0


def _shape(name, value, throughput=None):
    value = max(0.0, float(value))
    if name == "linear":
        return value
    if name == "sq":
        return value * value
    if name == "sqrt":
        return math.sqrt(value)
    if name == "log":
        return math.log1p(value)
    if name == "log10":
        return math.log10(1.0 + value)
    if name == "hinge":
        # Degenerates to linear when the throughput is missing or non-positive.
        if not throughput or throughput <= 0:
            return value
        unit = value / float(throughput)
        return unit + HINGE_GAIN * max(0.0, unit - 1.0) ** 2
    return value


def _market_parameters(obs, item):
    base, throughput, below_fn, below_move, above_fn, above_move = MARKET[item]
    custom = (((obs or {}).get("market", {}) or {}).get("params", {}) or {}).get(
        item, {}
    )
    return (
        float(custom.get("base", base)),
        float(custom.get("T", throughput)),
        str(custom.get("below_func", below_fn)),
        float(custom.get("below_target", below_move)),
        str(custom.get("above_func", above_fn)),
        float(custom.get("above_target", above_move)),
        float(custom.get("I0", MARKET_I0)),
    )


def _price_at(item, inventory, obs=None):
    (
        base,
        throughput,
        below_fn,
        below_move,
        above_fn,
        above_move,
        equilibrium,
    ) = _market_parameters(obs, item)
    if inventory < equilibrium:
        amplitude = below_move * base / max(
            1e-9, _shape(below_fn, throughput, throughput)
        )
        value = base + amplitude * _shape(
            below_fn, equilibrium - inventory, throughput
        )
    else:
        amplitude = above_move * base / max(
            1e-9, _shape(above_fn, throughput, throughput)
        )
        value = base - amplitude * _shape(
            above_fn, inventory - equilibrium, throughput
        )
    return max(1, int(round(value)))


def _town_demand_per_day(obs, item):
    # The town centre buys one of each product once per day and does not scale
    # with the calendar; shop instances are drawn with replacement, so the same
    # shop can appear several times and each copy consumes independently.
    center = 0 if item == "FERTILIZER" else 1
    shop = 0
    for name in (((obs or {}).get("town", {}) or {}).get(
        "unlocked_shops", []
    ) or []):
        products = SHOPS.get(name, ())
        if item in products:
            shop += 12 if len(products) == 1 else 6
    return center + shop


def _opponent_visible_supply(obs, item, horizon=1):
    player = int((obs or {}).get("player", 0) or 0)
    day = int((obs or {}).get("day", 0) or 0)
    animal_for = {"EGG": "GOOSE", "MILK": "COW", "WOOL": "SHEEP"}
    total = 0
    for index, farm in enumerate((obs or {}).get("farms", []) or []):
        if index == player:
            continue
        for row in farm.get("tiles", []) or []:
            for tile in row:
                if not isinstance(tile, dict):
                    continue
                if (
                    item in CROPS
                    and tile.get("kind") == "PLANT"
                    and tile.get("crop") == item
                ):
                    rule = CROPS[item]
                    planted = tile.get("planted_day")
                    planted_day = day if planted is None else int(planted)
                    age = day - planted_day
                    held = int(tile.get("yield_units", 0) or 0)
                    if held > 0 and age >= rule["first"]:
                        total += held
                    elif age + horizon >= rule["ripe"]:
                        total += max(1, min(rule["max_yield"], held + horizon))
                elif item in animal_for and tile.get("animal") == animal_for[item]:
                    total += int(tile.get("yield_units", 0) or 0)
                    if horizon > 0:
                        total += min(2 * horizon, ANIMALS.get(
                            tile.get("animal"), {"max_held": 4}
                        )["max_held"])
    return total


def _distance(a, b):
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _shed_tiles(board_size, tiles=None):
    half = board_size // 2
    candidates = (
        (half - 1, half - 1),
        (half, half - 1),
        (half - 1, half),
        (half, half),
    )
    if tiles is None:
        return candidates
    accessible = tuple(
        position
        for position in candidates
        if tiles[position[1]][position[0]] != "LOCKED"
    )
    return accessible or candidates[:1]


def _nearest_shed(position, board_size, tiles=None):
    return min(
        _shed_tiles(board_size, tiles),
        key=lambda target: (_distance(position, target), target[1], target[0]),
    )


def _bfs_first_step(tiles, source, target):
    source = (int(source[0]), int(source[1]))
    target = (int(target[0]), int(target[1]))
    if source == target:
        return ["PASS"]
    board_size = len(tiles)
    queue = deque([source])
    parent = {source: None}
    parent_move = {}
    while queue:
        current = queue.popleft()
        if current == target:
            break
        for name, dx, dy in MOVES:
            nxt = (current[0] + dx, current[1] + dy)
            if not (0 <= nxt[0] < board_size and 0 <= nxt[1] < board_size):
                continue
            if nxt in parent or tiles[nxt[1]][nxt[0]] == "LOCKED":
                continue
            parent[nxt] = current
            parent_move[nxt] = name
            queue.append(nxt)
    if target not in parent:
        return ["PASS"]
    current = target
    while parent[current] != source:
        current = parent[current]
        if current is None:
            return ["PASS"]
    return [parent_move[current]]


def _melon_target(obs):
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    price = int(prices.get("MELON", MARKET["MELON"][0]) or MARKET["MELON"][0])
    opponent_tiles = 0
    player = int(obs.get("player", 0) or 0)
    for index, other in enumerate(obs.get("farms", []) or []):
        if index == player:
            continue
        for row in other.get("tiles", []) or []:
            opponent_tiles += sum(
                isinstance(tile, dict)
                and tile.get("kind") == "PLANT"
                and tile.get("crop") == "MELON"
                for tile in row
            )
    if price >= 300 and opponent_tiles <= 5:
        return MELON_TILES_MAX
    if price <= 170 or opponent_tiles >= 12:
        return MELON_TILES_MIN
    if opponent_tiles >= 9:
        return MELON_TILES_BASE - 1
    return MELON_TILES_BASE


def _private_item_total(private, item):
    total = int((private.get("shed", {}) or {}).get(item, 0) or 0)
    for inventory in private.get("inventories", []) or []:
        total += int((inventory or {}).get(item, 0) or 0)
    return total


def _farm_animal_counts(farm):
    counts = {animal: 0 for animal in ANIMALS}
    for row in farm.get("tiles", []) or []:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal") in counts:
                counts[tile["animal"]] += 1
    return counts


def _opponent_animal_counts(obs):
    player = int(obs.get("player", 0) or 0)
    counts = {animal: 0 for animal in ANIMALS}
    for index, farm in enumerate(obs.get("farms", []) or []):
        if index == player:
            continue
        visible = _farm_animal_counts(farm)
        for animal, count in visible.items():
            counts[animal] += count
    return counts


def _public_type_counts(farm):
    counts = {}
    for row in farm.get("tiles", []) or []:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "PLANT":
                name = str(tile.get("crop", "UNKNOWN"))
            elif tile.get("animal"):
                name = str(tile["animal"])
            else:
                name = str(tile.get("kind", "STRUCTURE"))
            counts[name] = counts.get(name, 0) + 1
    return counts


def _schedule_signature(obs):
    global _SIGNATURE_ACTIVE, _SIGNATURE_LAST_STEP
    raw_step = obs.get("step")
    step = int(
        raw_step
        if raw_step is not None
        else 24 * int(obs.get("day", 0) or 0) + int(obs.get("hour", 0) or 0)
    )
    if step == 0 or step <= _SIGNATURE_LAST_STEP:
        _SIGNATURE_ACTIVE = False
    _SIGNATURE_LAST_STEP = step

    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0) or 0)
    if len(farms) != 2 or not (0 <= player < 2):
        return False
    opponent = farms[1 - player]
    counts = _public_type_counts(opponent)

    if step == 24:
        hard_negative = any(
            counts.get(item, 0) for item in ("GOOSE", "CARROT", "TOMATO")
        )
        _SIGNATURE_ACTIVE = (
            not hard_negative
            and len(opponent.get("unlocked_quadrants", []) or []) == 1
            and counts.get("COW", 0) == 3
            and counts.get("SHEEP", 0) == 1
            and counts.get("MELON", 0) == 6
            and counts.get("STRAWBERRY", 0) == 0
        )
    if step == 192 and _SIGNATURE_ACTIVE:
        _SIGNATURE_ACTIVE = (
            len(opponent.get("unlocked_quadrants", []) or []) == 1
            and 3 <= counts.get("COW", 0) <= 5
            and counts.get("SHEEP", 0) == 1
            and 9 <= counts.get("MELON", 0) <= 10
            and 6 <= counts.get("STRAWBERRY", 0) <= 7
        )
    if step == 264 and _SIGNATURE_ACTIVE:
        hard_negative = any(
            counts.get(item, 0) for item in ("GOOSE", "CARROT", "TOMATO")
        )
        _SIGNATURE_ACTIVE = (
            not hard_negative
            and len(opponent.get("unlocked_quadrants", []) or []) == 2
            and 3 <= counts.get("COW", 0) <= 5
            and counts.get("SHEEP", 0) == 5
            and counts.get("MELON", 0) == 6
            and 15 <= counts.get("STRAWBERRY", 0) <= 16
            and 4 <= counts.get("PASTURE", 0) <= 5
        )
    return _SIGNATURE_ACTIVE


def _livestock_score(obs, animal, own_count, opponent_count):
    rule = ANIMALS[animal]
    product = rule["product"]
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    price = float(prices.get(product, MARKET[product][0]) or MARKET[product][0])
    normalized_price = price / float(MARKET[product][0])
    demand_support = 1.0 + 0.012 * _town_demand_per_day(obs, product)
    crowding = 1.0 + 0.18 * opponent_count + 0.08 * own_count
    return normalized_price * demand_support / crowding


def _quadrant_of(position, board_size):
    x, y = position
    half = board_size // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def _reserved_animal_slots(farm):
    tiles = farm.get("tiles", []) or []
    board_size = len(tiles)
    unlocked = set(farm.get("unlocked_quadrants", []) or ["NW"])
    sheds = _shed_tiles(board_size, tiles)
    slots = []
    by_quadrant = {}
    for quadrant in ("NW", "NE", "SW", "SE"):
        if quadrant not in unlocked:
            continue
        cells = []
        for y, row in enumerate(tiles):
            for x, tile in enumerate(row):
                if tile == "LOCKED" or _quadrant_of((x, y), board_size) != quadrant:
                    continue
                distance = min(_distance((x, y), shed) for shed in sheds)
                cells.append((distance, y, x))
        cells.sort()
        count = min(ANIMAL_SLOTS[quadrant], len(cells))
        selected = [(x, y) for _, y, x in cells[:count]]
        by_quadrant[quadrant] = {
            "reserved": selected,
            "crops": [(x, y) for _, y, x in cells[count:]],
        }
        slots.extend(selected)
    return slots, by_quadrant


def _herd_targets(obs, farm, private, capacity):
    day = int(obs.get("day", 0) or 0)
    left = TOTAL_DAYS - day
    placed = _farm_animal_counts(farm)
    owned = {
        animal: placed[animal] + _private_item_total(private, animal)
        for animal in ("COW", "SHEEP")
    }
    if day < HERD_EXPANSION_DAY:
        stage_target = CORE_HERD
    elif day < HERD_FINAL_DAY:
        stage_target = MID_HERD
    else:
        stage_target = TARGET_HERD
    if day > ANIMAL_PURCHASE_LAST_DAY or left < 8:
        stage_target = sum(owned.values())
    target_total = min(capacity, max(sum(owned.values()), stage_target))

    targets = {
        animal: max(
            CORE_HERD_SEQUENCE.count(animal)
            if target_total >= CORE_HERD
            else 0,
            owned[animal],
        )
        for animal in ("COW", "SHEEP")
    }
    opponents = _opponent_animal_counts(obs)
    while sum(targets.values()) < target_total:
        animal = max(
            ("COW", "SHEEP"),
            key=lambda name: (
                _livestock_score(
                    obs,
                    name,
                    targets[name],
                    opponents[name],
                ),
                -targets[name],
                name == "COW",
            ),
        )
        targets[animal] += 1
    return targets


def _role_plan(obs, farm):
    private = obs.get("private", {}) or {}
    tiles = farm.get("tiles", []) or []
    animal_slots, zones = _reserved_animal_slots(farm)
    targets = _herd_targets(obs, farm, private, len(animal_slots))
    desired_animals = min(len(animal_slots), sum(targets.values()))
    active_slots = list(animal_slots[:desired_animals])
    for position in animal_slots:
        x, y = position
        tile = tiles[y][x]
        if isinstance(tile, dict) and "animal" in tile and position not in active_slots:
            active_slots.append(position)

    assigned = {"COW": 0, "SHEEP": 0}
    roles = {}
    core_sequence = CORE_HERD_SEQUENCE
    for index, position in enumerate(active_slots):
        x, y = position
        tile = tiles[y][x]
        actual = tile.get("animal") if isinstance(tile, dict) else None
        if actual in assigned:
            animal = actual
        elif index < len(core_sequence) and assigned[core_sequence[index]] < targets[
            core_sequence[index]
        ]:
            animal = core_sequence[index]
        else:
            animal = max(
                ("COW", "SHEEP"),
                key=lambda name: (
                    targets[name] - assigned[name],
                    _private_item_total(private, name),
                    name == "COW",
                ),
            )
        roles[position] = ("ANIMAL", animal)
        assigned[animal] += 1

    melon_target = _melon_target(obs)
    for quadrant in ("NW", "NE", "SW", "SE"):
        zone = zones.get(quadrant)
        if not zone:
            continue
        cells = zone["crops"]
        fixed = dict(CROP_MIX[quadrant])
        if quadrant == "NW":
            fixed["MELON"] = min(melon_target, len(cells))
        strawberry_count = max(0, len(cells) - sum(fixed.values()))
        sequence = []
        if quadrant == "NW":
            sequence.extend(["MELON"] * fixed.get("MELON", 0))
        sequence.extend(["STRAWBERRY"] * strawberry_count)
        sequence.extend(["WHEAT"] * fixed.get("WHEAT", 0))
        sequence.extend(["CARROT"] * fixed.get("CARROT", 0))
        if quadrant != "NW":
            sequence.extend(["MELON"] * fixed.get("MELON", 0))
        for position, crop in zip(cells, sequence):
            roles[position] = ("CROP", crop)
    return roles


# Observation summaries and job generation

def _inventory_total(inventory, excluded=()):
    return sum(
        int(value)
        for item, value in (inventory or {}).items()
        if item not in excluded and isinstance(value, (int, float)) and value > 0
    )


def _survey(farm, private, roles=None, day=0):
    summary = {
        "animals": 0,
        "unfed": 0,
        "at_risk_animals": 0,
        "at_risk_crops": 0,
        "open_structures": 0,
        "structures_todo": 0,
        "plants": 0,
        "plantable": 0,
        "weeds": 0,
    }
    for row in farm.get("tiles", []) or []:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if "animal" in tile:
                summary["animals"] += 1
                if not tile.get("fed_today", False):
                    summary["unfed"] += 1
                if int(tile.get("consecutive_unfed", 0) or 0) >= 1:
                    summary["at_risk_animals"] += 1
            elif tile.get("kind") in {"COOP", "PASTURE"}:
                summary["open_structures"] += 1
            elif tile.get("kind") == "PLANT":
                summary["plants"] += 1
                if int(tile.get("consecutive_unwatered", 0) or 0) >= 1:
                    summary["at_risk_crops"] += 1
            elif tile.get("kind") == "WEED":
                summary["weeds"] += 1

    if roles:
        for (x, y), (kind, item) in roles.items():
            tile = farm["tiles"][y][x]
            if kind == "ANIMAL" and tile is None:
                summary["structures_todo"] += 1
            elif (
                kind == "CROP"
                and tile is None
                and day <= CROPS[item]["last_plant"]
            ):
                summary["plantable"] += 1

    summary["wheat_stock"] = int((private.get("shed", {}) or {}).get("WHEAT", 0))
    summary["animal_stock"] = {
        animal: int((private.get("shed", {}) or {}).get(animal, 0) or 0)
        for animal in ANIMALS
    }
    summary["shed_load"] = sum(
        max(0, int(value or 0))
        for value in (private.get("shed", {}) or {}).values()
    )
    summary["carried_load"] = 0
    for inventory in private.get("inventories", []) or []:
        summary["wheat_stock"] += int((inventory or {}).get("WHEAT", 0))
        for animal in ANIMALS:
            summary["animal_stock"][animal] += int(
                (inventory or {}).get(animal, 0) or 0
            )
        summary["carried_load"] += _inventory_total(inventory)
    return summary


def _policy_phase(obs, farm, private, summary):
    day = int(obs.get("day", 0) or 0)
    step = int(obs.get("step", day * 24 + int(obs.get("hour", 0) or 0)) or 0)
    actions_left = max(0, 719 - step)
    if actions_left <= LIQUIDATION_TURNS:
        return "LIQUIDATE"
    workers = 1 + len(farm.get("hands", []) or [])
    if (
        summary["at_risk_animals"] + summary["at_risk_crops"] > workers
        or summary["shed_load"] + summary["carried_load"] >= 95
    ):
        return "CRISIS"
    if day <= 4:
        return "BOOTSTRAP"
    if day <= 21:
        return "COMPOUND"
    return "REALIZE"


def _add_job(
    jobs,
    priority,
    value,
    target,
    action,
    need=None,
    reason="",
    latest_hour=23,
):
    jobs.append(
        {
            "priority": int(priority),
            "value": float(value),
            "target": tuple(target),
            "action": list(action),
            "need": need,
            "reason": str(reason),
            "latest_hour": int(latest_hour),
        }
    )


def _animal_produces_tonight(tile, rule, day):
    next_day = int(day) + 1
    placed_day = int(tile.get("placed_day", day) or 0)
    days_since_first = next_day - placed_day - int(rule["first"])
    return (
        days_since_first >= 0
        and days_since_first % int(rule["interval"]) == 0
    )


def _crop_jobs(obs, jobs, tile, target, day, liquidation):
    crop = tile.get("crop")
    rule = CROPS.get(crop)
    if rule is None:
        return
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    price = float(prices.get(crop, MARKET[crop][0]) or MARKET[crop][0])
    age = day - int(tile.get("planted_day", day))
    amount = int(tile.get("yield_units", 0) or 0)
    watered = bool(tile.get("watered_today", False))
    drought = int(tile.get("consecutive_unwatered", 0) or 0)
    critical = drought >= 1

    if liquidation:
        if amount > 0 and age >= rule["first"]:
            _add_job(
                jobs,
                0,
                amount * price,
                target,
                ("HARVEST",),
                reason="terminal_harvest",
            )
        return

    if critical and not watered:
        protected = max(amount, rule["max_yield"] * 0.7) * price
        _add_job(
            jobs,
            0,
            protected,
            target,
            ("WATER",),
            reason="critical_water",
        )
        return

    if rule["ongoing"]:
        next_day = day + 1
        interval = max(1, int(rule.get("interval", 1)))
        days_since_first = (
            next_day - int(tile.get("planted_day", day)) - rule["first"]
        )
        production_index = (
            days_since_first // interval + 1 if days_since_first >= 0 else 0
        )
        produces_tonight = (
            days_since_first >= 0
            and days_since_first % interval == 0
            and production_index <= rule["max_yield"]
        )
        fertilized_until = tile.get("fertilized_until_day", -1)
        fertilized_until = (
            -1 if fertilized_until is None else int(fertilized_until)
        )
        if (
            crop == "STRAWBERRY"
            and produces_tonight
            and fertilized_until < day
        ):
            _add_job(
                jobs,
                2,
                max(100.0, price),
                target,
                ("FERTILIZE",),
                need="FERTILIZER",
                reason="strawberry_production_fertilizer",
            )
        if amount >= rule["max_yield"] - 1 or (amount > 0 and day >= 27):
            _add_job(
                jobs,
                2,
                amount * price,
                target,
                ("HARVEST",),
                reason="ongoing_harvest",
            )
        elif not watered and age >= rule["first"] - 1:
            _add_job(
                jobs,
                3,
                price,
                target,
                ("WATER",),
                reason="ongoing_water",
            )
        return

    ripe = age >= rule["ripe"] and amount > 0
    in_growth_window = (rule["max_day"] + 1) // 2 <= age <= rule["max_day"]
    if ripe:
        if in_growth_window and not watered and amount < rule["max_yield"]:
            _add_job(
                jobs,
                1,
                price,
                target,
                ("WATER",),
                reason="final_growth_water",
            )
        else:
            _add_job(
                jobs,
                2,
                amount * price,
                target,
                ("HARVEST",),
                reason="ripe_harvest",
            )
    elif in_growth_window and not watered:
        _add_job(
            jobs,
            3,
            price,
            target,
            ("WATER",),
            reason="yield_water",
        )


def _field_jobs(obs, farm, private, roles, liquidation):
    day = int(obs.get("day", 0) or 0)
    hour = int(obs.get("hour", 0) or 0)
    left = TOTAL_DAYS - day
    tiles = farm["tiles"]
    seeds = dict(private.get("seeds", {}) or {})
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    jobs = []
    planned_roles = dict(roles)
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict) or (x, y) in planned_roles:
                continue
            if tile.get("kind") == "PLANT" and tile.get("crop") in CROPS:
                planned_roles[(x, y)] = ("CROP", tile["crop"])
            elif tile.get("animal") in ANIMALS:
                planned_roles[(x, y)] = ("ANIMAL", tile["animal"])

    for target, role in planned_roles.items():
        x, y = target
        tile = tiles[y][x]
        role_kind, role_item = role

        if tile is None:
            if liquidation:
                continue
            if role_kind == "ANIMAL":
                animal_rule = ANIMALS[role_item]
                if left >= animal_rule["first"] + 2:
                    _add_job(
                        jobs,
                        3,
                        420,
                        target,
                        ("BUILD_" + animal_rule["structure"],),
                        reason="build_" + animal_rule["structure"].lower(),
                        latest_hour=22,
                    )
            elif (
                hour <= 22
                and day <= CROPS[role_item]["last_plant"]
                and seeds.get(role_item, 0) > 0
            ):
                rule = CROPS[role_item]
                expected = 4 if role_item == "WHEAT" else rule["max_yield"]
                price = float(
                    prices.get(role_item, MARKET[role_item][0])
                    or MARKET[role_item][0]
                )
                value = max(40, 0.65 * expected * price - rule["seed"])
                _add_job(
                    jobs,
                    4,
                    value,
                    target,
                    ("PLANT", role_item),
                    reason="plant_" + role_item,
                    latest_hour=22,
                )
            continue

        if not isinstance(tile, dict):
            continue
        kind = tile.get("kind")
        if role_kind == "ANIMAL" and kind in {"WEED", "PLANT"}:
            if not liquidation:
                _add_job(
                    jobs,
                    2,
                    500,
                    target,
                    ("DIG",),
                    reason="clear_animal_slot",
                    latest_hour=22,
                )
            continue
        if kind == "WEED":
            if not liquidation:
                _add_job(
                    jobs,
                    4,
                    120 if left > 5 else 10,
                    target,
                    ("DIG",),
                    reason="dig_weed",
                    latest_hour=22,
                )
            continue
        if kind == "PLANT":
            _crop_jobs(obs, jobs, tile, target, day, liquidation)
            continue
        if (
            role_kind == "ANIMAL"
            and kind == ANIMALS[role_item]["structure"]
            and "animal" not in tile
        ):
            if not liquidation:
                _add_job(
                    jobs,
                    1,
                    900,
                    target,
                    ("PLACE", role_item),
                    need=role_item,
                    reason="place_" + role_item.lower(),
                )
            continue
        if (
            role_kind == "ANIMAL"
            and kind in {"COOP", "PASTURE"}
            and kind != ANIMALS[role_item]["structure"]
            and "animal" not in tile
        ):
            if not liquidation:
                _add_job(
                    jobs,
                    3,
                    250,
                    target,
                    ("DIG",),
                    reason="replace_incompatible_structure",
                )
            continue
        if "animal" not in tile:
            continue
        if liquidation:
            if int(tile.get("yield_units", 0) or 0) > 0:
                product = ANIMALS.get(
                    tile.get("animal"), ANIMALS["GOOSE"]
                )["product"]
                value = int(tile.get("yield_units", 0) or 0) * float(
                    prices.get(product, MARKET[product][0])
                    or MARKET[product][0]
                )
                _add_job(
                    jobs,
                    0,
                    value,
                    target,
                    ("HARVEST",),
                    reason="terminal_animal",
                )
            if tile.get("fertilizer_available", False):
                _add_job(
                    jobs,
                    0,
                    float(
                        prices.get("FERTILIZER", MARKET["FERTILIZER"][0])
                        or MARKET["FERTILIZER"][0]
                    ),
                    target,
                    ("COLLECT_FERTILIZER",),
                    reason="terminal_fertilizer",
                )
            continue
        if not tile.get("fed_today", False):
            risk = int(tile.get("consecutive_unfed", 0) or 0) >= 1
            _add_job(
                jobs,
                0 if risk else 1,
                900 if risk else 260,
                target,
                ("FEED",),
                need="WHEAT",
                reason="critical_feed" if risk else "feed",
            )
        held = int(tile.get("yield_units", 0) or 0)
        animal_rule = ANIMALS.get(tile.get("animal"), ANIMALS["GOOSE"])
        product = animal_rule["product"]
        pending_care = int(tile.get("pending_care_bonus", 0) or 0)
        produces_tonight = _animal_produces_tonight(
            tile, animal_rule, day
        )
        production_gain = 1 + pending_care if produces_tonight else 0
        if held > 0 and (
            held >= 3
            or held + production_gain >= animal_rule["max_held"]
            or day >= 27
        ):
            _add_job(
                jobs,
                2,
                held
                * float(
                    prices.get(product, MARKET[product][0])
                    or MARKET[product][0]
                ),
                target,
                ("HARVEST",),
                reason="animal_harvest",
            )
        if tile.get("fertilizer_available", False):
            _add_job(
                jobs,
                2,
                float(
                    prices.get("FERTILIZER", MARKET["FERTILIZER"][0])
                    or MARKET["FERTILIZER"][0]
                ),
                target,
                ("COLLECT_FERTILIZER",),
                reason="fertilizer",
            )
        if (
            not tile.get("cared_today", False)
            and day <= 27
            and held
            + (0 if produces_tonight else pending_care)
            + 1
            < animal_rule["max_held"]
            and float(
                prices.get(product, MARKET[product][0])
                or MARKET[product][0]
            ) >= 20
        ):
            _add_job(
                jobs,
                3,
                float(
                    prices.get(product, MARKET[product][0])
                    or MARKET[product][0]
                ),
                target,
                ("CARE",),
                reason="care",
            )
    return jobs


def _terminal_feasible(position, target, tiles, actions_left):
    board_size = len(tiles)
    return (
        _distance(position, target)
        + 1
        + min(
            _distance(target, shed)
            for shed in _shed_tiles(board_size, tiles)
        )
        + 1
        <= actions_left
    )


# Duplicate-target-aware field assignment

def _unit_actions(obs, config, farm, private, roles):
    tiles = farm["tiles"]
    board_size = len(tiles)
    day = int(obs.get("day", 0) or 0)
    hour = int(obs.get("hour", 0) or 0)
    step = int(obs.get("step", day * 24 + hour) or 0)
    final_step = int(_cfg(config, "episodeSteps", 720)) - 2
    actions_left = max(0, final_step - step + 1)
    liquidation = actions_left <= LIQUIDATION_TURNS

    positions = [farm["farmer"], *(farm.get("hands", []) or [])]
    inventories = [dict(inv or {}) for inv in private.get("inventories", []) or []]
    while len(inventories) < len(positions):
        inventories.append({})

    summary = _survey(farm, private, roles, day)
    jobs = _field_jobs(obs, farm, private, roles, liquidation)
    seed_budget = dict(private.get("seeds", {}) or {})
    actions = [["PASS"] for _ in positions]

    feed_jobs = [job for job in jobs if job["need"] == "WHEAT"]
    shed_wheat = int((private.get("shed", {}) or {}).get("WHEAT", 0) or 0)
    carried_wheat = sum(int(inv.get("WHEAT", 0) or 0) for inv in inventories)

    missions = []
    for job in jobs:
        mission = dict(job)
        mission.update({"kind": "FIELD"})
        missions.append(mission)

    wheat_missing = max(0, len(feed_jobs) - carried_wheat)
    wheat_pickups = min(
        len(positions),
        int(math.ceil(min(wheat_missing, shed_wheat) / 6.0)),
    )
    wheat_remaining = min(wheat_missing, shed_wheat)
    critical_feed = any(job["priority"] == 0 for job in feed_jobs)
    for _ in range(wheat_pickups):
        amount = min(6, wheat_remaining)
        wheat_remaining -= amount
        missions.append(
            {
                "kind": "PICKUP",
                "item": "WHEAT",
                "amount": amount,
                "priority": 0 if critical_feed else 1,
                "value": 900 if critical_feed else 500,
                "target": None,
            }
        )

    fertilizer_jobs = [
        job for job in jobs if job.get("need") == "FERTILIZER"
    ]
    shed_fertilizer = int(
        (private.get("shed", {}) or {}).get("FERTILIZER", 0) or 0
    )
    carried_fertilizer = sum(
        int(inventory.get("FERTILIZER", 0) or 0)
        for inventory in inventories
    )
    fertilizer_missing = max(
        0, len(fertilizer_jobs) - carried_fertilizer
    )
    fertilizer_remaining = min(fertilizer_missing, shed_fertilizer)
    fertilizer_pickups = min(
        len(positions),
        int(math.ceil(fertilizer_remaining / 4.0)),
    )
    for _ in range(fertilizer_pickups):
        amount = min(4, fertilizer_remaining)
        fertilizer_remaining -= amount
        missions.append(
            {
                "kind": "PICKUP",
                "item": "FERTILIZER",
                "amount": amount,
                "priority": 1,
                "value": 700,
                "target": None,
            }
        )

    for animal in ANIMALS:
        place_jobs = [job for job in jobs if job["need"] == animal]
        shed_animals = int(
            (private.get("shed", {}) or {}).get(animal, 0) or 0
        )
        carried_animals = sum(
            int(inv.get(animal, 0) or 0) for inv in inventories
        )
        pickup_count = min(
            max(0, len(place_jobs) - carried_animals),
            shed_animals,
            2,
            len(positions),
        )
        for _ in range(pickup_count):
            missions.append(
                {
                    "kind": "PICKUP",
                    "item": animal,
                    "amount": 1,
                    "priority": 1,
                    "value": 900,
                    "target": None,
                }
            )

    market_prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    pressure = summary["shed_load"] + summary["carried_load"]
    cash_needed = (
        day < 22
        and float(farm.get("money", 0) or 0) < 500
    )
    for index, inventory in enumerate(inventories):
        cash_units = sum(
            max(0, int(inventory.get(item, 0) or 0)) for item in PRODUCTS
        )
        if cash_units <= 0:
            continue
        cash_value = sum(
            max(0, int(inventory.get(item, 0) or 0))
            * float(market_prices.get(item, MARKET[item][0]) or MARKET[item][0])
            for item in PRODUCTS
        )
        has_feed_mission = (
            int(inventory.get("WHEAT", 0) or 0) > 0 and bool(feed_jobs)
        )
        should_drop = (
            liquidation
            or pressure >= 80
            or cash_units >= 20
            or cash_value >= 2500
            or (cash_needed and cash_value >= 400)
            or (
                tuple(positions[index]) in _shed_tiles(board_size, tiles)
                and not has_feed_mission
                and cash_needed
            )
        )
        if should_drop:
            missions.append(
                {
                    "kind": "DROP",
                    "eligible": index,
                    "priority": -1 if liquidation else 2,
                    "value": max(120.0, 0.22 * cash_value),
                    "target": None,
                }
            )

    pairs = []
    for worker_index, raw_position in enumerate(positions):
        position = (int(raw_position[0]), int(raw_position[1]))
        inventory = inventories[worker_index]
        for mission_index, mission in enumerate(missions):
            kind = mission["kind"]
            if kind == "DROP" and mission["eligible"] != worker_index:
                continue
            if kind == "FIELD":
                need = mission.get("need")
                if need is not None and int(inventory.get(need, 0) or 0) <= 0:
                    continue
                target = mission["target"]
                distance = _distance(position, target)
                if hour + distance > mission.get("latest_hour", 23):
                    continue
                if liquidation and not _terminal_feasible(
                    position, target, tiles, actions_left
                ):
                    continue
            else:
                target = _nearest_shed(position, board_size, tiles)
                distance = _distance(position, target)
                if kind == "PICKUP" and int(
                    inventory.get(mission["item"], 0) or 0
                ) > 0:
                    continue

            priority = int(mission["priority"])
            score = (
                PRIORITY_BONUS.get(priority, -1000.0 * priority)
                + float(mission["value"])
                - TRAVEL_COST * distance
            )
            pairs.append(
                (
                    -score,
                    distance,
                    worker_index,
                    mission_index,
                    target[1],
                    target[0],
                    target,
                )
            )

    used_workers = set()
    used_missions = set()
    used_targets = set()
    shed_capacity = int(_cfg(config, "shedCapacity", SHED_CAPACITY))
    drop_room = max(0, shed_capacity - summary["shed_load"])
    for _, distance, worker_index, mission_index, _, _, target in sorted(pairs):
        if worker_index in used_workers or mission_index in used_missions:
            continue
        mission = missions[mission_index]
        target_key = target
        if mission["kind"] == "FIELD":
            operation = mission["action"][0]
            if (
                liquidation
                and operation in {"HARVEST", "COLLECT_FERTILIZER"}
            ) or operation == "FERTILIZE":
                target_key = (target, operation)
            if target_key in used_targets:
                continue

        action = None
        plant_crop = None
        if mission["kind"] == "FIELD":
            planned = mission["action"]
            if planned[0] == "PLANT":
                plant_crop = planned[1]
                if int(seed_budget.get(plant_crop, 0) or 0) <= 0:
                    continue
            action = (
                list(planned)
                if distance == 0
                else _bfs_first_step(tiles, positions[worker_index], target)
            )
        elif mission["kind"] == "PICKUP":
            action = (
                ["PICKUP", mission["item"], int(mission["amount"])]
                if distance == 0
                else _bfs_first_step(tiles, positions[worker_index], target)
            )
        else:
            inventory = inventories[worker_index]
            product_counts = {
                item: max(0, int(inventory.get(item, 0) or 0))
                for item in PRODUCTS
                if int(inventory.get(item, 0) or 0) > 0
            }
            if distance:
                action = _bfs_first_step(
                    tiles, positions[worker_index], target
                )
            else:
                cash_units = sum(product_counts.values())
                noncash = _inventory_total(inventory) - cash_units
                if cash_units <= 0 or drop_room <= 0:
                    continue
                if noncash <= 0 and cash_units <= drop_room:
                    action = ["DROP"]
                    drop_room -= cash_units
                else:
                    item = max(
                        product_counts,
                        key=lambda name: (
                            float(
                                market_prices.get(name, MARKET[name][0])
                                or MARKET[name][0]
                            ),
                            name,
                        ),
                    )
                    quantity = min(product_counts[item], drop_room)
                    if quantity <= 0:
                        continue
                    action = ["PLACE", item, quantity]
                    drop_room -= quantity

        if not action or (action == ["PASS"] and distance > 0):
            continue
        if plant_crop is not None:
            seed_budget[plant_crop] -= 1
        if mission["kind"] == "FIELD":
            used_targets.add(target_key)
        actions[worker_index] = action
        used_workers.add(worker_index)
        used_missions.add(mission_index)

    return {
        "farmer": actions[0] if actions else ["PASS"],
        "hands": actions[1:],
        "liquidation": liquidation,
    }


# Market and capital allocation

def _fib(index):
    a, b = 1, 1
    for _ in range(index):
        a, b = b, a + b
    return a


def _pending_drop(private, field, capacity=SHED_CAPACITY):
    pending = {}
    inventories = list(private.get("inventories", []) or [])
    actions = [field["farmer"], *field["hands"]]
    room = max(
        0,
        int(capacity)
        - sum(
            max(0, int(value or 0))
            for value in (private.get("shed", {}) or {}).values()
        ),
    )
    for index, action in enumerate(actions):
        if index >= len(inventories) or not action or room <= 0:
            continue
        inventory = inventories[index] or {}
        if action[0] == "DROP":
            for item, count in inventory.items():
                accepted = min(max(0, int(count or 0)), room)
                if item in PRODUCTS and accepted > 0:
                    pending[item] = pending.get(item, 0) + accepted
                room -= accepted
                if room <= 0:
                    break
        elif action[0] == "PLACE" and len(action) >= 2:
            item = action[1]
            requested = int(action[2]) if len(action) >= 3 else 1
            accepted = min(
                max(0, requested),
                max(0, int(inventory.get(item, 0) or 0)),
                room,
            )
            if item in PRODUCTS and accepted > 0:
                pending[item] = pending.get(item, 0) + accepted
            room -= accepted
    return pending


def _post_field_storage(private, field, capacity=SHED_CAPACITY):
    shed = {
        item: max(0, int(count or 0))
        for item, count in (private.get("shed", {}) or {}).items()
    }
    inventories = [
        {
            item: max(0, int(count or 0))
            for item, count in (inventory or {}).items()
            if int(count or 0) > 0
        }
        for inventory in (private.get("inventories", []) or [])
    ]
    actions = [field.get("farmer", ["PASS"]), *field.get("hands", [])]

    while len(inventories) < len(actions):
        inventories.append({})

    for index, action in enumerate(actions):
        if not action:
            continue
        inventory = inventories[index]
        operation = action[0]
        if operation == "DROP":
            for item, count in list(inventory.items()):
                room = max(0, int(capacity) - sum(shed.values()))
                accepted = min(max(0, int(count or 0)), room)
                if accepted > 0:
                    shed[item] = shed.get(item, 0) + accepted
                del inventory[item]
        elif operation == "PLACE" and len(action) >= 2:
            item = action[1]
            if item not in PRODUCTS:
                continue
            requested = int(action[2]) if len(action) >= 3 else 1
            accepted = min(
                max(0, requested),
                max(0, int(inventory.get(item, 0) or 0)),
                max(0, int(capacity) - sum(shed.values())),
            )
            if accepted > 0:
                inventory[item] -= accepted
                if inventory[item] == 0:
                    del inventory[item]
                shed[item] = shed.get(item, 0) + accepted
        elif operation == "PICKUP" and len(action) >= 2:
            item = action[1]
            requested = int(action[2]) if len(action) >= 3 else 1
            picked = min(
                max(0, requested),
                max(0, int(shed.get(item, 0) or 0)),
            )
            if picked > 0:
                shed[item] -= picked
                inventory[item] = inventory.get(item, 0) + picked
        elif (
            operation == "FEED"
            and int(inventory.get("WHEAT", 0) or 0) > 0
        ):
            inventory["WHEAT"] -= 1
            if inventory["WHEAT"] == 0:
                del inventory["WHEAT"]
        elif (
            operation == "FERTILIZE"
            and int(inventory.get("FERTILIZER", 0) or 0) > 0
        ):
            inventory["FERTILIZER"] -= 1
            if inventory["FERTILIZER"] == 0:
                del inventory["FERTILIZER"]

    return shed, inventories


def _market_commitment_cost(obs, farm, orders):
    prices = ((obs.get("market", {}) or {}).get("prices", {}) or {})
    hires = int(farm.get("hires_today", 0) or 0)
    land_index = max(0, len(farm.get("unlocked_quadrants", []) or []) - 1)
    cost = 0.0
    for order in orders:
        if not order:
            continue
        operation = order[0]
        quantity = int(order[2]) if len(order) > 2 else 1
        if operation == "HIRE":
            cost += _fib(hires)
            hires += 1
        elif operation == "BUY_LAND" and land_index < len(LAND_PRICES):
            cost += LAND_PRICES[land_index]
            land_index += 1
        elif operation == "BUY_ANIMAL" and len(order) > 1:
            cost += ANIMALS.get(order[1], {"cost": 10_000})["cost"] * quantity
        elif operation == "BUY_SEED" and len(order) > 1:
            cost += CROPS.get(order[1], {"seed": 10_000})["seed"] * quantity
        elif operation == "BUY_PRODUCT" and len(order) > 1:
            cost += float(prices.get(order[1], 100) or 100) * quantity * 1.25
    return cost


def _append_schedule_order(orders, order, max_orders):
    result = [list(value) for value in orders[:max_orders]]
    if len(result) < max_orders:
        result.append(order)
        return result, True
    for index in range(len(result) - 1, -1, -1):
        if result[index] and result[index][0] == "HIRE":
            result[index] = order
            return result, True
    return result, False


def _schedule_market_adjustment(obs, config, farm, private, orders):
    global _SCHEDULE_WHEAT_REQUESTED
    active = _schedule_signature(obs)
    raw_step = obs.get("step")
    step = int(
        raw_step
        if raw_step is not None
        else 24 * int(obs.get("day", 0) or 0) + int(obs.get("hour", 0) or 0)
    )
    if step == 0 or not active:
        _SCHEDULE_WHEAT_REQUESTED = 0
        return orders
    day = int(obs.get("day", step // 24) or 0)
    hour = int(obs.get("hour", step % 24) or 0)
    if day != 11:
        _SCHEDULE_WHEAT_REQUESTED = 0
        return orders

    max_orders = int(_cfg(config, "maxMarketOrdersPerTurn", MAX_MARKET_ORDERS))
    result = [list(order) for order in orders[:max_orders]]
    if hour == 2 and _SCHEDULE_WHEAT_REQUESTED == 0:
        wheat_price = float(
            (((obs.get("market", {}) or {}).get("prices", {}) or {}).get(
                "WHEAT", MARKET["WHEAT"][0]
            )
            or MARKET["WHEAT"][0])
        )
        money = float(farm.get("money", 0) or 0)
        committed = _market_commitment_cost(obs, farm, result)
        affordable = int(
            max(0.0, money - committed - 750.0)
            // max(1.0, wheat_price + 25.0)
        )
        quantity = min(SCHEDULE_WHEAT_CAP, affordable)
        if quantity > 0:
            result, inserted = _append_schedule_order(
                result,
                ["BUY_PRODUCT", "WHEAT", quantity],
                max_orders,
            )
            if inserted:
                _SCHEDULE_WHEAT_REQUESTED = quantity
                return result

    if hour == 19 and _SCHEDULE_WHEAT_REQUESTED > 0:
        shed_wheat = int((private.get("shed", {}) or {}).get("WHEAT", 0) or 0)
        animals = sum(_farm_animal_counts(farm).values())
        quantity = min(
            _SCHEDULE_WHEAT_REQUESTED,
            max(0, shed_wheat - 3 * animals),
        )
        _SCHEDULE_WHEAT_REQUESTED = 0
        if quantity > 0:
            result, inserted = _append_schedule_order(
                result,
                ["SELL", "WHEAT", quantity],
                max_orders,
            )
            if inserted:
                return result
    return orders


def _sell_quantity(item, have, inventory, day, shed_load, obs=None):
    left = TOTAL_DAYS - day
    if left <= 1:
        return have
    base = _market_parameters(obs, item)[0]
    reserve = base * RESERVE_FRACTION[item]
    if left <= 7:
        reserve *= max(0.0, (left - 1) / 6.0)
    if shed_load >= 0.75:
        reserve *= 0.55

    opponent_supply = _opponent_visible_supply(obs, item, horizon=1)
    town_demand = _town_demand_per_day(obs, item)
    if opponent_supply > town_demand:
        reserve *= max(0.72, 1.0 - 0.015 * (opponent_supply - town_demand))
    projected_inventory = inventory + opponent_supply - town_demand
    future_price = _price_at(item, projected_inventory, obs)
    threshold = reserve
    if shed_load < 0.75 and left > 7:
        threshold = max(threshold, 0.88 * future_price)

    quantity = 0
    while (
        quantity < have
        and _price_at(item, inventory + quantity, obs) >= threshold
    ):
        quantity += 1
    if left <= 12:
        forced = int(math.ceil(have / float(max(1, left - 1))))
        quantity = max(quantity, min(have, forced))
    return quantity


def _seed_needs(obs, farm, private, roles):
    day = int(obs.get("day", 0) or 0)
    seeds = private.get("seeds", {}) or {}
    needs = {}
    for (x, y), (kind, item) in roles.items():
        if (
            kind == "CROP"
            and (
                farm["tiles"][y][x] is None
                or (
                    isinstance(farm["tiles"][y][x], dict)
                    and farm["tiles"][y][x].get("kind") == "WEED"
                )
            )
            and day <= CROPS[item]["last_plant"]
        ):
            needs[item] = needs.get(item, 0) + 1
    return {
        crop: max(0, count - int(seeds.get(crop, 0) or 0))
        for crop, count in needs.items()
    }


def _target_hands(obs, farm, private, roles):
    day = int(obs.get("day", 0) or 0)
    summary = _survey(farm, private, roles, day)
    due_jobs = len(_field_jobs(obs, farm, private, roles, liquidation=False))
    active_roles = (
        summary["plants"]
        + summary["animals"]
        + summary["plantable"]
        + summary["structures_todo"]
    )
    floor = 10 if day <= 27 and active_roles > 0 else 4
    risk_load = 2 * (
        summary["at_risk_animals"] + summary["at_risk_crops"]
    )
    demand_target = int(math.ceil((due_jobs + risk_load) / 7.0))
    return max(4, min(MAX_HANDS, max(floor, demand_target)))


def _market_actions(obs, config, farm, private, roles, field):
    day = int(obs.get("day", 0) or 0)
    hour = int(obs.get("hour", 0) or 0)
    left = TOTAL_DAYS - day
    money = float(farm.get("money", 0) or 0)
    shed_capacity = int(_cfg(config, "shedCapacity", SHED_CAPACITY))
    shed, post_field_inventories = _post_field_storage(
        private, field, shed_capacity
    )
    market_inventory = dict(
        ((obs.get("market", {}) or {}).get("inventory", {}) or {})
    )
    max_orders = int(_cfg(config, "maxMarketOrdersPerTurn", MAX_MARKET_ORDERS))
    summary = _survey(farm, private, roles, day)
    phase = _policy_phase(obs, farm, private, summary)
    orders = []
    occupancy = sum(max(0, int(value or 0)) for value in shed.values())
    shed_load = occupancy / float(max(1, shed_capacity))
    animal_pipeline = summary["animals"] + sum(
        summary["animal_stock"].values()
    )
    feed_floor = animal_pipeline * FEED_STOCK_DAYS
    total_wheat = int(shed.get("WHEAT", 0) or 0) + sum(
        int(inventory.get("WHEAT", 0) or 0)
        for inventory in post_field_inventories
    )

    sells = []
    for item in PRODUCTS:
        have = int(shed.get(item, 0) or 0)
        if item == "WHEAT" and left > 2:
            have = min(have, max(0, total_wheat - feed_floor))
        if have <= 0:
            continue
        raw_inventory = market_inventory.get(item)
        inventory = MARKET_I0 if raw_inventory is None else int(raw_inventory)
        quantity = _sell_quantity(
            item, have, inventory, day, shed_load, obs
        )
        if quantity <= 0:
            continue
        proceeds = sum(
            _price_at(item, inventory + offset, obs)
            for offset in range(quantity)
        )
        sells.append((proceeds, item, quantity))
    sells.sort(reverse=True)
    for proceeds, item, quantity in sells:
        if len(orders) >= max_orders:
            break
        orders.append(["SELL", item, quantity])
        money += 0.85 * proceeds
        occupancy = max(0, occupancy - quantity)
        shed[item] = max(0, int(shed.get(item, 0) or 0) - quantity)
        raw_inventory = market_inventory.get(item)
        inventory = MARKET_I0 if raw_inventory is None else int(raw_inventory)
        market_inventory[item] = inventory + quantity

    if field["liquidation"] or left <= 1:
        if day >= 29 and hour <= 1:
            terminal_jobs = _field_jobs(
                obs, farm, private, roles, liquidation=True
            )
            target = min(8, len(terminal_jobs))
            hires = int(farm.get("hires_today", 0) or 0)
            while hires < target and len(orders) < max_orders:
                cost = _fib(hires)
                if money < cost + 20:
                    break
                orders.append(["HIRE"])
                money -= cost
                hires += 1
        return orders[:max_orders]

    placed = _farm_animal_counts(farm)
    role_targets = {animal: 0 for animal in ANIMALS}
    for kind, item in roles.values():
        if kind == "ANIMAL" and item in role_targets:
            role_targets[item] += 1
    owned = {
        animal: placed[animal] + _private_item_total(private, animal)
        for animal in ANIMALS
    }
    animal_capital_open = phase in {"BOOTSTRAP", "COMPOUND"} or (
        phase == "CRISIS"
        and summary["at_risk_animals"] == 0
        and summary["shed_load"] + summary["carried_load"] < 95
        and summary["open_structures"] > 0
        and animal_pipeline
        < summary["animals"] + summary["open_structures"]
    )
    if (
        animal_capital_open
        and day <= ANIMAL_PURCHASE_LAST_DAY
        and left >= 8
    ):
        purchase_order = sorted(
            ("COW", "SHEEP"),
            key=lambda animal: (
                _livestock_score(
                    obs,
                    animal,
                    owned[animal],
                    _opponent_animal_counts(obs)[animal],
                ),
                role_targets[animal] - owned[animal],
                animal == "COW",
            ),
            reverse=True,
        )
        for animal in purchase_order:
            if len(orders) >= max_orders:
                break
            missing = max(0, role_targets[animal] - owned[animal])
            if missing <= 0:
                continue
            operating_reserve = 80 if sum(owned.values()) < CORE_HERD else 220
            quantity = min(
                missing,
                2,
                max(0, shed_capacity - occupancy),
                max(
                    0,
                    int(
                        (money - operating_reserve)
                        // ANIMALS[animal]["cost"]
                    ),
                ),
            )
            if quantity > 0:
                orders.append(["BUY_ANIMAL", animal, quantity])
                money -= quantity * ANIMALS[animal]["cost"]
                occupancy += quantity
                owned[animal] += quantity

    total_wheat = int(shed.get("WHEAT", 0) or 0) + sum(
        int(inventory.get("WHEAT", 0) or 0)
        for inventory in post_field_inventories
    )
    planned_herd = sum(owned.values())
    desired_wheat = max(
        planned_herd * FEED_STOCK_DAYS,
        8 if planned_herd > 0 else 0,
    )
    if (
        desired_wheat > total_wheat
        and len(orders) < max_orders
        and planned_herd > 0
    ):
        raw_inventory = market_inventory.get("WHEAT")
        inventory = MARKET_I0 if raw_inventory is None else int(raw_inventory)
        emergency_reserve = 0 if summary["at_risk_animals"] else 80
        quantity = 0
        cost = 0
        limit = min(
            desired_wheat - total_wheat,
            max(0, shed_capacity - occupancy),
        )
        for offset in range(limit):
            unit = _price_at("WHEAT", inventory - offset - 1, obs)
            if money - cost - unit < emergency_reserve:
                break
            cost += unit
            quantity += 1
        if quantity > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            money -= cost
            occupancy += quantity

    extra_land = max(0, len(farm.get("unlocked_quadrants", ["NW"])) - 1)
    if (
        phase in {"BOOTSTRAP", "COMPOUND"}
        and extra_land < MAX_EXTRA_LAND
        and day >= LAND_OPEN_DAYS[extra_land]
        and left >= 12
        and len(orders) < max_orders
    ):
        cost = LAND_PRICES[extra_land]
        reserve = 300 if extra_land == 0 else 500
        if money >= cost + reserve:
            orders.append(["BUY_LAND"])
            money -= cost

    needs = _seed_needs(obs, farm, private, roles)
    seed_reserve = 80 if day <= 4 else 150
    seed_order = (
        ("MELON",)
        if day == 0
        else ("MELON", "WHEAT", "STRAWBERRY", "CARROT", "TOMATO")
    )
    for crop in seed_order:
        if len(orders) >= max_orders or needs.get(crop, 0) <= 0:
            continue
        cost = CROPS[crop]["seed"]
        quantity = min(
            needs[crop],
            25,
            max(0, int((money - seed_reserve) // cost)),
        )
        if quantity > 0:
            orders.append(["BUY_SEED", crop, quantity])
            money -= quantity * cost

    if hour <= 2:
        target_hands = _target_hands(obs, farm, private, roles)
        hires = int(farm.get("hires_today", 0) or 0)
        while hires < target_hands and len(orders) < max_orders:
            cost = _fib(hires)
            if money < max(20, 3 * cost):
                break
            orders.append(["HIRE"])
            money -= cost
            hires += 1

    return orders[:max_orders]


def _decide(obs, config=None):
    farms = obs.get("farms", []) or []
    player = int(obs.get("player", 0) or 0)
    if not (0 <= player < len(farms)):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    private = obs.get("private", {}) or {}
    roles = _role_plan(obs, farm)
    field = _unit_actions(obs, config, farm, private, roles)
    market = _market_actions(obs, config, farm, private, roles, field)
    market = _schedule_market_adjustment(obs, config, farm, private, market)
    return {
        "farmer": field["farmer"],
        "hands": field["hands"],
        "market": market,
    }




# State-gated labor-cap coordinate. The base decision rule is preserved and
# only its final hand-count ceiling changes.
_LABOR_GATE_BASE_TARGET_HANDS = _target_hands
_LABOR_GATE_CONDITIONS = ({'field': 'obs.day', 'operator': '>=', 'value': 20},)
_LABOR_GATE_INSIDE_CAP = 13
_LABOR_GATE_OUTSIDE_CAP = 12
MAX_HANDS = 13


def _labor_gate_active(obs, farm):
    for condition in _LABOR_GATE_CONDITIONS:
        field = condition["field"]
        operator = condition["operator"]
        threshold = condition["value"]
        if field == "obs.day":
            value = int(obs.get("day", 0) or 0)
        elif field == "farm.money_pre_action":
            value = float(farm.get("money", 0) or 0)
        else:
            return False
        if operator == "<=" and not value <= threshold:
            return False
        if operator == ">=" and not value >= threshold:
            return False
    return True


def _target_hands(obs, farm, private, roles):
    requested = int(_LABOR_GATE_BASE_TARGET_HANDS(obs, farm, private, roles))
    cap = (
        _LABOR_GATE_INSIDE_CAP
        if _labor_gate_active(obs, farm)
        else _LABOR_GATE_OUTSIDE_CAP
    )
    return min(requested, cap)
def agent(obs, config=None):
    try:
        return _decide(obs, config)
    except Exception:
        farms = obs.get("farms", []) if hasattr(obs, "get") else []
        player = int(obs.get("player", 0)) if hasattr(obs, "get") else 0
        hand_count = (
            len(farms[player].get("hands", []) or [])
            if 0 <= player < len(farms)
            else 0
        )
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in range(hand_count)],
            "market": [],
        }