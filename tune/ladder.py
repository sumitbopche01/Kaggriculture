"""Ladder proxy: win rate + margin vs strong opponents (not just mean vs starter).

Ladder cares about beating diverse bots. Local mean$ vs starter can invert
true strength. This harness runs our agent against frozen/local packages and
reports WR, mean margin, and mean scores.

Usage:
  .venv/bin/python -m tune.ladder
  .venv/bin/python -m tune.ladder --opponents starter,frozen_73k6 --seedSet ladder20
  .venv/bin/python -m tune.ladder --opponents opponents/frozen_73k6/main.py --both-seats

Drop external submissions under opponents/<name>/ with main.py (+ brain/).
"""

from __future__ import annotations

import argparse
import os
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from kaggle_environments import make

from tune.evaluate import MEAN_SEEDS_15, TUNE_SEEDS_30, TUNE_SEEDS_60

ROOT = Path(__file__).resolve().parents[1]
OUR_AGENT = str(ROOT / "main.py")
OPPONENTS_DIR = ROOT / "opponents"
FROZEN_73K6_COMMIT = "5f379de"
FROZEN_73K6_DIR = OPPONENTS_DIR / "frozen_73k6"

# Elite overlap + soft floor + diversity. Fixed slate so WR is comparable run-to-run.
LADDER_SEEDS_20 = [
    42,
    13,
    33,
    99,
    777,
    12,
    21,
    123,
    2024,
    49090797,
    1584566076,
    25138847,
    1012421698,
    1941500822,
    456398262,
    1571069459,
    2119622091,
    1295704409,
    1184506744,
    269540093,
]


@dataclass(frozen=True)
class MatchResult:
    seed: int
    opponent: str
    seat: int  # 0 = we are player 0
    us: int
    them: int

    @property
    def win(self) -> bool:
        return self.us > self.them

    @property
    def draw(self) -> bool:
        return self.us == self.them

    @property
    def margin(self) -> int:
        return self.us - self.them


def ensure_frozen_73k6() -> Path:
    """Materialize the ~73.6k submission snapshot from git if missing."""
    main_py = FROZEN_73K6_DIR / "main.py"
    if main_py.is_file():
        return FROZEN_73K6_DIR
    import subprocess

    FROZEN_73K6_DIR.mkdir(parents=True, exist_ok=True)
    paths = [
        "main.py",
        "submission.py",
        "tune/params.json",
        "analysis/schedules_by_archetype.json",
        "brain/__init__.py",
        "brain/board.py",
        "brain/dynamics.py",
        "brain/lookahead.py",
        "brain/map.py",
        "brain/market.py",
        "brain/plan.py",
        "brain/playbook.py",
        "brain/schedules.py",
        "brain/turn_budget.py",
    ]
    proc = subprocess.run(
        ["git", "archive", FROZEN_73K6_COMMIT, *paths],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Cannot build {FROZEN_73K6_DIR} from {FROZEN_73K6_COMMIT}: "
            f"{proc.stderr.decode()[:200]}"
        )
    subprocess.run(
        ["tar", "-x", "-C", str(FROZEN_73K6_DIR)],
        input=proc.stdout,
        check=True,
    )
    elite = ROOT / "analysis" / "schedules_by_archetype_elite.json"
    if elite.is_file():
        dest = FROZEN_73K6_DIR / "analysis"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / elite.name).write_bytes(elite.read_bytes())
    return FROZEN_73K6_DIR


def _resolve_opponent(spec: str) -> tuple[str, str]:
    """Return (label, kaggle env.run agent ref)."""
    s = spec.strip()
    if not s:
        raise ValueError("empty opponent")
    if s in ("starter", "random", "pass"):
        return s, s
    if s in ("frozen_73k6", "frozen"):
        ensure_frozen_73k6()
        s = "frozen_73k6"
    p = Path(s)
    if not p.is_absolute():
        candidates = [
            p,
            ROOT / p,
            OPPONENTS_DIR / p,
            OPPONENTS_DIR / p / "main.py",
            OPPONENTS_DIR / s / "main.py",
        ]
        for c in candidates:
            if c.is_file() and c.suffix == ".py":
                return c.parent.name if c.name == "main.py" else c.stem, str(c.resolve())
            if c.is_dir() and (c / "main.py").is_file():
                return c.name, str((c / "main.py").resolve())
    elif p.is_file():
        return p.parent.name if p.name == "main.py" else p.stem, str(p)
    raise FileNotFoundError(f"opponent not found: {spec}")


