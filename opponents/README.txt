Ladder opponents (each folder needs main.py with agent()).

Fair strategy bots (default ladder):
  frozen_73k6   — auto from git 5f379de (~73.6k mean)
  ecobot_v2     — public EcoBot kernel (melon/land schedule)
  deepesh       — public nearest-job baseline (weak)

Ceiling / not a fair strategy:
  deterministic — public compressed-action bot (~125k mean vs us).
                  Likely seed-agnostic schedule dump; use --with-ceiling.

Refresh:
  .venv/bin/python -m tune.fetch_opponents

Run:
  .venv/bin/python -m tune.ladder
  .venv/bin/python -m tune.ladder --with-ceiling
