"""Export the siting study: the value of a new data center's waste heat at every candidate site.

For every point of a grid over the municipality, the regional heat plan of theme 1 is solved with
a new data center there (dcopt.siting.heat_value). The script also measures each site's distance to
the nearest substation and lines in OpenStreetMap, and checks with one joint solve the pair of sites
the location model picks for two new data centers at the app's other default settings. It writes
  out/siting/siting.json     read by the app page "Siting"
  out/siting/networks.json   the pipe networks of today's plan and of the plans for the best sites,
                             read by scripts/render_siting_animation.py

Run: uv run python scripts/export_siting.py [--spacing 1500] [--mw 10] [--workers 8]
     DCOPT_SOLVER=gurobi uv run python scripts/export_siting.py --workers 4 --out results/siting/gurobi.json   # optional check
     uv run python scripts/export_siting.py --networks-only    # redo networks.json for an export that is already there
     uv run python scripts/export_siting.py --pair-check-only  # redo only the pair check of an export that is already there
Takes about a quarter of an hour with 8 workers. Needs the Ishikari map data (scripts/fetch_data.py);
the power lines are downloaded on first use, and the study runs without them if that fails.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import geopandas as gpd
import numpy as np

from dcopt.common import provenance
from dcopt.common.geo import paths, road_path, use_overpass_mirror
from dcopt.common.workers import pool as worker_pool
from dcopt.heat.network import Params, build_instance, default_scenarios, ishikari_sources, seeded_plan, solver_name
from dcopt.heat.v1 import ishikari_sites
from dcopt.siting import gridmap
from dcopt.siting.candidates import grid_candidates, name_places
from dcopt.siting.heat_value import LOW_SHARE, heat_value, heat_value_of
from dcopt.siting.model import LINE_COST_M_YEN_KM, annuity, choose_sites

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "siting"
M = 1e6
PAIR_SPACING_M = 3000.0   # the pair check: the app's default distance between two new data centers
_W: dict = {}


def _init(base, links, users, P, scens) -> None:
    os.environ.setdefault("DCOPT_THREADS", "1")            # one thread per solve: the workers run side by side
    _W.update(base=base, links=links, users=users, P=P, scens=scens)


def _row(cid: str, mw: float, v) -> dict:
    return {"id": cid, "mw": mw, "value": v.value, "net": v.net, "sites": v.sites,
            "sites_from_candidate": v.sites_from_candidate, "pipe_km": v.pipe_km,
            "heat_from_candidate": v.heat_from_candidate, "seconds": v.seconds}


def _value(task: tuple) -> dict:
    cid, lon, lat, mw = task
    return _row(cid, mw, heat_value(_W["base"], _W["links"], _W["users"], lon, lat, mw, _W["P"], _W["scens"]))


def _pairs(plan) -> set:
    """The built links of a plan as pairs of road nodes, which do not depend on the node numbering."""
    nodes = [s.node for s in plan.inst.sources] + [u.node for u in plan.inst.users]
    return {frozenset((nodes[a], nodes[b])) for e, (a, b) in enumerate(plan.E) if plan.y[e].max() > 0.5}


def network(plan, base_pairs: set, d0: int) -> dict:
    """The pipes of a plan as road paths, each drawn in the direction its heat flows, and the users it
    connects. Data centers with an index of d0 or more are new: `new_heat` marks the pipes that
    carry their heat and `from_new` the users they serve. `in_base` marks the pipes of today's plan."""
    inst, nE = plan.inst, len(plan.E)
    nodes = [s.node for s in inst.sources] + [u.node for u in inst.users]
    heat = np.einsum("udtw,w->u", plan.s, plan.p)                      # expected MWh a year per user
    new = (plan.assign >= d0) & (plan.x > 0.5)
    pipes = []
    for e, (a, b) in enumerate(plan.E):
        if plan.y[e].max() <= 0.5:
            continue
        fwd, bwd = plan.g[:, e], plan.g[:, e + nE]
        if float(heat @ bwd) > float(heat @ fwd):
            a, b = b, a
        path = road_path(nodes[a], nodes[b])
        if len(path) < 2:
            path = list(path) * 2
        pipes.append({"path": [[round(float(lon), 5), round(float(lat), 5)] for lat, lon in path],
                      "dn": plan.P.sizes[int(np.argmax(plan.y[e]))].dn, "km": round(float(inst.dist[a, b]) / 1000, 3),
                      "from": int(a), "to": int(b), "in_base": frozenset((nodes[a], nodes[b])) in base_pairs,
                      "new_heat": bool((np.abs(fwd - bwd)[new] > 1e-6).any())})   # net flow: a there-and-back loop carries nothing
    return {"sources": inst.D, "pipes": pipes,
            "users": [{"index": u, "from_new": bool(new[u])} for u in range(inst.U) if plan.x[u] > 0.5]}


def _network(task: tuple) -> dict:
    cid, lon, lat, mw = task
    base = _W["base"]
    v = heat_value(base, _W["links"], _W["users"], lon, lat, mw, _W["P"], _W["scens"], keep_plan=True)
    return {**_row(cid, mw, v), "lon": lon, "lat": lat, **network(v.plan, _pairs(base), base.inst.D)}


