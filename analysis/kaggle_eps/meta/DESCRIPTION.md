Episode replays and results from the [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture) simulation competition, collected from the public episode API and refreshed daily. One episode is one 720-turn farming game (24 turns a day, 30 days).

The live report [Kaggriculture Daily Replays](https://www.kaggle.com/code/georgymamarin/kaggriculture-daily-replays-the-live-meta-report) is built entirely from these files. Community research on this data: [the opening census](https://www.kaggle.com/code/destbreso/everyone-is-playing-the-same-opening), [the game's physics](https://www.kaggle.com/code/destbreso/kaggriculture-what-kind-of-game-is-this), [the free experiment in validation games](https://www.kaggle.com/code/destbreso/kaggriculture-the-free-experiment-you-already-ran), all by destbreso.

## Content

- `episodes.csv`: one row per episode: times, `state`, `type` (`EPISODE_TYPE_PUBLIC` = ladder, `EPISODE_TYPE_VALIDATION` = self-play), per seat `sub_N`, `team_N`, `bank_N`, `rating_N`.
- `agents.csv`: `episode_id`, `agent_index`, `submission_id`, `team_id`, `final_bank`, `rating_after`.
- `teams.csv`: `team_id` to `team_name`, `ladder_score`, `last_submission` (a leaderboard snapshot, names about half the teams).
- `episode_features.csv`: one row per (episode, seat): `engine_version` (the balance patch it played under), `peak_crew`, `total_hires`, `first_land_day`, `tiles_planted`, `plants_*`, `price_*_min`/`_max`. `final_money` (= `bank_N`) and `elbow_day` derive from the outcome: keep both out of any feature set.
- `replays_2026-*.parquet`: full replays in monthly shards, `episode_id` plus `replay_json` as the CDN serves it, zstd ~236x.
- `stream_hashes.csv`: per (episode, seat), sha256 of the action stream cut at turns 24/48/100/136/200/300/400/719 (proposed by destbreso). Covers episodes stored here; new cuts backfill over a few nights.
- `per_submission_coverage.csv`: episodes indexed vs stored per submission. The crawl over-serves a few hundred submissions; `coverage` is the exact reweighting factor.
- `daily_stats.csv`: per UTC day: games, teams, median/p90/record bank.
- `state.json`, `README.md`, and the collector chain (`scrape.py`, `repack.py`, `teams.py`, `features.py`).

Read replays across all shards:

```python
import pandas as pd, json, glob, pyarrow.dataset as pads
base = "/kaggle/input/kaggriculture-episodes"
eid = pd.read_csv(f"{base}/episode_features.csv").episode_id.iloc[-1]
row = pads.dataset(sorted(glob.glob(f"{base}/replays_*.parquet"))).scanner(
    filter=pads.field("episode_id") == int(eid), batch_size=1).head(1)
replay = json.loads(row.column("replay_json")[0].as_py())
```

On completeness: coverage is per submission, not per day; `per_submission_coverage.csv` states it exactly. Daily totals are a sample of the ladder, not its true volume. Every stored episode has its replay.

The games belong to their players and to Kaggle; I only collect and reshape. Environment: [kaggle-environments](https://github.com/Kaggle/kaggle-environments).

New to the game? [Kaggriculture, Visualized](https://www.kaggle.com/code/georgymamarin/kaggriculture-visualized-what-every-crop-pays) draws every rule. Built something on this? The discussion tab is open.
