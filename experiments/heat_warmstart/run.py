"""Warm Ishikari (v1.design): does a warm start from a nearby plan make HiGHS faster?

    uv run python experiments/heat_warmstart/run.py
    uv run python experiments/heat_warmstart/run.py --config experiments/heat_warmstart/config.toml

For every move in the config: solve the "from" assumptions (the app's defaults), then solve the
"to" assumptions twice, cold and warm-started from the "from" plan. Wall time depends on the load
of the machine (HiGHS uses several threads), so run it on a quiet machine and compare times only
within one run. The objective is the annual net benefit (yen/yr); higher is better.

A solve without a start goes to scipy's milp, which is what the app does by default; a solve with
a start goes to highspy (dcopt.heat.v1.design). So "cold" against "warm" is the app's default
against its optional warm start (DCOPT_WARM_START=1), another build of HiGHS included.

Needs the Ishikari map data (data/cache/ishikari). Results go to results/heat_warmstart/<timestamp>/.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import tomllib
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dcopt.common import provenance
from dcopt.heat.v1 import Assumptions, design, ishikari_sites

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ASSUMED = {"new_greenhouse", "aquaculture", "snow"}
KINDS = {"greenhouse", "new_greenhouse", "aquaculture", "onsen", "pool", "hospital", "school", "snow"}  # as the app


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=HERE / "config.toml")
    args = ap.parse_args()
    cfg = tomllib.loads(args.config.read_text())
    kinds = KINDS if cfg["assumed_sites"] else KINDS - ASSUMED
    out = ROOT / "results" / "heat_warmstart" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    dc, sites = ishikari_sites()
    A0 = Assumptions()

    def run(A, start=None):
        t0 = time.perf_counter()
        d = design(dc, sites, A, k=cfg["k"], kinds=kinds, time_limit=cfg["time_limit"], start=start)
        return d, time.perf_counter() - t0

    base, t_base = run(A0)
    print(f"defaults: net {base.annual_net / 1e6:.1f} M yen/yr, {len(base.connected)} sites, "
          f"{base.status}, gap {base.gap:.2%}, {t_base:.1f}s", flush=True)
    rows = []
    for mv in cfg["move"]:
        A = replace(A0, **mv["to"])
        for rep in range(cfg["repeats"]):
            for mode in ("cold", "warm"):
                d, wall = run(A, base if mode == "warm" else None)
                rows.append({"move": mv["name"], "repeat": rep, "mode": mode, "wall_s": round(wall, 2),
                             "status": d.status, "gap": d.gap, "annual_net_yen": round(d.annual_net),
                             "sites": len(d.connected), "pipe_km": round(d.pipe_m / 1000, 2)})
                print(f"{mv['name']:70s} {mode}  {wall:6.1f}s  {d.status:20s} gap {d.gap:6.2%}  "
                      f"net {d.annual_net / 1e6:8.2f} M", flush=True)

    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "config.toml").write_text(args.config.read_text())
    (out / "run.json").write_text(json.dumps(
        {"config": cfg, "solver": "highs", "provenance": provenance.stamp(solver="highs"),
         "defaults": {"wall_s": round(t_base, 2), "status": base.status, "gap": base.gap,
                      "annual_net_yen": round(base.annual_net)}}, indent=2, ensure_ascii=False))
    print(f"results in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
