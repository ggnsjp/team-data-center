"""Warm Ishikari: the flat heat-loss share of model v2 against the loss of the plans' own pipes.

    uv run python scripts/export_heat_network_v2.py      # the three published plans -> out/heat_network_v2/plans.json
    uv run python experiments/heat_loss_check/run.py     # a second

For each published plan, the yearly loss of its pipes by the rule q = U x (mean water temperature -
ground temperature), with published coefficients and the ground temperature of Sapporo
(dcopt.heat.loss), as a share of the heat the plan delivers. The model's own assumption is 2 % for
the ambient loop and 8 % for a central 60 C network.
"""
from __future__ import annotations

import json
from pathlib import Path

from dcopt.heat.loss import yearly_loss_mwh
from dcopt.heat.network import Params

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
OUT = ROOT / "results" / "heat_loss_check"
PIPES = [("pair", 1, "two single pipes, series 1"), ("pair", 2, "two single pipes, series 2"),
         ("twin", 2, "twin pipe to DN200, series 2")]


def main() -> None:
    if not PLANS.exists():
        raise SystemExit("run scripts/export_heat_network_v2.py first")
    P = Params()
    modes = {"ambient loop": (P.network_c, P.network_c - P.dT_ambient, P.loss_ambient),
             "central network": (P.central_c, P.central_c - P.dT_central, P.loss_central)}
    data = json.loads(PLANS.read_text(encoding="utf-8"))
    lines = ["# Heat loss of the published plans' pipes", "",
             "| Plan | Route | Heat delivered (MWh/yr) | Network | Pipes | Loss (MWh/yr) | Share of the heat delivered | In the model |",
             "|---|---|---|---|---|---|---|---|"]
    out = {}
    for key, plan in data["plans"].items():
        pipes = [(p["dn"], p["km"]) for p in plan["pipes"]]
        delivered = float(sum(plan["delivered_month"]))
        km = sum(k for _, k in pipes)
        out[key] = {"km": km, "delivered_mwh": delivered, "loss": {}}
        for mode, (ts, tr, flat) in modes.items():
            for kind, series, label in PIPES:
                loss = yearly_loss_mwh(pipes, ts, tr, kind, series)
                out[key]["loss"][f"{mode}/{label}"] = {"mwh": loss, "share": loss / delivered}
                lines.append(f"| {key} | {km:.1f} km | {delivered:,.0f} | {mode}, {ts:.0f}/{tr:.0f} C | {label} | "
                             f"{loss:,.0f} | {100 * loss / delivered:.1f} % | {100 * flat:.0f} % |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
