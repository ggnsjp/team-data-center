"""The plan as a graph: built from an export, three questions, and the optional Neo4j side."""
import json
import sys
from pathlib import Path

import networkx as nx
import pytest

from dcopt.heat import plangraph as pg

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "out" / "heat_network_v2" / "plans.json"


def toy() -> dict:
    """Data center A supplies four users over three pipes, data center B supplies nobody, and one
    pipe runs from a junction to itself (two users at one street node)."""
    def site(name, lon, lat, dc, monthly):
        return {"name_en": name, "kind": "pool", "lon": lon, "lat": lat, "annual": 12 * monthly,
                "assumed": False, "dc": dc, "served": [monthly] * 12}

    pipes = [
        {"path": [[141.000, 43.000], [141.005, 43.000], [141.010, 43.000]], "dn": 200, "km": 0.8, "monthly": [35] * 12},
        {"path": [[141.010, 43.000], [141.020, 43.000]], "dn": 150, "km": 0.8, "monthly": [15] * 12},
        {"path": [[141.010, 43.000], [141.010, 43.010]], "dn": 80, "km": 1.1, "monthly": [20] * 12},
        {"path": [[141.020, 43.000], [141.020, 43.000]], "dn": 80, "km": 0.0, "monthly": [5] * 12},
    ]
    sites = [site("Pool", 141.0201, 43.0001, "a", 10), site("School", 141.0199, 42.9999, "a", 5),
             site("O'Hara bath", 141.0101, 43.0101, "a", 20), site("Farm", 141.30, 43.30, None, 0),
             site("Hotel", 141.0001, 43.0001, "a", 1)]
    dcs = [{"key": "a", "name_en": "Data center A", "lon": 141.0, "lat": 43.0002, "status": "operating"},
           {"key": "b", "name_en": "Data center B", "lon": 141.05, "lat": 43.0, "status": "planned"}]
    return {"dcs": dcs, "plans": {"toy": {"pipes": pipes, "sites": sites}}}


@pytest.fixture
def g() -> pg.PlanGraph:
    return pg.build(toy(), "toy")


def test_build_attaches_users_and_supplying_data_centers(g):
    assert [j["id"] for j in g.junctions] == ["j1", "j2", "j3", "j4"]
    assert [(p["id"], p["a"], p["b"]) for p in g.pipes] == [("p1", "j1", "j2"), ("p2", "j2", "j3"),
                                                           ("p3", "j2", "j4"), ("p4", "j3", "j3")]
    assert [(u["name"], u["junction"], u["mwh"]) for u in g.users] == [
        ("Pool", "j3", 120), ("School", "j3", 60), ("O'Hara bath", "j4", 240), ("Hotel", "j1", 12)]
    assert all(u["snap_m"] < 30 for u in g.users)
    assert {d["key"]: d["junction"] for d in g.dcs} == {"a": "j1", "b": None}     # B supplies nobody


def test_routes_cut_and_shared(g):
    found = pg.routes(g)
    assert found["u1"] == {"dc": "a", "pipes": ["p1", "p2"], "km": 1.6}
    assert found["u3"] == {"dc": "a", "pipes": ["p1", "p3"], "km": 1.9}
    assert found["u4"] == {"dc": "a", "pipes": [], "km": 0}                       # at the data center's junction
    assert pg.cut(g, "p2") == ["u1", "u2"] and pg.cut(g, "p1") == ["u1", "u2", "u3"] and pg.cut(g, "p4") == []
    assert pg.shared(g) == [{"pipe": "p1", "dn": 200, "km": 0.8, "users": 3, "mwh": 420},
                            {"pipe": "p2", "dn": 150, "km": 0.8, "users": 2, "mwh": 180},
                            {"pipe": "p3", "dn": 80, "km": 1.1, "users": 1, "mwh": 240}]


def test_statements_and_script(g, tmp_path):
    stmts = pg.statements(g)
    assert stmts[0][0] == "MATCH (n:PlanNode {plan: $plan}) DETACH DELETE n"
    assert [len(p.get("rows", [])) for _, p in stmts] == [0, 4, 4, 2, 1, 4, 4, 4]
    text = pg.script(g)
    assert "$rows" not in text and "$plan" not in text
    assert "MATCH (n:PlanNode {plan: 'toy'}) DETACH DELETE n;" in text and "'O\\'Hara bath'" in text
    made = pg.write(g, tmp_path)
    assert [p.name for p in made] == ["junctions.csv", "pipes.csv", "data_centers.csv", "users.csv", "load.cypher"]
    assert len((tmp_path / "users.csv").read_text(encoding="utf-8").splitlines()) == 5
    assert (tmp_path / "load.cypher").read_text(encoding="utf-8") == text


class _Result(list):
    def consume(self):
        return None


class _Record(dict):
    def data(self):
        return dict(self)


class _Driver:
    """Stands in for a Neo4j driver: records what is run and answers from a function."""

    def __init__(self, answers=lambda query, params: []):
        self.log, self.answers = [], answers

    def session(self, database=None):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.log.append((query, params))
        return _Result(_Record(row) for row in self.answers(query, params))


def _as_the_database_would(g, wrong=False):
    def answers(query, params):
        if query == pg.CYPHER["routes"]:
            return [{"user": u, "dc": r["dc"], "pipes": r["pipes"][:-1] if wrong else r["pipes"], "km": float(r["km"])}
                    for u, r in pg.routes(g).items()]
        if query == pg.CYPHER["shared"]:
            return pg.shared(g)
        if query == pg.CYPHER["cut"]:
            return [{"user": u} for u in pg.cut(g, params["pipe"])]
        return []
    return answers


def test_load_and_compare_with_a_stand_in_driver(g):
    driver = _Driver()
    pg.load(driver, g)
    assert len(driver.log) == 8 and all(params["plan"] == "toy" for _, params in driver.log)
    assert driver.log[0][0].startswith("MATCH (n:PlanNode")
    assert pg.differences(g, _Driver(_as_the_database_would(g))) == []
    assert pg.differences(g, _Driver(_as_the_database_would(g, wrong=True))) == ["routes"]


def test_connect_says_what_is_missing(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    with pytest.raises(pg.GraphDbUnavailable, match="NEO4J_URI"):
        pg.connect()
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setitem(sys.modules, "neo4j", None)                              # as if the driver were not installed
    with pytest.raises(pg.GraphDbUnavailable, match="uv sync --extra graph"):
        pg.connect()


@pytest.mark.skipif(not PLANS.exists(), reason="run scripts/export_heat_network_v2.py first")
def test_the_exported_plans_are_trees_with_a_route_to_every_user():
    plans = json.loads(PLANS.read_text(encoding="utf-8"))
    for name in plans["plans"]:
        graph = pg.build(plans, name)
        assert nx.is_tree(pg.network(graph)), name
        assert set(pg.routes(graph)) == {u["id"] for u in graph.users}, name
        attached = {u["junction"] for u in graph.users} | {d["junction"] for d in graph.dcs if d["junction"]}
        assert attached == {j["id"] for j in graph.junctions}, name
