"""Live-decode elite market schedules vs us on densify seeds.

Runs boatlee/hamburger/structured/frontier (+ us) vs starter on seeds
42/12/33/89 and prints day curves: land, hire, cows, empty, berry, sells,
and buy→place lag for cows (shed stall detector).

Usage:
  .venv/bin/python -m analysis.decode_elite_schedules
  .venv/bin/python -m analysis.decode_elite_schedules --seeds 42,12 --bots boatlee_v16,us
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from kaggle_environments import make

ROOT = Path(__file__).resolve().parents[1]
OPPONENTS_DIR = ROOT / "opponents"
OUT_DIR = ROOT / "analysis"
DEFAULT_PARAMS = str(ROOT / "tune" / "params.json")

DEFAULT_SEEDS = [42, 12, 33, 89]
DEFAULT_BOTS = [
    "boatlee_v16",
    "hamburger",
    "structured",
    "frontier_soil",
    "us",
]


@dataclass
class DaySnap:
    day: int
    cows: int
    sheep: int
    hands: int
    empty: int
    berry: int
    melon: int
    tomato: int
    wheat: int
    money: float
    quads: int
    sheds_cow: int
    hires_cum: int
    sell_units: int
    land: bool


@dataclass
class BotSeedTrace:
    bot: str
    seed: int
    score: int
    land_days: list[int] = field(default_factory=list)
    land_hours: list[tuple[int, int]] = field(default_factory=list)
    hire_by_day: dict[int, int] = field(default_factory=dict)
    sell_by_day: dict[int, int] = field(default_factory=dict)
    dump_day: int | None = None
    dump_units: int = 0
    cow_buy_events: list[tuple[int, int]] = field(default_factory=list)  # day, hour
    cow_place_lag_hours: list[int] = field(default_factory=list)
    days: list[DaySnap] = field(default_factory=list)
    shops_d16: list[str] = field(default_factory=list)


def _agent_path(bot: str) -> str:
    if bot == "us":
        return str(ROOT / "main.py")
    p = OPPONENTS_DIR / bot / "main.py"
    if not p.is_file():
        raise FileNotFoundError(p)
    return str(p)


def _animal_count(obs: dict[str, Any], kind: str) -> int:
    me = obs["farms"][obs["player"]]
    n = 0
    for row in me["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("animal") == kind:
                n += 1
    return n


def _crop_count(obs: dict[str, Any], crop: str) -> int:
    me = obs["farms"][obs["player"]]
    n = 0
    for row in me["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("crop") == crop:
                n += 1
    return n


def _empty_count(obs: dict[str, Any]) -> int:
    me = obs["farms"][obs["player"]]
    return sum(1 for row in me["tiles"] for t in row if t is None)


def _hands(obs: dict[str, Any]) -> int:
    me = obs["farms"][obs["player"]]
    return 1 + len(me.get("hands") or [])


def _quads(obs: dict[str, Any]) -> int:
    me = obs["farms"][obs["player"]]
    return len(me.get("unlocked_quadrants") or [])


def _shed_cow(obs: dict[str, Any]) -> int:
    priv = obs.get("private") or {}
    shed = priv.get("shed") or {}
    if isinstance(shed, dict):
        return int(shed.get("COW", 0) or 0)
    # Some envs put shed under inventories
    return 0


def run_trace(bot: str, seed: int, episode_steps: int = 720) -> BotSeedTrace:
    os.environ.setdefault("KAGGRICULTURE_PARAMS_PATH", DEFAULT_PARAMS)
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": episode_steps, "seed": seed},
        debug=False,
    )
    env.run([_agent_path(bot), "starter"])
    score = int(env.steps[-1][0]["reward"])

    hire_by_day: dict[int, int] = defaultdict(int)
    sell_by_day: dict[int, int] = defaultdict(int)
    land_days: list[int] = []
    land_hours: list[tuple[int, int]] = []
    cow_buys: list[tuple[int, int]] = []
    place_lags: list[int] = []
    pending_buy_step: int | None = None
    cows_before_buy = 0

    # Dawn snapshots
    days: list[DaySnap] = []
    hires_cum = 0
    sell_today = 0
    land_today = False
    last_day = -1

    shops_d16: list[str] = []

    for i in range(len(env.steps) - 1):
        obs = env.steps[i][0]["observation"]
        day = int(obs["day"])
        hour = int(obs["hour"])
        acts = (env.steps[i + 1][0].get("action") or {}).get("market") or []

        if day != last_day:
            if last_day >= 0 and days and days[-1].day == last_day:
                # patch sell/land into previous dawn snap at end of day — keep dawn values
                pass
            last_day = day
            sell_today = 0
            land_today = False

        for a in acts:
            if not a:
                continue
            op = a[0]
            if op == "HIRE":
                hire_by_day[day] += 1
                hires_cum += 1
            elif op == "BUY_LAND":
                land_days.append(day)
                land_hours.append((day, hour))
                land_today = True
            elif op == "BUY_ANIMAL" and len(a) >= 2 and a[1] == "COW":
                cow_buys.append((day, hour))
                pending_buy_step = i
                cows_before_buy = _animal_count(obs, "COW") + _shed_cow(obs)
            elif op == "SELL" and len(a) >= 3:
                n = int(a[2])
                sell_by_day[day] += n
                sell_today += n

        # Place lag: board+shed cows rose after buy
        if pending_buy_step is not None and i > pending_buy_step:
            cows_now = _animal_count(obs, "COW")
            # placed when board cows > pre-buy board (ignore shed accounting)
            # Simpler: shed cleared and board increased
            if _animal_count(obs, "COW") > cows_before_buy or (
                _shed_cow(obs) == 0 and _animal_count(obs, "COW") >= cows_before_buy
            ):
                # if board cows increased vs step-of-buy board
                buy_obs = env.steps[pending_buy_step][0]["observation"]
                board_at_buy = _animal_count(buy_obs, "COW")
                if _animal_count(obs, "COW") > board_at_buy:
                    place_lags.append(i - pending_buy_step)
                    pending_buy_step = None

        if hour == 0:
            days.append(
                DaySnap(
                    day=day,
                    cows=_animal_count(obs, "COW"),
                    sheep=_animal_count(obs, "SHEEP"),
                    hands=_hands(obs),
                    empty=_empty_count(obs),
                    berry=_crop_count(obs, "STRAWBERRY"),
                    melon=_crop_count(obs, "MELON"),
                    tomato=_crop_count(obs, "TOMATO"),
                    wheat=_crop_count(obs, "WHEAT"),
                    money=float(obs["farms"][obs["player"]].get("money") or 0),
                    quads=_quads(obs),
                    sheds_cow=_shed_cow(obs),
                    hires_cum=hires_cum,
                    sell_units=0,
                    land=False,
                )
            )

        if day == 16 and hour == 0:
            shops_d16 = list(obs.get("town", {}).get("unlocked_shops") or [])

    # Attach per-day sell/land onto dawn snaps
    day_land = set(land_days)
    for snap in days:
        snap.sell_units = int(sell_by_day.get(snap.day, 0))
        snap.land = snap.day in day_land

    dump_day = None
    dump_units = 0
    if sell_by_day:
        dump_day, dump_units = max(sell_by_day.items(), key=lambda kv: kv[1])

    return BotSeedTrace(
        bot=bot,
        seed=seed,
        score=score,
        land_days=land_days,
        land_hours=land_hours,
        hire_by_day=dict(hire_by_day),
        sell_by_day=dict(sell_by_day),
        dump_day=dump_day,
        dump_units=dump_units,
        cow_buy_events=cow_buys,
        cow_place_lag_hours=place_lags,
        days=days,
        shops_d16=shops_d16,
    )


def _fmt_curve(traces: list[BotSeedTrace], day: int, attr: str) -> str:
    parts = []
    for t in traces:
        snap = next((d for d in t.days if d.day == day), None)
        v = getattr(snap, attr) if snap else "-"
        parts.append(f"{t.bot[:6]}={v}")
    return " ".join(parts)


def print_report(traces: list[BotSeedTrace]) -> None:
    by_seed: dict[int, list[BotSeedTrace]] = defaultdict(list)
    for t in traces:
        by_seed[t.seed].append(t)

    for seed, ts in sorted(by_seed.items()):
        print(f"\n======== SEED {seed} ========")
        for t in ts:
            lag = t.cow_place_lag_hours
            lag_s = (
                f"med={sorted(lag)[len(lag)//2]}h n={len(lag)}"
                if lag
                else "n/a"
            )
            print(
                f"  {t.bot:14s} score={t.score:6d} land={t.land_days} "
                f"dump=d{t.dump_day}({t.dump_units}) place_lag={lag_s} "
                f"cow_buys={len(t.cow_buy_events)} shops@16={t.shops_d16}"
            )
        print("  --- dawn curves (cows / hands / empty / berry) ---")
        for day in range(6, 13):
            print(
                f"  d{day}: cows[{_fmt_curve(ts, day, 'cows')}] "
                f"hands[{_fmt_curve(ts, day, 'hands')}] "
                f"empty[{_fmt_curve(ts, day, 'empty')}] "
                f"berry[{_fmt_curve(ts, day, 'berry')}]"
            )
        print("  --- hire by day ---")
        for t in ts:
            curve = " ".join(
                f"d{d}:{t.hire_by_day.get(d, 0)}" for d in range(0, 14)
            )
            print(f"  {t.bot:14s} {curve}")
        print("  --- sell units by day (6–12, 24–29) ---")
        for t in ts:
            early = " ".join(
                f"d{d}:{t.sell_by_day.get(d, 0)}" for d in range(6, 13)
            )
            late = " ".join(
                f"d{d}:{t.sell_by_day.get(d, 0)}" for d in (24, 25, 26, 27, 28, 29)
            )
            print(f"  {t.bot:14s} early[{early}] late[{late}]")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=str, default=",".join(map(str, DEFAULT_SEEDS)))
    p.add_argument("--bots", type=str, default=",".join(DEFAULT_BOTS))
    p.add_argument("--episodeSteps", type=int, default=720)
    p.add_argument(
        "--out",
        type=str,
        default=str(OUT_DIR / "elite_schedule_decode.json"),
    )
    args = p.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    bots = [x.strip() for x in args.bots.split(",") if x.strip()]

    traces: list[BotSeedTrace] = []
    for seed in seeds:
        for bot in bots:
            print(f"running {bot} seed={seed}...", flush=True)
            traces.append(run_trace(bot, seed, episode_steps=args.episodeSteps))

    print_report(traces)

    payload = []
    for t in traces:
        row = asdict(t)
        payload.append(row)
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
