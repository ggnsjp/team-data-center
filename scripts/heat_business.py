"""Print the tables of docs/heat-business.md: the price window of each kind of user, for the published
plan and for the plan on today's facilities alone.

Reads out/heat_network_v2/plans.json (scripts/export_heat_network_v2.py) and, when present,
out/heat_business/plans.json (scripts/export_heat_business.py).

Run: uv run python scripts/heat_business.py [--lang ja]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dcopt.heat import business as bz
from dcopt.heat.network import Params

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "out" / "heat_network_v2" / "plans.json"
TODAY = ROOT / "out" / "heat_business" / "plans.json"

KIND = {"aquaculture": ("陸上養殖", "Fish farm"), "snow": ("融雪", "Snow melting"), "pool": ("プール・運動施設", "Pool, sports centre"),
        "hotel": ("ホテル", "Hotel"), "public": ("公共施設", "Public building"), "hospital": ("病院", "Hospital"),
        "school": ("学校", "School"), "greenhouse": ("温室", "Greenhouse"), "new_greenhouse": ("温室（新設候補）", "Greenhouse (new site)"),
        "onsen": ("浴場", "Bath")}


def table(plan: dict, ja: bool, P: Params) -> list[str]:
    pick = (lambda a, b: a) if ja else (lambda a, b: b)
    n = bz.network(plan, P)
    low, high = bz.windows(plan, bz.KEROSENE_LOW, P), {w.kind: w for w in bz.windows(plan, bz.KEROSENE_SURVEY, P)}
    lines = [pick(f"導管 {n.km:.1f} km、投資 {n.investment / 1e6:,.1f} 百万円、年額 {n.annuity / 1e6:,.1f} 百万円、届ける熱 {n.heat:,.0f} MWh/年。"
                  f"導管網が必要とする最低の熱の価格：{n.yen_per_mwh:,.0f} 円/MWh（灯油1 Lあたり {bz.per_litre(n.yen_per_mwh, P):.1f} 円）",
                  f"Pipes {n.km:.1f} km, investment {n.investment / 1e6:,.1f} M yen, annuity {n.annuity / 1e6:,.1f} M yen a year, heat delivered "
                  f"{n.heat:,.0f} MWh a year. The least price the network needs: {n.yen_per_mwh:,.0f} yen/MWh "
                  f"({bz.per_litre(n.yen_per_mwh, P):.1f} yen per litre of kerosene replaced)"), "",
             pick("| 種類 | 件数 | 熱（MWh/年） | 送り温度（℃） | ヒートポンプの電気（円/MWh） | ヒートポンプの年額（円/MWh） | 払える上限、灯油115円/L | 払える上限、灯油156.8円/L | 窓が開く灯油価格（円/L） |",
                  "| Kind | Users | Heat (MWh/yr) | Supply (°C) | Own heat pump: electricity (yen/MWh) | Own heat pump: annuity (yen/MWh) | Most it can pay, kerosene 115 yen/L | Most it can pay, kerosene 156.8 yen/L | Window opens above (yen/L of kerosene) |"),
             "|---|---|---|---|---|---|---|---|---|"]
    for w in low:
        name = pick(*KIND.get(w.kind, (w.kind, w.kind))) + (pick("（仮定）", " (assumed)") if w.assumed else "")
        lines.append(f"| {name} | {w.users} | {w.heat:,.0f} | {w.supply_c:g} | {w.electricity:,.0f} | {w.heat_pump:,.0f} | "
                     f"{w.most:,.0f} | {high[w.kind].most:,.0f} | {w.opens_at:.0f} |")
    lines.append("")
    for k in (bz.KEROSENE_LOW, bz.mean_kerosene(), bz.KEROSENE_SURVEY):
        lines.append(pick(f"灯油 {k:g} 円/L：余剰 {bz.surplus(plan, k, P) / 1e6:,.1f} 百万円/年（今ある施設 {bz.surplus(plan, k, P, assumed=False) / 1e6:,.1f}、"
                          f"仮定の施設 {bz.surplus(plan, k, P, assumed=True) / 1e6:,.1f}）",
                          f"Kerosene {k:g} yen/L: surplus {bz.surplus(plan, k, P) / 1e6:,.1f} M yen a year (today's facilities "
                          f"{bz.surplus(plan, k, P, assumed=False) / 1e6:,.1f}, assumed sites {bz.surplus(plan, k, P, assumed=True) / 1e6:,.1f})"))
    lines.append(pick(f"モデルの期待純便益：{plan['kpi']['expected_net_m']} 百万円/年", f"The model's expected net benefit: {plan['kpi']['expected_net_m']} M yen a year"))
    lines.append(pick(f"余剰がゼロになる灯油価格：{bz.breakeven_kerosene(plan, P):.1f} 円/L",
                      f"Kerosene price at which the surplus is zero: {bz.breakeven_kerosene(plan, P):.1f} yen/L"))
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "ja"], default="en")
    ja = ap.parse_args().lang == "ja"
    P = Params()
    plans = [(("公表した計画（仮定の施設を含む）", "The published plan (with the assumed sites)"),
              json.loads(PUBLISHED.read_text(encoding="utf-8"))["plans"]["expected"])]
    if TODAY.exists():
        today = json.loads(TODAY.read_text(encoding="utf-8"))["plans"]
        plans.append((("今ある施設だけの計画", "The plan on today's facilities alone"), today["existing"]))
        if "documented_fish_farm" in today:
            plans.append((("道路融雪と、道内で確認できた規模（年1,000 MWh）の陸上養殖を加えた計画",
                           "The plan with the road heating and a fish farm of the scale documented in Hokkaido (1,000 MWh a year)"),
                          today["documented_fish_farm"]))
    else:
        print("out/heat_business/plans.json is missing: uv run python scripts/export_heat_business.py")
    for (title_ja, title_en), plan in plans:
        print(f"\n## {title_ja if ja else title_en}\n")
        print("\n".join(table(plan, ja, P)))


if __name__ == "__main__":
    main()
