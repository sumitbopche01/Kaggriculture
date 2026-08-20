"""Extract per-step (hourly) market + shop timeline for seed analysis."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from kaggle_environments import make

ROOT = Path(__file__).resolve().parents[1]
AGENT = str(ROOT / "main.py")
DEFAULT_PARAMS_PATH = str(ROOT / "tune" / "params.json")

PRODUCTS = [
    "WHEAT",
    "CARROT",
    "TOMATO",
    "STRAWBERRY",
    "MELON",
    "EGG",
    "MILK",
    "WOOL",
    "FERTILIZER",
]

BERRY_SHOPS = {"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"}


def market_actions_at(env, step_i: int) -> list[list]:
    if step_i + 1 >= len(env.steps):
        return []
    return (env.steps[step_i + 1][0].get("action") or {}).get("market") or []


def actions_summary(actions: list[list]) -> str:
    parts: list[str] = []
    for a in actions:
        if not a:
            continue
        if len(a) >= 3:
            parts.append(f"{a[0]}:{a[1]}x{a[2]}")
        else:
            parts.append(str(a[0]))
    return "|".join(parts)


def run_seed(seed: int, episode_steps: int = 720) -> tuple[list[dict], list[dict]]:
    os.environ.setdefault("KAGGRICULTURE_PARAMS_PATH", DEFAULT_PARAMS_PATH)
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": episode_steps, "seed": seed},
        debug=False,
    )
    env.run([AGENT, "starter"])

    hourly_rows: list[dict] = []
    action_rows: list[dict] = []
    prev_prices: dict[str, int] = {}

    for step_i in range(len(env.steps)):
        obs = env.steps[step_i][0]["observation"]
        me = obs["farms"][0]
        market = obs.get("market") or {}
        prices = dict(market.get("prices") or {})
        inventory = dict(market.get("inventory") or {})
        shops = list(obs.get("town", {}).get("unlocked_shops") or [])
        day = int(obs["day"])
        hour = int(obs["hour"])

        actions = market_actions_at(env, step_i)
        action_str = actions_summary(actions)

        row: dict[str, str | int | float] = {
            "seed": seed,
            "step": step_i,
            "day": day,
            "hour": hour,
            "money": int(me.get("money", 0)),
            "quads": len(me.get("unlocked_quadrants", [])),
            "empty_tiles": sum(1 for row_t in me["tiles"] for t in row_t if t is None),
            "shops": "|".join(shops),
            "berry_shop_open": int(any(s in BERRY_SHOPS for s in shops)),
            "shop_count": len(shops),
            "market_actions": action_str,
            "market_action_count": len([a for a in actions if a]),
        }

        for p in PRODUCTS:
            px = int(prices.get(p, 0))
            inv = int(inventory.get(p, 0))
            prev = prev_prices.get(p)
            delta = px - prev if prev is not None else 0
            row[f"px_{p}"] = px
            row[f"delta_{p}"] = delta
            row[f"inv_{p}"] = inv
            prev_prices[p] = px

        hourly_rows.append(row)

        for idx, a in enumerate(actions):
            if not a:
                continue
            kind = a[0]
            item = a[1] if len(a) > 1 else ""
            qty = int(a[2]) if len(a) > 2 else 0
            px_at_action = int(prices.get(item, 0)) if item in prices else 0
            action_rows.append(
                {
                    "seed": seed,
                    "step": step_i,
                    "day": day,
                    "hour": hour,
                    "action_index": idx,
                    "action": kind,
                    "item": item,
                    "qty": qty,
                    "px_item": px_at_action,
                    "money_before": int(me.get("money", 0)),
                }
            )

    return hourly_rows, action_rows


def main() -> None:
    seeds = [21, 2063069147, 256, 1024]
    out_dir = ROOT / "analysis"
    out_dir.mkdir(exist_ok=True)

    all_hourly: list[dict] = []
    all_actions: list[dict] = []

    for seed in seeds:
        hourly, actions = run_seed(seed)
        all_hourly.extend(hourly)
        all_actions.extend(actions)
        print(f"seed {seed}: {len(hourly)} steps, {len(actions)} market actions")

    hourly_path = out_dir / "seed_hourly_market.csv"
    actions_path = out_dir / "seed_market_actions.csv"

    if all_hourly:
        with hourly_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_hourly[0].keys()))
            w.writeheader()
            w.writerows(all_hourly)

    if all_actions:
        with actions_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_actions[0].keys()))
            w.writeheader()
            w.writerows(all_actions)

    print("wrote", hourly_path)
    print("wrote", actions_path)


if __name__ == "__main__":
    main()
