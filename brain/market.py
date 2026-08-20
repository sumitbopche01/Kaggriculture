"""Inventory–price surface and sell/hold EV.

The env prices goods from market inventory (I0=10_000). Shops drain
inventory and lift prices; dumping stock pushes inventory up. Selling is
an economy decision — compare live px to the surface and to a short
forward fair value — not only spike/demand flags.
"""

from __future__ import annotations

import math
from typing import Any

MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0

# Env-aligned inventory→price curves (same tables as the live sim).
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
    "FERTILIZER": {
        "base": 100,
        "I0": MARKET_I0,
        "T": 200,
        "below_func": "sqrt",
        "below_target": 0.30,
        "above_func": "log",
        "above_target": 0.40,
    },
}


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
    """Fair price on the inventory surface (env curve)."""
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


def market_inventory(s: dict[str, Any], item: str) -> int:
    inv = (s.get("inventory") or {}).get(item, MARKET_I0)
    return int(inv if inv is not None else MARKET_I0)


def shop_drain_per_hour(item: str, demand: dict[str, int] | None) -> float:
    """Approx units drained from market inventory per hour by town shops."""
    d = int((demand or {}).get(item, 0) or 0)
    if d <= 0:
        return 0.0
    # Empirically ~1–5 units/hour once sinks are open; scale lightly by demand.
    return 0.75 * float(d)


def forward_inventory(
    item: str,
    inventory: int,
    demand: dict[str, int] | None,
    hours: float,
) -> int:
    drain = shop_drain_per_hour(item, demand) * max(0.0, float(hours))
    return max(0, int(round(float(inventory) - drain)))


def live_premium(live_px: float, item: str, inventory: int) -> float:
    """How rich is the live quote vs the inventory surface. 0 = fair."""
    fair = float(market_price(item, inventory))
    if fair <= 0:
        return 0.0
    return float(live_px) / fair - 1.0


def hold_edge(
    *,
    item: str,
    live_px: float,
    inventory: int,
    demand: dict[str, int] | None,
    days_left: int,
    hold_hours: float = 8.0,
    price_ma: float | None = None,
) -> float:
    """Positive ⇒ waiting looks better than selling now (fraction of live px)."""
    if int(days_left) <= 2:
        return -1.0  # force liquidate late
    fwd_inv = forward_inventory(item, inventory, demand, hold_hours)
    fwd_fair = float(market_price(item, fwd_inv))
    # Blend surface forward with MA when available (observed momentum).
    if price_ma is not None and float(price_ma) > 0:
        fwd = 0.65 * fwd_fair + 0.35 * float(price_ma)
    else:
        fwd = fwd_fair
    if live_px <= 0:
        return 0.0
    return float(fwd) / float(live_px) - 1.0


def sell_edge(
    *,
    item: str,
    live_px: float,
    inventory: int,
    demand: dict[str, int] | None,
    days_left: int,
    price_ma: float | None = None,
    spiked: bool = False,
    liquidate: bool = False,
) -> float:
    """Net sell attractiveness. >0 sell; <0 prefer hold.

    Combines rich-vs-surface premium with (negated) hold option.
    """
    if liquidate or int(days_left) <= 2:
        return 1.0
    prem = live_premium(live_px, item, inventory)
    hold = hold_edge(
        item=item,
        live_px=live_px,
        inventory=inventory,
        demand=demand,
        days_left=days_left,
        price_ma=price_ma,
    )
    # Spike is a strong sell cue but not the only one.
    spike_boost = 0.35 if spiked else 0.0
    # Demand sinks raise the chance shops keep draining — lowers hold value.
    sink = int((demand or {}).get(item, 0) or 0)
    sink_boost = 0.04 * min(3, sink)
    return prem - 0.85 * hold + spike_boost + sink_boost


def sale_score(
    *,
    item: str,
    n: int,
    live_px: float,
    inventory: int,
    demand: dict[str, int] | None,
    days_left: int,
    price_ma: float | None = None,
    spiked: bool = False,
    liquidate: bool = False,
    momentum: float = 1.0,
) -> int:
    """Rank score for a candidate SELL lot (higher = sell sooner / prefer)."""
    if n <= 0 or live_px <= 0:
        return 0
    edge = sell_edge(
        item=item,
        live_px=live_px,
        inventory=inventory,
        demand=demand,
        days_left=days_left,
        price_ma=price_ma,
        spiked=spiked,
        liquidate=liquidate,
    )
    # Soft hold: deep negative edge → skip unless late / liquidate.
    if edge < -0.08 and not liquidate and int(days_left) >= 6:
        return 0
    # Scale revenue by how good the trade is vs the surface.
    scale = 0.55 + 0.90 * max(-0.2, min(1.0, edge + 0.15))
    raw = float(n) * float(live_px) * scale * max(0.7, min(1.3, float(momentum)))
    return max(0, int(raw))


def keep_qty(
    *,
    item: str,
    stock: int,
    base_keep: int,
    live_px: float,
    inventory: int,
    demand: dict[str, int] | None,
    days_left: int,
    price_ma: float | None = None,
    spiked: bool = False,
    liquidate: bool = False,
) -> int:
    """Adaptive shed floor: hold more when the surface says wait."""
    if liquidate or int(days_left) <= 2 or stock <= 0:
        return 0
    edge = sell_edge(
        item=item,
        live_px=live_px,
        inventory=inventory,
        demand=demand,
        days_left=days_left,
        price_ma=price_ma,
        spiked=spiked,
        liquidate=False,
    )
    keep = int(base_keep)
    if edge < -0.05:
        # Waiting looks good — thicken the floor.
        keep = int(round(keep * (1.25 + min(0.75, -edge))))
    elif edge > 0.12 or spiked:
        # Rich quote / spike — thin the floor.
        keep = int(round(keep * 0.45))
    return max(0, min(int(stock), keep))
