"""Theme 3, siting: the location model, the candidate grid, the grid distances and the heat value of
a new data center. Synthetic data only: no map, no download."""
from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, Point, box
from synthetic import SCENS

from dcopt.heat.network import Instance, Params, Source, solve
from dcopt.heat.v1 import Site
from dcopt.siting import gridmap
from dcopt.siting.candidates import grid_points
from dcopt.siting.heat_value import LOW_SHARE, candidate_source, carry_over, heat_value, heat_value_of
from dcopt.siting.model import annuity, choose_sites, pareto

P0 = Params(mip_rel_gap=0.0, time_limit=60)


# ------------------------------------------------------------------------------- location model
XY = [(0, 0), (1000, 0), (5000, 0), (9000, 0)]


def test_choose_sites_takes_the_best_scores():
    c = choose_sites([10.0, 30.0, 20.0, 5.0], [0, 0, 0, 0], XY, n=2)
    assert c.chosen == [1, 2] and c.heat == 50.0 and c.grid == 0.0 and c.status == "optimal"


def test_grid_cost_changes_the_choice():
    heat, km = [10.0, 30.0, 20.0, 5.0], [0.0, 10.0, 1.0, 0.0]
    assert choose_sites(heat, km, XY, n=1).chosen == [1]
    c = choose_sites(heat, km, XY, n=1, yen_per_km_year=2.0)
    assert c.chosen == [2] and c.grid == pytest.approx(2.0) and c.net == pytest.approx(18.0)


def test_spacing_keeps_two_picks_apart():
    heat = [30.0, 29.0, 10.0, 5.0]                       # the two best are 1 km apart
    assert choose_sites(heat, [0] * 4, XY, n=2).chosen == [0, 1]
    assert choose_sites(heat, [0] * 4, XY, n=2, spacing_m=2000.0).chosen == [0, 2]


def test_headroom_limits_a_connection_point():
    heat, group = [30.0, 29.0, 10.0, 5.0], ["a", "a", "b", "b"]
    c = choose_sites(heat, [0] * 4, XY, n=2, mw=10.0, group=group, headroom={"a": 10.0})
    assert c.chosen == [0, 2]                             # only one 10 MW site fits at "a"


def test_too_many_sites_asked_for_is_reported_not_forced():
    c = choose_sites([3.0, 2.0], [0, 0], XY[:2], n=2, spacing_m=5000.0)
    assert c.chosen == [] and c.status.startswith("no feasible choice")
    assert choose_sites([3.0, -2.0], [0, 0], XY[:2], n=2, exactly=False).chosen == [0]   # at most n: only what pays


def test_unknown_grid_distance_costs_nothing():
    c = choose_sites([5.0, 4.0], [float("nan"), 1.0], XY[:2], n=1, yen_per_km_year=3.0)
    assert c.chosen == [0] and c.grid == 0.0


def test_pareto_keeps_sites_that_nothing_beats():
    assert pareto([10.0, 8.0, 12.0, 3.0], [2.0, 1.0, 5.0, 4.0]) == [1, 0, 2]


def test_annuity():
    assert annuity(0.03, 30) == pytest.approx(0.0510, abs=1e-4) and annuity(0.0, 20) == pytest.approx(0.05)


# ------------------------------------------------------------------------------ candidate grid
def test_grid_points_fill_the_polygon():
    pts = grid_points(box(0, 0, 4000, 4000), 1000.0)
    assert len(pts) == 16 and all(0 < x < 4000 and 0 < y < 4000 for x, y in pts)
    inner = grid_points(box(0, 0, 4000, 4000), 1000.0, inset_m=600.0)
    assert len(inner) == 4 and set(inner) < set(pts)
    assert grid_points(box(0, 0, 100, 100), 1000.0, inset_m=200.0) == []


# ------------------------------------------------------------------------------ grid distances
def _power() -> gpd.GeoDataFrame:
    rows = [
        {"power": "line", "name": "trunk", "voltage": "275000", "substation": None, "geometry": LineString([(0, 0), (10000, 0)])},
        {"power": "line", "name": "feeder", "voltage": "66000", "substation": None, "geometry": LineString([(0, 3000), (10000, 3000)])},
        {"power": "substation", "name": "A", "voltage": "66000;6600", "substation": "distribution", "geometry": Point(1000, 3000)},
        {"power": "substation", "name": "B", "voltage": "187000;66000", "substation": "transmission", "geometry": Point(9000, 0)},
        {"power": "substation", "name": "plant yard", "voltage": "275000", "substation": "generation", "geometry": Point(1000, 1000)},
    ]
    g = gpd.GeoDataFrame(rows, crs=gridmap.METRIC_CRS)
    g["kv"] = g["voltage"].map(gridmap.top_voltage)
    return g


def test_top_voltage_reads_the_tag():
    assert gridmap.top_voltage("187000;66000") == 187000.0 and gridmap.top_voltage("66000") == 66000.0
    assert math.isnan(gridmap.top_voltage(None)) and math.isnan(gridmap.top_voltage("medium"))


