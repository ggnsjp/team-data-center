"""Study-area geography: boundaries, the drivable road network (OpenStreetMap), road distances.

Each area has its own folder under data/cache/<area>/ with the municipal boundary, the road network,
facilities and named features; `uv run python scripts/fetch_data.py --area <area>` builds it.
Map data: (c) OpenStreetMap contributors, ODbL 1.0.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "out"

# town: Nominatim query for the boundary. anchors: places outside the boundary the study area must
# reach (hospitals residents travel to). max_lat: clip a very long municipality to its populated part.
AREAS = {
    "ishikari": {"town": "石狩市, 北海道, 日本", "label": ("石狩市", "Ishikari"),
                 "anchors": ["手稲駅, 北海道, 日本"], "max_lat": 43.30},
}
DEFAULT_AREA = "ishikari"

# Snow slows everything down. Applied on top of free-flow travel times.
WINTER_FACTOR = 1.3


def paths(area: str = DEFAULT_AREA) -> dict[str, Path]:
    d = CACHE / area
    return {"dir": d, "graph": d / "study_drive.graphml", "boundary": d / "boundary.geojson",
            "area": d / "study_area.geojson", "pois": d / "pois.geojson", "mesh": d / "mesh_pop.geojson",
            "named": d / "named.geojson"}


# the files ishikari_sites() and the road distances read; the fetch writes them all
MAP_FILES = ("graph", "boundary", "pois", "named")


def fetch_command(area: str = DEFAULT_AREA) -> str:
    return f"uv run python scripts/fetch_data.py --area {area}"


def missing_map_data(area: str = DEFAULT_AREA) -> list[Path]:
    """The map files a page needs that are not there yet (none missing: an empty list). A fetch that
    has not run, or has not finished, leaves some of them out."""
    p = paths(area)
    need = [p[k] for k in MAP_FILES] + [p["dir"] / "heat_candidates.geojson"]
    return [f for f in need if not f.exists()]


OVERPASS_MIRROR = "https://maps.mail.ru/osm/tools/overpass/api"
NAME_COLUMNS = ["name", "name:en", "name:ja-Latn"]     # the name tags kept when map data is fetched


def overpass_url() -> str:
    """The Overpass server every script asks: OVERPASS_URL when it is set, else the public mirror above."""
    import os
    return (os.environ.get("OVERPASS_URL") or OVERPASS_MIRROR).rstrip("/")


def english_name(row) -> str:
    """The name to show in English: OpenStreetMap's name:en, else its romanised name, else the name itself.

    `row` holds one feature's attributes. Files fetched before these tags were kept have neither column.
    """
    for column in NAME_COLUMNS[1:]:
        value = row.get(column)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return row["name"]


def use_overpass_mirror(timeout: int = 300) -> None:
    """osmnx settings shared by the scripts: a public Overpass mirror (overpass-api.de is often at
    capacity; set OVERPASS_URL to override) and the response cache in data/raw/osmnx_cache."""
    ox.settings.overpass_url = overpass_url()
    ox.settings.overpass_rate_limit = False
    ox.settings.http_user_agent = "team-data-center/0.1 (research code)"
    ox.settings.requests_timeout = timeout
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(RAW / "osmnx_cache")


def mesh3_polygon(code: str):
    """Polygon (lon/lat, JGD2011 ~ WGS84) of a 3rd-level (1 km) standard grid square."""
    p, u = int(code[0:2]), int(code[2:4])
    q, v = int(code[4]), int(code[5])
    r, w = int(code[6]), int(code[7])
    south = p / 1.5 + q * 5 / 60 + r * 30 / 3600
    west = u + 100 + v * 7.5 / 60 + w * 45 / 3600
    return box(west, south, west + 45 / 3600, south + 30 / 3600)


_GRAPHS: dict[str, nx.MultiDiGraph] = {}


def load_graph(area: str = DEFAULT_AREA) -> nx.MultiDiGraph:
    """Drivable road network with free-flow `travel_time` (seconds) on every edge."""
    if area not in _GRAPHS:
        path = paths(area)["graph"]
        if not path.exists():
            raise FileNotFoundError(f"{path} missing: run scripts/fetch_data.py --area {area} first")
        _GRAPHS[area] = ox.load_graphml(path)
    return _GRAPHS[area]


def nearest_nodes(lons, lats, area: str = DEFAULT_AREA) -> list[int]:
    return [snap(x, y, area) for x, y in zip(lons, lats)]


_MAIN: dict[str, set] = {}
_TREE: dict[str, tuple] = {}


def main_component(area: str = DEFAULT_AREA) -> set:
    """Nodes of the largest strongly connected component: every pair reachable both ways.
    One-way stubs and parking aisles outside it would make places unreachable."""
    if area not in _MAIN:
        _MAIN[area] = max(nx.strongly_connected_components(load_graph(area)), key=len)
    return _MAIN[area]


def snap(lon: float, lat: float, area: str = DEFAULT_AREA) -> int:
    """Nearest road node inside the main component."""
    if area not in _TREE:
        from sklearn.neighbors import BallTree
        G = load_graph(area)
        ids = [n for n in G.nodes if n in main_component(area)]
        coords = np.radians([[G.nodes[n]["y"], G.nodes[n]["x"]] for n in ids])
        _TREE[area] = (BallTree(coords, metric="haversine"), ids)
    tree, ids = _TREE[area]
    _, idx = tree.query(np.radians([[lat, lon]]), k=1)
    return ids[int(idx[0][0])]


_CSR: dict[str, tuple[sp.csr_matrix, dict[int, int]]] = {}


def _csr(area: str):
    """Directed adjacency (seconds) of the road graph; parallel edges keep the fastest."""
    if area not in _CSR:
        G = load_graph(area)
        pos = {n: i for i, n in enumerate(G.nodes)}
        best: dict[tuple[int, int], float] = {}
        for u, v, d in G.edges(data=True):
            t = float(d.get("travel_time", 0.0))
            k = (pos[u], pos[v])
            if k not in best or t < best[k]:
                best[k] = t
        rows, cols = zip(*best.keys())
        M = sp.csr_matrix((np.fromiter(best.values(), float) + 1e-9, (rows, cols)), shape=(len(pos), len(pos)))
        _CSR[area] = (M, pos)
    return _CSR[area]


_LEN: dict[str, sp.csr_matrix] = {}


def road_distance_matrix(nodes: list[int], area: str = DEFAULT_AREA) -> np.ndarray:
    """Metres along roads between every pair of graph nodes (undirected: pipes follow streets)."""
    if area not in _LEN:
        G = load_graph(area)
        pos = _csr(area)[1]
        best: dict[tuple[int, int], float] = {}
        for u, v, d in G.edges(data=True):
            a, b = sorted((pos[u], pos[v]))
            length = float(d.get("length", 0.0))
            if (a, b) not in best or length < best[a, b]:
                best[a, b] = length
        rows, cols = zip(*best.keys())
        M = sp.csr_matrix((np.fromiter(best.values(), float) + 1e-6, (rows, cols)), shape=(len(pos), len(pos)))
        _LEN[area] = M
    pos = _csr(area)[1]
    idx = [pos[n] for n in nodes]
    return dijkstra(_LEN[area], directed=False, indices=idx)[:, idx]


def road_path(a: int, b: int, area: str = DEFAULT_AREA) -> list[tuple[float, float]]:
    """(lat, lon) points of the shortest road path between two graph nodes, by length."""
    G = load_graph(area)
    nodes = nx.shortest_path(G.to_undirected(as_view=True), a, b, weight="length")
    return [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in nodes]


def travel_time_matrix(nodes: list[int], winter: bool = True, area: str = DEFAULT_AREA) -> np.ndarray:
    """Minutes between every pair of graph nodes (directed, by car)."""
    M, pos = _csr(area)
    idx = [pos[n] for n in nodes]
    D = dijkstra(M, directed=True, indices=idx)          # seconds, one row per source
    factor = WINTER_FACTOR if winter else 1.0
    return D[:, idx] / 60.0 * factor


def geocode(place: str, *, transport=None) -> tuple[float, float, str]:
    """One place name -> (lat, lon, display label) via OSM Nominatim, biased to Ishikari city.

    The viewbox bounds results to the Ishikari area so short names ("新港", "手稲") resolve nearby;
    the app caption credits OpenStreetMap, which also covers Nominatim's attribution requirement.
    Transport injectable for tests; raises LookupError when nothing matches.
    """
    import json as _json
    import urllib.parse
    import urllib.request
    url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&bounded=1"
           "&viewbox=141.05,43.40,141.75,43.05&q=" + urllib.parse.quote(place))
    send = transport or (lambda u: urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": "team-data-center demo app"}), timeout=30))
    with send(url) as res:  # noqa: SIM115 - the context manager closes the real response
        rows = _json.loads(res.read().decode("utf-8"))
    if not rows:
        raise LookupError(f"Nominatim found no place for {place!r} in the Ishikari area")
    return float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0]["display_name"]
