"""Weather-year scenarios for the heat network: does the plan survive real weather?

The published results hold demand at the JMA climate normals (one average year) and vary only the
IT load and the kerosene price (4 scenarios). This experiment replaces that single average year
with the real weather of every year 1976-2025 (JMA daily observations for Sapporo, dcopt.heat.weather):
each year rescales and reshapes every user's monthly demand, and the network is sized once for the
worst year's peak. Two stages:

  A  weather risk at the headline config: N weather-year scenarios (IT high, kerosene 156.8 yen/L).
  B  the full cross: a stratified subset of years x the four published IT x kerosene levels.

For each stage: the stochastic plan (RP), the plan built for the mean scenario evaluated on the
same set (EEV), the value of the stochastic solution VSS = RP - EEV, and the same set evaluation
of the published weather-free 4-scenario plan. Tail risk: the worst year and the 5 % CVaR of the
annual net benefit. `--evpi` also solves every scenario's own optimum (wait-and-see), which costs
one extra solve per scenario.

Run: uv run python experiments/weather_years/run.py [ambient|central] [--stage a|b|both] [--evpi]
Data: uv run python -m dcopt.heat.weather 1976 2025   (one-time; the years ship in data/jma/, fetch only to extend)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from dcopt.common.geo import use_overpass_mirror
from dcopt.heat import weather as W
from dcopt.heat.network import (Params, Scenario, build_instance, default_scenarios,
                                evaluate, ishikari_sources, mean_scenario, plan_for, solve_kernel,
                                user_data)
from dcopt.heat.v1 import ishikari_sites

MODE = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("ambient", "central") else "ambient"
STAGE = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ("a", "b", "both") else "both"
WITH_EVPI = "--evpi" in sys.argv
WITH_BOUND = "--bound" in sys.argv   # LP relaxation bound of each stage's first-stage model
FULL = float(next((a.split("=")[1] for a in sys.argv if a.startswith("--full=")), 0.0))
M = 1e6
YEARS = (1976, 2025)

use_overpass_mirror()
if not W.year_csv(YEARS[0]).exists() or not W.year_csv(YEARS[1]).exists():
    print(f"fetching JMA daily data {YEARS[0]}-{YEARS[1]} (one-time, ~10 min)...", flush=True)
    subprocess.run([sys.executable, "-m", "dcopt.heat.weather", *map(str, YEARS)], check=True)
years = W.load_years(*YEARS)
checks = W.validate_normals(years)
print(f"weather years {YEARS[0]}-{YEARS[1]}: {len(years)}; normals check {checks}", flush=True)

sakura, sites = ishikari_sites()
inst = build_instance(ishikari_sources(sakura), sites)
P = Params(mode=MODE, time_limit=60.0)

# seed links: each data center's own plan on the published 4-scenario set (as in the README's
# headline plans, heat_v2_compare). Seeds from a different scenario set change the kernel search.
t0 = time.perf_counter()
extra_set: set[tuple[int, int]] = set()
for d in range(inst.D):
    one = inst.subset([d], list(range(inst.U)))
    o = solve_kernel(one, P, default_scenarios())
    extra_set |= set(one.lift([(a, b) for a, b, _, _ in o.built]))
extra = sorted(extra_set)
print(f"seed links: {len(extra)} in {time.perf_counter() - t0:.0f}s", flush=True)


def stats(plan, scens, name: str) -> dict:
    """Expected net, worst year, CVaR 5 %, unmet demand and the per-scenario nets of one plan on one
    scenario set. The unmet share is convention-free: deliveries against each scenario's own demand."""
    net = np.array(plan.net)
    p = np.array([s.prob for s in scens])
    order = np.argsort(net)
    tail = max(1, int(round(0.05 * len(net))))
    delivered = plan.s.sum(axis=(0, 1, 2)) if plan.s.size else np.zeros(len(scens))
    asked = plan.ud.demand.sum(axis=(0, 1))
    unmet = np.clip(1.0 - delivered / np.maximum(asked, 1e-9), 0.0, 1.0)
    return {"name": name, "expected": float(p @ net), "worst": float(net.min()),
            "cvar5": float(net[order[:tail]].mean()), "median": float(np.median(net)),
            "unmet_expected": float(p @ unmet), "unmet_worst": float(unmet.max()),
            "sites": len(plan.connected), "km": plan.pipe_m / 1000,
            "capex_oku": plan.capex / 1e8, "per_scenario": net.tolist()}


