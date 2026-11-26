"""Exergy view of the published heat-network plans: what the heat is worth as work, and what it costs.

  uv run python scripts/exergy_balance.py                  # the tables of docs/exergy.md
  uv run python scripts/exergy_balance.py --plan current   # by kind of user for another plan

Reads out/heat_network_v2/plans.json (from scripts/export_heat_network_v2.py) and writes
out/exergy/balance.json. The definitions and the assumptions are in dcopt.heat.exergy; the
reasoning, the limits and the references are in docs/exergy.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dcopt.heat import exergy as ex
from dcopt.heat.network import Params

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
OUT = ROOT / "out" / "exergy"


def pct(x: float) -> str:
    return f"{100 * x:.1f} %"


def table(head: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Exergy view of the published heat-network plans.")
    ap.add_argument("--plan", default="expected", help="plan shown by kind of user: expected, robust or current")
    args = ap.parse_args(argv)
    if not PLANS.exists():
        print(f"{PLANS.relative_to(ROOT)} is missing: run scripts/export_heat_network_v2.py first", file=sys.stderr)
        return 1
    data = json.loads(PLANS.read_text(encoding="utf-8"))
    if args.plan not in data["plans"]:
        print(f"no plan '{args.plan}'; there are: {', '.join(data['plans'])}", file=sys.stderr)
        return 1
    P, temps = Params(), data["temp"]
    jan, aug = temps[0], temps[7]

    print(f"Reference state: monthly outdoor mean ({jan:g} C in January, {aug:g} C in August). Waste heat at "
          f"{P.waste_c:g} C, loop at {P.network_c:g} C, heat pumps at {P.carnot_eff:.0%} of the Carnot COP "
          f"(cap {P.cop_cap:g}), boiler {P.boiler_eff:.0%}, kerosene exergy {ex.FUEL_EXERGY_KWH_PER_L:g} kWh/L.\n")

    print("One MWh delivered in January, by kind of user\n")
    rows = []
    for kind in sorted(P.supply_c, key=lambda k: (P.supply_c[k], k)):
        f, cop = ex.month_flows(kind, 1.0, jan, P), P.cop(kind)
        rows.append([kind, f"{P.supply_c[kind]:g}", f"{f.heat_exergy:.3f}", "direct" if cop is None else f"{cop:.2f}",
                     f"{f.electricity:.3f}", f"{f.waste_heat:.3f}", pct(f.boiler_efficiency), pct(f.plan_efficiency)])
    print(table(["Kind", "Supply (C)", "Exergy (MWh)", "COP", "Electricity (MWh)", "Waste heat (MWh)",
                 "Boiler", "Plan"], rows))

    energy, exergy = ex.resource(data["plans"][args.plan]["waste_month"], temps, P)
    print(f"\nWaste heat on offer: {energy / 1000:.1f} GWh a year, of which exergy {exergy / 1000:.2f} GWh "
          f"({pct(exergy / energy)}); {pct(ex.carnot_factor(P.waste_c, jan))} in January, "
          f"{pct(ex.carnot_factor(P.waste_c, aug))} in August.\n")

    print("The plans (MWh a year)\n")
    rows, saved = [], {}
    for name, plan in data["plans"].items():
        by = ex.balance(plan["sites"], temps, P)
        a = by["all"]
        saved[name] = {kind: asdict(f) | {"quality": f.quality, "boiler_efficiency": f.boiler_efficiency,
                                          "plan_efficiency": f.plan_efficiency} for kind, f in by.items()}
        saved[name]["all"]["central_electricity"] = ex.central_electricity(a.heat, P)
        rows.append([name, a.users, f"{a.heat:,.0f}", f"{a.heat_exergy:,.0f}", pct(a.quality), f"{a.fuel_exergy:,.0f}",
                     pct(a.boiler_efficiency), f"{a.electricity:,.0f}", f"{a.waste_exergy:,.0f}", pct(a.plan_efficiency),
                     pct(a.high_grade_cut), f"{ex.central_electricity(a.heat, P):,.0f}"])
    print(table(["Plan", "Users", "Heat", "Its exergy", "Share", "Kerosene exergy", "Boilers", "Electricity",
                 "Waste-heat exergy", "Plan", "High-grade input cut", "Electricity at 60 C"], rows))

    print(f"\nPlan '{args.plan}' by kind of user (MWh a year)\n")
    by = ex.balance(data["plans"][args.plan]["sites"], temps, P)
    total = by["all"].heat
    rows = [[kind, f.users, f"{f.heat:,.0f}", pct(f.heat / total), f"{P.supply_c[kind]:g}",
             "direct" if P.cop(kind) is None else f"{P.cop(kind):.2f}", pct(f.quality), f"{f.electricity:,.0f}"]
            for kind, f in sorted(by.items(), key=lambda kv: -kv[1].heat) if kind != "all"]
    print(table(["Kind", "Users", "Heat", "Share", "Supply (C)", "COP", "Exergy / energy", "Electricity"], rows))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "balance.json").write_text(json.dumps({"temp": temps, "plans": saved}, indent=1), encoding="utf-8")
    print(f"\nwrote {(OUT / 'balance.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
