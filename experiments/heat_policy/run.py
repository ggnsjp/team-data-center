"""Warm Ishikari: what a carbon price or an investment subsidy changes in the regional plan.

    uv run python experiments/heat_policy/run.py                    # ambient loop, HiGHS
    uv run python experiments/heat_policy/run.py --mode central --workers 8
    DCOPT_SOLVER=gurobi uv run python experiments/heat_policy/run.py --workers 4   # optional check

The plans come from a heuristic search, and a search can land on different plans for reasons that
have nothing to do with the policy. To keep that out of the comparison, every policy is given the
same chances:
  1. Candidate links. The links of the published plan (seeded_plan) plus the links of each data
     center's own plan under the strongest carbon price and the strongest subsidy; the same set
     for every policy.
  2. Pool. Kernel search for every policy, once on the published links and once on the full set.
  3. Cross-evaluation. Every build in the pool is evaluated under every policy (pipes fixed,
     deliveries re-optimized), and each policy takes the best build for its own objective.
  4. Polish. The full MILP on all candidate links, started from that build, with a time limit;
     the polished builds join the pool and step 3 is repeated.
After step 4 no policy would prefer another policy's plan, so the no-policy plan has the largest
plain net benefit of all and the cost of the extra tonnes is never negative.

Reported for each policy:
  net to the project   expected value of the heat (with the carbon price) minus the project's share
                       of the annual cost (after the subsidy)
  plain net            the same plan with no carbon price and no subsidy
  cost of extra tonne  (plain net of the no-policy plan - plain net of this plan) / extra CO2 avoided
  subsidy per extra t  the subsidy as an annuity (the same factors as the costs) / extra CO2 avoided:
                       public money per additional tonne, since part of a subsidy pays for pipes that
                       would be built anyway
  gap                  distance to the best bound of the full MILP on the candidate links

Needs the Ishikari map data (data/cache/ishikari). Results go to results/heat_policy/<timestamp>/.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dcopt.common.geo import use_overpass_mirror
from dcopt.heat.network import (
    Params,
    build_instance,
    candidate_edges,
    default_scenarios,
    ishikari_sources,
    seeded_plan,
    solve,
    solve_kernel,
    solver_name,
    user_data,
)
from dcopt.heat.v1 import GRID_SCENARIOS, ishikari_sites

ROOT = Path(__file__).resolve().parents[2]
M = 1e6
# Carbon prices in yen per t CO2, on top of today's fuel taxes. 1,700 and 4,300 are the lower and upper
# reference prices of Japan's emissions trading scheme for FY2026 (METI notification No. 27 of 2026);
# 10,000 and 20,000 are higher levels for comparison.
CARBON = (0, 1700, 4300, 10000, 20000)
# Shares of the investment. Programmes that name such equipment pay 1/3 to 2/3 (see docs/data-sources.md).
SUBSIDY = (1 / 3, 1 / 2, 2 / 3)
POLICIES = ([(c, 0.0) for c in CARBON] + [(0, s) for s in SUBSIDY] + [(4300, 1 / 2)])


def own_plan_links(args) -> list[tuple[int, int]]:
    inst, P, scens, d = args
    one = inst.subset([d], list(range(inst.U)))
    plan = solve_kernel(one, P, scens)
    return one.lift([(a, b) for a, b, _, _ in plan.built])


def kernel_build(args) -> dict:
    inst, P, scens, links = args
    plan = solve_kernel(inst, P, scens, extra_edges=links)
    return {"E": plan.E, "build": plan.build()}


def metrics(plan) -> dict:
    P = plan.P
    full_cost = P.crf * plan.capex_pipes + P.crf_hp * plan.capex_hp
    co2 = plan.co2_scenarios()
    return {"sites": len(plan.connected), "per_dc": plan.sites_per_dc(), "km": plan.pipe_m / 1000,
            "heat_mwh": float(plan.p @ plan.delivered), "electricity_mwh": float(plan.p @ plan.electricity),
            **{f"co2_{k}": v for k, v in co2.items()}, "co2_model": float(plan.p @ plan.co2),
            "capex": plan.capex, "subsidy_yen": plan.subsidy_yen, "full_cost": full_cost,
            "subsidy_per_year": P.subsidy * full_cost,
            "carbon_value": float(plan.p @ plan.carbon_value), "net_project": plan.expected_net,
            "plain_net": float(plan.p @ (plan.value - plan.carbon_value)) - full_cost,
            "payback": plan.payback, "abatement_yen_t": plan.abatement_yen_t,
            "connected": [plan.inst.users[u].key for u in plan.connected]}


def evaluate_build(args) -> dict:
    inst, P, scens, item, peak = args
    return metrics(solve(inst, P, scens, edges=item["E"], fix=item["build"], design_peak=peak))


def polish(args) -> dict:
    inst, P, scens, item, peak, edges, seconds = args
    start = solve(inst, P, scens, edges=item["E"], fix=item["build"], design_peak=peak)
    plan = solve(inst, replace(P, time_limit=seconds), scens, edges=edges, start=start)
    if plan.expected_net < start.expected_net - 1.0:           # the start is always available as a fallback
        return {"E": item["E"], "build": item["build"], "bound": plan.dual_bound}
    return {"E": plan.E, "build": plan.build(), "bound": plan.dual_bound}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="ambient", choices=["ambient", "central"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--polish", type=float, default=120.0, help="seconds for the full MILP of each policy")
    args = ap.parse_args()

    use_overpass_mirror()
    t0 = time.perf_counter()
    sakura, sites = ishikari_sites()
    inst = build_instance(ishikari_sources(sakura), sites)
    P = Params(mode=args.mode)
    scens = default_scenarios()
    peak = user_data(inst, P, scens).peak
    policy_params = [replace(P, carbon_yen_t=float(c), subsidy=s) for c, s in POLICIES]
    print(f"instance: {inst.D} data centers, {inst.U} candidate sites; mode {args.mode}; solver {solver_name(P)}",
          flush=True)

    published, links = seeded_plan(inst, P, scens)
    print(f"published plan (no policy): E[net] {published.expected_net / M:.1f}M, {len(published.connected)} sites, "
          f"{published.pipe_m / 1000:.1f} km  [{time.perf_counter() - t0:.0f}s]", flush=True)
    pool = [{"E": published.E, "build": published.build()}]

    def best_per_policy(pool_now, executor) -> list[tuple[int, dict]]:
        jobs = [(inst, Q, scens, item, peak) for Q in policy_params for item in pool_now]
        res = list(executor.map(evaluate_build, jobs, chunksize=4))
        out = []
        for j in range(len(policy_params)):
            mine = res[j * len(pool_now):(j + 1) * len(pool_now)]
            k = max(range(len(pool_now)), key=lambda i: mine[i]["net_project"])
            out.append((k, mine[k]))
        return out

    with ProcessPoolExecutor(args.workers) as pool_exec:
        strongest = [replace(P, carbon_yen_t=float(max(CARBON))), replace(P, subsidy=max(SUBSIDY))]
        extra = pool_exec.map(own_plan_links, [(inst, Q, scens, d) for Q in strongest for d in range(inst.D)])
        union = sorted(set(links) | {e for es in extra for e in es})
        edges = sorted(set(candidate_edges(inst, P)) | set(union))
        print(f"candidate links: {len(links)} seeded + {len(union) - len(links)} from the strongest policies, "
              f"{len(edges)} in the full MILP  [{time.perf_counter() - t0:.0f}s]", flush=True)
        pool += list(pool_exec.map(kernel_build, [(inst, Q, scens, ls) for Q in policy_params for ls in (links, union)]))
        first = best_per_policy(pool, pool_exec)
        print(f"pool of {len(pool)} builds; best build per policy before polishing: {[k for k, _ in first]} "
              f"net {[round(m['net_project'] / M, 1) for _, m in first]}  [{time.perf_counter() - t0:.0f}s]", flush=True)
        polished = list(pool_exec.map(polish, [(inst, Q, scens, pool[k], peak, edges, args.polish)
                                               for Q, (k, _) in zip(policy_params, first)]))
        pool += [{"E": p["E"], "build": p["build"]} for p in polished]
        final = best_per_policy(pool, pool_exec)

    rows = []
    for (c, s), (k, m), p in zip(POLICIES, final, polished):
        m = dict(m, carbon_yen_t=float(c), subsidy=s, pool_index=k, bound=p["bound"],
                 gap=(p["bound"] - m["net_project"]) / max(abs(p["bound"]), 1e-9))
        rows.append(m)
    base = rows[0]
    for r in rows:
        extra_t = r["co2_model"] - base["co2_model"]
        r["extra_co2"] = extra_t
        r["cost_extra_tonne"] = (base["plain_net"] - r["plain_net"]) / extra_t if extra_t > 1e-6 else None
        r["subsidy_per_extra_tonne"] = r["subsidy_per_year"] / extra_t if extra_t > 1e-6 and r["subsidy"] > 0 else None

    print("\ncarbon  subsidy | sites   km   heat MWh | CO2 t/yr: renewable target2030 grid | invest  subsidy | "
          "carbon value  net to project  plain net | yen per extra t  subsidy per extra t | gap   build")
    for r in rows:
        cost = "-" if r["cost_extra_tonne"] is None else f"{r['cost_extra_tonne']:,.0f}"
        sub = "-" if r["subsidy_per_extra_tonne"] is None else f"{r['subsidy_per_extra_tonne']:,.0f}"
        print(f"{r['carbon_yen_t']:6,.0f}  {r['subsidy']:6.2f}  | {r['sites']:4d} {r['km']:5.1f} {r['heat_mwh']:9,.0f} | "
              f"{r['co2_renewable']:17,.0f} {r['co2_target2030']:10,.0f} {r['co2_grid']:6,.0f} | "
              f"{r['capex'] / 1e8:5.2f}  {r['subsidy_yen'] / 1e8:6.2f}  | {r['carbon_value'] / M:10.1f} "
              f"{r['net_project'] / M:14.1f} {r['plain_net'] / M:10.1f} | {cost:>15s} {sub:>20s} | {r['gap']:.3f} {r['pool_index']:4d}")
    print("\nelectricity scenarios (t CO2 per MWh): "
          + ", ".join(f"{k} {f:g}" for k, (_, _, f) in GRID_SCENARIOS.items()))
    print(f"no-policy plan: a tonne of CO2 avoided costs {base['abatement_yen_t']:,.0f} yen "
          "(negative: the plan pays for itself)")

    out = ROOT / "results" / "heat_policy" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=False).stdout.strip()
    (out / "policy.json").write_text(json.dumps(
        {"mode": args.mode, "solver": solver_name(P), "commit": commit, "candidate_links": len(edges),
         "published_net": published.expected_net, "polish_seconds": args.polish,
         "seconds": time.perf_counter() - t0, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(out / "policy.csv", "w", newline="", encoding="utf-8") as f:
        keys = [k for k in rows[0] if k not in ("per_dc", "connected")]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nwritten to {out.relative_to(ROOT)}  [{time.perf_counter() - t0:.0f}s]")


if __name__ == "__main__":
    main()
