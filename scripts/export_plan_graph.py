"""The published heat-network plan as a graph: tables, a Cypher script and three answers.

  uv run python scripts/export_plan_graph.py                  # NetworkX; nothing else is needed
  uv run python scripts/export_plan_graph.py --plan robust
  uv run python scripts/export_plan_graph.py --neo4j          # also load it into Neo4j and compare

Reads out/heat_network_v2/plans.json (from scripts/export_heat_network_v2.py) and writes
out/plan_graph/<plan>/: four tables and load.cypher. The questions are the route from a data
center to each user, the users that lose supply when one pipe is out, and the pipes most users
share. With --neo4j (`uv sync --extra graph`; NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD and, if
needed, NEO4J_DATABASE) the graph is loaded into the database, the same questions are asked in
Cypher, and the script reports whether the answers agree.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dcopt.heat import plangraph as pg

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"
OUT = ROOT / "out" / "plan_graph"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The published heat-network plan as a graph.")
    ap.add_argument("--plan", default="expected", help="expected, robust or current (default: expected)")
    ap.add_argument("--neo4j", action="store_true", help="also load the graph into Neo4j and compare the answers")
    args = ap.parse_args(argv)
    if not PLANS.exists():
        print(f"{PLANS.relative_to(ROOT)} is missing: run scripts/export_heat_network_v2.py first", file=sys.stderr)
        return 1
    plans = json.loads(PLANS.read_text(encoding="utf-8"))
    if args.plan not in plans["plans"]:
        print(f"no plan '{args.plan}'; there are: {', '.join(plans['plans'])}", file=sys.stderr)
        return 1

    g = pg.build(plans, args.plan)
    folder = OUT / args.plan
    pg.write(g, folder)
    names = {u["id"]: u["name"] for u in g.users}
    found = pg.routes(g)
    print(f"Plan '{g.plan}': {len(g.junctions)} junctions, {len(g.pipes)} pipes, {len(g.users)} users, "
          f"{sum(1 for d in g.dcs if d['junction'])} data centers supplying. Written to {folder.relative_to(ROOT)}/")
    if found:
        far = max(found, key=lambda u: found[u]["km"])
        print(f"Longest route: {found[far]['km']} km over {len(found[far]['pipes'])} pipes, "
              f"from {found[far]['dc']} to {names[far]}")
    for row in pg.shared(g)[:3]:
        print(f"Pipe {row['pipe']} (DN{row['dn']}, {row['km']} km) carries heat for {row['users']} users, "
              f"{row['mwh']:,} MWh a year; without it {len(pg.cut(g, row['pipe']))} lose their supply")
    if not args.neo4j:
        print("Answered with NetworkX. Add --neo4j to load the same graph into Neo4j and ask it there.")
        return 0

    database = os.environ.get("NEO4J_DATABASE") or None
    try:
        driver = pg.connect()
        with driver:
            pg.load(driver, g, database)
            differing = pg.differences(g, driver, database)
    except pg.GraphDbUnavailable as e:
        print(f"Neo4j: {e}", file=sys.stderr)
        return 1
    except Exception as e:                                   # the driver's own errors: no server, wrong password
        print(f"Neo4j: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if differing:
        print("Neo4j gives different answers for: " + ", ".join(differing), file=sys.stderr)
        return 1
    print("Loaded into Neo4j; the three questions asked in Cypher give the same answers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
