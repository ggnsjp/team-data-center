"""The global-solver cross-check of the hosting-capacity bracket (theme 2), as in the table of
docs/formulations/grid.md.

For every (case, bus, load level) of that table this computes the SDP upper bound and the
verified AC point (hosting_capacity), then solves the same AC problem with Gurobi as a nonconvex
quadratic program (global_gurobi) and records its best value, its proven bound and its status.
It writes results/grid_global/table.csv and results/grid_global/provenance.json (not committed:
git commit, Gurobi version, feasibility tolerance, time limit, run times) and prints the rows as a
Markdown table in the column layout of grid.md.

Gurobi is optional (CONTRIBUTING.md, Solvers). Without gurobipy or a usable licence the script
prints a one-line note and exits with status 0. PGLib-OPF cases that are not in data/cache/pglib/
are skipped with a message; --download fetches them (CC BY 4.0, see data/register.toml).

Run: uv run --extra gurobi python experiments/grid_global/run.py [--time-limit 240] [--feas-tol 1e-9]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from importlib.metadata import version
from pathlib import Path

from dcopt.common import provenance
from dcopt.grid import cases
from dcopt.grid.cases import Case
from dcopt.grid.hosting import hosting_capacity
from dcopt.grid.lifted import weights

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "grid_global"
PF = 0.95                              # power factor of the added load, as everywhere in grid.md

# The problems of the table in docs/formulations/grid.md: (case, bus labels, load levels).
# Bus labels are the case's own bus numbers. Assumption: the doc names load levels 0.6 and 0.8 for
# the 5-bus ring but not the third of its "3 load levels"; 1.0 (the case as given) is used here.
# The PGLib cases run at the load of the case as given. feeder8 buses 4, 6 and 8 are the ones
# tests/test_grid_hosting.py checks (the doc mentions the feeder in the text, not in the table).
TABLE = (
    ("ring5", ("1", "2", "3", "4", "5"), (0.6, 0.8, 1.0)),
    ("feeder8", ("4", "6", "8"), (1.0,)),
    ("case30_ieee", ("29", "30", "26"), (1.0,)),
    ("case57_ieee", ("1", "7", "8"), (1.0,)),
    ("case39_epri", ("21",), (1.0,)),
)
FIELDS = ("case", "bus", "load_level", "sdp_mw", "ac_mw", "gurobi_best_mw", "gurobi_bound_mw", "gurobi_status",
          "hosting_s", "gurobi_s")


def bus_index(case: Case, label: str) -> int:
    """The index of the bus whose original number is `label`."""
    for i in range(case.n):
        if case.label(i) == str(label):
            return i
    raise KeyError(f"{case.name} has no bus {label}")


def row(case: Case, label: str, level: float = 1.0, time_limit: float = 240.0, feas_tol: float = 1e-9,
        pf: float = PF) -> dict:
    """One line of the table: the SDP bound and AC point, then Gurobi's best value and bound (MW).
    Raises gurobipy.GurobiError when Gurobi cannot run (for example without a licence)."""
    from dcopt.grid.ac import global_gurobi

    c = case if level == 1.0 else case.scaled_loads(level)
    i = bus_index(c, label)
    t0 = time.perf_counter()
    h = hosting_capacity(c, i, pf, methods=("sdp", "ac"))
    t1 = time.perf_counter()
    best, bound, status = global_gurobi(c, weights(c, i), math.tan(math.acos(pf)), time_limit=time_limit,
                                        feas_tol=feas_tol)
    t2 = time.perf_counter()
    mva = c.base_mva
    return {"case": case.name, "bus": str(label), "load_level": level, "sdp_mw": h.sdp, "ac_mw": h.ac,
            "gurobi_best_mw": None if best is None else best * mva,
            "gurobi_bound_mw": None if bound is None else bound * mva,
            "gurobi_status": status, "hosting_s": t1 - t0, "gurobi_s": t2 - t1}


def _mw(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


def markdown(rows: list[dict], time_limit: float) -> str:
    """The rows in the column layout of the table in docs/formulations/grid.md."""
    lines = ["| Problem | SDP bound (MW) | AC point (MW) | Global solver |", "|---|---|---|---|"]
    for r in rows:
        problem = f"{r['case']} bus {r['bus']}" + ("" if r["load_level"] == 1.0 else f" at load level {r['load_level']}")
        if r["gurobi_status"] == "optimal":
            glob = f"optimal, {_mw(r['gurobi_best_mw'])}"
        elif r["gurobi_status"] == "time limit":
            glob = f"best {_mw(r['gurobi_best_mw'])}, bound {_mw(r['gurobi_bound_mw'])} at {time_limit:g} s"
        else:
            glob = f"{r['gurobi_status']}; best {_mw(r['gurobi_best_mw'])}, bound {_mw(r['gurobi_bound_mw'])}"
        lines.append(f"| {problem} | {_mw(r['sdp_mw'])} | {_mw(r['ac_mw'])} | {glob} |")
    return "\n".join(lines)


def gurobi_problem() -> str | None:
    """None when Gurobi can run here, otherwise the reason it cannot."""
    try:
        import gurobipy as gp
    except ImportError:
        return "gurobipy is not installed (uv sync --extra gurobi)"
    try:
        with gp.Env(empty=True) as env:
            env.setParam("OutputFlag", 0)
            env.start()
    except gp.GurobiError as err:
        return f"no usable Gurobi licence ({err})"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Global-solver cross-check of the hosting-capacity bracket")
    ap.add_argument("--time-limit", type=float, default=240.0, help="Gurobi time limit per problem, s")
    ap.add_argument("--feas-tol", type=float, default=1e-9, help="Gurobi feasibility tolerance")
    ap.add_argument("--cases", default="", help="comma-separated subset of the table's cases (default: all)")
    ap.add_argument("--download", action="store_true", help="download PGLib cases that are not cached")
    ap.add_argument("--out", type=Path, default=OUT, help="output folder")
    args = ap.parse_args(argv)

    problem = gurobi_problem()
    if problem is not None:
        print(f"grid_global: skipped, Gurobi is optional and cannot run here: {problem}.")
        return 0
    import gurobipy as gp

    gurobi = ".".join(map(str, gp.gurobi.version()))
    wanted = {c for c in args.cases.split(",") if c}
    stamp = provenance.stamp(solver=f"gurobi {gurobi}", conic_solver=f"clarabel {version('clarabel')}",
                             feas_tol=args.feas_tol, time_limit_s=args.time_limit, power_factor=PF)
    print(f"global-solver cross-check; Gurobi {gurobi}, feasibility tolerance {args.feas_tol:g}, "
          f"time limit {args.time_limit:g} s; commit {stamp['git_commit'][:7] or 'unknown'}")
    rows, skipped = [], []
    t0 = time.perf_counter()
    for name, buses, levels in TABLE:
        if wanted and name not in wanted:
            continue
        try:
            case = cases.load(name, download=args.download)
        except FileNotFoundError:
            msg = f"{name}: skipped, not in {cases.pglib_path(name).parent} (run with --download)"
            print(msg)
            skipped.append(msg)
            continue
        for level in levels:
            for bus in buses:
                try:
                    r = row(case, bus, level, args.time_limit, args.feas_tol)
                except gp.GurobiError as err:          # e.g. a size-limited licence on a larger case
                    msg = f"{name} bus {bus} at load level {level}: Gurobi error ({err})"
                    print(msg)
                    skipped.append(msg)
                    continue
                print(f"  {name} bus {bus} x{level}: SDP {_mw(r['sdp_mw'])}, AC {_mw(r['ac_mw'])}, "
                      f"Gurobi {r['gurobi_status']} best {_mw(r['gurobi_best_mw'])} bound {_mw(r['gurobi_bound_mw'])} "
                      f"({r['gurobi_s']:.1f} s)")
                rows.append(r)
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "table.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    stamp.update(run_s=time.perf_counter() - t0, rows=len(rows), skipped=skipped)
    (args.out / "provenance.json").write_text(json.dumps(stamp, indent=1), encoding="utf-8")
    print()
    print(markdown(rows, args.time_limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
