"""Export the plan on today's facilities alone, for the business view of theme 1 (docs/heat-business.md).

The published plan (out/heat_network_v2/plans.json) connects two assumed sites, a fish farm and a
road-heating area, that do not exist today. This solves the plan without them, the way
experiments/input_sensitivity does ("assumed sites: all left out"): the yearly demand of the assumed
kinds is set to zero and the kernel search runs with the candidate links of the published plan.
A middle step keeps the road heating and gives the fish farm the yearly demand documented for a
fish farm in Hokkaido (1,000 MWh instead of 5,000, as in the sensitivity study). Writes
out/heat_business/plans.json in the format of the published export, plus the published plan as solved
here, so that a reader can see whether this machine reproduces it, and each plan's exact figures.

Run: uv run python scripts/export_heat_business.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from dcopt.common import provenance
from dcopt.common.geo import use_overpass_mirror
from dcopt.heat.network import Params, build_instance, default_scenarios, ishikari_sources, seeded_plan, solve_kernel
from dcopt.heat.v1 import ishikari_sites

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "heat_business"
ASSUMED = ("aquaculture", "snow", "new_greenhouse")      # as scripts/export_heat_network_v2.py
FISH_FARM_DOCUMENTED = 0.2      # 1,000 of the assumed 5,000 MWh a year (experiments/input_sensitivity, docs/input-evidence.md)

sys.path.insert(0, str(ROOT / "scripts"))
from export_heat_network_v2 import export_plan  # the same format as the published export


def main() -> None:
    use_overpass_mirror()
    OUT.mkdir(parents=True, exist_ok=True)
    sakura, sites = ishikari_sites()
    inst = build_instance(ishikari_sources(sakura), sites)
    P = Params(mode="ambient", time_limit=60)
    scens = default_scenarios()
    published, links = seeded_plan(inst, P, scens)
    today = replace(inst, users=[replace(u, annual_mwh=0.0) if u.kind in ASSUMED else u for u in inst.users])
    smaller = replace(inst, users=[replace(u, annual_mwh=u.annual_mwh * FISH_FARM_DOCUMENTED) if u.kind == "aquaculture"
                                   else u for u in inst.users])
    plans = {"existing": (solve_kernel(today, P, scens, extra_edges=links),
                          "Plan on today's facilities (assumed sites left out), ambient loop"),
             "documented_fish_farm": (solve_kernel(smaller, P, scens, extra_edges=links),
                                      "Plan with the road heating and a fish farm of 1,000 MWh a year, ambient loop"),
             "published_here": (published, "The published plan as solved on this machine")}
    data = {"plans": {key: export_plan(plan, label) for key, (plan, label) in plans.items()},
            "exact": {key: {"expected_net": plan.expected_net, "capex_pipes": plan.capex_pipes, "capex_hp": plan.capex_hp,
                            "bound": (plan.kernel or {}).get("bound"), "gap": (plan.kernel or {}).get("gap")}
                      for key, (plan, _) in plans.items()},
            "provenance": provenance.stamp(solver="highs (default)")}
    (OUT / "plans.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for key, p in data["plans"].items():
        print(key, p["kpi"])


if __name__ == "__main__":
    main()
