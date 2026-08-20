Ladder opponents (each folder needs main.py with agent()).

Fair strategy bots (default ladder):
  frozen_73k6   — auto from git 5f379de (~73.6k mean)
  ecobot_v2     — public EcoBot kernel (melon/land schedule)
  structured    — pilkwang structured economic policy (beats us hard)
  frontier_soil — prvsiyan Soil RC5 modal route (beats us hard)
  deepesh       — public nearest-job baseline (weak)

Ceiling / not a fair strategy (schedule dumps / replay traces):
  deterministic — public compressed-action bot (~125k mean vs us).
                  Likely seed-agnostic schedule dump; use --with-ceiling.
  Local-only dumps under opponents/ (hamburger, top10_read, kaito_v27,
  multiroute, boatlee_v16, adaptive) are useful as score ceilings but are
  not committed — re-extract from public kernels if needed.

Refresh (EcoBot + deterministic + deepesh; structured/frontier need
encoded-payload extract — see tune/fetch_opponents.py):
  .venv/bin/python -m tune.fetch_opponents

Run:
  .venv/bin/python -m tune.ladder
  .venv/bin/python -m tune.ladder --with-ceiling
  .venv/bin/python -m tune.ladder --opponents structured,frontier_soil
