"""Download the map data for a study area (OpenStreetMap through osmnx).

Fetches the municipal boundary, the drivable road network, facilities, named features, and heat
sources and users (greenhouses, farmland, baths, hospitals, schools, pools, data centers) with their
floor or land area. Everything goes to data/cache/<area>/ and data/raw/, which git ignores.

Source: (c) OpenStreetMap contributors, ODbL 1.0 (Nominatim and Overpass).

Run: uv run python scripts/fetch_data.py --area ishikari
"""
from __future__ import annotations

import argparse
import time

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import box

from dcopt.common.geo import AREAS, DEFAULT_AREA, NAME_COLUMNS, RAW, paths, use_overpass_mirror

MARGIN_DEG = 0.03

# Fallback speeds (km/h) where OSM has no maxspeed: typical rural Hokkaido values.
HWY_SPEEDS = {
    "motorway": 80, "motorway_link": 50, "trunk": 60, "trunk_link": 40,
    "primary": 50, "primary_link": 40, "secondary": 50, "secondary_link": 40,
    "tertiary": 40, "tertiary_link": 30, "unclassified": 40, "residential": 30,
    "living_street": 20, "service": 20, "road": 30,
}

POI_TAGS = {
    "amenity": ["hospital", "clinic", "doctors", "townhall", "community_centre",
                "post_office", "pharmacy", "social_facility"],
    "shop": ["supermarket", "convenience"],
    "railway": ["station"],
    "highway": ["bus_stop"],
}

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_area(cfg: dict, P: dict) -> tuple[gpd.GeoDataFrame, tuple[float, float, float, float]]:
    town = ox.geocode_to_gdf(cfg["town"])[["geometry"]].assign(name=cfg["label"][0])
    if "max_lat" in cfg:           # a long municipality: keep its populated southern part
        town["geometry"] = town.geometry.intersection(box(-180, -90, 180, cfg["max_lat"]))
    town.to_file(P["boundary"], driver="GeoJSON")
    parts = [town[["geometry"]]]
    if cfg["anchors"]:
        points = [ox.geocode(q) for q in cfg["anchors"]]          # (lat, lon)
        parts.append(gpd.GeoDataFrame(geometry=gpd.points_from_xy([p[1] for p in points],
                                                                  [p[0] for p in points]), crs=4326))
        log("anchors: " + ", ".join(f"{q.split(',')[0]} ({p[0]:.4f}, {p[1]:.4f})"
                                    for q, p in zip(cfg["anchors"], points)))
    west, south, east, north = pd.concat(parts).total_bounds
    bbox = (west - MARGIN_DEG, south - MARGIN_DEG, east + MARGIN_DEG, north + MARGIN_DEG)
    gpd.GeoDataFrame(geometry=[box(*bbox)], crs=4326).to_file(P["area"], driver="GeoJSON")
    log(f"study area bbox (W,S,E,N) = {tuple(round(v, 4) for v in bbox)}")
    return town, bbox


def fetch_roads(bbox, P: dict) -> None:
    G = ox.graph_from_bbox(bbox=bbox, network_type="drive")
    G = ox.routing.add_edge_speeds(G, hwy_speeds=HWY_SPEEDS)
    G = ox.routing.add_edge_travel_times(G)
    ox.save_graphml(G, P["graph"])
    log(f"road network: {len(G.nodes):,} nodes, {len(G.edges):,} edges -> {P['graph']}")


def classify(row) -> str:
    amenity, shop = row.get("amenity"), row.get("shop")
    if amenity == "hospital":
        return "hospital"
    if amenity in ("clinic", "doctors"):
        return "clinic"
    if amenity == "townhall":
        return "townhall"
    if amenity == "community_centre":
        return "community"
    if amenity == "post_office":
        return "post"
    if amenity == "pharmacy":
        return "pharmacy"
    if amenity == "social_facility":
        return "care"
    if shop == "supermarket":
        return "supermarket"
    if shop == "convenience":
        return "convenience"
    if row.get("railway") == "station":
        return "station"
    if row.get("highway") == "bus_stop":
        return "bus_stop"
    return "other"


def fetch_pois(bbox, P: dict) -> None:
    gdf = ox.features_from_bbox(bbox=bbox, tags=POI_TAGS).reset_index()
    keep = [c for c in ["element", "id", *NAME_COLUMNS, "amenity", "shop", "railway", "highway",
                        "operator", "healthcare", "geometry"] if c in gdf.columns]
    gdf = gdf[keep].copy()
    gdf["kind"] = gdf.apply(classify, axis=1)
    # Polygons (buildings) -> a point guaranteed to lie inside them.
    gdf["geometry"] = gdf.geometry.to_crs(6680).representative_point().to_crs(4326)
    gdf = gdf[gdf["kind"] != "other"]
    gdf.to_file(P["pois"], driver="GeoJSON")
    log("facilities: " + ", ".join(f"{k} {v}" for k, v in gdf["kind"].value_counts().items()))


def fetch_named(town, P: dict) -> None:
    """Every named feature inside the town (bus-stop landmarks, schools, onsen...)."""
    gdf = ox.features_from_polygon(town.geometry.iloc[0], tags={"name": True}).reset_index()
    gdf = gdf[gdf["name"].notna()].copy()
    gdf["geometry"] = gdf.geometry.to_crs(6680).representative_point().to_crs(4326)
    keep = [c for c in ["element", "id", *NAME_COLUMNS, "amenity", "shop", "highway", "railway", "public_transport",
                        "place", "leisure", "building", "tourism"] if c in gdf.columns]
    gdf[keep + ["geometry"]].to_file(P["named"], driver="GeoJSON")
    log(f"named features: {len(gdf):,}")


HEAT_TAGS = {"landuse": ["greenhouse_horticulture", "farmland"], "building": ["greenhouse", "data_center"],
             "telecom": ["data_center"], "amenity": ["public_bath", "hospital", "school", "social_facility",
                                                     "nursing_home"],
             "leisure": ["swimming_pool", "sports_centre", "ice_rink"]}


def fetch_heat_candidates(town, P: dict) -> None:
    """Heat sources and heat users for Warm Ishikari (idea 17), with floor or land area."""
    g = ox.features_from_polygon(town.geometry.iloc[0], tags=HEAT_TAGS).reset_index().to_crs(6680)
    g["area_m2"] = g.geometry.area
    g["geometry"] = g.geometry.representative_point()
    g = g.to_crs(4326)

    def kind(r):
        for col, vals in HEAT_TAGS.items():
            v = r.get(col)
            if isinstance(v, str) and v in vals:
                return f"{col}={v}"
        return "other"

    g["kind"] = g.apply(kind, axis=1)
    keep = [c for c in ["element", "id", *NAME_COLUMNS, "kind", "area_m2", "operator", "geometry"] if c in g.columns]
    g[keep].to_file(P["dir"] / "heat_candidates.geojson", driver="GeoJSON")
    log("heat candidates: " + ", ".join(f"{k} {v}" for k, v in g["kind"].value_counts().items()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--area", default=DEFAULT_AREA, choices=sorted(AREAS))
    args = ap.parse_args()
    cfg, P = AREAS[args.area], paths(args.area)
    P["dir"].mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    use_overpass_mirror(timeout=600)
    log(f"area: {args.area} ({cfg['label'][1]})")
    town, bbox = fetch_area(cfg, P)
    fetch_pois(bbox, P)
    fetch_named(town, P)
    fetch_heat_candidates(town, P)
    fetch_roads(bbox, P)
    log("done")


if __name__ == "__main__":
    main()
