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

    Full horizon (default): two-dawn residual after live water debt, then
    free hands each remaining day — used for plot-3/4 expansion NPV.
    short_horizon=True keeps the old two-dawn-only residual (packed printers).
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


def hollow_expand_window(
    *,
    n_quads: int,
    empty: int,
    soft_cap: int = 14,
    hollow_max: int = 45,
) -> bool:
    """Softfloor mid-hollow board: expand before packing (not packed printers)."""
    if int(n_quads) != 2:
        return False
    empty_n = int(empty)
    return int(soft_cap) < empty_n <= int(hollow_max)


def live_tiles_for_hollow_expand(
    *,
    live_tiles: int,
    workers: int,
    hungry: int = 0,
    live_cap_factor: float = 1.35,
) -> int:
    """Cap live stand for expand NPV so mid-ramp densify does not zero spare labor.

    Softfloor buys plot-3 with a modest stand and spare crew. If we already
    planted into a fat stand on a hollow board, raw live/2 kills plant_per_day
    and NPV refuses land — the densify trap. Packed printers never enter the
    hollow window (empty ≤ soft_cap), so they keep full live and stay put.
    """
    live = max(0, int(live_tiles))
    free = max(0, int(workers) - max(0, int(hungry)))
    cap = max(8, int(float(free) * max(0.5, float(live_cap_factor))))
    return min(live, cap)


def expand_vs_stay_advantage(
    *,
    workers: int,
    hungry: int = 0,
    live_tiles: int,
    productive_days: int,
    tile_ev: float,
    land_cost: int,
    seed_cost: int,
    empty: int = 0,
    hire_n: int = 0,
    hire_cost_total: int = 0,
    new_empty: int = 25,
    stand_factor: float = 1.0,
    realize: float = 0.7,
    margin: float = 0.0,
    # Multi-stream extras (berries/milk/eggs/wool/inventory).
    animal_unlock_ev: float = 0.0,
    inventory_ev: float = 0.0,
) -> float:
    """Long-term profit: expand (+new_empty) minus stay-and-densify.

    Returns advantage (expand_net - stay_net). Buy land only when > margin.

    Spare planting rate after watering the live stand:
      plant_per_day ≈ max(0, free - live/2)
    If spare is ~0 (fat packed printer), incremental tiles from a new plot
    cannot be worked → advantage ≤ 0 (stay put). Softfloor hollow boards
    with spare crew clear land cost and score positive.

    `tile_ev` should already be the blended crop fill EV (berry/tomato/…).
    `animal_unlock_ev` credits milk/egg/wool mouths the new plot can host,
    scaled by spare labor so packed printers still stay put.
    """
    w = max(0, int(workers) + max(0, int(hire_n)))
    h = max(0, int(hungry))
    free = max(0, w - h)
    live = max(0, int(live_tiles))
    days = max(0, int(productive_days))
    empty_n = max(0, int(empty))
    extra = max(0, int(new_empty))
    if days <= 0 or free <= 0:
        return 0.0

    # Daily plant residual after ~half the crew waters the live stand.
    plant_per_day = max(0.0, float(free) - float(live) / 2.0)
    labor_cap = plant_per_day * float(days)
    if labor_cap <= 0:
        return 0.0

    stay_plant = min(float(empty_n), labor_cap)
    expand_plant = min(float(empty_n + extra), labor_cap)
    incremental = expand_plant - stay_plant
    if incremental <= 0:
        return 0.0

    ev = max(0.0, float(tile_ev)) * max(0.0, min(1.5, float(stand_factor)))
    # Incremental tiles come online after current empties are filled.
    days_clear_old = stay_plant / plant_per_day if plant_per_day > 0 else float(days)
    days_incr = incremental / plant_per_day if plant_per_day > 0 else float(days)
    avg_prod = max(1.0, float(days) - days_clear_old - 0.5 * days_incr)
    realized = incremental * ev * avg_prod * max(0.1, min(1.0, float(realize)))

    # Diverting plant days onto the new plot softens live-stand uptime.
    divert = min(float(days), days_incr)
    damage = float(live) * ev * divert * 0.35

    # Animal unlock only when crew can actually work the new plot.
    labor_scale = min(1.0, plant_per_day / 3.0)
    animal_credit = max(0.0, float(animal_unlock_ev)) * labor_scale
    # Inventory is identical stay vs expand — omit from advantage (kept for API).
    del inventory_ev

    wave = min(int(incremental), max(8, 2 * free))
    cost = (
        int(land_cost)
        + wave * max(0, int(seed_cost))
        + max(0, int(hire_cost_total))
    )
    return (
        realized
        + animal_credit
        - float(cost)
        - damage
        - max(0.0, float(margin))
    )

def expansion_project_npv(
    *,
    workers: int,
    hungry: int = 0,
    live_tiles: int,
    productive_days: int,
    tile_ev: float,
    land_cost: int,
    seed_cost: int,
    empty: int = 0,
    hire_n: int = 0,
    hire_cost_total: int = 0,
    new_empty: int = 25,
    hollow_soft_cap: int = 14,
    hollow_penalty_k: float = 4.0,
    stand_factor: float = 1.0,
    realize: float = 0.7,
    animal_unlock_ev: float = 0.0,
    inventory_ev: float = 0.0,
    margin: float = 0.0,
) -> float:
    """NPV of buying the next plot vs staying put (long-term profit).

    Prefer expand_vs_stay_advantage. hollow_* kept for API compatibility;
    spare-labor compare replaces packed short-horizon / hollow hard pens.
    """
    del hollow_soft_cap, hollow_penalty_k  # unused — stay/expand EV replaces them
    return expand_vs_stay_advantage(
        workers=workers,
        hungry=hungry,
        live_tiles=live_tiles,
        productive_days=productive_days,
        tile_ev=tile_ev,
        land_cost=land_cost,
        seed_cost=seed_cost,
        empty=empty,
        hire_n=hire_n,
        hire_cost_total=hire_cost_total,
        new_empty=new_empty,
        stand_factor=stand_factor,
        realize=realize,
        margin=margin,
        animal_unlock_ev=animal_unlock_ev,
        inventory_ev=inventory_ev,
    )


def land_expansion_npv(
    *,
    plantable_new: int | None = None,
    tile_ev: float,
    productive_days: int,
    land_cost: int,
    seed_cost: int,
    live_tiles: int,
    skip_days: float = 0.0,
    # Preferred expansion API (when workers is set, plantable_new is ignored).
    workers: int | None = None,
    hungry: int = 0,
    empty: int = 0,
    hire_n: int = 0,
    hire_cost_total: int = 0,
    new_empty: int = 25,
    hollow_soft_cap: int = 14,
    hollow_penalty_k: float = 4.0,
    stand_factor: float = 1.0,
    realize: float = 0.7,
) -> float:
    """NPV of the next quad — prefers multi-dawn expansion_project_npv."""
    if workers is not None:
        return expansion_project_npv(
            workers=int(workers),
            hungry=hungry,
            live_tiles=live_tiles,
            productive_days=productive_days,
            tile_ev=tile_ev,
            land_cost=land_cost,
            seed_cost=seed_cost,
            empty=empty,
            hire_n=hire_n,
            hire_cost_total=hire_cost_total,
            new_empty=new_empty,
            hollow_soft_cap=hollow_soft_cap,
            hollow_penalty_k=hollow_penalty_k,
            stand_factor=stand_factor,
            realize=realize,
        )
    # Legacy two-dawn path (tests / callers that only pass plantable_new).
    fill_n = max(0, int(plantable_new or 0))
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
