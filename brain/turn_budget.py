"""TurnBudget — labor, day capacity, and project NPV for one hour.

Hourly plantable is free workers after feed/water. Day capacity is what
the crew can plant after the live field is watered at the next dawn —
that is the number land/seed limbs may actually realize.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ProjectKind = Literal["land", "cow", "seed", "hire", "wheat", "fert", "hold"]
PlantHorizon = Literal["hour", "day"]


@dataclass(frozen=True)
class TurnBudget:
    """Capacity snapshot for one agent step."""

    workers: int
    hungry: int
    unwatered: int
    at_risk: int
    live_tiles: int
    empty: int
    plantable: int
    day_plantable: int
    tile_ev: float
    productive_days: int
    hour: int


def plant_slots(
    *,
    workers: int,
    hungry: int = 0,
    live_tiles: int = 0,
    empty: int,
    unwatered: int = 0,
    horizon: PlantHorizon = "hour",
) -> int:
    """Shared plant capacity for field seed caps and market seed buys.

    hour: free hands after watering still-dry tiles, capped by empty.
    day: two-dawn residual after watering the live cash crop, capped by empty.
    """
    free = max(0, int(workers) - int(hungry))
    empty_n = max(0, int(empty))
    if horizon == "hour":
        return min(max(0, free - max(0, int(unwatered))), empty_n)
    return min(max(0, 2 * free - max(0, int(live_tiles))), empty_n)


def compute_turn_budget(
    s: dict[str, Any],
    *,
    cash_crop: str,
    tile_ev: float,
    productive_days: int,
) -> TurnBudget:
    """Hour plantable + multi-dawn residual after watering the live field."""
    workers = int(s.get("workers") or 0)
    hungry = int(s.get("hungry") or 0)
    unwatered = int(s.get("unwatered") or 0)
    at_risk = int(s.get("at_risk") or 0)
    hour = int(s.get("hour") or 0)
    live = 0
    if cash_crop:
        live = int((s.get("crops") or {}).get(cash_crop, 0) or 0)
    empty = int(s.get("empty") or 0)
    free = max(0, workers - hungry)
    plantable = plant_slots(
        workers=workers,
        hungry=hungry,
        empty=empty,
        unwatered=unwatered,
        horizon="hour",
    )
    # Labor residual only — may exceed current empty before a land buy.
    day_plantable = max(0, 2 * free - live)
    return TurnBudget(
        workers=workers,
        hungry=hungry,
        unwatered=unwatered,
        at_risk=at_risk,
        live_tiles=live,
        empty=empty,
        plantable=plantable,
        day_plantable=day_plantable,
        tile_ev=max(0.0, float(tile_ev)),
        productive_days=max(0, int(productive_days)),
        hour=hour,
    )


def post_land_seed_cap(
    *, workers: int, hungry: int, live_tiles: int, empty: int
) -> int:
    """Seeds after land: two-dawn residual, never more than new empties."""
    return plant_slots(
        workers=workers,
        hungry=hungry,
        live_tiles=live_tiles,
        empty=empty,
        horizon="day",
    )


def land_fillable_tiles(
    *,
    workers: int,
    hungry: int,
    live_tiles: int,
    productive_days: int,
    new_empty: int = 25,
    short_horizon: bool = False,
) -> int:
    """Tiles plantable on a new plot before the engine ends.

    Plot 3+ (short_horizon): only the next two dawns after live water debt —
    packed printers correctly score ~0. 1→2: two-dawn residual plus free
    tiles/day afterward so a full first quad can still unlock expansion.
    """
    free = max(0, int(workers) - int(hungry))
    live = max(0, int(live_tiles))
    early = max(0, 2 * free - live)
    if short_horizon:
        return min(max(0, int(new_empty)), early)
    later = max(0, int(productive_days) - 2) * free
    return min(max(0, int(new_empty)), early + later)


def skip_days_after_land(*, live_tiles: int, extra_empty: int, workers: int) -> float:
    """Days the live field waits if we add a new plot (dawn water first)."""
    w = max(1, int(workers))
    # Two dawns of labor before the new plot is expected full.
    backlog = max(0, int(live_tiles) + int(extra_empty) - 2 * w)
    return backlog / float(w)


def land_expansion_npv(
    *,
    plantable_new: int,
    tile_ev: float,
    productive_days: int,
    land_cost: int,
    seed_cost: int,
    live_tiles: int,
    skip_days: float,
) -> float:
    """NPV of the next quad using dawn-capacity tiles, not fantasy 25."""
    fill_n = max(0, int(plantable_new))
    ev = max(0.0, float(tile_ev))
    days = max(0, int(productive_days))
    realized = fill_n * ev * days
    fill_cost = fill_n * max(0, int(seed_cost))
    damage = max(0, int(live_tiles)) * ev * max(0.0, float(skip_days))
    return realized - int(land_cost) - fill_cost - damage


def cow_project_ev(*, cow_ev: float, cow_cost: int) -> float:
    """Net EV of spending cow_cost on one cow (already amortized in animal_score)."""
    if cow_ev <= 0 or cow_cost <= 0:
        return 0.0
    return float(cow_ev)


def cow_horizon_ev(
    *,
    per_day: float,
    productive_days: int,
    setup_days: float = 2.0,
) -> float:
    """Cow NPV over remaining engine days, minus a short setup lag."""
    days = max(0.0, float(productive_days) - max(0.0, float(setup_days)))
    # Keep at least one day of credit so mid-game cows still clear hold.
    return max(0.0, float(per_day)) * max(1.0, days)


def seed_project_ev(
    *,
    tile_ev: float,
    productive_days: int,
    n_seeds: int,
    seed_cost: int,
) -> float:
    n = max(0, int(n_seeds))
    if n <= 0:
        return 0.0
    return n * max(0.0, float(tile_ev)) * max(0, int(productive_days)) - n * max(
        0, int(seed_cost)
    )


def hire_project_ev(
    *,
    tile_ev: float,
    productive_days: int,
    hire_cost: int,
    empty: int,
    workers: int,
    hungry: int,
    unwatered: int,
    live_tiles: int,
) -> float:
    """NPV of one extra hand: more hour slots + two-dawn plant residual."""
    if hire_cost <= 0:
        return 0.0
    w0 = max(0, int(workers))
    w1 = w0 + 1
    h = max(0, int(hungry))
    u = max(0, int(unwatered))
    live = max(0, int(live_tiles))
    empty_n = max(0, int(empty))
    hour0 = max(0, max(0, w0 - h) - u)
    hour1 = max(0, max(0, w1 - h) - u)
    day0 = max(0, 2 * max(0, w0 - h) - live)
    day1 = max(0, 2 * max(0, w1 - h) - live)
    hour_gain = min(empty_n, max(0, hour1 - hour0))
    day_gain = max(0, day1 - day0)
    ev = max(0.0, float(tile_ev))
    days = max(1, int(productive_days))
    # Hour gain realizes soon; day residual is a lighter two-dawn credit.
    realized = hour_gain * ev * min(2, days) + day_gain * ev * 0.5
    return realized - int(hire_cost)


def wheat_project_ev(
    *,
    feed_crisis: bool,
    wheat_gap: int,
    mouths: int,
    milk_px: float,
    productive_days: int,
    seed_cost: int = 10,
) -> float:
    """Feed crisis dominates; otherwise modest EV for closing the wheat tile gap."""
    if feed_crisis:
        # Must clear before discretionary projects — beats normal NPVs.
        return 1_000_000.0
    gap = max(0, int(wheat_gap))
    if gap <= 0:
        return 0.0
    mouths_n = max(0, int(mouths))
    # Keep wheat competitive only as light herd insurance, not vs berry NPV.
    herd = mouths_n * max(0.0, float(milk_px)) * 0.01 * min(3, max(1, int(productive_days)))
    plant = gap * 8.0
    return max(0.0, max(herd, plant) - gap * max(0, int(seed_cost)))


def fert_project_ev(
    *,
    keep_n: int,
    fert_px: float,
    tile_ev: float,
    live_cash_tiles: int,
) -> float:
    """Net value of keeping fertilizer vs selling it this hour."""
    n = max(0, int(keep_n))
    if n <= 0:
        return 0.0
    # One fert on a live cash tile is a light yield bump; forgone sale is fert_px.
    boost = max(0.0, float(tile_ev)) * 0.15 * min(n, max(0, int(live_cash_tiles)))
    return boost - n * max(0.0, float(fert_px))


def sell_slots_for_funding(
    *,
    base_sell_n: int,
    money: int,
    project_cost: int,
    est_proceeds_per_slot: float,
    max_sell_n: int = 8,
) -> int:
    """Bump sell actions when the best project is not yet affordable."""
    base = max(0, int(base_sell_n))
    cost = max(0, int(project_cost))
    cash = int(money)
    if cost <= cash:
        return base
    per = max(1.0, float(est_proceeds_per_slot))
    need = int((cost - cash + per - 1) // per)
    return min(int(max_sell_n), max(base, base + need))


def choose_project(
    *,
    land_npv: float,
    can_land: bool,
    cow_ev: float,
    can_cow: bool,
    seed_ev: float,
    can_seed: bool,
    hire_ev: float = 0.0,
    can_hire: bool = False,
    wheat_ev: float = 0.0,
    can_wheat: bool = False,
    fert_ev: float = 0.0,
    can_fert: bool = False,
) -> ProjectKind:
    """Pick the single best cash project this market hour (or hold)."""
    best: ProjectKind = "hold"
    best_score = 0.0
    if can_land and land_npv > best_score:
        best, best_score = "land", land_npv
    if can_cow and cow_ev > best_score:
        best, best_score = "cow", cow_ev
    if can_seed and seed_ev > best_score:
        best, best_score = "seed", seed_ev
    if can_hire and hire_ev > best_score:
        best, best_score = "hire", hire_ev
    if can_wheat and wheat_ev > best_score:
        best, best_score = "wheat", wheat_ev
    if can_fert and fert_ev > best_score:
        best, best_score = "fert", fert_ev
    return best


def cow_beats_seeds(
    *,
    cow_ev: float,
    tile_ev: float,
    cow_cost: int,
    seed_cost: int,
    plantable: int,
    empty: int,
    buy_gap: int,
) -> bool:
    """True when a cow is a better leftover-cash project than engine seeds."""
    if cow_ev <= 0:
        return False
    if plantable > 0 and empty > 0 and buy_gap > 0:
        seed_c = max(1, int(seed_cost))
        alt = max(0.0, float(tile_ev)) * (int(cow_cost) / float(seed_c))
        return float(cow_ev) > alt
    return True
