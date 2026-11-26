"""A plan of the heat network as a graph, with three questions asked of it.

A plan from ``scripts/export_heat_network_v2.py`` is a list of pipes drawn along streets. Here it
becomes a graph: junctions (the ends of the pipes), pipes between them, and the data centers and
heat users, each attached to the junction nearest to it. The questions:

- the route from a data center to each of its users;
- the users that lose their supply when one pipe is out;
- the pipes that most users share.

NetworkX answers them with nothing else installed. The same graph can also be loaded into a Neo4j
database, where the same questions are Cypher queries (``uv sync --extra graph``; the connection
comes from NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD). Nothing else in the project needs it.

The export carries coordinates and no node ids, so the connection points are found again as the
nearest junction; ``snap_m`` records how far away each one was.
"""
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

MAX_SEGMENTS = 60          # the longest route the Cypher queries look for, in pipes


class GraphDbUnavailable(RuntimeError):
    """Neo4j was asked for, but the driver or the connection settings are missing."""


@dataclass(frozen=True)
class PlanGraph:
    plan: str
    junctions: list[dict]      # id, lon, lat
    pipes: list[dict]          # id, a, b (junction ids), dn, km, mwh (heat carried in a year)
    dcs: list[dict]            # key, name, status, lon, lat, junction (None when it supplies nobody), snap_m
    users: list[dict]          # id, name, kind, assumed, mwh (heat received in a year), dc, junction, snap_m, lon, lat


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lon, lat) points."""
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def build(plans: dict, name: str = "expected") -> PlanGraph:
    """The graph of one plan in the export of scripts/export_heat_network_v2.py."""
    plan = plans["plans"][name]
    ids: dict[tuple[float, float], str] = {}
    junctions: list[dict] = []

    def junction(point) -> str:
        key = (round(point[0], 5), round(point[1], 5))
        if key not in ids:
            ids[key] = f"j{len(ids) + 1}"
            junctions.append({"id": ids[key], "lon": key[0], "lat": key[1]})
        return ids[key]

    pipes = [{"id": f"p{i}", "a": junction(p["path"][0]), "b": junction(p["path"][-1]), "dn": int(p["dn"]),
              "km": float(p["km"]), "mwh": int(round(sum(p["monthly"])))}
             for i, p in enumerate(plan["pipes"], 1)]

    def nearest(lon: float, lat: float) -> tuple[str | None, int | None]:
        if not junctions:
            return None, None
        dist, jid = min((_metres((lon, lat), (j["lon"], j["lat"])), j["id"]) for j in junctions)
        return jid, round(dist)

    users: list[dict] = []
    for site in plan["sites"]:
        if not site.get("dc"):
            continue
        jid, dist = nearest(site["lon"], site["lat"])
        users.append({"id": f"u{len(users) + 1}", "name": site["name_en"], "kind": site["kind"],
                      "assumed": bool(site["assumed"]), "mwh": int(round(sum(site["served"]))), "dc": site["dc"],
                      "junction": jid, "snap_m": dist, "lon": site["lon"], "lat": site["lat"]})
    supplying = {u["dc"] for u in users}
    dcs = []
    for dc in plans["dcs"]:
        jid, dist = nearest(dc["lon"], dc["lat"]) if dc["key"] in supplying else (None, None)
        dcs.append({"key": dc["key"], "name": dc["name_en"], "status": dc.get("status", ""),
                    "lon": dc["lon"], "lat": dc["lat"], "junction": jid, "snap_m": dist})
    return PlanGraph(name, junctions, pipes, dcs, users)


# ---- the three questions, answered with NetworkX ----

def network(g: PlanGraph) -> nx.Graph:
    """Junctions and pipes as a NetworkX graph. A pipe that starts and ends at one junction (two users
    at the same street node) is left out: it is on no route."""
    G = nx.Graph()
    G.add_nodes_from(j["id"] for j in g.junctions)
    for p in g.pipes:
        if p["a"] != p["b"] and not G.has_edge(p["a"], p["b"]):
            G.add_edge(p["a"], p["b"], id=p["id"], km=p["km"])
    return G


def routes(g: PlanGraph) -> dict[str, dict]:
    """For each user: its data center, the pipes on the way from it and their length in km. The route
    is the one with the fewest pipes; a plan is a tree, so it is the only one."""
    G = network(g)
    start = {d["key"]: d["junction"] for d in g.dcs}
    out: dict[str, dict] = {}
    for u in g.users:
        try:
            nodes = nx.shortest_path(G, start[u["dc"]], u["junction"])
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        steps = list(zip(nodes, nodes[1:]))
        out[u["id"]] = {"dc": u["dc"], "pipes": [G.edges[s]["id"] for s in steps],
                        "km": round(sum(G.edges[s]["km"] for s in steps), 2)}
    return out


def cut(g: PlanGraph, pipe: str) -> list[str]:
    """The users that lose their supply when this pipe is out."""
    return sorted(u for u, r in routes(g).items() if pipe in r["pipes"])


def shared(g: PlanGraph) -> list[dict]:
    """Per pipe on some route: how many users it carries heat for and how much heat they receive in a
    year, the most shared pipe first."""
    mwh = {u["id"]: u["mwh"] for u in g.users}
    info = {p["id"]: p for p in g.pipes}
    rows: dict[str, dict] = {}
    for user, r in routes(g).items():
        for p in r["pipes"]:
            row = rows.setdefault(p, {"pipe": p, "dn": info[p]["dn"], "km": info[p]["km"], "users": 0, "mwh": 0})
            row["users"] += 1
            row["mwh"] += mwh[user]
    return sorted(rows.values(), key=lambda row: (-row["users"], row["pipe"]))


# ---- the same graph and the same questions in Neo4j (optional) ----

_ROUTE = ("MATCH (d:DataCenter {plan: $plan})-[:SUPPLIES]->(u:HeatUser {plan: $plan}) "
          "MATCH (d)-[:FEEDS]->(a:Junction), (u)-[:TAPS]->(b:Junction) "
          f"CALL {{ WITH a, b MATCH p = (a)-[:PIPE*0..{MAX_SEGMENTS}]-(b) RETURN p ORDER BY length(p) LIMIT 1 }} ")
CYPHER = {
    "routes": _ROUTE + ("RETURN u.id AS user, d.key AS dc, [r IN relationships(p) | r.id] AS pipes, "
                        "reduce(km = 0.0, r IN relationships(p) | km + r.km) AS km ORDER BY user"),
    "cut": _ROUTE + ("WITH u, p WHERE any(r IN relationships(p) WHERE r.id = $pipe) "
                     "RETURN u.id AS user ORDER BY user"),
    "shared": _ROUTE + ("UNWIND relationships(p) AS r RETURN r.id AS pipe, r.dn AS dn, r.km AS km, "
                        "count(DISTINCT u) AS users, sum(u.mwh) AS mwh ORDER BY users DESC, pipe"),
}


def statements(g: PlanGraph) -> list[tuple[str, dict]]:
    """The Cypher that loads the graph, each statement with its rows. Every node carries the label
    PlanNode and the plan's name, and the first statement removes an earlier copy of the same plan."""
    def rows(items: list[dict], *keys: str) -> dict:
        return {"rows": [{k: item[k] for k in keys} for item in items]}

    at = "{plan: $plan, id: r.id}"
    return [
        ("MATCH (n:PlanNode {plan: $plan}) DETACH DELETE n", {}),
        ("UNWIND $rows AS r CREATE (:PlanNode:Junction {plan: $plan, id: r.id, lon: r.lon, lat: r.lat})",
         rows(g.junctions, "id", "lon", "lat")),
        ("UNWIND $rows AS r MATCH (a:Junction {plan: $plan, id: r.a}), (b:Junction {plan: $plan, id: r.b}) "
         "CREATE (a)-[:PIPE {id: r.id, dn: r.dn, km: r.km, mwh: r.mwh}]->(b)",
         rows(g.pipes, "id", "a", "b", "dn", "km", "mwh")),
        ("UNWIND $rows AS r CREATE (:PlanNode:DataCenter {plan: $plan, key: r.key, name: r.name, "
         "status: r.status, lon: r.lon, lat: r.lat})", rows(g.dcs, "key", "name", "status", "lon", "lat")),
        ("UNWIND $rows AS r MATCH (d:DataCenter {plan: $plan, key: r.key}), (j:Junction {plan: $plan, "
         "id: r.junction}) CREATE (d)-[:FEEDS {snap_m: r.snap_m}]->(j)",
         rows([d for d in g.dcs if d["junction"]], "key", "junction", "snap_m")),
        ("UNWIND $rows AS r CREATE (:PlanNode:HeatUser {plan: $plan, id: r.id, name: r.name, kind: r.kind, "
         "assumed: r.assumed, mwh: r.mwh, lon: r.lon, lat: r.lat})",
         rows(g.users, "id", "name", "kind", "assumed", "mwh", "lon", "lat")),
        (f"UNWIND $rows AS r MATCH (u:HeatUser {at}), (j:Junction {{plan: $plan, id: r.junction}}) "
         "CREATE (u)-[:TAPS {snap_m: r.snap_m}]->(j)",
         rows([u for u in g.users if u["junction"]], "id", "junction", "snap_m")),
        (f"UNWIND $rows AS r MATCH (d:DataCenter {{plan: $plan, key: r.dc}}), (u:HeatUser {at}) "
         "CREATE (d)-[:SUPPLIES {mwh: r.mwh}]->(u)", rows(g.users, "id", "dc", "mwh")),
    ]


