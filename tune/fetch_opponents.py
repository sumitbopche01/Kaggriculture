"""Fetch public Kaggriculture agents into opponents/.

Pulls Kaggle kernels that write main.py and the deepeshumrao GitHub submission.
Does not download private competition submissions (API cannot).

Usage:
  .venv/bin/python -m tune.fetch_opponents
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPP = ROOT / "opponents"
DOWNLOAD = OPP / "_download"
KAGGLE = ROOT / ".venv" / "bin" / "kaggle"

KERNELS = [
    ("premaananda108/kaggriculture-ecobot-v2", "ecobot_v2"),
    (
        "ameythakur20/kaggriculture-deterministic-farm-planning-agent",
        "deterministic",
    ),
]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    return env


def _extract_writefile(nb_path: Path, out_dir: Path) -> None:
    nb = json.loads(nb_path.read_text())
    chunks: list[str] = []
    for cell in nb.get("cells", []):
        src = "".join(cell.get("source") or [])
        if src.lstrip().startswith("%%writefile main.py"):
            body = src.split("\n", 1)[1] if "\n" in src else ""
            chunks.append(body)
    if not chunks:
        raise RuntimeError(f"no %%writefile main.py in {nb_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "main.py").write_text(chunks[-1])


def fetch_kernels() -> None:
    DOWNLOAD.mkdir(parents=True, exist_ok=True)
    for ref, label in KERNELS:
        dest = DOWNLOAD / label
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(
            [str(KAGGLE), "kernels", "pull", ref, "-p", str(dest)],
            cwd=ROOT,
            env=_env(),
            check=True,
        )
        nbs = list(dest.glob("*.ipynb"))
        if not nbs:
            raise RuntimeError(f"no notebook in {dest}")
        _extract_writefile(nbs[0], OPP / label)
        print(f"wrote {OPP / label / 'main.py'}")


def fetch_deepesh() -> None:
    repo = DOWNLOAD / "deepesh"
    if repo.exists():
        shutil.rmtree(repo)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "https://github.com/deepeshumrao/kaggriculture-agent.git",
            str(repo),
        ],
        check=True,
    )
    src = repo / "deliverables" / "kaggriculture_submission.py"
    out = OPP / "deepesh"
    out.mkdir(parents=True, exist_ok=True)
    (out / "main.py").write_text(src.read_text())
    print(f"wrote {out / 'main.py'}")


def main() -> None:
    if not KAGGLE.is_file():
        raise SystemExit(f"missing kaggle CLI at {KAGGLE}")
    fetch_kernels()
    fetch_deepesh()
    print("done")


if __name__ == "__main__":
    main()
