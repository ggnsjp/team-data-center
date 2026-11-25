"""Warm Ishikari: how far the published plan moves when one input moves to the end of its published range.

    uv run python experiments/input_sensitivity/run.py --workers 6        # about ten minutes

docs/data-sources.md gives, for every input of the heat-network model, the range found in published
sources. This experiment puts each input at the ends of that range, one at a time, and reports two
numbers in M yen a year (the published plan is the expected plan of model v2, ambient loop):

  published pipes kept   the published pipes and connections, deliveries re-optimised under the changed
                         input: what the plan is worth if the input is not what the model assumed
  best plan found        the best of every plan the experiment has for that input, each evaluated under
                         the changed value: what a planner who knew the value could reach, and the
                         network that goes with it

The plans come from a heuristic search, so a search under one value can miss a plan that a search
under a neighbouring value finds. To keep that noise out, every plan found for an input (the
published one and the one re-planned under each of its values) is evaluated under every value of
that input with its pipes fixed, and each value takes the best. A plan whose pipes are too small
under a value (more loss or more demand needs more capacity) is not feasible there and is left out.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

from dcopt.common import provenance
from dcopt.heat.network import (
    Instance,
    Params,
    build_instance,
    default_scenarios,
    ishikari_sources,
    seeded_plan,
    solve,
    solve_kernel,
    solver_name,
)
from dcopt.heat.v1 import ishikari_sites

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "input_sensitivity"
M = 1e6

# (group, input, value in the model, [(label of the changed value, change)], where the range comes from)
# A change is a dict: Params fields, or "pipe_cost" (factor on every pipe size), "demand" (factor on
# every user's yearly demand), "demand_of" ({kind: factor}), "peak_of" ({kind: peak factor}), "it_load"
# (factor on every data center's IT load) or "kerosene_low" (the price in the low-price scenarios).
CASES = [
    ("network", "Network heat loss (ambient loop)", "2 %",
     [("3.7 %", {"loss_ambient": 0.037}), ("4.5 %", {"loss_ambient": 0.045})],
     "published loss coefficients applied to the plan's own pipes: pair pipes, insulation series 2 and 1 (dcopt.heat.loss)"),
    ("network", "Pipe cost per metre", "2019 quotes",
     [("x 1.22", {"pipe_cost": 1.22}), ("x 1.5", {"pipe_cost": 1.5})],
     "construction cost deflator FY2019 to FY2025; paved streets against open ground"),
    ("network", "Pipe life", "30 years",
     [("40 years", {"years": 40}), ("45 years", {"years": 45})],
     "technical life in the Swiss and Danish planning data"),
    ("finance", "Discount rate", "3 %",
     [("1 %", {"rate": 0.01}), ("4 %", {"rate": 0.04})],
     "reference value and standard value of the public project appraisal guideline"),
    ("heat pump", "Heat-pump life", "20 years",
     [("15 years", {"hp_years": 15}), ("25 years", {"hp_years": 25})],
     "range in the Danish technology data"),
    ("demand", "Greenhouse heat demand", "0.40 MWh/m2 a year",
     [("0.25", {"demand_of": {"greenhouse": 0.625, "new_greenhouse": 0.625}}),
      ("0.17", {"demand_of": {"greenhouse": 0.425, "new_greenhouse": 0.425}})],
     "calculated loads for Hokkaido greenhouses scaled to Sapporo: 0.17 (multi-span with curtain) to 0.40"),
    ("demand", "Snow-melting heat demand", "0.12 MWh/m2 a year",
     [("0.20", {"demand_of": {"snow": 0.20 / 0.12}})],
     "design load 250 W/m2 over 600 to 800 hours of operation: 0.15 to 0.24"),
    ("demand", "Fish-farm heat demand", "5,000 MWh a year",
     [("1,000", {"demand_of": {"aquaculture": 0.2}}), ("500", {"demand_of": {"aquaculture": 0.1}})],
     "a documented surplus-heat system with a sturgeon farm in Hokkaido delivers about 1,000 MWh a year in all"),
    ("demand", "Peak factor of schools and public buildings", "2.0",
     [("3.0", {"peak_of": {"school": 3.0, "public": 3.0}})],
     "hourly load patterns of buildings used in the daytime only: about 3 to 4"),
    ("demand", "All yearly demands", "as assumed",
     [("x 0.7", {"demand": 0.7}), ("x 1.3", {"demand": 1.3})],
     "a common factor on every user, for the spread between buildings of one type"),
    ("supply", "Recoverable share of the IT heat", "0.6",
     [("0.33", {"recovery": 0.33}), ("0.9", {"recovery": 0.9})],
     "an operating air-cooled case captures about a third; reviews put the ceiling near 0.97"),
    ("supply", "Power actually drawn by the data centers", "the stated IT load, all year",
     [("half of it", {"it_load": 0.5})],
     "published load factors are about half of the installed IT capacity (IEA 2025; the Japanese association)"),
    ("supply", "Heat-pump efficiency (share of the Carnot COP)", "0.5",
     [("0.43", {"carnot_eff": 0.43}), ("0.6", {"carnot_eff": 0.6})],
     "40 to 60 % in the Danish technology data, 43 to 50 % for waste-heat units"),
    ("supply", "Electricity price for the heat pumps", "25 yen/kWh",
     [("30 yen/kWh", {"power_yen_kwh": 30.0}), ("34 yen/kWh", {"power_yen_kwh": 34.0})],
     "high-voltage tariff of Hokkaido Electric Power from November 2026 with the basic charge, before tax: 28 to 34"),
    ("supply", "Heat from a litre of kerosene (heating value x boiler efficiency)", "9.7 kWh x 0.85 = 8.2 kWh",
     [("7.6 kWh", {"boiler_eff": 7.6 / 9.7}), ("8.7 kWh", {"boiler_eff": 8.7 / 9.7})],
     "gross heating value 10.17 kWh/L x 75 to 86 % measured on boilers in use in Hokkaido"),
    ("supply", "Kerosene price in the low-price scenarios", "115 yen/L",
     [("135 yen/L", {"kerosene_low": 135.0})],
     "wholesale and large-lorry prices in Hokkaido, autumn 2026, with tax: about 123 to 137 yen/L"),
    ("sites", "Assumed sites (fish farm, road heating, new greenhouses)", "included",
     [("fish farm left out", {"demand_of": {"aquaculture": 0.0}}),
      ("all left out", {"demand_of": {"aquaculture": 0.0, "snow": 0.0, "new_greenhouse": 0.0}})],
     "these sites do not exist today; the others are facilities on the map with an assumed demand"),
]

_STATE: dict = {}


SPECIAL = ("pipe_cost", "demand", "demand_of", "peak_of", "it_load", "kerosene_low")


def changed(inst: Instance, P: Params, scens: list, change: dict) -> tuple[Instance, Params, list]:
    P2 = replace(P, **{k: v for k, v in change.items() if k not in SPECIAL})
    if "peak_of" in change:
        P2 = replace(P2, peak_factor={**P.peak_factor, **change["peak_of"]})
    if "pipe_cost" in change:
        P2 = replace(P2, sizes=tuple(replace(s, yen_m=s.yen_m * change["pipe_cost"]) for s in P.sizes))
    if "demand" in change or "demand_of" in change:
        by_kind = change.get("demand_of", {})
        users = [replace(u, annual_mwh=u.annual_mwh * change.get("demand", 1.0) * by_kind.get(u.kind, 1.0))
                 for u in inst.users]
        inst = replace(inst, users=users)
    if "it_load" in change:
        inst = replace(inst, sources=[replace(s, it_mw={k: v * change["it_load"] for k, v in s.it_mw.items()})
                                      for s in inst.sources])
    if "kerosene_low" in change:
        low = min(s.kerosene_yen_l for s in scens)
        scens = [replace(s, kerosene_yen_l=change["kerosene_low"]) if s.kerosene_yen_l == low else s for s in scens]
    return inst, P2, scens


def describe(plan) -> dict:
    return {"net_m": plan.expected_net / M, "sites": len(plan.connected), "km": plan.pipe_m / 1000,
            "capex_m": plan.capex / M, "status": plan.status}


def frozen(plan) -> dict:
    """What is needed to evaluate a plan's pipes under other inputs."""
    return {"E": plan.E, "build": plan.build(), "peak": plan.ud.peak}


