# Phase 0: diagnose why softfloor cows@10 stay ~4.
# Usage: .venv/bin/python analysis/probe_plot3_qualify.py

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from kaggle_environments import make

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main as M  # noqa: E402

SOFTFLOOR = [
    12,
    21,
    33,
    123,
    2024,
    3141,
    993781610,
    49090797,
    1827862996,
]
DENSIFY = [42, 7, 89, 55]
OUT_JSON = Path(__file__).resolve().parent / "plot3_qualify_probe.json"
OUT_MD = Path(__file__).resolve().parent / "plot3_qualify_2026-08-21.md"


def _label_seed(dawn_rows: list[dict], cows10: int | None) -> str:
    if cows10 is not None and cows10 >= 6:
        return "OK_HERD"
    window = [r for r in dawn_rows if 7 <= r["day"] <= 10 and r["quads"] >= 2]
    if not window:
        window = [r for r in dawn_rows if 7 <= r["day"] <= 10]
    if not window:
        return "ROUTER_OFF"
    mode_on = sum(1 for r in window if r["softfloor_mode"])
    if mode_on < 2:
        return "ROUTER_OFF"
    # Mode on often but cows low
    want_asks = [r for r in window if r["want_cows"] > r["cows"]]
    if not want_asks:
        return "WANT_FLAT"
    shedish = [
        r
        for r in want_asks
        if r["shed_cows"] > 0 and r["empty_pasture"] == 0
    ]
    if len(shedish) >= max(1, len(want_asks) // 2):
        return "SHED_BLOCK"
    # Wanted more but cows didn't rise → treat as cash/market block
    return "CASH_BLOCK"


def probe(seed: int) -> dict:
    rows: list[dict] = []
    buys: list[tuple[int, str]] = []

    def wrapped(obs):
        if obs["player"] != 0:
            return M.agent(obs)
        s = M.read_signals(obs)
        if int(s.get("hour") or 0) == 0 and int(s.get("day") or 0) <= 12:
            shed = obs["private"].get("shed") or {}
            strat = M.map_strategy(s)
            rows.append(
                {
                    "day": int(s["day"]),
                    "quads": int(s["n_quads"]),
                    "empty": int(s["empty"]),
                    "cows": int(s["cows"]),
                    "berry": int(s["crops"].get("STRAWBERRY", 0) or 0),
                    "melon": int(s["crops"].get("MELON", 0) or 0),
                    "workers": int(s.get("workers") or 0),
                    "strategy": strat,
                    "softfloor_mode": bool(M._softfloor_mode(s)),
                    "softfloor_active": bool(
                        M.softfloor_mode_active(s, strat, M.PARAMS)
                    ),
                    "want_cows": int(M.want_cows(s)),
                    "shed_cows": int(shed.get("COW", 0) or 0),
                    "empty_pasture": int(
                        (s.get("empty_struct") or {}).get("PASTURE", 0) or 0
                    ),
                    "calendar_ready": bool(M._softfloor_calendar_land_ready(s)),
                    "need_land": bool(M.need_land(s)),
                    "money": int(s.get("money") or 0),
                }
            )
        out = M.agent(obs)
        if int(s.get("hour") or 0) == 0:
            for act in out.get("market") or []:
                if act and act[0] == "BUY_ANIMAL" and act[1] == "COW":
                    buys.append((int(s["day"]), "COW"))
        return out

    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": seed},
        debug=False,
    )
    env.run([wrapped, "starter"])
    score = float(env.steps[-1][0]["reward"] or 0)
    cows10 = next((r["cows"] for r in rows if r["day"] == 10), None)
    label = _label_seed(rows, cows10)
    return {
        "seed": seed,
        "score": score,
        "cows_d10": cows10,
        "label": label,
        "cow_buys": buys,
        "dawn": rows,
    }


def main() -> None:
    soft = [probe(s) for s in SOFTFLOOR]
    dens = [probe(s) for s in DENSIFY]
    labels = Counter(r["label"] for r in soft)
    lines = [
        "# Plot3 qualify probe (Phase 0) — 2026-08-21",
        "",
        "## Softfloor labels",
        "",
        "| seed | score | cows@10 | label | mode_on d7-10 |",
        "|-----:|------:|--------:|-------|---------------|",
    ]
    for r in soft:
        window = [d for d in r["dawn"] if 7 <= d["day"] <= 10]
        mode_n = sum(1 for d in window if d["softfloor_mode"])
        lines.append(
            f"| {r['seed']} | {r['score']:.0f} | {r['cows_d10']} | `{r['label']}` | {mode_n}/{len(window)} |"
        )
    lines += [
        "",
        f"**Label counts:** {dict(labels)}",
        "",
        "## Densify softfloor_mode (must stay mostly off)",
        "",
        "| seed | score | cows@10 | mode_on d7-10 |",
        "|-----:|------:|--------:|---------------|",
    ]
    for r in dens:
        window = [d for d in r["dawn"] if 7 <= d["day"] <= 10]
        mode_n = sum(1 for d in window if d["softfloor_mode"])
        lines.append(
            f"| {r['seed']} | {r['score']:.0f} | {r['cows_d10']} | {mode_n}/{len(window)} |"
        )

    dominant = labels.most_common(1)[0][0] if labels else "UNKNOWN"
    # Detail dawns for softfloor
    lines += ["", "## Dawn detail (softfloor d6–d12)", ""]
    for r in soft:
        lines.append(f"### seed {r['seed']} — `{r['label']}`")
        for d in r["dawn"]:
            if d["day"] < 6:
                continue
            lines.append(
                f"- d{d['day']}: q={d['quads']} empty={d['empty']} cows={d['cows']} "
                f"want={d['want_cows']} mode={d['softfloor_mode']} act={d['softfloor_active']} "
                f"strat={d['strategy']} shedC={d['shed_cows']} past={d['empty_pasture']} "
                f"berry={d['berry']} melon={d['melon']} need={d['need_land']} "
                f"cal={d['calendar_ready']} ${d['money']}"
            )
        lines.append("")

    lines += [
        "## One-line summary",
        "",
        f"Dominant softfloor cause: **`{dominant}`** "
        f"({labels[dominant]}/9). Densify mode_on should stay low. "
        f"Phase 1 fork: "
        + (
            "1a router"
            if dominant == "ROUTER_OFF"
            else "1b want/cash"
            if dominant in ("WANT_FLAT", "CASH_BLOCK")
            else "1c softfloor shed"
            if dominant == "SHED_BLOCK"
            else "skip herd (OK_HERD)"
        )
        + ".",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))
    OUT_JSON.write_text(
        json.dumps({"softfloor": soft, "densify": dens, "labels": dict(labels)}, indent=2)
    )
    print(OUT_MD.read_text())
    print(f"wrote {OUT_MD} and {OUT_JSON}")


if __name__ == "__main__":
    main()
