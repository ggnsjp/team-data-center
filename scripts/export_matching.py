"""Theme 4: compute the numbers quoted in the README and docs from the 30-minute area records.

Writes results/matching/summary.json (every number, with a provenance block) and summary.md (the
tables as text). The records are downloaded on first use into data/cache/hepco_area/.

Run: uv run python scripts/export_matching.py            (a few seconds)
     uv run python scripts/export_matching.py --portfolio  (adds the linear programs: several minutes)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from dcopt.common import provenance
from dcopt.matching import records, score, system
from dcopt.matching.portfolio import Costs, cheapest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "matching"
YEARS = (2024, 2025)
LOAD_MW = 100.0
TARGETS = (0.8, 0.9, 0.95, 0.99, 1.0)


def area(df) -> dict:
    e = records.energy_gwh
    th, vre, cut = records.thermal(df), df["solar"] + df["wind"], records.curtailed_renewable(df)
    demand = e(df["demand"])
    return {
        "slots": len(df), "check": {k: (str(v) if not isinstance(v, (int, float)) else v)
                                    for k, v in records.check(df).items()},
        "demand_twh": demand / 1000, "peak_mw": float(df["demand"].max()), "mean_mw": float(df["demand"].mean()),
        "share": {k: e(df[k]) / demand for k in records.SUPPLY},
        "thermal_twh": e(th) / 1000, "thermal_share": e(th) / demand, "thermal_min_mw": float(th.min()),
        "thermal_floor_mw": system.thermal_floor(df),
        "solar_wind_share": e(vre) / demand, "fleet_solar_share": score.fleet_solar_share(df),
        "curtailed_gwh": e(cut), "curtailed_rate": e(cut) / (e(vre) + e(cut)), "curtailed_slots": int((cut > 0).sum()),
        "slots_solar_wind_above_half": int((vre / df["demand"] > 0.5).sum()),
        "slots_solar_wind_below_5pct": int((vre / df["demand"] < 0.05).sum()),
        "net_export_twh": -e(df["interconnection"]) / 1000,
    }


def counting(df) -> dict:
    n = len(df)
    load = score.flat_load(n, LOAD_MW)
    fleet = score.fleet_solar_share(df)
    grid = np.linspace(0, 1, 101)
    best = float(max(grid, key=lambda a: score.score(load, score.contracted(df, load, 1.0, a)).matched))
    out = {"load_mw": LOAD_MW, "used_gwh": system.gwh(load), "best_solar_share": best, "mixes": {}, "volume": {},
           "battery": {}, "shifting": {}}
    for name, a in [("solar_only", 1.0), ("wind_only", 0.0), ("area_mix", fleet), ("best_mix", best)]:
        s = score.score(load, score.contracted(df, load, 1.0, a))
        out["mixes"][name] = {"solar_share": a, "matched": s.matched, "slots_covered": s.slots_covered,
                              "longest_gap_h": s.longest_gap_h, "worst_week": s.worst_week}
    for x in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
        out["volume"][f"{x:g}"] = {"area_mix": score.score(load, score.contracted(df, load, x)).matched,
                                   "best_mix": max(score.score(load, score.contracted(df, load, x, a)).matched
                                                   for a in grid[::2])}
    gen = score.contracted(df, load, 1.0)
    for h in (1, 2, 4, 8, 24):
        out["battery"][str(h)] = score.score(load, score.with_storage(load, gen, LOAD_MW, LOAD_MW * h), gen).matched
    for flexible, headroom in [(0.1, 0.1), (0.2, 0.25), (0.5, 1.0)]:
        out["shifting"][f"{flexible:g}/{headroom:g}"] = score.shifted_share(load, gen, flexible, headroom)
    return out


def grid(df) -> dict:
    n = len(df)
    load = score.flat_load(n, LOAD_MW)
    gen = score.contracted(df, load, 1.0)
    floors = {"observed": system.thermal_floor(df), "lowest": float(records.thermal(df).min())}
    out = {"floors_mw": floors, "existing_plants": {}, "new_plants": {}, "break_even_mw": {}, "growth_twh": {}}
    r = system.replay(df, load, 0.0)
    out["existing_plants"] = {"thermal_change_gwh": r.thermal_change_gwh, "per_added_load": r.thermal_per_added_load,
                              "absorbed_gwh": system.absorbed_gwh(df, load),
                              "absorbed_share": system.absorbed_gwh(df, load) / r.added_load_gwh}
    for name, floor in floors.items():
        out["new_plants"][name] = {}
        for x in (1.0, 1.5, 2.0):
            b = system.replay(df, load, x * gen, floor)
            out["new_plants"][name][f"{x:g}"] = {"thermal_change_gwh": b.thermal_change_gwh,
                                                 "per_added_load": b.thermal_per_added_load,
                                                 "curtailed_gwh": b.curtailed_gwh}
        out["break_even_mw"][name] = {f"{k:g}": system.break_even_load(df, system.scaled_fleet(df, k, k), floor)
                                      for k in (1.5, 2.0, 3.0)}
    for k in (1.0, 1.5, 2.0, 3.0):
        out["growth_twh"][f"{k:g}"] = {str(d): system.replay(df, float(d), system.scaled_fleet(df, k, k),
                                                              floors["observed"]).thermal_gwh / 1000
                                       for d in (0, 100, 300, 500, 1000)}
    return out


def portfolios(df) -> dict:
    load = score.flat_load(len(df), 1.0)
    s, w = score.shaped(df["solar"], load), score.shaped(df["wind"], load)
    out = {}
    for battery in (True, False):
        for target in TARGETS:
            p = cheapest(load, s, w, target, Costs(), battery)
            out[f"{target:g}/{'battery' if battery else 'contract only'}"] = (
                {"feasible": False} if not p.feasible else
                {"feasible": True, "solar": p.solar, "wind": p.wind, "volume": p.volume, "battery_mw": p.battery_mw,
                 "battery_h": p.battery_h, "yen_per_kwh_used": p.yen_per_kwh_used})
            print(f"  target {target:g} battery={battery}: {out[f'{target:g}/' + ('battery' if battery else 'contract only')]}",
                  flush=True)
    return out


def text(data: dict) -> str:
    def pc(v: float, d: int = 1) -> str:
        return f"{100 * v:.{d}f} %"

    lines = ["# Theme 4: numbers from the 30-minute area records", ""]
    for fy, d in data["years"].items():
        a, c, g = d["area"], d["counting"], d["grid"]
        lines += [f"## FY{fy}", "",
                  (f"- area demand {a['demand_twh']:.2f} TWh; thermal {pc(a['thermal_share'])}; solar and wind "
                   f"{pc(a['solar_wind_share'])}; curtailed {a['curtailed_gwh']:.1f} GWh ({pc(a['curtailed_rate'], 2)}) in "
                   f"{a['curtailed_slots']} slots; thermal floor {a['thermal_floor_mw']:.0f} MW (lowest {a['thermal_min_mw']:.0f})"),
                  "- a contract for the yearly use: " + ", ".join(f"{k} {pc(v['matched'])}" for k, v in c["mixes"].items()),
                  "- more volume (area mix): " + ", ".join(f"x{k} {pc(v['area_mix'])}" for k, v in c["volume"].items()),
                  "- battery hours: " + ", ".join(f"{k} h {pc(v)}" for k, v in c["battery"].items()),
                  "- shifting (share/headroom): " + ", ".join(f"{k} {pc(v)}" for k, v in c["shifting"].items()),
                  (f"- existing plants: thermal +{pc(g['existing_plants']['per_added_load'])} of the use; "
                   f"curtailed output it could use {pc(g['existing_plants']['absorbed_share'], 2)}"),
                  ("- new plants (observed floor): " + ", ".join(
                      f"x{k} {100 * v['per_added_load']:+.1f} %" for k, v in g["new_plants"]["observed"].items())),
                  ("- new plants (lowest floor): " + ", ".join(
                      f"x{k} {100 * v['per_added_load']:+.1f} %" for k, v in g["new_plants"]["lowest"].items())),
                  ("- break-even load (observed / lowest floor): " + ", ".join(
                      f"x{k} {g['break_even_mw']['observed'][k]:.0f} / {g['break_even_mw']['lowest'][k]:.0f} MW"
                      for k in g["break_even_mw"]["observed"])), ""]
        if "portfolio" in d:
            lines += ["| target | with | solar | wind | battery MW per MW | battery h | yen per kWh used |", "|---|---|---|---|---|---|---|"]
            for k, p in d["portfolio"].items():
                t, mode = k.split("/")
                lines.append(f"| {pc(float(t), 0)} | {mode} | " + ("not reachable | | | | |" if not p["feasible"] else
                             f"{p['solar']:.2f} | {p['wind']:.2f} | {p['battery_mw']:.2f} | {p['battery_h']:.1f} | "
                             f"{p['yen_per_kwh_used']:.1f} |"))
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", action="store_true", help="also solve the cheapest portfolios (minutes)")
    args = ap.parse_args()
    data = {"provenance": provenance.stamp(source=records.SOURCE), "load_mw": LOAD_MW, "years": {}}
    for fy in YEARS:
        df = records.load_fiscal_year(fy)
        print(f"FY{fy}: {len(df)} slots", flush=True)
        data["years"][str(fy)] = {"area": area(df), "counting": counting(df), "grid": grid(df)}
        if args.portfolio:
            data["years"][str(fy)]["portfolio"] = portfolios(df)
            data["costs"] = {k: getattr(Costs(), k) for k in Costs.__dataclass_fields__}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "summary.md").write_text(text(data), encoding="utf-8")
    print(text(data))


if __name__ == "__main__":
    main()