def export_networks(path: Path, cands: list[dict], mw: float, n: int, workers: int, base, links, users, P, scens) -> None:
    """Solve the n best sites again, keep their plans, and write the pipe networks next to the export."""
    key = f"{mw:g}"
    best = sorted(cands, key=lambda c: -c["by_mw"][key]["value"])[:n]
    with worker_pool(min(workers, len(best)), initializer=_init, initargs=(base, links, users, P, scens)) as pool:
        rows = list(pool.map(_network, [(c["id"], c["lon"], c["lat"], mw) for c in best]))
    for c, r in zip(best, rows):
        r["value_in_export"] = c["by_mw"][key]["value"]
        note = "" if abs(r["value"] - r["value_in_export"]) < 0.05 * M else "   <- differs from the export (the search is heuristic)"
        print(f"  network of {c['id']}: {r['value'] / M:.1f}M, {r['sites']} sites, {r['pipe_km']:.1f} km "
              f"(export: {r['value_in_export'] / M:.1f}M){note}", flush=True)
    data = {"provenance": provenance.stamp(solver=solver_name(P)), "mw": mw,
            "base": {"net": base.expected_net, "sites": len(base.connected), "pipe_km": base.pipe_m / 1000,
                     **network(base, _pairs(base), base.inst.D)},
            "sites": rows}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path}")


def pair_check(cands: list[dict], mw: float, base, links, users, P, scens) -> dict | None:
    """The pair the location model picks for two new data centers at the app's other default settings (at
    least 3 km apart, each connected to the nearest 66 kV substation at the middle of the published unit
    costs), solved together once to see whether the single values add up."""
    key = f"{mw:g}"
    heat = [c["by_mw"][key]["value"] for c in cands]
    km = [(c.get("grid_66") or {}).get("substation_km") or 0.0 for c in cands]
    line = LINE_COST_M_YEN_KM["66"]
    pick = choose_sites(heat, km, [(c["x"], c["y"]) for c in cands], n=2, yen_per_km_year=annuity(0.03, 30) * line * 1e6,
                        spacing_m=PAIR_SPACING_M)
    if len(pick.chosen) != 2:
        return None
    pair = [cands[j] for j in pick.chosen]
    jv = heat_value_of(base, links, users, [(c["lon"], c["lat"], mw) for c in pair], P, scens)
    joint = {"ids": [c["id"] for c in pair], "sum_of_single_values": pick.heat, "joint_value": jv.value,
             "sites": jv.sites, "sites_from_candidates": jv.sites_from_candidate, "pipe_km": jv.pipe_km,
             "line_m_yen_km": line, "spacing_m": PAIR_SPACING_M}
    print(f"pair {joint['ids']}: single values add up to {pick.heat / M:.1f}M, joint value {jv.value / M:.1f}M", flush=True)
    return joint


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spacing", type=float, default=1500.0, help="grid spacing of the candidate sites, metres")
    ap.add_argument("--mw", default="10", help="IT load of the new data center, MW (comma-separated for several)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-power", action="store_true", help="do not download the power lines")
    ap.add_argument("--out", default=str(OUT / "siting.json"), help="where to write (the app reads the default path)")
    ap.add_argument("--networks", type=int, default=3, help="keep the pipe networks of this many best sites (0: none)")
    ap.add_argument("--networks-only", action="store_true", help="read the export at --out and only redo networks.json")
    ap.add_argument("--pair-check-only", action="store_true", help="read the export at --out and only redo the pair check")
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
    out = Path(args.out)
    if args.pair_check_only:
        done = json.loads(out.read_text(encoding="utf-8"))
        if abs(done["base"]["net"] - base.expected_net) > 0.05 * M:
            print(f"note: the export has a regional plan of {done['base']['net'] / M:.1f}M, this run {base.expected_net / M:.1f}M")
        done["pair_check"] = pair_check(done["candidates"], done["sizes_mw"][0], base, links, users, P, scens)
        if done["pair_check"]:
            done["pair_check"]["provenance"] = provenance.stamp(solver=solver_name(P))
        out.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out}  [{time.perf_counter() - t0:.0f}s]")
        return
    if args.networks_only:
        done = json.loads(out.read_text(encoding="utf-8"))
        if abs(done["base"]["net"] - base.expected_net) > 0.05 * M:
            print(f"note: the export has a regional plan of {done['base']['net'] / M:.1f}M, this run {base.expected_net / M:.1f}M")
        export_networks(out.with_name("networks.json"), done["candidates"], done["sizes_mw"][0], args.networks,
                        args.workers, base, links, users, P, scens)
        return

    cands = name_places(grid_candidates(spacing_m=args.spacing))
    sizes = [float(x) for x in args.mw.split(",")]
    tasks = [(c["id"], c["lon"], c["lat"], mw) for mw in sizes for c in cands]
    print(f"{len(cands)} candidate sites x {len(sizes)} size(s) on {args.workers} workers", flush=True)
    with worker_pool(args.workers, initializer=_init, initargs=(base, links, users, P, scens)) as pool:
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

    joint = pair_check(cands, sizes[0], base, links, users, P, scens)

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
    if args.networks > 0:
        export_networks(out.with_name("networks.json"), cands, sizes[0], args.networks, args.workers, base, links, users, P, scens)


if __name__ == "__main__":
    main()