def convention_check(scens: list[Scenario]) -> dict:
    """How hard the build-independent cap convention bites on this set: users whose smallest
    fitting pipe size rises against the set's mean scenario, and users no pipe in the ladder can
    carry (they are excluded, not partially served). Cheap (no solver) and decisive."""
    from dcopt.heat.network import smallest_size
    udm = user_data(inst, P, [mean_scenario(scens, inst.sources)])
    ud = user_data(inst, P, scens)
    dn = lambda q: (lambda i: P.sizes[i].dn if i is not None else None)(smallest_size(P, q))
    rose = sum(1 for a, b in zip(udm.q, ud.q)
               if (db := dn(b)) is not None and (da := dn(a)) is not None and db > da)
    unconnectable = sum(1 for q in ud.q if dn(q) is None)
    return {"users": int(inst.U), "size_class_rises": rose, "unconnectable_at_design_peak": unconnectable,
            "q_ratio_mean_of": round(float(np.mean(ud.q / np.maximum(udm.q, 1e-9))), 3)}


def run_stage(name: str, scens: list[Scenario], baseline_plans: dict[str, str]) -> dict:
    """RP and EEV on one scenario set; every plan re-evaluated on the same set."""
    t = time.perf_counter()
    rp = plan_for(inst, P, scens, extra_edges=extra, full_time=FULL)
    ev = plan_for(inst, P, [mean_scenario(scens, inst.sources)], extra_edges=extra, full_time=FULL)
    eev = evaluate(ev, scens)
    gap = lambda pl: float((pl.kernel or {}).get("gap") or 0.0)   # noqa: E731 - kernel dict is optional
    out = {"seconds": round(time.perf_counter() - t, 1),
           "gap_rp": gap(rp), "gap_ev": gap(ev),
           "convention_check": convention_check(scens),
           "plans": {"rp": stats(rp, scens, "RP (stochastic)"), "eev": stats(eev, scens, "EEV (mean plan)")},
           "vss": rp.expected_net - eev.expected_net}
    if WITH_EVPI:
        own = [plan_for(inst, P, [sc], extra_edges=extra, full_time=FULL) for sc in scens]
        ws = float(sum(sc.prob * max(float(o.expected_net), float(rp.net[i]), float(eev.net[i]))
                       for i, (sc, o) in enumerate(zip(scens, own))))
        out["ws"], out["evpi"] = ws, ws - rp.expected_net
    if WITH_BOUND:   # the LP bound tells whether the mean-built plan is even inside this stage's model
        from dcopt.heat.network import lp_relaxation
        bnd, _e, _y = lp_relaxation(inst, P, scens)
        out["lp_bound"] = bnd
        print(f"  LP bound {bnd / M:.1f}M vs EEV plan {out['plans']['eev']['expected'] / M:.1f}M -> "
              f"{'EEV outside the model (cap convention excludes it)' if bnd < out['plans']['eev']['expected'] else 'EEV inside: kernel gap, not exclusion'}",
              flush=True)
    for label, key in baseline_plans.items():        # the published weather-free plans on this set
        base = PLAN_CACHE[key]
        out["plans"][label] = stats(evaluate(base, scens), scens, label)
    print(f"{name}: RP {out['plans']['rp']['expected'] / M:.1f}M  EEV {out['plans']['eev']['expected'] / M:.1f}M  "
          f"VSS {out['vss'] / M:.1f}M  worst {out['plans']['rp']['worst'] / M:.1f}M  "
          f"CVaR5 {out['plans']['rp']['cvar5'] / M:.1f}M  unmet {out['plans']['rp']['unmet_expected'] * 100:.1f}%"
          f"/{out['plans']['rp']['unmet_worst'] * 100:.1f}%  gaps {out['gap_rp']:.3f}/{out['gap_ev']:.3f} "
          f"({out['seconds']}s, {len(rp.connected)} sites, {rp.pipe_m / 1000:.1f} km)", flush=True)
    print(f"  convention check on this set: {out['convention_check']}", flush=True)
    return out


