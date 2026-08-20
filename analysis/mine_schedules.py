"""Mine hire / land / sell / herd schedules from local Kaggle replays.

Reads `replays/episode-*-replay.json`, keeps the winner's market timeline,
classifies shop archetype, and writes:
  analysis/schedules_raw.jsonl   — one row per episode
  analysis/schedules_by_archetype.json — median priors
  analysis/schedules_report.md   — human summary

Usage:
  .venv/bin/python -m analysis.mine_schedules
  .venv/bin/python -m analysis.mine_schedules --diff-us  # also run our agent on overlapping seeds
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPLAY_DIR = ROOT / "replays"
OUT_DIR = ROOT / "analysis"

BERRY_SHOPS = frozenset(
    {"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"}
)
MILK_SHOPS = frozenset({"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "PET_CAFE"})
# PET_CAFE is carrot; keep milk via pizza/ice/smoothie only for milk-led.
MILK_CORE = frozenset({"PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP"})


@dataclass
class EpisodeSchedule:
    episode_id: int
    seed: int | None
    winner: int
    winner_name: str
    loser_name: str
    reward_w: float
    reward_l: float
    archetype: str
    shops: list[str]
    land_days: list[int]
    land_hours: list[tuple[int, int]]
    n_quads_final: int
    hire_by_day: dict[int, int]
    hire_total: int
    peak_hires_day: int
    peak_hands: int
    first_full_crew_day: int | None  # first day with >=10 hires
    sell_units_by_day: dict[int, int]
    sell_value_proxy_by_day: dict[int, float]  # sum n*live_px when available
    dump_day: int | None  # day with max sell units
    dump_units: int
    late_sell_share: float  # units on days 24–29 / total
    cows_peak: int
    sheep_peak: int
    geese_peak: int
    tomato_peak: int
    berry_peak: int
    wheat_peak: int
    melon_seeds_day0: int
    opening_market: list[list[Any]] = field(default_factory=list)


def _median(xs: list[float | int]) -> float | None:
    vals = [float(x) for x in xs if x is not None]
    if not vals:
        return None
    return float(statistics.median(vals))


def _classify(shops: list[str]) -> str:
    berry = sum(1 for s in shops if s in BERRY_SHOPS)
    milk = sum(1 for s in shops if s in MILK_CORE)
    pizza = sum(1 for s in shops if s == "PIZZA_SHOP")
    if pizza >= 2 and berry == 0:
        return "PIZZA"
    if milk >= 1 and berry == 0:
        return "MILK_LED"
    if berry >= 2:
        return "BERRY"
    if berry >= 1 and milk >= 1:
        return "MIXED"
    if berry >= 1:
        return "BERRY"
    return "OTHER"


def _count_animals(tiles: list) -> tuple[int, int, int]:
    cows = sheep = geese = 0
    for row in tiles:
        for t in row:
            if not isinstance(t, dict):
                continue
            a = t.get("animal")
            if a == "COW":
                cows += 1
            elif a == "SHEEP":
                sheep += 1
            elif a == "GOOSE":
                geese += 1
    return cows, sheep, geese


def _count_crops(tiles: list) -> dict[str, int]:
    c: Counter[str] = Counter()
    for row in tiles:
        for t in row:
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                crop = t.get("crop")
                if crop:
                    c[crop] += 1
    return dict(c)


def mine_replay(path: Path) -> EpisodeSchedule | None:
    data = json.loads(path.read_text())
    rewards = data.get("rewards") or [0, 0]
    if len(rewards) < 2:
        return None
    winner = 0 if float(rewards[0]) >= float(rewards[1]) else 1
    loser = 1 - winner
    info = data.get("info") or {}
    agents = info.get("Agents") or [{}, {}]
    seed = info.get("seed")
    try:
        episode_id = int(info.get("EpisodeId") or path.stem.split("-")[1])
    except Exception:
        episode_id = -1

    steps = data.get("steps") or []
    hire_by_day: Counter[int] = Counter()
    sell_by_day: Counter[int] = Counter()
    sell_value_by_day: dict[int, float] = defaultdict(float)
    land_hours: list[tuple[int, int]] = []
    peak_hands = 0
    cows_peak = sheep_peak = geese_peak = 0
    tomato_peak = berry_peak = wheat_peak = 0
    first_full_crew_day: int | None = None
    opening_market: list[list[Any]] = []
    shops_final: list[str] = []
    n_quads_final = 1
    melon_seeds_day0 = 0

    for si, step in enumerate(steps):
        if not isinstance(step, list) or len(step) < 2:
            continue
        pl = step[winner]
        obs = pl.get("observation") or {}
        day = int(obs.get("day") or 0)
        hour = int(obs.get("hour") or 0)
        act = pl.get("action") or {}
        market = (act.get("market") if isinstance(act, dict) else None) or []
        prices = ((obs.get("market") or {}).get("prices")) or {}

        if si == 0 or (day == 0 and hour <= 1 and not opening_market):
            opening_market = [list(m) for m in market if m]

        for m in market:
            if not m:
                continue
            op = m[0]
            if op == "HIRE":
                hire_by_day[day] += 1
            elif op == "BUY_LAND":
                land_hours.append((day, hour))
            elif op == "SELL" and len(m) >= 3:
                n = int(m[2])
                item = m[1]
                sell_by_day[day] += n
                sell_value_by_day[day] += n * float(prices.get(item, 0) or 0)
            elif op == "BUY_SEED" and day == 0 and len(m) >= 3 and m[1] == "MELON":
                melon_seeds_day0 += int(m[2])

        farms = obs.get("farms") or []
        if winner >= len(farms):
            continue
        farm = farms[winner]
        hands = len(farm.get("hands") or [])
        peak_hands = max(peak_hands, hands)
        if first_full_crew_day is None and hire_by_day[day] >= 10:
            first_full_crew_day = day

        cows, sheep, geese = _count_animals(farm.get("tiles") or [])
        cows_peak = max(cows_peak, cows)
        sheep_peak = max(sheep_peak, sheep)
        geese_peak = max(geese_peak, geese)
        crops = _count_crops(farm.get("tiles") or [])
        tomato_peak = max(tomato_peak, int(crops.get("TOMATO", 0)))
        berry_peak = max(berry_peak, int(crops.get("STRAWBERRY", 0)))
        wheat_peak = max(wheat_peak, int(crops.get("WHEAT", 0)))

        shops_final = list((obs.get("town") or {}).get("unlocked_shops") or shops_final)
        n_quads_final = max(n_quads_final, len(farm.get("unlocked_quadrants") or []))

    land_days = sorted({d for d, _ in land_hours})
    dump_day = None
    dump_units = 0
    if sell_by_day:
        dump_day, dump_units = max(sell_by_day.items(), key=lambda kv: kv[1])
    total_sell = sum(sell_by_day.values()) or 1
    late_sell = sum(sell_by_day.get(d, 0) for d in range(24, 30))
    peak_hires_day = max(hire_by_day, key=lambda d: hire_by_day[d]) if hire_by_day else 0

    wname = (agents[winner] or {}).get("Name") or f"p{winner}"
    lname = (agents[loser] or {}).get("Name") or f"p{loser}"

    return EpisodeSchedule(
        episode_id=episode_id,
        seed=int(seed) if seed is not None else None,
        winner=winner,
        winner_name=str(wname),
        loser_name=str(lname),
        reward_w=float(rewards[winner]),
        reward_l=float(rewards[loser]),
        archetype=_classify(shops_final),
        shops=shops_final,
        land_days=land_days,
        land_hours=land_hours,
        n_quads_final=n_quads_final,
        hire_by_day={int(k): int(v) for k, v in sorted(hire_by_day.items())},
        hire_total=int(sum(hire_by_day.values())),
        peak_hires_day=int(peak_hires_day),
        peak_hands=int(peak_hands),
        first_full_crew_day=first_full_crew_day,
        sell_units_by_day={int(k): int(v) for k, v in sorted(sell_by_day.items())},
        sell_value_proxy_by_day={
            int(k): float(v) for k, v in sorted(sell_value_by_day.items())
        },
        dump_day=dump_day,
        dump_units=int(dump_units),
        late_sell_share=float(late_sell) / float(total_sell),
        cows_peak=cows_peak,
        sheep_peak=sheep_peak,
        geese_peak=geese_peak,
        tomato_peak=tomato_peak,
        berry_peak=berry_peak,
        wheat_peak=wheat_peak,
        melon_seeds_day0=melon_seeds_day0,
        opening_market=opening_market,
    )


def aggregate(rows: list[EpisodeSchedule]) -> dict[str, Any]:
    by: dict[str, list[EpisodeSchedule]] = defaultdict(list)
    for r in rows:
        by[r.archetype].append(r)
    by["ALL"] = list(rows)

    out: dict[str, Any] = {}
    for arch, group in sorted(by.items()):
        if not group:
            continue
        land1 = [r.land_days[0] for r in group if r.land_days]
        land2 = [r.land_days[1] for r in group if len(r.land_days) >= 2]
        # Hire curve: median hires for each day 0..20
        hire_curve: dict[str, float] = {}
        for d in range(0, 21):
            vals = [float(r.hire_by_day.get(d, 0)) for r in group]
            hire_curve[str(d)] = float(statistics.median(vals))
        out[arch] = {
            "n": len(group),
            "median_reward": _median([r.reward_w for r in group]),
            "median_land1_day": _median(land1),
            "median_land2_day": _median(land2),
            "share_2plus_quads": sum(1 for r in group if r.n_quads_final >= 2) / len(group),
            "share_3plus_quads": sum(1 for r in group if r.n_quads_final >= 3) / len(group),
            "median_peak_hands": _median([r.peak_hands for r in group]),
            "median_first_full_crew_day": _median(
                [r.first_full_crew_day for r in group if r.first_full_crew_day is not None]
            ),
            "median_dump_day": _median([r.dump_day for r in group if r.dump_day is not None]),
            "median_late_sell_share": _median([r.late_sell_share for r in group]),
            "median_cows_peak": _median([r.cows_peak for r in group]),
            "median_berry_peak": _median([r.berry_peak for r in group]),
            "median_tomato_peak": _median([r.tomato_peak for r in group]),
            "median_wheat_peak": _median([r.wheat_peak for r in group]),
            "share_melon_day0": sum(1 for r in group if r.melon_seeds_day0 > 0) / len(group),
            "hire_curve_median": hire_curve,
            "top_winners": sorted(
                (
                    {
                        "episode": r.episode_id,
                        "seed": r.seed,
                        "name": r.winner_name,
                        "reward": r.reward_w,
                        "land_days": r.land_days,
                        "cows": r.cows_peak,
                        "berry": r.berry_peak,
                        "tomato": r.tomato_peak,
                        "dump_day": r.dump_day,
                    }
                    for r in group
                ),
                key=lambda x: -float(x["reward"]),
            )[:5],
        }
    return out


def render_report(rows: list[EpisodeSchedule], agg: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Replay schedule priors\n")
    lines.append(f"Episodes mined: **{len(rows)}** from `replays/`.\n")
    lines.append("## By archetype\n")
    for arch, block in agg.items():
        if arch == "ALL":
            continue
        lines.append(f"### {arch} (n={block['n']}, median $={block['median_reward']:.0f})")
        lines.append(
            f"- Land1 day median **{block['median_land1_day']}**; "
            f"Land2 **{block['median_land2_day']}**; "
            f"3+ quads share **{block['share_3plus_quads']:.0%}**"
        )
        lines.append(
            f"- Full crew (≥10 hires) by day **{block['median_first_full_crew_day']}**; "
            f"peak hands **{block['median_peak_hands']}**"
        )
        lines.append(
            f"- Dump day median **{block['median_dump_day']}**; "
            f"late(24–29) sell share **{block['median_late_sell_share']:.0%}**"
        )
        lines.append(
            f"- Peaks — cows **{block['median_cows_peak']}**, "
            f"berry **{block['median_berry_peak']}**, "
            f"tomato **{block['median_tomato_peak']}**, "
            f"wheat **{block['median_wheat_peak']}**"
        )
        lines.append(f"- Melon seeds on day0: **{block['share_melon_day0']:.0%}** of winners")
        hc = block["hire_curve_median"]
        sample = ", ".join(f"d{d}:{hc[str(d)]:.0f}" for d in (0, 3, 6, 8, 10, 12, 15, 18))
        lines.append(f"- Hire curve (median): {sample}")
        lines.append("")
    lines.append("## Policy takeaways\n")
    berry = agg.get("BERRY") or {}
    pizza = agg.get("PIZZA") or agg.get("MILK_LED") or {}
    if berry:
        lines.append(
            f"- **Berry maps**: land1≈{berry.get('median_land1_day')}, "
            f"land2≈{berry.get('median_land2_day')}, "
            f"crew full≈d{berry.get('median_first_full_crew_day')}, "
            f"berry peak≈{berry.get('median_berry_peak')}, "
            f"dump≈d{berry.get('median_dump_day')}."
        )
    if pizza:
        lines.append(
            f"- **Pizza/milk maps**: land1≈{pizza.get('median_land1_day')}, "
            f"land2≈{pizza.get('median_land2_day')}, "
            f"cows≈{pizza.get('median_cows_peak')}, "
            f"tomato≈{pizza.get('median_tomato_peak')}, "
            f"3+quads only {pizza.get('share_3plus_quads', 0):.0%}."
        )
    lines.append(
        "- Prefer **schedule priors by archetype** over starter-mean tuning; "
        "hire ramp and dump window are the transferable stolen schedules."
    )
    return "\n".join(lines) + "\n"


def diff_our_agent(rows: list[EpisodeSchedule], limit: int = 6) -> str:
    """Compare our local agent schedules on overlapping seeds (expensive)."""
    from tune.evaluate import run_vs_starter_env

    lines = ["## Diff vs our agent (overlapping seeds)\n"]
    seeds = [r for r in rows if r.seed is not None]
    seeds = sorted(seeds, key=lambda r: -r.reward_w)[:limit]
    for r in seeds:
        assert r.seed is not None
        env, us, _ = run_vs_starter_env(int(r.seed))
        # Mine our schedule from env steps (player 0)
        hire: Counter[int] = Counter()
        land: list[int] = []
        cows_peak = berry_peak = tomato_peak = 0
        for step in env.steps:
            obs = step[0]["observation"]
            day = int(obs["day"])
            act = step[0].get("action") or {}
            for m in act.get("market") or []:
                if not m:
                    continue
                if m[0] == "HIRE":
                    hire[day] += 1
                elif m[0] == "BUY_LAND":
                    land.append(day)
            f = obs["farms"][0]
            c, _, _ = _count_animals(f["tiles"])
            cows_peak = max(cows_peak, c)
            crops = _count_crops(f["tiles"])
            berry_peak = max(berry_peak, crops.get("STRAWBERRY", 0))
            tomato_peak = max(tomato_peak, crops.get("TOMATO", 0))
        lines.append(
            f"- seed **{r.seed}** ({r.archetype}, winner ${r.reward_w:.0f} / us ${us}): "
            f"land {r.land_days} vs us {sorted(set(land))}; "
            f"cows {r.cows_peak} vs {cows_peak}; "
            f"berry {r.berry_peak} vs {berry_peak}; "
            f"tomato {r.tomato_peak} vs {tomato_peak}; "
            f"hire d8 {r.hire_by_day.get(8, 0)} vs {hire.get(8, 0)}"
        )
    return "\n".join(lines) + "\n"


def _collect_paths(dirs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for d in dirs:
        base = Path(d)
        if not base.is_absolute():
            base = ROOT / base
        paths.extend(sorted(base.glob("episode-*-replay.json")))
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        if p.name in seen:
            continue
        seen.add(p.name)
        out.append(p)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dirs",
        nargs="+",
        default=["replays"],
        help="Replay folders relative to repo root (e.g. replays/top5 replays/v2)",
    )
    p.add_argument(
        "--exclude-winner-substr",
        nargs="*",
        default=[],
        help="Drop episodes whose winner name contains any of these (case-insensitive)",
    )
    p.add_argument("--min-reward", type=float, default=0.0)
    p.add_argument(
        "--tag",
        type=str,
        default="",
        help="Suffix for output files, e.g. top5 → schedules_raw_top5.jsonl",
    )
    p.add_argument("--diff-us", action="store_true", help="Compare to local agent on top seeds")
    p.add_argument("--diff-limit", type=int, default=8)
    args = p.parse_args()

    paths = _collect_paths(list(args.dirs))
    if not paths:
        raise SystemExit(f"No replays in {args.dirs}")

    excl = [s.lower() for s in args.exclude_winner_substr if s]
    rows: list[EpisodeSchedule] = []
    for path in paths:
        try:
            sched = mine_replay(path)
        except Exception as exc:  # noqa: BLE001 — keep mining others
            print(f"skip {path.name}: {exc}")
            continue
        if sched is None:
            continue
        if float(sched.reward_w) < float(args.min_reward):
            print(f"skip {sched.episode_id}: reward {sched.reward_w:.0f} < {args.min_reward}")
            continue
        if excl and any(x in (sched.winner_name or "").lower() for x in excl):
            print(f"skip {sched.episode_id}: excluded winner {sched.winner_name}")
            continue
        rows.append(sched)
        print(
            f"{sched.episode_id} seed={sched.seed} {sched.archetype} "
            f"${sched.reward_w:.0f} [{sched.winner_name}] land={sched.land_days} "
            f"cows={sched.cows_peak} berry={sched.berry_peak} mel0={sched.melon_seeds_day0} "
            f"dump=d{sched.dump_day}"
        )

    if not rows:
        raise SystemExit("No episodes left after filters")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""
    raw_path = OUT_DIR / f"schedules_raw{suffix}.jsonl"
    agg_path = OUT_DIR / f"schedules_by_archetype{suffix}.json"
    report_path = OUT_DIR / f"schedules_report{suffix}.md"
    with raw_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(asdict(r)) + "\n")

    agg = aggregate(rows)
    agg_path.write_text(json.dumps(agg, indent=2))
    report = f"# Corpus: {', '.join(args.dirs)} (n={len(rows)})\n\n" + render_report(rows, agg)
    if args.diff_us:
        report += "\n" + diff_our_agent(rows, limit=args.diff_limit)
    report_path.write_text(report)
    print(f"\nWrote {raw_path}")
    print(f"Wrote {agg_path}")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
