"""Export model v2 plans (theme 1) for drawing: pipes with sizes and monthly flows, sites, data centers.

Solves the expected (stochastic) plan and the robust plan (budget Gamma = 1) in the ambient mode with
heat-pump investment, and writes out/heat_network_v2/plans.json. The animated README figure is drawn
from it by scripts/render_readme_animation.py.

Run: uv run python scripts/export_heat_network_v2.py
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from dcopt.common.geo import road_path, use_overpass_mirror
from dcopt.heat.network import (KEROSENE_SURVEY, BudgetSet, Params, build_instance, ccg, default_scenarios,
                                evaluate, ishikari_sources, seeded_plan, solve_kernel)
from dcopt.heat.v1 import MONTHS_EN, TEMP, ishikari_sites

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "heat_network_v2"
ASSUMED = {"new_greenhouse", "aquaculture", "snow"}


def r5(x: float) -> float:
    return round(float(x), 5)


def export_plan(plan, label: str) -> dict:
    inst, P = plan.inst, plan.P
    nE = len(plan.E)
    prob = plan.p
    nodes = [s.node for s in inst.sources] + [u.node for u in inst.users]
    served = np.einsum("udtw,w->udt", plan.s, prob)          # expected MWh per user, data center, month
    per_user = served.sum(axis=1)                             # users x months
    pipes = []
    for e, (a, b) in enumerate(plan.E):
        if plan.y[e].max() <= 0.5:
            continue
        k = int(np.argmax(plan.y[e]))
        fwd = plan.g[:, e] if nE else np.zeros(inst.U)
        bwd = plan.g[:, e + nE] if nE else np.zeros(inst.U)
        monthly = per_user.T @ (fwd + bwd)                    # months: heat carried through this link
        path = road_path(nodes[a], nodes[b])                  # (lat, lon) from a to b
        if float(per_user.sum(axis=1) @ bwd) > float(per_user.sum(axis=1) @ fwd):
            path = list(reversed(path))                       # draw in the direction the heat flows
        if len(path) < 2:
            path = list(path) * 2
        pipes.append({"path": [[r5(lon), r5(lat)] for lat, lon in path], "dn": P.sizes[k].dn,
                      "km": round(float(inst.dist[a, b]) / 1000, 2), "monthly": [round(float(v)) for v in monthly]})
    sites = []
    for u, s in enumerate(inst.users):
        d = int(plan.assign[u])
        sites.append({"name_en": s.name_en, "kind": s.kind, "lon": r5(s.lon), "lat": r5(s.lat),
                      "annual": round(s.annual_mwh), "assumed": s.kind in ASSUMED,
                      "dc": inst.sources[d].key if plan.x[u] > 0.5 else None,
                      "served": [round(float(v)) for v in per_user[u]]})
    waste = np.einsum("dtw,w->t", plan.W, prob)
    return {"label": label, "pipes": pipes, "sites": sites,
            "delivered_month": [round(float(v)) for v in per_user.sum(axis=0)],
            "waste_month": [round(float(v)) for v in waste],
            "kpi": {"sites": len(plan.connected), "km": round(plan.pipe_m / 1000, 1),
                    "expected_net_m": round(plan.expected_net / 1e6, 1), "per_dc": plan.sites_per_dc(),
                    "km_by_dn": {str(k): round(v, 1) for k, v in plan.km_by_dn().items()}}}


def main() -> None:
    use_overpass_mirror()
    OUT.mkdir(parents=True, exist_ok=True)
    sakura, sites = ishikari_sites()
    inst = build_instance(ishikari_sources(sakura), sites)
    P = Params(mode="ambient", time_limit=60)
    scens = default_scenarios()
    expected, extra = seeded_plan(inst, P, scens)        # seed links: each data center's own plan
    robust = evaluate(ccg(inst, P, BudgetSet(budget=1), extra_edges=extra)["plan"], scens)
    today = [replace(s, prob=0.5) for s in scens if s.kerosene_yen_l == KEROSENE_SURVEY]
    current = solve_kernel(inst, P, today, extra_edges=extra)                # at today's kerosene price
    data = {
        "months": MONTHS_EN, "temp": TEMP,
        "dcs": [{"key": s.key, "name_en": s.name_en, "lon": r5(s.lon), "lat": r5(s.lat), "status": s.status,
                 "where": s.where[1]} for s in inst.sources],
        "plans": {"expected": export_plan(expected, "Expected plan (stochastic), ambient loop"),
                  "robust": export_plan(robust, "Robust plan (budget 1), ambient loop"),
                  "current": export_plan(current, "Plan at today's kerosene price (156.8 yen/L), ambient loop")},
        "note": "Model v2, ambient loop, heat-pump investment included; several sites and data-center "
                "positions are assumptions or placeholders. Map data (c) OpenStreetMap contributors (ODbL).",
    }
    (OUT / "plans.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for key, p in data["plans"].items():
        print(key, p["kpi"], "pipes", len(p["pipes"]))


if __name__ == "__main__":
    main()