def _literal(value) -> str:
    """A Python value written as a Cypher literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_literal(v)}" for k, v in value.items()) + "}"
    return "[" + ", ".join(_literal(v) for v in value) + "]"


def script(g: PlanGraph) -> str:
    """The same load as one text with the rows written in, for cypher-shell or the Neo4j Browser."""
    lines = [f"// Heat-network plan '{g.plan}' as a graph (scripts/export_plan_graph.py)."]
    for query, params in statements(g):
        lines.append(query.replace("$rows", _literal(params.get("rows", []))).replace("$plan", _literal(g.plan)) + ";")
    return "\n".join(lines) + "\n"


def write(g: PlanGraph, folder: Path) -> list[Path]:
    """The graph as four tables and the Cypher script, in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    for name, items in (("junctions", g.junctions), ("pipes", g.pipes), ("data_centers", g.dcs), ("users", g.users)):
        path = folder / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            if items:
                writer = csv.DictWriter(f, fieldnames=list(items[0]))
                writer.writeheader()
                writer.writerows(items)
        made.append(path)
    made.append(folder / "load.cypher")
    made[-1].write_text(script(g), encoding="utf-8")
    return made


def connect():
    """A Neo4j driver from NEO4J_URI, NEO4J_USERNAME (default: neo4j) and NEO4J_PASSWORD."""
    uri = os.environ.get("NEO4J_URI")
    if not uri:
        raise GraphDbUnavailable("NEO4J_URI is not set (for example bolt://localhost:7687)")
    try:
        import neo4j
    except ImportError:
        raise GraphDbUnavailable("the Neo4j driver is not installed: uv sync --extra graph") from None
    auth = (os.environ.get("NEO4J_USERNAME", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
    return neo4j.GraphDatabase.driver(uri, auth=auth)


def load(driver, g: PlanGraph, database: str | None = None) -> None:
    """Load the graph into the database, replacing an earlier copy of the same plan."""
    with driver.session(database=database) as session:
        for query, params in statements(g):
            session.run(query, plan=g.plan, **params).consume()


def ask(driver, g: PlanGraph, question: str, database: str | None = None, **params) -> list[dict]:
    """One of the questions in CYPHER, asked of the database."""
    with driver.session(database=database) as session:
        return [record.data() for record in session.run(CYPHER[question], plan=g.plan, **params)]


def differences(g: PlanGraph, driver, database: str | None = None) -> list[str]:
    """Ask the database the three questions and name those whose answer differs from NetworkX's."""
    found = []
    theirs = {r["user"]: {"dc": r["dc"], "pipes": r["pipes"], "km": round(r["km"], 2)}
              for r in ask(driver, g, "routes", database)}
    if theirs != routes(g):
        found.append("routes")
    ours = shared(g)
    if {r["pipe"]: r for r in ask(driver, g, "shared", database)} != {r["pipe"]: r for r in ours}:
        found.append("shared")
    for pipe in [r["pipe"] for r in ours[:3]]:
        if [r["user"] for r in ask(driver, g, "cut", database, pipe=pipe)] != cut(g, pipe):
            found.append(f"cut {pipe}")
    return found
