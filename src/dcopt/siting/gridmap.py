"""Transmission lines and substations around the study area, as mapped in OpenStreetMap.

There is no public network model of the Hokkaido grid, so the siting model cannot use a hosting
capacity yet. What OpenStreetMap does give is geometry: the lines with their voltage classes and
the substations. This module downloads them into data/cache/<area>/power.geojson (ODbL, never
committed) and measures, for any point, the distance to the nearest substation and to the nearest
line of each voltage class. Those distances stand in for the cost of a grid connection.

The data is what volunteers mapped. It is not checked against the grid operator's records.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

from dcopt.common.geo import CACHE, DEFAULT_AREA, paths

METRIC_CRS = 6680                      # JGD2011 / Japan Plane Rectangular CS XII (western Hokkaido), metres
CLASSES = (275000, 187000, 66000)      # voltage classes of the transmission system around Ishikari, volts
TAGS = {"power": ["line", "minor_line", "cable", "substation", "plant"]}
COLUMNS = ["power", "name", "voltage", "operator", "circuits", "substation", "plant:source", "plant:output:electricity"]


def power_path(area: str = DEFAULT_AREA) -> Path:
    return CACHE / area / "power.geojson"


def top_voltage(tag) -> float:
    """The highest voltage in an OpenStreetMap voltage tag such as "187000;66000" (nan if none)."""
    values = [int(t) for t in str(tag).replace(",", ";").split(";") if t.strip().isdigit()]
    return float(max(values)) if values else float("nan")


def fetch_power(area: str = DEFAULT_AREA, margin_deg: float = 0.06) -> Path | None:
    """Download the power features around the study area. Returns the cache path, or None when the
    download fails (offline, a busy server); callers then carry on without grid distances."""
    import osmnx as ox

    from dcopt.common.geo import use_overpass_mirror
    try:
        use_overpass_mirror(timeout=180)
        west, south, east, north = gpd.read_file(paths(area)["area"]).total_bounds
        box = (west - margin_deg, south - margin_deg, east + margin_deg, north + margin_deg)
        g = ox.features_from_bbox(box, TAGS).reset_index()
        g = g[[c for c in COLUMNS if c in g.columns] + ["geometry"]]
        path = power_path(area)
        path.parent.mkdir(parents=True, exist_ok=True)
        g.to_file(path, driver="GeoJSON")
        return path
    except Exception:  # noqa: BLE001  (network trouble, a busy server or an empty answer: carry on without)
        return None


def load_power(area: str = DEFAULT_AREA, download: bool = True) -> gpd.GeoDataFrame | None:
    """The cached power features with a numeric `kv` column (volts), in a metric projection."""
    path = power_path(area)
    if not path.exists() and (not download or fetch_power(area) is None):
        return None
    return prepare(gpd.read_file(path))


def prepare(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = g.to_crs(METRIC_CRS).copy()
    g["kv"] = g["voltage"].map(top_voltage) if "voltage" in g.columns else np.nan
    return g


def connections(power: gpd.GeoDataFrame, lonlat: list[tuple[float, float]], min_kv: float = 66000.0) -> list[dict]:
    """For each (lon, lat): the nearest substation of at least `min_kv` volts (the switchyards of
    power plants are left out) and the distance to the nearest line of each voltage class, in km."""
    pts = gpd.GeoSeries([Point(xy) for xy in lonlat], crs=4326).to_crs(METRIC_CRS)
    subs = power[(power["power"] == "substation") & (power["kv"] >= min_kv)]
    if "substation" in subs.columns:
        subs = subs[subs["substation"] != "generation"]
    lines = power[power["power"].isin(["line", "cable", "minor_line"])]
    by_class = {c: lines[lines["kv"] == c].geometry for c in CLASSES}
    out = []
    for p in pts:
        row: dict = {"substation": None, "substation_kv": None, "substation_km": None}
        if len(subs):
            d = subs.geometry.distance(p)
            i = d.idxmin()
            name = subs.loc[i, "name"] if "name" in subs.columns else None
            row.update(substation=name if isinstance(name, str) else None, substation_kv=float(subs.loc[i, "kv"]),
                       substation_km=float(d.min()) / 1000, substation_id=int(i))
        for c, geoms in by_class.items():
            row[f"line_{c // 1000}_km"] = float(geoms.distance(p).min()) / 1000 if len(geoms) else None
        out.append(row)
    return out


def layers(power: gpd.GeoDataFrame, bounds: tuple[float, float, float, float]) -> dict:
    """Lines by voltage class and substations inside (west, south, east, north), as plain lon/lat
    lists for a map layer."""
    west, south, east, north = bounds
    g = power.to_crs(4326).cx[west:east, south:north]
    lines = []
    for _, r in g[g["power"].isin(["line", "cable", "minor_line"]) & g["kv"].isin(CLASSES)].iterrows():
        for part in getattr(r.geometry, "geoms", [r.geometry]):
            lines.append({"kv": int(r["kv"]), "name": r["name"] if isinstance(r.get("name"), str) else None,
                          "path": [[round(x, 5), round(y, 5)] for x, y in part.coords]})
    subs = []
    for _, r in g[(g["power"] == "substation") & g["kv"].isin(CLASSES)].iterrows():
        p = r.geometry.representative_point()
        subs.append({"kv": int(r["kv"]), "name": r["name"] if isinstance(r.get("name"), str) else None,
                     "lon": round(p.x, 5), "lat": round(p.y, 5),
                     "generation": r.get("substation") == "generation"})
    return {"lines": lines, "substations": subs}
