"""Cheap 2–5 day bucket look-ahead for land vs cow vs seed.

No grid pathing — daily labor buckets, env-grounded crop/animal/price
tables, mark-to-market wealth. Used by market_for to rank capital projects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Literal

ProjectKind = Literal["land", "cow", "seed", "hold"]

# Env-aligned tables (kaggle_environments Kaggriculture).
LAND_PRICES = (1000, 2000, 4000)
COW_COST = 400
SEED_COST = {
    "WHEAT": 10,
    "CARROT": 20,
    "TOMATO": 50,
    "STRAWBERRY": 100,
    "MELON": 80,
}
MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
MARKET_PARAMS: dict[str, dict[str, Any]] = {
    "WHEAT": {
        "base": 25,
        "I0": MARKET_I0,
        "T": 400,
        "below_func": "sqrt",
        "below_target": 0.80,
        "above_func": "log",
        "above_target": 0.20,
    },
    "CARROT": {
        "base": 35,
        "I0": MARKET_I0,
        "T": 450,
        "below_func": "hinge",
        "below_target": 1.00,
        "above_func": "sqrt",
        "above_target": 0.70,
    },
    "TOMATO": {
        "base": 60,
        "I0": MARKET_I0,
        "T": 200,
        "below_func": "hinge",
        "below_target": 0.40,
        "above_func": "sqrt",
        "above_target": 0.60,
    },
    "STRAWBERRY": {
        "base": 120,
        "I0": MARKET_I0,
        "T": 100,
        "below_func": "sqrt",
        "below_target": 0.70,
        "above_func": "linear",
        "above_target": 1.60,
    },
    "MELON": {
        "base": 250,
        "I0": MARKET_I0,
        "T": 300,
        "below_func": "log",
        "below_target": 0.20,
        "above_func": "sq",
        "above_target": 3.60,
    },
    "EGG": {
        "base": 50,
        "I0": MARKET_I0,
        "T": 332,
        "below_func": "hinge",
        "below_target": 0.40,
        "above_func": "log",
        "above_target": 0.20,
    },
    "MILK": {
        "base": 160,
        "I0": MARKET_I0,
        "T": 122,
        "below_func": "sqrt",
        "below_target": 0.60,
        "above_func": "linear",
        "above_target": 1.60,
    },
    "WOOL": {
        "base": 200,
        "I0": MARKET_I0,
        "T": 105,
        "below_func": "log",
        "below_target": 0.20,
        "above_func": "sq",
        "above_target": 3.20,
    },
}

# Steady production per day once mature (env interval inverted).
ONGOING_YIELD_PER_DAY = {"TOMATO": 1.0, "STRAWBERRY": 0.5}
ANIMAL_YIELD_PER_DAY = {"COW": 0.5, "SHEEP": 1.0 / 3.0, "GOOSE": 1.0}
ANIMAL_PRODUCT = {"COW": "MILK", "SHEEP": "WOOL", "GOOSE": "EGG"}
CASH_CROPS = ("STRAWBERRY", "TOMATO", "CARROT", "MELON")


def _shape(func: str, x: float, T: float | None = None) -> float:
    x = max(0.0, float(x))
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def market_price(item: str, inventory: int) -> int:
    p = MARKET_PARAMS.get(item)
    if not p:
        return PRICE_FLOOR
    base = float(p["base"])
    i0 = float(p["I0"])
    t = float(p["T"])
    inv = float(inventory)
    if inv < i0:
        f = str(p["below_func"])
        amp = float(p["below_target"]) * base / _shape(f, t, t)
        price = base + amp * _shape(f, i0 - inv, t)
    else:
        f = str(p["above_func"])
        amp = float(p["above_target"]) * base / _shape(f, t, t)
        price = base - amp * _shape(f, inv - i0, t)
    return max(PRICE_FLOOR, int(round(price)))


@dataclass
class FarmSnapshot:
    """Coarse farm state for bucket roll-forward (no grid)."""

    money: float
    empty: int
    n_quads: int
    workers: int
    day: int
    cows: int = 0
    sheep: int = 0
    geese: int = 0
    waiting_cows: int = 0
    crops: dict[str, int] = field(default_factory=dict)
    seeds: dict[str, int] = field(default_factory=dict)
    shed: dict[str, float] = field(default_factory=dict)
    market_inv: dict[str, int] = field(default_factory=dict)
    demand: dict[str, int] = field(default_factory=dict)
    unfed_streak: int = 0
    primary: str = "STRAWBERRY"
    actions_per_worker_day: int = 8

    def mouths(self) -> int:
        return int(self.cows) + int(self.sheep) + int(self.geese)

    def live_tiles(self) -> int:
        total = 0
        for crop, n in self.crops.items():
            total += max(0, int(n))
        return total

    def clone(self) -> FarmSnapshot:
        return replace(
            self,
            crops=dict(self.crops),
            seeds=dict(self.seeds),
            shed=dict(self.shed),
            market_inv=dict(self.market_inv),
            demand=dict(self.demand),
        )


def wealth(snap: FarmSnapshot) -> float:
    """Money + shed mark-to-market + residual herd/empty option value."""
    total = float(snap.money)
    for item, qty in snap.shed.items():
        q = float(qty)
        if q <= 0:
            continue
        inv = int(snap.market_inv.get(item, MARKET_I0))
        total += q * float(market_price(item, inv))
    primary = snap.primary
    planted = int(snap.crops.get(primary, 0) or 0)
    if planted > 0 and primary in MARKET_PARAMS:
        inv = int(snap.market_inv.get(primary, MARKET_I0))
        total += 0.35 * planted * float(market_price(primary, inv))
    # Empty tiles = option to plant primary (labor-limited).
    if snap.empty > 0 and primary in MARKET_PARAMS:
        inv = int(snap.market_inv.get(primary, MARKET_I0))
        plantable = min(
            int(snap.empty),
            max(0, snap.workers * snap.actions_per_worker_day // 2),
        )
        total += 0.25 * plantable * float(market_price(primary, inv))
    # Residual herd value over a short remaining window (beyond roll days).
    left = max(1, 27 - int(snap.day))
    horizon = min(left, 8)
    if snap.cows > 0:
        inv = int(snap.market_inv.get("MILK", MARKET_I0))
        total += (
            snap.cows
            * ANIMAL_YIELD_PER_DAY["COW"]
            * horizon
            * float(market_price("MILK", inv))
        )
    if snap.sheep > 0:
        inv = int(snap.market_inv.get("WOOL", MARKET_I0))
        total += (
            snap.sheep
            * ANIMAL_YIELD_PER_DAY["SHEEP"]
            * horizon
            * float(market_price("WOOL", inv))
        )
    if snap.geese > 0:
        inv = int(snap.market_inv.get("EGG", MARKET_I0))
        total += (
            snap.geese
            * ANIMAL_YIELD_PER_DAY["GOOSE"]
            * horizon
            * float(market_price("EGG", inv))
        )
    return total


def from_agent_state(
    s: dict[str, Any],
    *,
    actions_per_worker_day: int = 8,
    primary: str | None = None,
) -> FarmSnapshot:
    crops = {k: int(v or 0) for k, v in (s.get("crops") or {}).items()}
    seeds = {k: int(v or 0) for k, v in (s.get("seeds") or {}).items()}
    shed_raw = s.get("shed") or {}
    shed = {k: float(shed_raw.get(k, 0) or 0) for k in (
        "WHEAT",
        "CARROT",
        "TOMATO",
        "STRAWBERRY",
        "MELON",
        "EGG",
        "MILK",
        "WOOL",
    )}
    inv_raw = s.get("inventory") or {}
    market_inv = {
        k: int(inv_raw.get(k, MARKET_I0) or MARKET_I0) for k in MARKET_PARAMS
    }
    demand = {k: int(v or 0) for k, v in (s.get("demand") or {}).items()}
    prim = primary or "STRAWBERRY"
    waiting = int((s.get("shed") or {}).get("COW", 0) or 0)
    return FarmSnapshot(
        money=float(s.get("money") or 0),
        empty=int(s.get("empty") or 0),
        n_quads=int(s.get("n_quads") or 1),
        workers=max(1, int(s.get("workers") or 1)),
        day=int(s.get("day") or 0),
        cows=int(s.get("cows") or 0),
        sheep=int(s.get("sheep") or 0),
        geese=int(s.get("geese") or 0),
        waiting_cows=waiting,
        crops=crops,
        seeds=seeds,
        shed=shed,
        market_inv=market_inv,
        demand=demand,
        unfed_streak=0,
        primary=prim,
        actions_per_worker_day=max(1, int(actions_per_worker_day)),
    )


def apply_project(
    snap: FarmSnapshot,
    kind: ProjectKind,
    *,
    n_seeds: int = 0,
    seed_crop: str | None = None,
) -> FarmSnapshot:
    """Apply an immediate capital action, then return a new snapshot."""
    out = snap.clone()
    if kind == "hold":
        return out
    if kind == "land":
        if out.n_quads >= 4:
            return out
        cost = LAND_PRICES[min(out.n_quads - 1, len(LAND_PRICES) - 1)]
        if out.money < cost:
            return out
        out.money -= cost
        out.empty += 25
        out.n_quads += 1
        # Couple a modest primary seed buy (chooser does this after land).
        crop = seed_crop or out.primary
        cost_u = int(SEED_COST.get(crop, 100))
        if cost_u > 0 and out.money >= cost_u:
            labor_cap = max(0, out.workers * out.actions_per_worker_day // 2)
            buy_n = max(4, int(n_seeds) if n_seeds else 8)
            n = min(int(out.money // cost_u), 25, labor_cap, buy_n)
            if n > 0:
                out.money -= n * cost_u
                out.seeds[crop] = int(out.seeds.get(crop, 0) or 0) + n
        return out
    if kind == "cow":
        if out.money < COW_COST:
            return out
        out.money -= COW_COST
        # Place on empty as pasture, else wait in shed.
        if out.empty > 0:
            out.empty -= 1
            out.cows += 1
        else:
            out.waiting_cows += 1
            out.cows += 1  # still own the animal for feed/yield
        return out
    if kind == "seed":
        crop = seed_crop or out.primary
        cost_u = int(SEED_COST.get(crop, 100))
        n = max(0, int(n_seeds))
        if n <= 0 or cost_u <= 0:
            return out
        afford_n = int(out.money // cost_u)
        n = min(n, afford_n, max(0, out.empty))
        if n <= 0:
            return out
        out.money -= n * cost_u
        out.seeds[crop] = int(out.seeds.get(crop, 0) or 0) + n
        return out
    return out


def step_day(snap: FarmSnapshot) -> FarmSnapshot:
    """One dawn→dusk labor bucket."""
    out = snap.clone()
    labor = max(0, out.workers * out.actions_per_worker_day)
    mouths = out.mouths()
    live = out.live_tiles()

    # Place waiting cows if empties exist (pasture).
    while out.waiting_cows > 0 and out.empty > 0 and labor > 0:
        out.empty -= 1
        out.waiting_cows -= 1
        labor -= 1

    # Feed debt.
    feed_need = mouths
    fed = 0
    wheat_shed = float(out.shed.get("WHEAT", 0) or 0)
    take = min(feed_need, int(wheat_shed), labor)
    out.shed["WHEAT"] = wheat_shed - take
    fed += take
    labor -= take
    feed_need -= take
    # Harvest wheat tiles into feed if still short.
    wheat_planted = int(out.crops.get("WHEAT", 0) or 0)
    if feed_need > 0 and wheat_planted > 0 and labor > 0:
        harvest = min(feed_need, wheat_planted, labor)
        out.crops["WHEAT"] = wheat_planted - harvest
        out.empty += harvest
        fed += harvest
        labor -= harvest
        feed_need -= harvest
    if feed_need > 0:
        out.unfed_streak += 1
    else:
        out.unfed_streak = 0
    if out.unfed_streak >= 2 and mouths > 0:
        # Escape one animal (prefer goose, then sheep, then cow).
        if out.geese > 0:
            out.geese -= 1
        elif out.sheep > 0:
            out.sheep -= 1
        elif out.cows > 0:
            out.cows -= 1
        out.unfed_streak = 0

    # Water debt — unmet water becomes weeds on cash tiles.
    water_need = live
    watered = min(water_need, labor)
    labor -= watered
    unpaid = water_need - watered
    if unpaid > 0:
        # Lose up to half the unpaid tiles from the primary printer.
        lose = max(1, unpaid // 2) if unpaid >= 2 else 0
        for crop in (out.primary, "TOMATO", "STRAWBERRY", "WHEAT", "CARROT"):
            have = int(out.crops.get(crop, 0) or 0)
            if have <= 0 or lose <= 0:
                continue
            cut = min(have, lose)
            out.crops[crop] = have - cut
            # Weeds occupy the tile (not plantable empty).
            lose -= cut

    # Plant seeds onto empty with remaining labor.
    for crop in (out.primary, "WHEAT", "STRAWBERRY", "TOMATO"):
        seed_n = int(out.seeds.get(crop, 0) or 0)
        if seed_n <= 0 or out.empty <= 0 or labor <= 0:
            continue
        n = min(seed_n, out.empty, labor)
        out.seeds[crop] = seed_n - n
        out.crops[crop] = int(out.crops.get(crop, 0) or 0) + n
        out.empty -= n
        labor -= n

    # Produce ongoing crops into shed.
    for crop, rate in ONGOING_YIELD_PER_DAY.items():
        planted = int(out.crops.get(crop, 0) or 0)
        if planted <= 0:
            continue
        gained = planted * rate
        out.shed[crop] = float(out.shed.get(crop, 0) or 0) + gained

    # One-shot wheat/carrot: slow maturation credit into shed + free tile.
    for crop, frac in (("WHEAT", 0.25), ("CARROT", 0.3), ("MELON", 0.15)):
        planted = int(out.crops.get(crop, 0) or 0)
        if planted <= 0:
            continue
        done = max(0, int(round(planted * frac)))
        if done <= 0:
            continue
        out.crops[crop] = planted - done
        out.empty += done
        out.shed[crop] = float(out.shed.get(crop, 0) or 0) + done * (
            4.0 if crop == "WHEAT" else 3.0 if crop == "CARROT" else 5.0
        )

    # Animal products.
    if out.cows > 0:
        out.shed["MILK"] = float(out.shed.get("MILK", 0) or 0) + out.cows * ANIMAL_YIELD_PER_DAY[
            "COW"
        ]
    if out.sheep > 0:
        out.shed["WOOL"] = float(out.shed.get("WOOL", 0) or 0) + out.sheep * ANIMAL_YIELD_PER_DAY[
            "SHEEP"
        ]
    if out.geese > 0:
        out.shed["EGG"] = float(out.shed.get("EGG", 0) or 0) + out.geese * ANIMAL_YIELD_PER_DAY[
            "GOOSE"
        ]

    # Light shop/town drain on market inventory (prices drift).
    for item, d in out.demand.items():
        if item not in out.market_inv:
            continue
        drain = max(0, int(d))
        out.market_inv[item] = max(0, int(out.market_inv[item]) - drain)

    out.day += 1
    return out


def roll(snap: FarmSnapshot, days: int) -> FarmSnapshot:
    out = snap
    for _ in range(max(0, int(days))):
        out = step_day(out)
    return out


def score_horizon(
    snap0: FarmSnapshot,
    kind: ProjectKind,
    *,
    days: int,
    n_seeds: int = 0,
    seed_crop: str | None = None,
) -> float:
    """Δ wealth over the horizon after applying the project."""
    w0 = wealth(snap0)
    applied = apply_project(snap0, kind, n_seeds=n_seeds, seed_crop=seed_crop)
    final = roll(applied, days)
    return wealth(final) - w0


def rank_projects(
    s: dict[str, Any],
    *,
    days: int = 3,
    actions_per_worker_day: int = 8,
    primary: str | None = None,
    n_seeds: int = 0,
    can_land: bool = False,
    can_cow: bool = False,
    can_seed: bool = False,
    land_cost_ok: bool = True,
) -> dict[str, float]:
    """Return project scores as advantage over hold (hold ≈ 0)."""
    prim = primary or "STRAWBERRY"
    snap0 = from_agent_state(
        s, actions_per_worker_day=actions_per_worker_day, primary=prim
    )
    hold_score = score_horizon(snap0, "hold", days=days)
    scores: dict[str, float] = {
        "hold": 0.0,
        "land": 0.0,
        "cow": 0.0,
        "seed": 0.0,
    }
    if can_land and land_cost_ok:
        scores["land"] = (
            score_horizon(snap0, "land", days=days) - hold_score
        )
    if can_cow:
        scores["cow"] = score_horizon(snap0, "cow", days=days) - hold_score
    if can_seed and n_seeds > 0:
        scores["seed"] = (
            score_horizon(
                snap0, "seed", days=days, n_seeds=n_seeds, seed_crop=prim
            )
            - hold_score
        )
    return scores
