"""Export the heat-supply proposals: for every data center, its five ranked partners and their proposals.

Solves the regional plan as for the published results (ambient loop, heat-pump investment, kernel search
with seed links; a few minutes), ranks each data center's partners by the net benefit the plan loses
without them (rank_partners), and writes
  out/proposals/proposals.json      every number of every proposal (read by the app page)
  out/proposals/html/<lang>/*.html  printable proposals, A4, Japanese and English

Run: uv run python scripts/export_proposals.py [--mode ambient|central] [--top 5]
     uv run python scripts/export_proposals.py --render-only    # redraw the HTML from proposals.json
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np

from dcopt.common.geo import road_path, use_overpass_mirror
from dcopt.heat.network import (Params, build_instance, default_scenarios, ishikari_sources, rank_partners,
                                seeded_plan)
from dcopt.heat.proposal import BaseMap, proposal_data, render_html
from dcopt.heat.v1 import ishikari_sites

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "proposals"
BASE = ROOT / "out" / "heat_story" / "base.json"


def jsonable(x):
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "site"


def render_all(data: dict) -> int:
    base = BaseMap(json.loads(BASE.read_text(encoding="utf-8"))) if BASE.exists() else None
    n = 0
    for lang in ("ja", "en"):
        folder = OUT / "html" / lang
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.html"):
            old.unlink()
        for key, rows in data["partners"].items():
            for r in rows:
                site = r["proposal"]["site"]
                html = render_html(r["proposal"], lang, base, data["network"])
                (folder / f"{key}-{r['rank']}-{slug(site['key'])}.html").write_text(html, encoding="utf-8")
                n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="ambient", choices=["ambient", "central"])
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--time-limit", type=float, default=60.0)
    ap.add_argument("--render-only", action="store_true", help="redraw the HTML from out/proposals/proposals.json")
    args = ap.parse_args()
    if args.render_only:
        n = render_all(json.loads((OUT / "proposals.json").read_text(encoding="utf-8")))
        print(f"wrote {n} HTML files to {OUT / 'html'}")
        return
    use_overpass_mirror()
    t0 = time.time()
    sakura, sites = ishikari_sites()
    inst = build_instance(ishikari_sources(sakura), sites)
    P = Params(mode=args.mode, time_limit=args.time_limit)
    scens = default_scenarios()
    plan, _ = seeded_plan(inst, P, scens)
    print(f"regional plan: {len(plan.connected)} sites, {plan.pipe_m / 1000:.1f} km, "
          f"{plan.expected_net / 1e6:.1f}M yen/yr ({time.time() - t0:.0f}s)")
    nodes = [s.node for s in inst.sources] + [u.node for u in inst.users]
    network = [{"path": [[round(lon, 5), round(lat, 5)] for lat, lon in road_path(nodes[a], nodes[b])],
                "dn": P.sizes[k].dn} for a, b, _, k in plan.built]
    partners: dict = {}
    for d, src in enumerate(inst.sources):
        rows = rank_partners(plan, d, top=args.top)
        partners[src.key] = []
        for i, r in enumerate(rows, 1):
            u = r["u"]
            route = [[lon, lat] for lat, lon in road_path(src.node, inst.users[u].node)]
            prop = proposal_data(plan, d, u, rank=i, loss=r["loss"], route=route)
            partners[src.key].append({"rank": i, "u": u, "in_plan": r["in_plan"], "loss": r["loss"], "proposal": prop})
            pr = prop["pair"]
            print(f"  {src.key:6s} #{i} {inst.users[u].name_en[:38]:38s} in plan {str(r['in_plan']):5s} "
                  + (f"loss {r['loss'] / 1e6:6.1f}M  " if r["loss"] is not None else " " * 15)
                  + (f"pair {pr['dist_m'] / 1000:4.1f} km DN{pr['dn']} net {pr['net'] / 1e6:6.1f}M "
                     f"price {pr['p_min']:,.0f}-{pr['p_max']:,.0f}" if pr else "no dedicated pipe"))
    data = {"mode": P.mode, "regional": {"sites": len(plan.connected), "km": round(plan.pipe_m / 1000, 2),
                                         "net": plan.expected_net},
            "dcs": [{"key": s.key, "name": s.name, "name_en": s.name_en, "status": s.status} for s in inst.sources],
            "network": network, "partners": partners,
            "note": "Model v2; several sites and data-center positions are assumptions or placeholders. "
                    "Map data (c) OpenStreetMap contributors (ODbL)."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "proposals.json").write_text(json.dumps(jsonable(data), ensure_ascii=False, separators=(",", ":")),
                                        encoding="utf-8")
    n = render_all(jsonable(data))
    print(f"wrote {OUT / 'proposals.json'} and {n} HTML files ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