# the published weather-free plans, once: the 4-scenario stochastic plan and its mean-scenario plan
print("solving the published 4-scenario plans (weather-free)...", flush=True)
t = time.perf_counter()
PLAN_CACHE = {"sp4": plan_for(inst, P, default_scenarios(), extra_edges=extra),
              "ev4": plan_for(inst, P, [mean_scenario(default_scenarios(), inst.sources)], extra_edges=extra)}
PLAN_CACHE["ev4x"] = evaluate(PLAN_CACHE["ev4"], default_scenarios())
print(f"  4-scenario RP {PLAN_CACHE['sp4'].expected_net / M:.1f}M, {len(PLAN_CACHE['sp4'].connected)} sites, "
      f"{PLAN_CACHE['sp4'].pipe_m / 1000:.1f} km in {time.perf_counter() - t:.0f}s")
print(f"  replication of the published numbers: RP {PLAN_CACHE['sp4'].expected_net / M:.1f}M (93.8), "
      f"EEV {PLAN_CACHE['ev4x'].expected_net / M:.1f}M (79.0), "
      f"VSS {(PLAN_CACHE['sp4'].expected_net - PLAN_CACHE['ev4x'].expected_net) / M:.1f}M (14.8)")

results: dict = {"mode": MODE, "years": list(YEARS), "normals_check": checks,
                 "published_replication": {
                     "rp": PLAN_CACHE["sp4"].expected_net, "eev": PLAN_CACHE["ev4x"].expected_net,
                     "vss": PLAN_CACHE["sp4"].expected_net - PLAN_CACHE["ev4x"].expected_net,
                     "published": {"rp": 93.8e6, "eev": 79.0e6, "vss": 14.8e6}},
                 "weather_index_stats": {
                     "hdd18": [round(min(w.hdd18_index for w in years), 3), round(max(w.hdd18_index for w in years), 3)],
                     "snow": [round(min(w.snow_index for w in years), 3), round(max(w.snow_index for w in years), 3)]},
                 "stages": {}}

if STAGE in ("a", "both"):
    scens_a = [Scenario(f"y{w.year}", f"{w.year}年・高負荷・156.8円/L", f"{w.year}, IT high, 156.8 yen/L",
                        1.0 / len(years), 156.8, "high", None, w) for w in years]
    results["stages"]["a"] = run_stage(
        f"A ({len(scens_a)} weather years, IT high, 156.8 yen/L)", scens_a,
        {"published-4-plan": "sp4", "published-mean-plan": "ev4x"})

if STAGE in ("b", "both"):
    # stratified years: the union of HDD18 and snowfall quantiles at 5/25/50/75/95 %
    def pick(values, qs):
        order = np.argsort(values)
        return {years[order[int(q * (len(order) - 1))]].year for q in qs}

    qs = [0.05, 0.25, 0.5, 0.75, 0.95]
    sel = sorted(pick([w.hdd18_index for w in years], qs) | pick([w.snow_index for w in years], qs))
    wy = [w for w in years if w.year in sel]
    scens_b = []
    for w in wy:
        for lv, price in (("low", 115.0), ("low", 156.8), ("high", 115.0), ("high", 156.8)):
            scens_b.append(Scenario(f"y{w.year}-{lv}-{price:g}", f"{w.year}年・{lv}・{price:g}円/L",
                                    f"{w.year}, IT {lv}, {price:g} yen/L", 1.0 / (4 * len(wy)), price, lv, None, w))
    results["stages"]["b"] = {"years": sel}
    results["stages"]["b"].update(run_stage(
        f"B ({len(scens_b)} scenarios: {len(sel)} years x 4)", scens_b,
        {"published-4-plan": "sp4", "published-mean-plan": "ev4x"}))

out_dir = Path(__file__).resolve().parents[2] / "results" / "weather_years" / datetime.now().strftime("%Y%m%d-%H%M%S")
out_dir.mkdir(parents=True, exist_ok=True)
commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
results["git_commit"] = commit
results["solver"] = P.solver or "highs (default)"
(out_dir / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
for stage, st in results["stages"].items():
    (out_dir / f"stage_{stage}_nets.csv").write_text(
        "plan,scenario,net_m_yen\n" + "\n".join(
            f"{label},{i},{v / M:.3f}" for label, r in st["plans"].items()
            for i, v in enumerate(r["per_scenario"])), encoding="utf-8")
print(f"results -> {out_dir}")
