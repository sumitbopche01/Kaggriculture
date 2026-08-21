"""tune/optimize.py

Optuna-based parameter tuning for the Kaggriculture heuristic agent.

Each trial:
  1) Samples a param set (merged onto full DEFAULT_PARAMS — never a partial wipe)
  2) Writes it to `tune/params.json`
  3) Evaluates densify (mean15) + holdout; objective is densify_mean with
     holdout floor prune (dual objective — do not hide holdout collapses)

Softfloor / plot-3 knobs are in the search space (max_quads 2–4).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import optuna
from optuna.exceptions import TrialPruned

from evaluate import (
    HOLDOUT_SEEDS,
    MEAN_SEEDS_30,
    dawn_step,
    run_vs_starter,
    run_vs_starter_env,
)


ROOT = Path(__file__).resolve().parents[1]
PARAMS_PATH = ROOT / "tune" / "params.json"
BEST_PATH = ROOT / "tune" / "best_params.json"
DB_PATH = ROOT / "tune" / "optuna.db"

# Regression guards — keep densify floors current (~80k band), not legacy 40k.
REG_GUARD_REWARD: dict[int, int] = {
    42: 78000,
    89: 85000,
    827875246: 55000,
    993781610: 70000,
    1827862996: 65000,  # holdout miss — prune if softfloor path dies
}
REG_GUARD_EMPTY_SEEDS: set[int] = {993781610, 89}

_BERRY_SHOPS = {"SMOOTHIE_SHOP", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "FARMERS_MARKET"}


def berry_shop_open(env: object, step_i: int) -> bool:
    obs = env.steps[step_i][0]["observation"]  # type: ignore[attr-defined]
    unlocked = list(obs.get("town", {}).get("unlocked_shops") or [])
    return any(name in _BERRY_SHOPS for name in unlocked)


def empty_at_step(env: object, step_i: int) -> int:
    me = env.steps[step_i][0]["observation"]["farms"][0]  # type: ignore[attr-defined]
    return sum(1 for row in me["tiles"] for t in row if t is None)


def _base_params() -> dict[str, int | float]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import main as kaggriculture_main

    return dict(kaggriculture_main.DEFAULT_PARAMS)


def _write_params(params: dict) -> None:
    """Write full param dict (overlay already merged onto defaults)."""
    PARAMS_PATH.write_text(
        json.dumps(params, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _suggest_params(trial: optuna.trial.Trial) -> dict[str, int | float]:
    """
    Search space includes softfloor / hollow / land expand knobs.
    max_quads_for_land is searchable (2–4) — plot-3 must be discoverable.
    """
    return {
        # Wheat engine
        "wheat_engine_day_max": trial.suggest_int("wheat_engine_day_max", 18, 26),
        "wheat_buffer_add": trial.suggest_int("wheat_buffer_add", 1, 3),
        "wheat_min_tiles": trial.suggest_int("wheat_min_tiles", 5, 7),
        "wheat_no_mouth_tiles": trial.suggest_int("wheat_no_mouth_tiles", 3, 5),
        "wheat_filler_day_max": trial.suggest_int("wheat_filler_day_max", 16, 24),
        "late_wheat_seed_buffer_day_min": trial.suggest_int(
            "late_wheat_seed_buffer_day_min", 14, 20
        ),
        "late_wheat_seed_buffer": trial.suggest_int("late_wheat_seed_buffer", 0, 4),
        # Herd ramp / cash gates
        "cow_day_max": trial.suggest_int("cow_day_max", 18, 26),
        "cow_milk_px_min": trial.suggest_int("cow_milk_px_min", 60, 95),
        "cow_floor_day_max": trial.suggest_int("cow_floor_day_max", 18, 22),
        "cow_floor": trial.suggest_int("cow_floor", 1, 3),
        "cow_expand_cap": trial.suggest_int("cow_expand_cap", 8, 12),
        "sheep_day_max": trial.suggest_int("sheep_day_max", 18, 22),
        "sheep_wool_px_min": trial.suggest_int("sheep_wool_px_min", 60, 95),
        "sheep_floor_day_max": trial.suggest_int("sheep_floor_day_max", 18, 22),
        "sheep_floor": trial.suggest_int("sheep_floor", 1, 3),
        "sheep_expand_cap": trial.suggest_int("sheep_expand_cap", 2, 6),
        # Land timing / softfloor expand
        "land_day_min": trial.suggest_int("land_day_min", 4, 8),
        "land_day_max": trial.suggest_int("land_day_max", 20, 26),
        "max_quads_for_land": trial.suggest_int("max_quads_for_land", 2, 4),
        "land2_day_min": trial.suggest_int("land2_day_min", 8, 13),
        "land2_money_min": trial.suggest_int("land2_money_min", 2500, 4500),
        "land2_empty_max": trial.suggest_int("land2_empty_max", 3, 8),
        "land2_strawberry_min": trial.suggest_int("land2_strawberry_min", 8, 20),
        "land2_schedule_cow_min": trial.suggest_int("land2_schedule_cow_min", 4, 8),
        "land2_schedule_empty_max": trial.suggest_int(
            "land2_schedule_empty_max", 40, 60
        ),
        "land2_dense_money_min": trial.suggest_int("land2_dense_money_min", 2200, 3000),
        "land_hollow_soft_cap": trial.suggest_int("land_hollow_soft_cap", 10, 18),
        "land2_hollow_empty_max": trial.suggest_int("land2_hollow_empty_max", 35, 55),
        "hollow_land_day_max": trial.suggest_int("hollow_land_day_max", 10, 16),
        "hollow_land_npv_min": trial.suggest_int("hollow_land_npv_min", 1000, 8000),
        "hollow_herd_deep_empty": trial.suggest_int("hollow_herd_deep_empty", 16, 28),
        "nonberry_secondary_cap": trial.suggest_int("nonberry_secondary_cap", 0, 24),
        "capital_followup": trial.suggest_int("capital_followup", 0, 1),
        "lt_animal_project_scale": trial.suggest_float(
            "lt_animal_project_scale", 0.05, 0.4
        ),
        "lt_land_animal_scale": trial.suggest_float("lt_land_animal_scale", 0.0, 0.3),
        "berry_animal_buy_day_max": trial.suggest_int(
            "berry_animal_buy_day_max", 16, 24
        ),
        # Sell-hold
        "sell_hold_price_factor": trial.suggest_float("sell_hold_price_factor", 0.70, 0.90),
        # Animal buy caps / cash floors
        "animal_buy_day_max": trial.suggest_int("animal_buy_day_max", 18, 26),
        "mouth_cap_2qplus": trial.suggest_int("mouth_cap_2qplus", 12, 16),
        "animal_cash_floor_2qplus": trial.suggest_int(
            "animal_cash_floor_2qplus", 200, 800
        ),
        # Melon filler
        "melon_leftover_min": trial.suggest_int("melon_leftover_min", 4, 10),
        "melon_day_max": trial.suggest_int("melon_day_max", 14, 18),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=200)
    p.add_argument(
        "--densifyCount",
        type=int,
        default=30,
        help="How many MEAN_SEEDS_30 to score for the objective",
    )
    p.add_argument(
        "--holdoutCount",
        type=int,
        default=8,
        help="Holdout seeds checked each trial (prune if mean collapses)",
    )
    p.add_argument(
        "--holdoutFloor",
        type=int,
        default=65000,
        help="Prune if holdout mean drops below this",
    )
    p.add_argument("--episodeSteps", type=int, default=720)
    p.add_argument("--studyName", type=str, default="kaggriculture_param_tune_v2")
    p.add_argument("--nStartupTrials", type=int, default=10)
    args = p.parse_args()

    densify_seeds = MEAN_SEEDS_30[: args.densifyCount]
    holdout_seeds = [s for s in HOLDOUT_SEEDS if s not in MEAN_SEEDS_30][
        : args.holdoutCount
    ]
    base = _base_params()

    def objective(trial: optuna.trial.Trial) -> float:
        overlay = _suggest_params(trial)
        params = dict(base)
        params.update(overlay)
        _write_params(params)

        for seed, floor in REG_GUARD_REWARD.items():
            env, us, _starter = run_vs_starter_env(
                seed, episode_steps=args.episodeSteps
            )
            if us < floor:
                raise TrialPruned()
            if seed in REG_GUARD_EMPTY_SEEDS:
                d16 = dawn_step(16)
                quads = len(
                    env.steps[d16][0]["observation"]["farms"][0]["unlocked_quadrants"]
                )
                if quads >= 3 and berry_shop_open(env, d16):
                    if empty_at_step(env, d16) > 24:
                        raise TrialPruned()

        # Holdout panel — separate from densify objective.
        hold_total = 0
        for seed in holdout_seeds:
            us, _ = run_vs_starter(seed, episode_steps=args.episodeSteps)
            hold_total += us
        hold_mean = hold_total / len(holdout_seeds)
        if hold_mean < args.holdoutFloor:
            raise TrialPruned()
        trial.set_user_attr("holdout_mean", hold_mean)

        total = 0
        for i, seed in enumerate(densify_seeds):
            us, _starter = run_vs_starter(seed, episode_steps=args.episodeSteps)
            total += us
            mean_so_far = total / (i + 1)
            trial.report(mean_so_far, step=i)
            if trial.should_prune():
                raise TrialPruned()
        densify_mean = total / len(densify_seeds)
        trial.set_user_attr("densify_mean", densify_mean)
        return densify_mean

    storage = f"sqlite:///{DB_PATH}"
    study = optuna.create_study(
        direction="maximize",
        study_name=args.studyName,
        storage=storage,
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=0),
        pruner=optuna.pruners.MedianPruner(
            n_startup_trials=args.nStartupTrials,
            n_warmup_steps=5,
        ),
    )

    try:
        enqueue = {
            k: base[k]
            for k in (
                "wheat_engine_day_max",
                "wheat_buffer_add",
                "wheat_min_tiles",
                "wheat_no_mouth_tiles",
                "wheat_filler_day_max",
                "late_wheat_seed_buffer_day_min",
                "late_wheat_seed_buffer",
                "cow_day_max",
                "cow_milk_px_min",
                "cow_floor_day_max",
                "cow_floor",
                "cow_expand_cap",
                "sheep_day_max",
                "sheep_wool_px_min",
                "sheep_floor_day_max",
                "sheep_floor",
                "sheep_expand_cap",
                "land_day_min",
                "land_day_max",
                "max_quads_for_land",
                "land2_day_min",
                "land2_money_min",
                "land2_empty_max",
                "land2_strawberry_min",
                "land2_schedule_cow_min",
                "land2_schedule_empty_max",
                "land2_dense_money_min",
                "land_hollow_soft_cap",
                "land2_hollow_empty_max",
                "hollow_land_day_max",
                "hollow_land_npv_min",
                "hollow_herd_deep_empty",
                "nonberry_secondary_cap",
                "capital_followup",
                "lt_animal_project_scale",
                "lt_land_animal_scale",
                "berry_animal_buy_day_max",
                "sell_hold_price_factor",
                "animal_buy_day_max",
                "mouth_cap_2qplus",
                "animal_cash_floor_2qplus",
                "melon_leftover_min",
                "melon_day_max",
            )
            if k in base
        }
        if enqueue:
            study.enqueue_trial(enqueue)
    except Exception:
        pass

    study.optimize(objective, n_trials=args.trials, show_progress_bar=True)

    complete = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if not complete:
        print("No completed trials (all pruned by regression guards). Nothing to write.")
        return

    best_overlay = study.best_params
    best_full = dict(base)
    best_full.update(best_overlay)
    _write_params(best_full)
    BEST_PATH.write_text(
        json.dumps(best_full, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print("best_densify_mean", study.best_value)
    print(
        "best_holdout_mean",
        study.best_trial.user_attrs.get("holdout_mean"),
    )
    print("best_params_overlay", best_overlay)
    print(
        "NOTE: full params.json written (defaults + overlay). "
        "Re-check holdout + ladder before submitting."
    )


if __name__ == "__main__":
    main()
