"""What the waste heat of a new data center is worth, by location.

For a candidate site the regional heat plan of theme 1 is solved twice on the same instance: the
existing data centers plus the candidate. In the first solve the candidate has no IT load, so it
supplies nothing; in the second it has its load. The difference of the two expected net benefits
is the value of the candidate's waste heat:

    h_j(L) = N*(existing data centers + a data center of L MW at site j) - N*(existing data centers)

Keeping the search out of the comparison (the plans come from a heuristic search):
  - both sides live on the same instance, so the plan without the candidate is a feasible plan with
    it, and the value can never be negative;
  - the plan without the candidate is the published regional plan, carried over link by link, the
    same for every site;
  - the search for the plan with the candidate gets that plan's links and the links of the
    candidate's own best plan as extra candidates.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace

import numpy as np

from dcopt.heat.network import Instance, Params, Plan, Scenario, Source, build_instance, solve, solve_kernel
from dcopt.heat.v1 import Site

LOW_SHARE = 0.6        # assumption: the low IT-load scenario of a new data center, as for data center No. 1 (6 of 10 MW)


def candidate_source(lon: float, lat: float, mw: float, key: str = "candidate") -> Source:
    """A data center of `mw` MW of IT load at (lon, lat); its low-load scenario is LOW_SHARE of that."""
    return Source(key, "新しいデータセンター（候補地）", "New data center (candidate site)", lon, lat,
                  {"low": LOW_SHARE * mw, "high": mw}, "planned",
                  ("仮定：立地の候補地", "Assumption: a candidate site of the siting study"),
                  f"assumption: {mw:g} MW of IT load ({LOW_SHARE:.0%} of it in the low scenario) at ({lat:.4f}, {lon:.4f})")


def carry_over(base: Plan, inst: Instance) -> tuple[list[tuple[int, int]], dict]:
    """The build of `base` (on the existing data centers) in the node numbering of `inst`, which has
    more data centers appended after them: users move up by that many indices, the existing data
    centers keep theirs."""
    d0, extra = base.inst.D, inst.D - base.inst.D
    if extra < 1 or inst.U != base.inst.U:
        raise ValueError("the instance must be the base instance plus appended data centers")
    edges = [(a if a < d0 else a + extra, b if b < d0 else b + extra) for a, b in base.E]
    return edges, base.build()


@dataclass
class HeatValue:
    value: float                 # yen per year: expected net benefit with the candidates minus without
    base_net: float              # expected net benefit of the plan without the candidates
    net: float                   # expected net benefit of the plan with the candidates
    sites: int                   # sites connected in the plan with the candidates
    sites_from_candidate: int    # of which served by a candidate
    pipe_km: float
    heat_from_candidate: float   # MWh per year delivered from the candidates (expected)
    seconds: float
    plan: Plan | None = None


def heat_value_of(base: Plan, base_links: list[tuple[int, int]], users: list[Site],
                  places: list[tuple[float, float, float]], P: Params, scens: list[Scenario],
                  build=build_instance, keep_plan: bool = False) -> HeatValue:
    """The joint value of the waste heat of new data centers at `places`: (lon, lat, MW) each.

    base: the regional plan on the existing data centers (for example from seeded_plan), with its
    seed links `base_links`. build(sources, users) makes the instance; tests pass a synthetic one."""
    t0 = time.perf_counter()
    d0, extra = base.inst.D, len(places)
    sources = [replace(s) for s in base.inst.sources]
    new = [candidate_source(lon, lat, mw, key=f"candidate{i + 1}") for i, (lon, lat, mw) in enumerate(places)]
    inst = build(sources + new, users)
    edges0, build0 = carry_over(base, inst)
    kept = solve(inst, P, scens, edges=edges0, fix=build0, design_peak=base.ud.peak)       # the base plan, candidates unused
    seeds = {(a if a < d0 else a + extra, b if b < d0 else b + extra) for a, b in base_links} | set(edges0)
    for d in range(d0, d0 + extra):                                                       # each candidate's own best plan
        own = inst.subset([d], list(range(inst.U)))
        own_plan = solve_kernel(own, P, scens)
        seeds |= set(own.lift([(a, b) for a, b, _, _ in own_plan.built]))
    found = solve_kernel(inst, P, scens, extra_edges=sorted(seeds))
    best = found if found.expected_net >= kept.expected_net else kept
    from_candidates = best.s[:, d0:].sum(axis=(0, 1, 2))                                   # W: MWh per scenario
    served = int(((best.assign >= d0) & (best.x > 0.5)).sum())
    return HeatValue(
        value=best.expected_net - kept.expected_net, base_net=kept.expected_net, net=best.expected_net,
        sites=len(best.connected), sites_from_candidate=served, pipe_km=best.pipe_m / 1000,
        heat_from_candidate=float(best.p @ np.atleast_1d(from_candidates)),
        seconds=time.perf_counter() - t0, plan=best if keep_plan else None)


def heat_value(base: Plan, base_links: list[tuple[int, int]], users: list[Site], lon: float, lat: float, mw: float,
               P: Params, scens: list[Scenario], build=build_instance, keep_plan: bool = False) -> HeatValue:
    """The value of the waste heat of one new data center of `mw` MW at (lon, lat)."""
    return heat_value_of(base, base_links, users, [(lon, lat, mw)], P, scens, build, keep_plan)
