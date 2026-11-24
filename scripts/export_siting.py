"""Export the siting study: the value of a new data center's waste heat at every candidate site.

For every point of a grid over the municipality, the regional heat plan of theme 1 is solved with
a new data center there (dcopt.siting.heat_value). The script also measures each site's distance to
the nearest substation and lines in OpenStreetMap, and checks the pair of sites the location model
picks with one joint solve. It writes
  out/siting/siting.json     read by the app page "Siting"

Run: uv run python scripts/export_siting.py [--spacing 1500] [--mw 10] [--workers 8]
     DCOPT_SOLVER=gurobi uv run python scripts/export_siting.py --workers 4 --out results/siting/gurobi.json   # optional check
Takes about a quarter of an hour with 8 workers. Needs the Ishikari map data (scripts/fetch_data.py);
the power lines are downloaded on first use, and the study runs without them if that fails.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import geopandas as gpd

from dcopt.common import provenance
from dcopt.common.geo import paths, use_overpass_mirror
from dcopt.heat.network import Params, build_instance, default_scenarios, ishikari_sources, seeded_plan, solver_name
from dcopt.heat.v1 import ishikari_sites
from dcopt.siting import gridmap
from dcopt.siting.candidates import grid_candidates, name_places
from dcopt.siting.heat_value import LOW_SHARE, heat_value, heat_value_of
from dcopt.siting.model import annuity, choose_sites

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "siting"
M = 1e6
_W: dict = {}


def _init(base, links, users, P, scens) -> None:
    os.environ.setdefault("DCOPT_THREADS", "1")            # one thread per solve: the workers run side by side
    _W.update(base=base, links=links, users=users, P=P, scens=scens)


def _value(task: tuple) -> dict:
    cid, lon, lat, mw = task
    v = heat_value(_W["base"], _W["links"], _W["users"], lon, lat, mw, _W["P"], _W["scens"])
    return {"id": cid, "mw": mw, "value": v.value, "net": v.net, "sites": v.sites,
            "sites_from_candidate": v.sites_from_candidate, "pipe_km": v.pipe_km,
            "heat_from_candidate": v.heat_from_candidate, "seconds": v.seconds}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spacing", type=float, default=1500.0, help="grid spacing of the candidate sites, metres")
    ap.add_argument("--mw", default="10", help="IT load of the new data center, MW (comma-separated for several)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-power", action="store_true", help="do not download the power lines")
    ap.add_argument("--out", default=str(OUT / "siting.json"), help="where to write (the app reads the default path)")
    args = ap.parse_args()

    use_overpass_mirror()
    t0 = time.perf_counter()
    sakura, users = ishikari_sites()
    sources = ishikari_sources(sakura)
    inst = build_instance(sources, users)
    P, scens = Params(mode="ambient"), default_scenarios()
    base, links = seeded_plan(inst, P, scens)
    print(f"regional plan without a new data center: {base.expected_net / M:.1f}M, {len(base.connected)} sites, "
          f"{base.pipe_m / 1000:.1f} km  [{time.perf_counter() - t0:.0f}s]", flush=True)

    cands = name_places(grid_candidates(spacing_m=args.spacing))
    sizes = [float(x) for x in args.mw.split(",")]
    tasks = [(c["id"], c["lon"], c["lat"], mw) for mw in sizes for c in cands]
    print(f"{len(cands)} candidate sites x {len(sizes)} size(s) on {args.workers} workers", flush=True)
    with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(base, links, users, P, scens)) as pool:
        rows = list(pool.map(_value, tasks))
    by = {(r["id"], r["mw"]): r for r in rows}
    for c in cands:
        c["by_mw"] = {f"{mw:g}": {k: by[c["id"], mw][k] for k in ("value", "sites", "sites_from_candidate", "pipe_km",
                                                                    "heat_from_candidate")} for mw in sizes}
    print(f"heat values done  [{time.perf_counter() - t0:.0f}s]; best: "
          + ", ".join(f"{c['id']} {c['by_mw'][f'{sizes[0]:g}']['value'] / M:.1f}M"
                      for c in sorted(cands, key=lambda c: -c["by_mw"][f"{sizes[0]:g}"]["value"])[:5]), flush=True)

    power = None if args.no_power else gridmap.load_power()
    layers = None
    if power is not None:
        for min_kv in (66000, 187000):
            for c, row in zip(cands, gridmap.connections(power, [(c["lon"], c["lat"]) for c in cands], min_kv)):
                c[f"grid_{min_kv // 1000}"] = row
        for s, row in zip(sources, gridmap.connections(power, [(s.lon, s.lat) for s in sources], 66000)):
            print(f"  {s.key}: nearest substation {row['substation']} ({row['substation_km']:.2f} km)")
        west, south, east, north = gpd.read_file(paths("ishikari")["area"]).total_bounds
        layers = gridmap.layers(power, (west, south, east, north))
    else:
        print("power lines not available: the study carries on with heat values only")

    # the pair the location model picks at its default settings, checked by one joint solve
    mw0 = sizes[0]
    heat = [c["by_mw"][f"{mw0:g}"]["value"] for c in cands]
    km = [c.get("grid_66", {}).get("substation_km") or 0.0 for c in cands]
    pick = choose_sites(heat, km, [(c["x"], c["y"]) for c in cands], n=2, yen_per_km_year=annuity(0.03, 30) * 100e6,
                        spacing_m=3000.0)
    joint = None
    if len(pick.chosen) == 2:
        pair = [cands[j] for j in pick.chosen]
        jv = heat_value_of(base, links, users, [(c["lon"], c["lat"], mw0) for c in pair], P, scens)
        joint = {"ids": [c["id"] for c in pair], "sum_of_single_values": pick.heat, "joint_value": jv.value,
                 "sites": jv.sites, "sites_from_candidates": jv.sites_from_candidate, "pipe_km": jv.pipe_km}
        print(f"pair {joint['ids']}: single values add up to {pick.heat / M:.1f}M, joint value {jv.value / M:.1f}M")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "provenance": provenance.stamp(solver=solver_name(P)), "spacing_m": args.spacing, "sizes_mw": sizes,
        "low_share": LOW_SHARE, "mode": P.mode,
        "base": {"net": base.expected_net, "sites": len(base.connected), "pipe_km": base.pipe_m / 1000},
        "data_centers": [{"key": s.key, "name": s.name, "name_en": s.name_en, "lon": s.lon, "lat": s.lat,
                          "status": s.status, "it_mw": s.it_mw} for s in sources],
        "users": [{"key": u.key, "name": u.name, "name_en": u.name_en, "kind": u.kind, "lon": u.lon, "lat": u.lat,
                   "annual_mwh": u.annual_mwh, "in_base_plan": bool(base.x[i] > 0.5)} for i, u in enumerate(users)],
        "candidates": cands, "power": layers, "pair_check": joint, "seconds": time.perf_counter() - t0,
    }
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}  [{time.perf_counter() - t0:.0f}s]")


if __name__ == "__main__":
    main()
