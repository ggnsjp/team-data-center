"""Hosting-capacity brackets on public benchmark systems (theme 2).

For every bus of each case this computes the DC screening value, the SOCP and SDP upper bounds
and a verified AC-feasible lower bound, and writes one row per bus to
results/grid_hosting/<case>.csv (not committed). It prints, per case: how many buses got an AC
point, how tight the bracket is, how often DC screening overstates the capacity, which kind of
limit binds, and the solve times. Two smaller studies follow on one case: the bracket at lower
load levels, and the worst single-branch outage (N-1) for a few buses.

The cases come from PGLib-OPF (IEEE PES Task Force, CC BY 4.0) and are downloaded on first use
into data/cache/pglib/. The built-in systems (ring5, feeder8) need no download.

Run: uv run python experiments/grid_hosting/run.py [--cases case14_ieee,case30_ieee] [--workers 8]
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

from dcopt.grid import cases
from dcopt.grid.hosting import KINDS, hosting_curve, hosting_map, hosting_n1, summarize

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "grid_hosting"
DEFAULT = "case14_ieee,case30_ieee,case39_epri,case57_ieee,case118_ieee,case300_ieee"


def pct(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f} %"


def run_case(name: str, pf: float, workers: int) -> dict | None:
    try:
        case = cases.load(name)
    except FileNotFoundError as err:
        print(f"\n== {name}: skipped ({err})")
        return None
    t0 = time.perf_counter()
    rows = hosting_map(case, pf=pf, workers=workers)
    wall = time.perf_counter() - t0
    OUT.mkdir(parents=True, exist_ok=True)
    records = [h.row() for h in rows]
    fields = list(dict.fromkeys(k for r in records for k in r))
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    s = summarize(rows)
    mva = case.base_mva
    headroom = (case.pmax.sum() - case.pd.sum()) * mva
    ac = np.array([h.ac for h in rows if h.ac is not None])
    unsolved = {k: sum(1 for h in rows if getattr(h, k) is None) for k in ("socp", "sdp")}
    print(f"\n== {name}: {case.n} buses, {case.m} branches, {case.ng} generators; load {case.pd.sum() * mva:.0f} MW, "
          f"generation headroom {headroom:.0f} MW; power factor {pf}; {wall:.0f} s wall on {workers} worker(s)")
    print(f"   AC point found           {s['ac_found']} of {s['buses']} buses"
          f"   (relaxation not solved: SOCP {unsolved['socp']}, SDP {unsolved['sdp']})")
    if len(ac):
        print(f"   hostable load (AC)       median {np.median(ac):.1f} MW, min {ac.min():.1f}, max {ac.max():.1f}")
    print(f"   bracket closed           gap < 0.1 %: {s['gap_below_0.1%']} buses;  gap < 1 %: {s['gap_below_1%']} buses")
    print(f"   SDP gap to the AC point  median {pct(s['sdp_gap_median'], 3)}, max {pct(s['sdp_gap_max'])}")
    print(f"   SOCP gap to the AC point median {pct(s['socp_gap_median'], 3)}, max {pct(s['socp_gap_max'])}")
    print(f"   DC screening             above the upper bound at {s['dc_above_upper']} buses (provably too high); "
          f"above the AC point at {s['dc_above_ac']}, below it at {s['dc_below_ac']}")
    print("   binding limit            " + ", ".join(f"{k} {s['limits'][k]}" for k in KINDS))
    print("   median solve time        " + ", ".join(f"{k} {v:.3f} s" for k, v in s["time_median"].items() if v is not None))
    s.update(case=name, n=case.n, wall=wall, headroom=headroom)
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=DEFAULT, help="comma-separated PGLib or built-in case names")
    ap.add_argument("--pf", type=float, default=0.95, help="power factor of the added load (lagging)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--study-case", default="case30_ieee", help="case for the load-level and N-1 studies ('' to skip)")
    ap.add_argument("--study-buses", type=int, default=4, help="how many of its largest load buses to study")
    ap.add_argument("--n1-level", type=float, default=0.7, help="load level of the N-1 study (1.0: the case as given)")
    args = ap.parse_args()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=False).stdout.strip()
    print(f"hosting-capacity brackets; power factor {args.pf}; commit {commit or 'unknown'}; "
          + ", ".join(f"{pkg} {version(pkg)}" for pkg in ("clarabel", "scipy", "numpy")))
    for name in [c for c in args.cases.split(",") if c]:
        run_case(name, args.pf, args.workers)

    if not args.study_case:
        return
    try:
        case = cases.load(args.study_case)
    except FileNotFoundError as err:
        print(f"\nstudies skipped ({err})")
        return
    buses = [int(b) for b in np.argsort(-case.pd)[:args.study_buses]]
    levels = [0.6, 0.7, 0.8, 0.9, 1.0]
    print(f"\n== load levels on {case.name}: every existing load scaled, AC point / upper bound in MW")
    print("   bus    " + "".join(f"{f'x{a:.1f}':>22s}" for a in levels))
    for b in buses:
        cells = []
        for _, h in hosting_curve(case, b, levels, pf=args.pf):
            cells.append(f"{h.ac:9.1f} / {h.upper:9.1f}" if h.ac is not None and h.upper is not None else f"{'n/a':>21s}")
        print(f"   {case.label(b):>5s}  " + "  ".join(cells))
    methods = ("socp", "sdp", "ac")
    case = case.scaled_loads(args.n1_level)
    print(f"\n== single-branch outages (N-1) on {case.name} at load level x{args.n1_level}: "
          "the worst outage per bus, AC point and upper bound")
    for b in buses:
        intact = hosting_map(case, buses=[b], pf=args.pf, methods=methods)[0]
        n1 = hosting_n1(case, b, pf=args.pf, methods=methods, workers=args.workers)
        if n1["ac"] is None or intact.ac is None:
            print(f"   bus {case.label(b):>5s}: no AC point (intact {intact.ac}, worst outage {n1['ac']})")
            continue
        print(f"   bus {case.label(b):>5s}: intact {intact.ac:8.1f} MW (bound {intact.upper:8.1f}); worst outage "
              f"{n1['ac']:8.1f} MW at branch {n1['ac_branch']} (bound {n1['upper']:8.1f}); "
              f"{n1['outages']} outages checked, {n1['infeasible']} of them cannot serve even the existing load, "
              f"{n1['skipped']} split the network (not checked), {n1['missing_ac']} without an AC point")


if __name__ == "__main__":
    main()
