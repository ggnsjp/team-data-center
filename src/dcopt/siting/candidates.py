"""Candidate sites for a new data center: a regular grid over the municipality, snapped to roads.

A first screen, not a land survey: zoning, ownership, ground conditions and hazards are not
checked. The grid makes the heat value comparable across the whole area, including places nobody
has proposed.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

from dcopt.common.geo import DEFAULT_AREA, load_graph, paths, snap
from dcopt.siting.gridmap import METRIC_CRS


def grid_points(polygon, spacing_m: float, inset_m: float = 0.0) -> list[tuple[float, float]]:
    """Points of a square grid (metric coordinates) inside the polygon, at least inset_m from its edge."""
    shape = polygon.buffer(-inset_m) if inset_m > 0 else polygon
    if shape.is_empty:
        return []
    west, south, east, north = polygon.bounds            # the grid is anchored to the polygon; the inset only removes points
    xs = np.arange(west + spacing_m / 2, east, spacing_m)
    ys = np.arange(south + spacing_m / 2, north, spacing_m)
    return [(float(x), float(y)) for y in ys for x in xs if shape.contains(Point(x, y))]


def grid_candidates(area: str = DEFAULT_AREA, spacing_m: float = 2000.0, inset_m: float = 200.0,
                    max_snap_m: float = 600.0) -> list[dict]:
    """Grid points inside the municipal boundary, each moved to the nearest road node. A point
    farther than max_snap_m from any road is dropped (open water, dunes, fields without access)."""
    boundary = gpd.read_file(paths(area)["boundary"]).to_crs(METRIC_CRS)
    polygon = boundary.geometry.union_all() if hasattr(boundary.geometry, "union_all") else boundary.geometry.unary_union
    pts = grid_points(polygon, spacing_m, inset_m)
    if not pts:
        return []
    lonlat = gpd.GeoSeries([Point(p) for p in pts], crs=METRIC_CRS).to_crs(4326)
    graph = load_graph(area)
    out, seen = [], set()
    for (x, y), p in zip(pts, lonlat):
        node = snap(p.x, p.y, area)
        if node in seen:
            continue
        nlon, nlat = float(graph.nodes[node]["x"]), float(graph.nodes[node]["y"])
        q = gpd.GeoSeries([Point(nlon, nlat)], crs=4326).to_crs(METRIC_CRS).iloc[0]
        gap = float(np.hypot(q.x - x, q.y - y))
        if gap > max_snap_m:
            continue
        seen.add(node)
        out.append({"id": f"g{len(out) + 1:02d}", "lon": nlon, "lat": nlat, "node": int(node),
                    "x": float(q.x), "y": float(q.y), "snap_m": gap})
    return out


def name_places(cands: list[dict], area: str = DEFAULT_AREA) -> list[dict]:
    """Add `near` to each candidate: the name of the closest quarter or neighbourhood in the cached
    OpenStreetMap names (the grid points themselves have no names). Left out when there are none."""
    path = paths(area)["named"]
    if not path.exists() or not cands:
        return cands
    named = gpd.read_file(path)
    if "place" not in named.columns:
        return cands
    named = named[named["place"].isin(["quarter", "neighbourhood", "suburb", "village", "hamlet"]) & named["name"].notna()]
    if named.empty:
        return cands
    named = named.to_crs(METRIC_CRS)
    for c in cands:
        d = named.geometry.distance(Point(c["x"], c["y"]))
        i = d.idxmin()
        c["near"], c["near_m"] = str(named.loc[i, "name"]), float(d.min())
    return cands