def test_connections_measure_substations_and_lines():
    power = _power()
    lonlat = [(p.x, p.y) for p in gpd.GeoSeries([Point(1000, 2000)], crs=gridmap.METRIC_CRS).to_crs(4326)]
    low = gridmap.connections(power, lonlat, min_kv=66000)[0]
    assert low["substation"] == "A" and low["substation_km"] == pytest.approx(1.0, abs=1e-3)   # not the plant's yard
    assert low["line_275_km"] == pytest.approx(2.0, abs=1e-3) and low["line_66_km"] == pytest.approx(1.0, abs=1e-3)
    assert low["line_187_km"] is None                                                         # no such line mapped
    high = gridmap.connections(power, lonlat, min_kv=187000)[0]
    assert high["substation"] == "B" and high["substation_km"] == pytest.approx(math.hypot(8.0, 2.0), abs=1e-3)


def test_layers_list_lines_and_substations_in_view():
    power = _power()
    west, south, east, north = power.to_crs(4326).total_bounds
    lay = gridmap.layers(power, (west - 0.01, south - 0.01, east + 0.01, north + 0.01))
    assert {l["kv"] for l in lay["lines"]} == {275000, 66000}
    assert {s["name"] for s in lay["substations"]} == {"A", "B", "plant yard"}
    assert [s["generation"] for s in lay["substations"] if s["name"] == "plant yard"] == [True]


# ---------------------------------------------------------------- heat value of a new data center
# Coordinates are metres on a plane: one data center with plenty of heat at the origin, three users
# near it, and one large user 6 km away that it cannot serve profitably.
POS = {"gh": (600, 400), "school": (900, 200), "fish": (500, -500), "far": (6000, 0)}


def build(sources, users) -> Instance:
    pts = [(s.lon, s.lat) for s in sources] + [POS[u.key] for u in users]
    dist = np.array([[1.3 * math.dist(a, b) for b in pts] for a in pts])
    return Instance(list(sources), list(users), dist, road=False)


@pytest.fixture(scope="module")
def world():
    users = [Site("gh", "gh", "gh", "greenhouse", 0.0, 0.0, 2500.0, "test"), Site("school", "school", "school", "school", 0.0, 0.0, 300.0, "test"),
             Site("fish", "fish", "fish", "aquaculture", 0.0, 0.0, 1800.0, "test"), Site("far", "far", "far", "greenhouse", 0.0, 0.0, 2500.0, "test")]
    dc = Source("dc0", "DC 0", "DC 0", 0.0, 0.0, {"low": 2.0, "high": 3.0}, "operating", ("", ""), "test")
    base = solve(build([dc], users), P0, SCENS)
    assert base.x[3] < 0.5, "the far user is not worth a 6 km pipe from the existing data center"
    return base, users


def test_candidate_source_carries_the_load_scenarios():
    s = candidate_source(1.0, 2.0, 10.0)
    assert s.it_mw == {"low": LOW_SHARE * 10.0, "high": 10.0} and s.status == "planned" and s.basis.startswith("assumption")


def test_the_base_plan_carries_over_unchanged(world):
    base, users = world
    inst = build(list(base.inst.sources) + [candidate_source(6100.0, 0.0, 5.0)], users)
    edges, fixed = carry_over(base, inst)
    assert len(edges) == len(base.E) and all(a != 1 and b != 1 for a, b in edges)      # node 1 is the new data center
    kept = solve(inst, P0, SCENS, edges=edges, fix=fixed, design_peak=base.ud.peak)
    assert kept.expected_net == pytest.approx(base.expected_net, rel=1e-9, abs=1.0)


def test_a_data_center_next_to_an_unserved_user_has_value(world):
    base, users = world
    v = heat_value(base, list(base.E), users, 6100.0, 0.0, 5.0, P0, SCENS, build=build)
    assert v.base_net == pytest.approx(base.expected_net, abs=1.0)
    assert v.value > 0 and v.net == pytest.approx(v.base_net + v.value)
    assert v.sites == len(base.connected) + 1 and v.sites_from_candidate == 1 and v.heat_from_candidate > 0


def test_no_load_or_no_reach_means_no_value(world):
    base, users = world
    idle = heat_value(base, list(base.E), users, 6100.0, 0.0, 0.0, P0, SCENS, build=build)
    assert idle.value == pytest.approx(0.0, abs=1.0) and idle.sites_from_candidate == 0
    remote = heat_value(base, list(base.E), users, 60000.0, 0.0, 5.0, P0, SCENS, build=build)
    assert remote.value == pytest.approx(0.0, abs=1.0)


def test_two_data_centers_at_one_place_do_not_double_the_value(world):
    base, users = world
    one = heat_value(base, list(base.E), users, 6100.0, 0.0, 5.0, P0, SCENS, build=build)
    two = heat_value_of(base, list(base.E), users, [(6100.0, 0.0, 5.0), (6100.0, 50.0, 5.0)], P0, SCENS, build=build)
    assert one.value - 1.0 <= two.value < 2 * one.value                       # the same user cannot be served twice
