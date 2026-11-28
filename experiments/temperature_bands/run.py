"""Theme 1 with the heat above 60 C left out: steam and high-temperature heat at hospitals, hotels and
factories, which a 60 C supply cannot serve.

The model serves the whole yearly demand of hospitals, hotels and factories with water at 60 C. Part of it
is steam or hotter (sterilisation and humidification, kitchens, laundry, process heat). This takes that
part out of what the network can serve, with the shares found in published sources (docs/input-evidence.md):

  hospital  steam 49 % of the heat: five general hospitals in Kanto, Hokuriku and Kansai, measured
            2007-08 (Kuroda, Kawamura, Asaya, Hasehira 2009, SHASE annual meeting, doi 10.18948/
            shasetaikai.2009.2.0_1159: space heating 303, hot water 91, steam 383 MJ/m2 a year); 37 % with
            the paper's reference value for hot water (335) in place of the measured 91
  hotel     cooking 26 % of space heating, water heating and cooking (US lodging, EIA CBECS 2018, table E1:
            108, 111 and 76 trillion Btu); laundry steam is not separated there
  factory   heat at 100-400 C: 39 % of the useful heat of the food, drink and tobacco industry
            (EU-27 2009, JRC report EUR 25381, table 3.2.a: 162 of 418 PJ)

For the published plan and for the plan on today's facilities alone (assumed sites left out), it reports
the plan with its pipes kept and the plan made again with the kernel search, as experiments/
input_sensitivity does. Writes results/temperature_bands/summary.json. Takes about seven minutes.

Run: uv run python experiments/temperature_bands/run.py
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from dcopt.common import provenance
from dcopt.common.geo import use_overpass_mirror
from dcopt.heat import business as bz
from dcopt.heat.network import (
    Instance,
    Params,
    build_instance,
    default_scenarios,
    ishikari_sources,
    seeded_plan,
    solve,
    solve_kernel,
)
from dcopt.heat.v1 import ishikari_sites

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "temperature_bands"
sys.path.insert(0, str(ROOT / "scripts"))
from export_heat_network_v2 import ASSUMED, export_plan  # the same format as the published export

# the share of each kind's yearly heat that a 60 C supply can serve (1 - the share above 60 C)
CASES = {
    "published": {},
    "hospital steam 37 %": {"hospital": 0.63, "hotel": 0.74, "factory": 0.61},
    "hospital steam 49 %": {"hospital": 0.51, "hotel": 0.74, "factory": 0.61},
}


def servable(inst: Instance, share: dict[str, float], drop_assumed: bool = False) -> Instance:
    """The instance with each user's yearly demand cut to the part a 60 C supply can serve; with
    `drop_assumed`, the assumed sites have no demand (the plan on today's facilities)."""
    return replace(inst, users=[replace(u, annual_mwh=0.0) if drop_assumed and u.kind in ASSUMED
                                else replace(u, annual_mwh=u.annual_mwh * share.get(u.kind, 1.0)) for u in inst.users])


def describe(plan) -> dict:
    data = export_plan(plan, "")
    kinds: dict[str, int] = {}
    for s in data["sites"]:
        if s["dc"] is not None and sum(s["served"]) > 0:
            kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    return {"net_m": plan.expected_net / 1e6, "sites": len(plan.connected), "km": plan.pipe_m / 1000,
            "gap": (plan.kernel or {}).get("gap"), "breakeven_yen_l": bz.breakeven_kerosene(data),
            "network_yen_mwh": bz.network(data).yen_per_mwh, "kinds": kinds}


def main() -> None:
    use_overpass_mirror()
    t0 = time.perf_counter()
    sakura, sites = ishikari_sites()
    inst = build_instance(ishikari_sources(sakura), sites)
    P, scens = Params(mode="ambient", time_limit=60), default_scenarios()
    published, links = seeded_plan(inst, P, scens)
    today = solve_kernel(servable(inst, {}, True), P, scens, extra_edges=links)
    rows = {}
    for label, share in CASES.items():
        rows[label] = {}
        for name, base, drop in (("published plan", published, False), ("today's facilities", today, True)):
            inst_c = servable(inst, share, drop)
            kept = solve(inst_c, P, scens, edges=base.E, fix=base.build(), design_peak=base.ud.peak)
            again = solve_kernel(inst_c, P, scens, extra_edges=links)
            rows[label][name] = {"pipes kept": kept.expected_net / 1e6, "plan made again": describe(again)}
            print(f"{label} | {name}: pipes kept {kept.expected_net / 1e6:.1f}; made again {rows[label][name]['plan made again']}",
                  flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    data = {"cases": CASES, "results": rows, "seconds": round(time.perf_counter() - t0),
            "provenance": provenance.stamp(solver=P.solver or "highs (default)")}
    (OUT / "summary.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"results -> {OUT / 'summary.json'} ({data['seconds']} s)")


if __name__ == "__main__":
    main()
