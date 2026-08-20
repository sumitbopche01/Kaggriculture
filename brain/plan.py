"""Phase-aware sell/field/market profiles for the unified turn plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from brain.map import MapStrategy, strategy_defer_animals, strategy_spike_sell_bump
from brain.turn_budget import TurnBudget

Phase = Literal["ENGINE", "SPIKE", "LATE_RAMP", "ENDGAME", "LIQUIDATE"]
Mode = Literal["ENGINE", "LIQUIDATE"]
MarketRoute = Literal["standard", "late_sprint", "berry_prep"]
FieldPriority = Literal["normal", "fill", "harvest"]


@dataclass(frozen=True)
class PhaseProfile:
    """Behavior template for a regime phase — values sourced from PARAMS."""

    sell_n_base: int
    sell_n_build: int
    sell_n_liquidate: int
    sell_n_endgame: int
    sell_n_rescue: int
    spike_sell_bump: bool
    late_ongoing_sell_bump: bool
    hire_cap: int | None
    land_cash_buffer: int
    post_land_floor: int
    skip_animal_care: bool
    field_priority: FieldPriority


@dataclass
class TurnFlags:
    """Derived booleans computed once from game state (main.py helpers)."""

    late_shop_sprint: bool
    berry_prep: bool
    plant_sprint: bool
    berry_ramp: bool
    seed_fill_push: bool
    berry_replant_push: bool
    in_late_ramp: bool
    land_ramp_relax: bool
    board_fill_pressure: bool
    need_land: bool
    berry_ok: bool
    liquidity_stress: bool
    late_ongoing: bool
    demand_stack: bool
    price_spike: dict[str, bool]
    cash_ramp: bool = False
    field_short: bool = False


@dataclass
class TurnPlan:
    """Single source of truth for one agent step."""

    phase: Phase
    mode: Mode
    profile: PhaseProfile
    crops: dict[str, int]
    berry_gap: int
    cash_deficit: float
    flags: TurnFlags
    market_route: MarketRoute
    defer_animals: bool
    strategy: MapStrategy = "UNKNOWN"
    regime: dict[str, Any] = field(default_factory=dict)
    cash_crop: str = ""
    cash_gap: int = 0
    budget: TurnBudget | None = None

    @property
    def plant_pressure(self) -> float:
        """Empty (and plan gap) relative to hour plant slots — one field signal."""
        b = self.budget
        empty = float(b.empty if b is not None else 0)
        at_risk = float(b.at_risk if b is not None else 0)
        workers = max(1.0, float(b.workers if b is not None else 1))
        # Tiny plantable under water debt used to inflate pressure and push
        # plant-over-water; floor slots by crew so densify doesn't thrash.
        slots = max(
            1.0,
            float(b.plantable if b is not None else 0),
            workers if at_risk > 0 else 0.0,
        )
        pressure = empty / slots
        gap = float(max(self.berry_gap, self.cash_gap))
        if gap > 0:
            pressure = max(pressure, gap / slots)
        if self.flags.field_short:
            pressure = max(pressure, 1.0)
        return pressure

    @property
    def fill_board(self) -> bool:
        """Back-compat: prioritize planting when plant_pressure is at least 1."""
        return self.plant_pressure >= 1.0

    @property
    def skip_animal_care(self) -> bool:
        return self.profile.skip_animal_care

    @property
    def harvest_focus(self) -> bool:
        return self.profile.field_priority == "harvest"


def phase_profile(phase: Phase, params: dict[str, int | float]) -> PhaseProfile:
    """Map phase → behavior profile, reading sell/land knobs from PARAMS."""
    base = int(params["sell_n_base"])
    build = int(params["sell_n_build"])
    liquidate = int(params["sell_n_liquidate"])
    endgame = int(params["sell_n_endgame"])
    rescue = int(params["sell_n_rescue"])
    land_default = int(params["land_cash_buffer_default"])
    post_default = int(params["land_post_floor_default"])
    ramp_buffer = int(params["late_ramp_land_cash_buffer"])
    ramp_hire = int(params["late_ramp_hire_cap"])

    if phase == "LIQUIDATE":
        return PhaseProfile(
            sell_n_base=liquidate,
            sell_n_build=liquidate,
            sell_n_liquidate=liquidate,
            sell_n_endgame=liquidate,
            sell_n_rescue=liquidate,
            spike_sell_bump=False,
            late_ongoing_sell_bump=True,
            hire_cap=None,
            land_cash_buffer=land_default,
            post_land_floor=post_default,
            skip_animal_care=True,
            field_priority="harvest",
        )
    if phase == "ENDGAME":
        return PhaseProfile(
            sell_n_base=base,
            sell_n_build=build,
            sell_n_liquidate=liquidate,
            sell_n_endgame=endgame,
            sell_n_rescue=rescue,
            spike_sell_bump=True,
            late_ongoing_sell_bump=True,
            hire_cap=None,
            land_cash_buffer=land_default,
            post_land_floor=post_default,
            skip_animal_care=True,
            field_priority="fill",
        )
    if phase == "LATE_RAMP":
        return PhaseProfile(
            sell_n_base=base,
            sell_n_build=build,
            sell_n_liquidate=liquidate,
            sell_n_endgame=endgame,
            sell_n_rescue=rescue,
            spike_sell_bump=False,
            late_ongoing_sell_bump=False,
            hire_cap=ramp_hire,
            land_cash_buffer=ramp_buffer,
            post_land_floor=ramp_buffer,
            skip_animal_care=False,
            field_priority="fill",
        )
    if phase == "SPIKE":
        return PhaseProfile(
            sell_n_base=base,
            sell_n_build=build,
            sell_n_liquidate=liquidate,
            sell_n_endgame=endgame,
            sell_n_rescue=rescue,
            spike_sell_bump=True,
            late_ongoing_sell_bump=True,
            hire_cap=None,
            land_cash_buffer=land_default,
            post_land_floor=post_default,
            skip_animal_care=False,
            field_priority="normal",
        )
    return PhaseProfile(
        sell_n_base=base,
        sell_n_build=build,
        sell_n_liquidate=liquidate,
        sell_n_endgame=endgame,
        sell_n_rescue=rescue,
        spike_sell_bump=False,
        late_ongoing_sell_bump=False,
        hire_cap=None,
        land_cash_buffer=land_default,
        post_land_floor=post_default,
        skip_animal_care=False,
        field_priority="normal",
    )


def classify_phase(
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    late_shop_sprint: bool,
    price_spike_any: bool,
    days_left: int,
) -> Phase:
    from brain.schedules import late_dump_day

    dump = late_dump_day(int(params["liquidate_day_min"]))
    if s["day"] >= dump:
        return "LIQUIDATE"
    if days_left <= int(params["endgame_days_left"]):
        return "ENDGAME"
    if late_shop_sprint:
        return "LATE_RAMP"
    if price_spike_any:
        return "SPIKE"
    return "ENGINE"


def resolve_market_route(
    phase: Phase,
    flags: TurnFlags,
    *,
    mode: Mode,
) -> MarketRoute:
    if mode == "LIQUIDATE":
        return "standard"
    if flags.late_shop_sprint:
        return "late_sprint"
    if flags.berry_prep and not flags.late_shop_sprint:
        return "berry_prep"
    return "standard"


def resolve_defer_animals(
    s: dict[str, Any],
    flags: TurnFlags,
    berry_gap: int,
    *,
    strategy: MapStrategy = "UNKNOWN",
    params: dict[str, int | float] | None = None,
) -> bool:
    return strategy_defer_animals(strategy, s, flags, berry_gap, params or {})


def compute_sell_n(
    plan: TurnPlan,
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    mode: Mode,
    base_prices: dict[str, int],
    px: Any,
    ongoing_crops: set[str],
) -> int:
    """Sell-slot budget from TurnPlan profile + liquidity signals."""
    prof = plan.profile
    if mode == "LIQUIDATE":
        sell_n = prof.sell_n_liquidate
    elif (
        (plan.flags.berry_ok and plan.berry_gap > 0)
        or plan.cash_gap > 0
        or plan.flags.need_land
    ):
        sell_n = prof.sell_n_build
    else:
        sell_n = prof.sell_n_base

    deficit_min = float(params["sell_n_cash_deficit_min"])
    if mode != "LIQUIDATE" and plan.cash_deficit >= deficit_min:
        sell_n = max(sell_n, int(params["sell_n_cash_deficit_bump"]))

    rescue = (
        mode != "LIQUIDATE"
        and s.get("day", 0) <= int(params["liquidity_rescue_day_max"])
        and s.get("empty", 0) >= 8
        and plan.cash_deficit >= 900
    )
    if rescue:
        sell_n = max(sell_n, prof.sell_n_rescue)

    if plan.phase == "ENDGAME":
        sell_n = max(sell_n, prof.sell_n_endgame)

    # Replay late-sell share ~36%; start dumping before LIQUIDATE.
    from brain.schedules import late_dump_day

    dump_day = late_dump_day(int(params.get("liquidate_day_min", 26)))
    if mode != "LIQUIDATE" and int(s.get("day", 0)) >= max(22, dump_day - 4):
        sell_n = max(sell_n, int(params.get("sell_n_pre_dump", 6)))

    if prof.spike_sell_bump and plan.phase == "SPIKE":
        berry_sink = int(s.get("berry_sink", 0) or 0)
        if not strategy_spike_sell_bump(
            plan.strategy, s, params, berry_sink=berry_sink
        ):
            return sell_n
        spikes = plan.flags.price_spike
        shed = s.get("shed") or {}
        spike_items = ("STRAWBERRY", "TOMATO", "MELON", "MILK", "WOOL")
        mult = float(params["spike_sell_base_mult"])
        held_spike = any(
            spikes.get(item)
            and shed.get(item, 0) > 0
            and px(s, item) >= int(base_prices[item]) * mult
            for item in spike_items
        )
        if held_spike:
            sell_n = max(sell_n, int(params["spike_sell_n_min"]))

    if prof.late_ongoing_sell_bump and plan.flags.late_ongoing:
        shed = s.get("shed") or {}
        if any(shed.get(c, 0) > 0 for c in ongoing_crops):
            sell_n = max(sell_n, int(params["sell_n_late_ongoing_bump"]))

    return sell_n


def build_regime_dict(
    plan: TurnPlan,
    *,
    endgame: bool,
) -> dict[str, Any]:
    f = plan.flags
    return {
        "phase": plan.phase,
        "demand_stack": f.demand_stack,
        "price_spike": f.price_spike,
        "late_ongoing": f.late_ongoing,
        "late_shop_sprint": f.late_shop_sprint,
        "berry_prep": f.berry_prep,
        "liquidity_stress": f.liquidity_stress,
        "endgame": endgame,
        "cash_deficit": plan.cash_deficit,
        "strategy": plan.strategy,
    }


def build_turn_plan(
    s: dict[str, Any],
    params: dict[str, int | float],
    *,
    crops: dict[str, int],
    berry_gap: int,
    flags: TurnFlags,
    cash_deficit: float,
    days_left: int,
    endgame: bool,
    strategy: MapStrategy = "UNKNOWN",
) -> TurnPlan:
    price_spike_any = any(flags.price_spike.values())
    phase = classify_phase(
        s,
        params,
        late_shop_sprint=flags.late_shop_sprint,
        price_spike_any=price_spike_any,
        days_left=days_left,
    )
    mode: Mode = "LIQUIDATE" if phase == "LIQUIDATE" else "ENGINE"
    profile = phase_profile(phase, params)
    market_route = resolve_market_route(phase, flags, mode=mode)
    defer = resolve_defer_animals(s, flags, berry_gap, strategy=strategy, params=params)

    plan = TurnPlan(
        phase=phase,
        mode=mode,
        profile=profile,
        crops=crops,
        berry_gap=berry_gap,
        cash_deficit=cash_deficit,
        flags=flags,
        market_route=market_route,
        defer_animals=defer,
        strategy=strategy,
    )
    plan.regime = build_regime_dict(plan, endgame=endgame)
    return plan