def run_match(
    seed: int,
    *,
    us_agent: str,
    opp_agent: str,
    seat: int = 0,
    episode_steps: int = 720,
) -> tuple[int, int]:
    # Do not force a shared params path — each agent package loads its own
    # tune/params.json via Path(__file__). Otherwise frozen opponents silently
    # run on HEAD params and the ladder collapses toward draws.
    os.environ.pop("KAGGRICULTURE_PARAMS_PATH", None)
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": episode_steps, "seed": seed},
        debug=False,
    )
    order = [us_agent, opp_agent] if seat == 0 else [opp_agent, us_agent]
    env.run(order)
    r0 = int(env.steps[-1][0]["reward"])
    r1 = int(env.steps[-1][1]["reward"])
    if seat == 0:
        return r0, r1
    return r1, r0


def evaluate_ladder(
    seeds: Iterable[int],
    opponents: list[str],
    *,
    both_seats: bool = False,
    episode_steps: int = 720,
    us_agent: str | None = None,
) -> list[MatchResult]:
    us = us_agent or OUR_AGENT
    seats = (0, 1) if both_seats else (0,)
    rows: list[MatchResult] = []
    resolved = [_resolve_opponent(o) for o in opponents]
    for label, opp_ref in resolved:
        for seed in seeds:
            for seat in seats:
                our, their = run_match(
                    seed,
                    us_agent=us,
                    opp_agent=opp_ref,
                    seat=seat,
                    episode_steps=episode_steps,
                )
                rows.append(
                    MatchResult(
                        seed=seed, opponent=label, seat=seat, us=our, them=their
                    )
                )
                tag = "W" if our > their else ("D" if our == their else "L")
                print(
                    f"{tag} seed={seed} vs={label} seat={seat} "
                    f"us={our} them={their} margin={our - their:+d}"
                )
    return rows


def summarize(rows: list[MatchResult]) -> None:
    if not rows:
        print("no matches")
        return
    by_opp: dict[str, list[MatchResult]] = {}
    for r in rows:
        by_opp.setdefault(r.opponent, []).append(r)

    print("\n=== Ladder summary ===")
    for opp, group in sorted(by_opp.items()):
        wins = sum(1 for r in group if r.win)
        draws = sum(1 for r in group if r.draw)
        n = len(group)
        wr = wins / n if n else 0.0
        margins = [r.margin for r in group]
        mean_m = statistics.mean(margins)
        mean_us = statistics.mean(r.us for r in group)
        mean_them = statistics.mean(r.them for r in group)
        print(
            f"vs {opp}: WR {wins}/{n}={wr:.1%} "
            f"(D {draws}) mean_margin={mean_m:+.0f} "
            f"mean_us={mean_us:.0f} mean_them={mean_them:.0f}"
        )
    wins = sum(1 for r in rows if r.win)
    n = len(rows)
    print(
        f"ALL: WR {wins}/{n}={wins / n:.1%} "
        f"mean_margin={statistics.mean(r.margin for r in rows):+.0f}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--episodeSteps", type=int, default=720)
    p.add_argument(
        "--seedSet",
        default="ladder20",
        choices=["ladder20", "mean15", "tune30", "tune60"],
    )
    p.add_argument("--seedCount", type=int, default=0, help="0 = all in seedSet")
    p.add_argument(
        "--opponents",
        default="frozen_73k6,ecobot_v2,structured,frontier_soil",
        help="Comma list. Fair defaults exclude replay/compressed bots. "
        "structured + frontier_soil are strong public policies that beat us. "
        "Add deterministic for ceiling (0%% WR expected).",
    )
    p.add_argument(
        "--with-ceiling",
        action="store_true",
        help="Also include opponents/deterministic (compressed schedule bot).",
    )
    p.add_argument(
        "--both-seats",
        action="store_true",
        help="Play each seed as player 0 and player 1 (2x matches)",
    )
    p.add_argument(
        "--us",
        default="",
        help="Override our agent path (default: ./main.py)",
    )
    args = p.parse_args()

    if args.seedSet == "ladder20":
        seeds_src = LADDER_SEEDS_20
    elif args.seedSet == "mean15":
        seeds_src = MEAN_SEEDS_15
    elif args.seedSet == "tune30":
        seeds_src = TUNE_SEEDS_30
    else:
        seeds_src = TUNE_SEEDS_60
    n = args.seedCount or len(seeds_src)
    seeds = list(seeds_src[:n])
    opps = [x.strip() for x in args.opponents.split(",") if x.strip()]
    if args.with_ceiling and "deterministic" not in opps:
        opps.append("deterministic")
    us = args.us.strip() or None

    print(f"seeds={len(seeds)} opponents={opps} both_seats={args.both_seats}")
    rows = evaluate_ladder(
        seeds,
        opps,
        both_seats=args.both_seats,
        episode_steps=args.episodeSteps,
        us_agent=us,
    )
    summarize(rows)


if __name__ == "__main__":
    main()
