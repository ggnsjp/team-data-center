"""Waste heat, geothermal heat or ground heat: the figures of docs/ground-heat.md.

  uv run python scripts/ground_heat.py                  # the tables of docs/ground-heat.md
  uv run python scripts/ground_heat.py --lang ja        # the same with Japanese headings
  uv run python scripts/ground_heat.py --plan current   # for another of the exported plans

Reads out/heat_network_v2/plans.json (from scripts/export_heat_network_v2.py) and writes
out/ground_heat/comparison.json. The definitions and the assumptions are in dcopt.heat.ground; the
reasoning, the limits and the references are in docs/ground-heat.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dcopt.heat import exergy as ex
from dcopt.heat import ground as gr
from dcopt.heat.network import Params
from dcopt.heat.v1 import KINDS

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
OUT = ROOT / "out" / "ground_heat"
DISTANCES_KM = (5.0, 10.0, 20.0, 30.0, 50.0)
GROUND_TEMPS_C = (gr.GROUND_C, gr.GROUND_C + gr.GROUND_RISE_AT_100M_K[0], gr.GROUND_C + gr.GROUND_RISE_AT_100M_K[1])


def table(head: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def m(yen: float) -> str:
    """Yen as millions with one decimal."""
    return f"{yen / 1e6:,.1f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Waste heat, geothermal heat or ground heat: the figures of the page.")
    ap.add_argument("--plan", default="expected", help="expected, robust or current")
    ap.add_argument("--lang", default="en", choices=["en", "ja"], help="language of the headings")
    args = ap.parse_args(argv)
    if not PLANS.exists():
        print(f"{PLANS.relative_to(ROOT)} is missing: run scripts/export_heat_network_v2.py first", file=sys.stderr)
        return 1
    data = json.loads(PLANS.read_text(encoding="utf-8"))
    if args.plan not in data["plans"]:
        print(f"no plan '{args.plan}'; there are: {', '.join(data['plans'])}", file=sys.stderr)
        return 1
    ja = args.lang == "ja"
    t = (lambda en, jp: jp) if ja else (lambda en, jp: en)
    P, plan, jan = Params(), data["plans"][args.plan], data["temp"][0]
    s = gr.summary(plan, P)
    loop, ground, hot = s["loop"], s["ground"], s["line"]
    direct = t("direct", "直接")

    print(t(f"Plan '{args.plan}': {s['users']} users, {s['heat']:,.0f} MWh a year. Hot-water line at "
            f"{gr.HOT_SUPPLY_C:g}/{gr.HOT_RETURN_C:g} C, ground at {gr.GROUND_C:g} C, loop at {P.network_c:g} C; heat pumps at "
            f"{P.carnot_eff:.0%} of the Carnot COP (cap {P.cop_cap:g}, approach {P.approach_k:g} K); electricity "
            f"{P.power_yen_kwh:g} yen/kWh; annuities at {P.rate:.0%} over {P.years} years (pipes) and {P.hp_years} years "
            f"(heat pumps).",
            f"計画「{args.plan}」：{s['users']}件、年{s['heat']:,.0f} MWh。温水の導管は{gr.HOT_SUPPLY_C:g}/{gr.HOT_RETURN_C:g}℃、"
            f"地中は{gr.GROUND_C:g}℃、ループは{P.network_c:g}℃。ヒートポンプはカルノーCOPの{P.carnot_eff:.0%}"
            f"（上限{P.cop_cap:g}、温度差{P.approach_k:g} K）。電気{P.power_yen_kwh:g}円/kWh。年額は利率{P.rate:.0%}で"
            f"{P.years}年（導管）と{P.hp_years}年（ヒートポンプ）。") + "\n")

    # ---- 1. hot water over a distance
    print(t("1. The model's pipe sizes as a line of 10 km\n", "1. モデルの管径ごとの、10 kmの導管\n"))
    rows = []
    for size in P.sizes:
        ln = gr.line(size.dn, 10.0, P)
        rows.append([f"DN{size.dn}", f"{size.yen_m:,.0f}", f"{size.capacity_mw(P.dT_ambient):.2f}", f"{ln.capacity_mw:.2f}",
                     m(ln.investment), m(ln.annuity), f"{ln.loss_mwh:,.0f}"])
    print(table(t(["Size", "Cost (yen/m)", f"Carries at {P.dT_ambient:g} K (MW)",
                   f"Carries at {gr.HOT_SUPPLY_C - gr.HOT_RETURN_C:g} K (MW)", "10 km: investment (M yen)",
                   "Annuity (M yen/yr)", "Heat loss (MWh/yr)"],
                  ["管径", "単価（円/m）", f"温度差{P.dT_ambient:g} Kで運べる熱（MW）",
                   f"温度差{gr.HOT_SUPPLY_C - gr.HOT_RETURN_C:g} Kで運べる熱（MW）", "10 kmの投資額（百万円）",
                   "年額（百万円/年）", "熱損失（MWh/年）"]), rows))

    print("\n" + t(f"The plan's users: design peaks {s['peak_mw']:.2f} MW in sum. The plan's own pipes: {s['pipe_km']:.1f} km, "
                   f"{m(s['pipe_investment'])} M yen, {m(s['pipe_annuity'])} M yen a year.",
                   f"計画の需要家：設計ピークの合計 {s['peak_mw']:.2f} MW。計画の導管：{s['pipe_km']:.1f} km、"
                   f"{m(s['pipe_investment'])}百万円、年{m(s['pipe_annuity'])}百万円。"))
    if hot is None:
        print(t("No size of the model carries that peak in one line.", "この熱を1本で運べる管径がモデルにありません。"))
    else:
        print(t(f"Line needed: DN{hot.dn}. Per 10 km: {m(hot.investment)} M yen, {m(hot.annuity)} M yen a year, loss "
                f"{hot.loss_mwh:,.0f} MWh a year ({s['loss_share']:.1%} of the heat delivered). "
                f"As much as the plan's pipes at {s['km_same_investment']:.1f} km. The heat pumps of the loop and their "
                f"electricity ({m(loop.yearly_yen)} M yen a year) pay for {s['km_paid_by_heat_pumps']:.1f} km.",
                f"必要な導管：DN{hot.dn}。10 kmあたり{m(hot.investment)}百万円、年{m(hot.annuity)}百万円、熱損失は年"
                f"{hot.loss_mwh:,.0f} MWh（届ける熱の{s['loss_share']:.1%}）。{s['km_same_investment']:.1f} kmで計画の導管と"
                f"同じ投資額。ループのヒートポンプとその電気（年{m(loop.yearly_yen)}百万円）でまかなえるのは"
                f"{s['km_paid_by_heat_pumps']:.1f} km。") + "\n")
        rows = []
        for km in DISTANCES_KM:
            ln = gr.line_for(s["peak_mw"], km, P)
            rows.append([f"{km:g}", "-", "-", "-", "-"] if ln is None else
                        [f"{km:g}", f"DN{ln.dn}", m(ln.investment), m(ln.annuity),
                         f"{ln.loss_mwh:,.0f}", f"{ln.loss_mwh / s['heat']:.0%}"])
        print(table(t(["Distance (km)", "Size", "Investment (M yen)", "Annuity (M yen/yr)", "Heat loss (MWh/yr)",
                       "Loss / heat delivered"],
                      ["距離（km）", "管径", "投資額（百万円）", "年額（百万円/年）", "熱損失（MWh/年）", "損失÷届ける熱"]), rows))
        cooler = gr.line_for(s["peak_mw"], 10.0, P, P.central_c, P.central_c - P.dT_central)
        if cooler is not None:
            print("\n" + t(f"At {P.central_c:g}/{P.central_c - P.dT_central:g} C (the model's central network): DN{cooler.dn}, "
                           f"{m(cooler.investment)} M yen and {cooler.loss_mwh:,.0f} MWh a year per 10 km.",
                           f"{P.central_c:g}/{P.central_c - P.dT_central:g}℃（モデルの60℃方式の温度）なら：DN{cooler.dn}、"
                           f"10 kmあたり{m(cooler.investment)}百万円、熱損失は年{cooler.loss_mwh:,.0f} MWh。"))
    print("\n" + t("Exergy of 1 kWh of heat in January", "1月の熱1 kWhのエクセルギー") + f" ({jan:g} C): "
          + ", ".join(f"{c:g} C {ex.carnot_factor(c, jan):.3f}" for c in (gr.HOT_SUPPLY_C, P.waste_c, gr.GROUND_C)) + " kWh\n")

    # ---- 2. ground-source heat pumps
    print(t("2. Heat-pump COP by kind of user: the loop and the ground\n", "2. 需要家の種類ごとのヒートポンプのCOP：ループと地中熱\n"))
    rows = []
    for kind in sorted(P.supply_c, key=lambda k: (P.supply_c[k], k)):
        cop = P.cop(kind)
        rows.append([KINDS[kind][0] if ja else kind, f"{P.supply_c[kind]:g}", direct if cop is None else f"{cop:.2f}"]
                    + [f"{gr.ground_cop(kind, P, g):.2f}" for g in GROUND_TEMPS_C])
    print(table(t(["Kind", "Supply (C)", f"Loop ({P.network_c:g} C)"], ["種類", "送り温度（℃）", f"ループ（{P.network_c:g}℃）"])
                + [t(f"Ground {g:g} C", f"地中{g:g}℃") for g in GROUND_TEMPS_C], rows))

    print("\n" + t(f"Plan '{args.plan}' by kind of user (MWh a year)\n", f"計画「{args.plan}」の種類別（MWh/年）\n"))
    kinds = gr.by_kind(plan["sites"], P)
    rows = [[KINDS[kind][0] if ja else kind, r["users"], f"{r['heat']:,.0f}", f"{P.supply_c[kind]:g}",
             f"{r['loop']:,.0f}", f"{r['ground']:,.0f}"] for kind, r in sorted(kinds.items(), key=lambda kv: -kv[1]["heat"])]
    rows.append([t("All", "合計"), s["users"], f"{s['heat']:,.0f}", "", f"{loop.electricity:,.0f}", f"{ground.electricity:,.0f}"])
    print(table(t(["Kind", "Users", "Heat", "Supply (C)", "Electricity on the loop", "Electricity on ground heat"],
                  ["種類", "件数", "熱", "送り温度（℃）", "ループでの電気", "地中熱での電気"]), rows))
    print("\n" + t("Ground temperature and the plan's electricity: ", "地中の温度と計画全体の電気：")
          + ", ".join(f"{g:g} C {gr.heat_pumps(plan['sites'], P, g).electricity:,.0f} MWh" for g in GROUND_TEMPS_C)
          + t(f"; on the loop {loop.electricity:,.0f} MWh (ratio at {gr.GROUND_C:g} C: {ground.electricity / loop.electricity:.2f})",
              f"。ループでは{loop.electricity:,.0f} MWh（{gr.GROUND_C:g}℃での比：{ground.electricity / loop.electricity:.2f}）"))

    print("\n" + t("Heat pumps in a year, with the model's prices\n", "ヒートポンプの1年の費用（モデルの単価）\n"))
    rows = [[label, hp.users, f"{hp.capacity_mw:.2f}", f"{hp.electricity:,.0f}", m(hp.electricity_yen), m(hp.investment),
             m(hp.annuity), m(hp.yearly_yen)]
            for label, hp in ((t("On the loop (the plan)", "ループ（計画）"), loop), (t("On ground heat", "地中熱"), ground))]
    print(table(t(["", "Users with a heat pump", "Capacity (MW)", "Electricity (MWh/yr)", "Electricity (M yen/yr)",
                   "Investment (M yen)", "Its annuity (M yen/yr)", "Sum (M yen/yr)"],
                  ["", "ヒートポンプのある件数", "容量（MW）", "電気（MWh/年）", "電気（百万円/年）", "投資額（百万円）",
                   "その年額（百万円/年）", "計（百万円/年）"]), rows))
    print("\n" + t(f"Ground heat spends {m(ground.yearly_yen - loop.yearly_yen)} M yen a year more on heat pumps and saves the pipes' "
                   f"{m(s['pipe_annuity'])} M yen a year. The ground loops are not costed; the two come out even if they cost "
                   f"{m(s['ground_loop_budget'])} M yen (at {P.rate:.0%} over {P.years} years).",
                   f"地中熱は、ヒートポンプに年{m(ground.yearly_yen - loop.yearly_yen)}百万円多くかかり、導管の年"
                   f"{m(s['pipe_annuity'])}百万円がいらなくなります。地中熱交換器の費用は含めていません。その投資額が"
                   f"{m(s['ground_loop_budget'])}百万円（利率{P.rate:.0%}、{P.years}年）なら、両者は同額になります。"))

    OUT.mkdir(parents=True, exist_ok=True)
    saved = {k: (asdict(v) if hasattr(v, "__dataclass_fields__") else v) for k, v in s.items()}
    saved["by_kind"] = kinds
    (OUT / "comparison.json").write_text(json.dumps({"plan": args.plan, "figures": saved}, indent=1), encoding="utf-8")
    print(f"\nwrote {(OUT / 'comparison.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