def _init(inst, P, scens, links) -> None:
    _STATE.update(inst=inst, P=P, scens=scens, links=links)


def _replan(job: tuple) -> dict:
    change = job[4]
    inst2, P2, scens2 = changed(_STATE["inst"], _STATE["P"], _STATE["scens"], change)
    t0 = time.perf_counter()
    plan = solve_kernel(inst2, P2, scens2, extra_edges=_STATE["links"])
    return {"plan": frozen(plan), "found": describe(plan), "seconds": time.perf_counter() - t0}


def _evaluate(task: tuple) -> dict | None:
    change, build = task
    inst2, P2, scens2 = changed(_STATE["inst"], _STATE["P"], _STATE["scens"], change)
    try:
        return describe(solve(inst2, P2, scens2, edges=build["E"], fix=build["build"], design_peak=build["peak"]))
    except RuntimeError:                   # no solution: the pipes are too small under this value
        return None


def text(data: dict) -> str:
    b = data["base"]
    lines = ["# How far the published plan moves with each input", "",
             f"Published plan: {b['net_m']:.1f} M yen a year, {b['sites']} sites, {b['km']:.1f} km.", "",
             "| Input | In the model | Changed to | Published pipes kept (M yen/yr) | Best plan found (M yen/yr) | Its sites, km |",
             "|---|---|---|---|---|---|"]
    for r in data["rows"]:
        kept, best = r["published_kept"], r["best"]
        k = f"{kept['net_m']:.1f} ({kept['net_m'] - b['net_m']:+.1f})" if kept else "pipes too small"
        lines.append(f"| {r['input']} | {r['model']} | {r['value']} | {k} | {best['net_m']:.1f} "
                     f"({best['net_m'] - b['net_m']:+.1f}) | {best['sites']}, {best['km']:.1f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", default="", help="comma-separated groups to run (default: all)")
    args = ap.parse_args()
    sakura, sites = ishikari_sites()
    inst = build_instance(ishikari_sources(sakura), sites)
    P = Params(mode="ambient", time_limit=60)
    scens = default_scenarios()
    t0 = time.perf_counter()
    base, links = seeded_plan(inst, P, scens)
    print(f"published plan: {describe(base)}  [{time.perf_counter() - t0:.0f} s]", flush=True)
    groups = {g for g in args.only.split(",") if g}
    jobs = [(g, name, mv, label, change, basis) for g, name, mv, values, basis in CASES
            if not groups or g in groups for label, change in values]
    with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(inst, P, scens, links)) as pool:
        found = list(pool.map(_replan, jobs))
        for job, f in zip(jobs, found):
            print(f"  searched: {job[1]} -> {job[3]}: {f['found']['net_m']:.1f} ({f['found']['sites']} sites, "
                  f"{f['found']['km']:.1f} km) [{f['seconds']:.0f} s]", flush=True)
        published = frozen(base)
        tasks, owner = [], []
        for i, job in enumerate(jobs):                         # every plan of the same input, under this value
            same_input = [found[j]["plan"] for j, other in enumerate(jobs) if other[1] == job[1]]
            for build in [published, *same_input]:
                tasks.append((job[4], build))
                owner.append(i)
        scored = list(pool.map(_evaluate, tasks))
    rows = []
    for i, job in enumerate(jobs):
        mine = [s for s, o in zip(scored, owner) if o == i]
        feasible = [s for s in mine if s is not None]
        best = max(feasible, key=lambda s: s["net_m"])
        rows.append({"group": job[0], "input": job[1], "model": job[2], "value": job[3], "change": job[4],
                     "basis": job[5], "published_kept": mine[0], "best": best, "searched": found[i]["found"]})
    OUT.mkdir(parents=True, exist_ok=True)
    stored = OUT / "summary.json"
    if groups and stored.exists():                             # a partial run replaces its groups in the stored table
        old = [r for r in json.loads(stored.read_text(encoding="utf-8"))["rows"] if r["group"] not in groups]
        order = {name: i for i, (_, name, *_rest) in enumerate(CASES)}
        rows = sorted(old + rows, key=lambda r: order.get(r["input"], len(order)))
    data = {"provenance": provenance.stamp(solver=solver_name(P)), "base": describe(base), "rows": rows}
    (OUT / "summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "summary.md").write_text(text(data), encoding="utf-8")
    print(text(data))


if __name__ == "__main__":
    main()
