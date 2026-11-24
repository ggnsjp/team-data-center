"""Warm Ishikari: where should data-center waste heat go?

A fixed-charge network design with twelve monthly heat balances, on Ishikari's real road network.

Supply   The data center's IT load x hours x recoverable share (assumptions), the same every month.
Demand   Each heat user's annual demand (an assumption per type) spread over the months by a profile
         built from JMA climate normals 1991-2020 for Sapporo (station 47412): heating degree-days
         from the monthly mean temperature, or total snowfall for snow melting.
Pipes    Follow streets (OpenStreetMap road distance). A central heat pump at the data center lifts
         the 30-35 C waste heat; the waste heat used is delivered heat x (1 - 1/COP).
Model    max  sum_t sum_j v * s_jt  -  sum_e c * len_e * y_e
         s.t. flow balance per node and month; waste heat per month; f_et <= M_t y_e; y binary.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import scipy.sparse as sp
from scipy.optimize import Bounds, LinearConstraint, milp
from sklearn.cluster import DBSCAN

from dcopt.common.geo import paths, road_distance_matrix, road_path, snap

AREA = "ishikari"
MONTHS_JA = [f"{m}月" for m in range(1, 13)]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
# JMA climate normals 1991-2020, Sapporo (47412): monthly mean temperature (C) and total snowfall (cm).
TEMP = [-3.2, -2.7, 1.1, 7.3, 13.0, 17.0, 21.1, 22.3, 18.6, 12.1, 5.2, -0.9]
SNOW = [137, 116, 74, 6, 0, 0, 0, 0, 0, 1, 30, 113]
JMA_SOURCE = ("気象庁 平年値（1991〜2020年）札幌 / JMA climate normals 1991-2020, Sapporo: "
              "https://www.data.jma.go.jp/obd/stats/etrn/view/nml_sfc_ym.php?prec_no=14&block_no=47412")


def _norm(x):
    s = float(sum(x))
    return [v / s for v in x]


_HDD18 = [d * max(0.0, 18 - t) for d, t in zip(DAYS, TEMP)]
_HDD15 = [d * max(0.0, 15 - t) for d, t in zip(DAYS, TEMP)]
PROFILES = {
    "building": _norm(_HDD18),                                            # space heating
    "greenhouse": _norm(_HDD15),                                          # crops kept above 15 C
    "school": _norm([h * (0.3 if m == 7 else 1.0) for m, h in enumerate(_HDD18)]),   # August break
    "pool": _norm([0.5 * d / 365 + 0.5 * h / sum(_HDD18) for d, h in zip(DAYS, _HDD18)]),
    "snow": _norm(SNOW),                                                  # melting follows snowfall
    "flat": _norm(DAYS),                                                  # aquaculture, process heat
}

# kind -> (ja, en, profile, default annual MWh or None if from floor area)
KINDS = {
    "greenhouse": ("温室（既存）", "Greenhouses (existing)", "greenhouse", None),
    "new_greenhouse": ("温室の新設候補（仮定）", "New greenhouse site (assumed)", "greenhouse", 4000.0),
    "aquaculture": ("陸上養殖（仮定）", "Land-based fish farm (assumed)", "flat", 5000.0),
    "onsen": ("温泉・浴場", "Hot spring / bath", "pool", 2000.0),
    "pool": ("プール・運動施設", "Pool / sports centre", "pool", 800.0),
    "hospital": ("病院", "Hospital", "building", 1500.0),
    "school": ("学校", "School", "school", 250.0),
    "snow": ("ロードヒーティング（仮定）", "Snow melting (assumed)", "snow", None),
    "public": ("公共施設", "Public building", "building", 400.0),
    "hotel": ("ホテル", "Hotel", "pool", 1000.0),
    "factory": ("工場", "Factory", "flat", 1000.0),
}
GREENHOUSE_MWH_PER_M2 = 0.40      # assumption: heated greenhouse in Hokkaido, per m2 per year
SNOW_MWH_PER_M2 = 0.12            # assumption: ~0.25 kWh per m2 per cm of snowfall x 479 cm
KEROSENE_KWH_PER_L = 9.7          # lower heating value of kerosene
KEROSENE_KG_CO2_PER_L = 2.49      # Ministry of the Environment emission factor
GRID_KG_CO2_PER_KWH = 0.55        # assumption for Hokkaido grid electricity
# Electricity for the heat pumps under three supply scenarios, kg CO2 per kWh (label ja, label en, factor).
GRID_SCENARIOS = {
    "renewable": ("再エネ100%", "100 % renewable power", 0.0),
    "target2030": ("2030年度の国の目標", "national target for FY2030", 0.25),
    "grid": ("北海道の系統電力（今）", "Hokkaido grid power today", GRID_KG_CO2_PER_KWH),
}


@dataclass(frozen=True)
class Assumptions:
    it_load_mw: float = 10.0        # data center IT load (assumption)
    recovery: float = 0.6           # share of IT heat recoverable at 30-35 C
    cop: float = 4.0                # heat pump coefficient of performance (to ~60 C)
    kerosene_yen_l: float = 115.0   # avoided fuel
    boiler_eff: float = 0.85
    power_yen_kwh: float = 25.0     # heat pump electricity
    pipe_yen_m: float = 100_000.0   # installed pipe, both ways, per metre of street
    years: int = 30
    rate: float = 0.03
    renewable_power: bool = True    # heat pumps on the data center's renewable power
    max_link_m: float = 8_000.0     # no candidate pipe longer than this
    carbon_yen_t: float = 0.0       # scenario: a price on the CO2 avoided, on top of today's fuel taxes
    subsidy: float = 0.0            # scenario: share of the investment paid by a subsidy

    @property
    def fuel_yen_per_mwh(self) -> float:
        return self.kerosene_yen_l / (KEROSENE_KWH_PER_L * self.boiler_eff) * 1000

    @property
    def hp_yen_per_mwh(self) -> float:
        return self.power_yen_kwh / self.cop * 1000

    @property
    def value_yen_per_mwh(self) -> float:
        return self.fuel_yen_per_mwh - self.hp_yen_per_mwh + self.carbon_yen_per_mwh

    @property
    def carbon_yen_per_mwh(self) -> float:
        """What the carbon price adds to a MWh of delivered heat: the price times the CO2 it avoids."""
        return self.carbon_yen_t * self.co2_t_per_mwh

    @property
    def own_pipe_yen_m(self) -> float:
        """Pipe cost per metre left to the project after the subsidy."""
        return self.pipe_yen_m * (1 - self.subsidy)

    @property
    def crf(self) -> float:
        r, n = self.rate, self.years
        return r * (1 + r) ** n / ((1 + r) ** n - 1)

    @property
    def co2_t_per_mwh(self) -> float:
        return self.co2_t_per_mwh_at(0.0 if self.renewable_power else GRID_KG_CO2_PER_KWH)

    def co2_t_per_mwh_at(self, grid_kg_co2_kwh: float) -> float:
        """t CO2 avoided per MWh delivered: the kerosene not burned minus the heat pump's electricity."""
        fuel = KEROSENE_KG_CO2_PER_L / (KEROSENE_KWH_PER_L * self.boiler_eff)          # kg per kWh heat
        return fuel - grid_kg_co2_kwh / self.cop                                        # t per MWh

    def waste_heat_mwh(self) -> list[float]:
        return [self.it_load_mw * 24 * d * self.recovery for d in DAYS]


@dataclass
class Site:
    key: str
    name: str
    name_en: str
    kind: str
    lon: float
    lat: float
    annual_mwh: float
    source: str               # where the site and its number come from
    node: int = -1

    def monthly(self) -> list[float]:
        return [self.annual_mwh * f for f in PROFILES[KINDS[self.kind][2]] ] if self.kind != "dc" else []


def _offset(lon, lat, east_m, north_m):
    return lon + east_m / (111_320 * math.cos(math.radians(lat))), lat + north_m / 110_540


def ishikari_sites() -> tuple[Site, list[Site]]:
    """The data center and candidate heat users in southern Ishikari (OSM), plus clearly marked
    assumed sites (new greenhouses on farmland, a fish farm, snow melting)."""
    p = paths(AREA)
    cand = gpd.read_file(p["dir"] / "heat_candidates.geojson")
    named = gpd.read_file(p["named"])
    pois = gpd.read_file(p["pois"])
    town = gpd.read_file(p["boundary"]).geometry.iloc[0]
    dc_row = cand[cand["kind"] == "telecom=data_center"].iloc[0]
    dc = Site("dc", dc_row["name"], "Sakura Internet Ishikari Data Center", "dc", dc_row.geometry.x,
              dc_row.geometry.y, 0.0, "OSM")
    sites: list[Site] = []

    gh = cand[cand["kind"] == "building=greenhouse"].to_crs(6680)
    if len(gh):
        xy = np.c_[gh.geometry.x, gh.geometry.y]
        labels = DBSCAN(eps=300, min_samples=1).fit_predict(xy)
        gh = gh.assign(cluster=labels)
        for c, grp in gh.groupby("cluster"):
            pt = gpd.GeoSeries([grp.geometry.union_all().centroid], crs=6680).to_crs(4326).iloc[0]
            area = float(grp["area_m2"].sum())
            sites.append(Site(f"gh{c}", f"温室群（{len(grp)}棟・{area:,.0f}m²）",
                              f"Greenhouses ({len(grp)} buildings, {area:,.0f} m2)", "greenhouse", pt.x, pt.y,
                              area * GREENHOUSE_MWH_PER_M2, "OSM（棟・面積）＋需要は仮定 / OSM + assumed demand"))

    def add_named(kind, rows):
        seen = set()
        for _, r in rows.iterrows():
            if not isinstance(r.get("name"), str) or r["name"] in seen:
                continue
            seen.add(r["name"])
            sites.append(Site(f"{kind}{len(sites)}", r["name"], r["name"], kind, r.geometry.x, r.geometry.y,
                              KINDS[kind][3], "OSM＋需要は仮定 / OSM + assumed demand"))

    add_named("onsen", cand[cand["kind"] == "amenity=public_bath"])
    sports = cand[(cand["kind"] == "leisure=sports_centre")
                  & cand["name"].fillna("").str.contains("プール|海洋センター|サン・ビレッジ")]
    add_named("pool", sports)
    hosp = named[named["name"].fillna("").str.endswith("病院") & named.within(town)]
    add_named("hospital", hosp)
    add_named("school", cand[(cand["kind"] == "amenity=school") & cand["name"].fillna("").str.contains("学校")])
    # Other named buildings that heat water or rooms all year (OpenStreetMap names; demand is an assumption).
    in_town = named[named.within(town)]
    names = in_town["name"].fillna("")
    not_stop = ~names.str.contains("前$|郵便局|バス|出張所")              # bus stops and post offices share these words
    add_named("public", in_town[not_stop & names.str.contains(
        "コミュニティセンター|公民館|図書館|市役所$|保健福祉センター|市民活動情報センター|体育館")])
    add_named("hotel", in_town[not_stop & names.str.contains("ホテル|旅館")])
    add_named("factory", in_town[not_stop & names.str.contains("工場")])

    # Assumed sites, labelled as such: the three largest farmland plots within 6 km get a 1 ha greenhouse.
    farm = cand[cand["kind"] == "landuse=farmland"].to_crs(6680)
    dc_pt = gpd.GeoSeries(gpd.points_from_xy([dc.lon], [dc.lat]), crs=4326).to_crs(6680).iloc[0]
    farm = farm[farm.distance(dc_pt) <= 6000].nlargest(3, "area_m2").to_crs(4326)
    for i, (_, r) in enumerate(farm.iterrows(), start=1):
        sites.append(Site(f"ng{i}", f"温室の新設候補{i}（農地、1ha・仮定）", f"New 1 ha greenhouse {i} (farmland, assumed)",
                          "new_greenhouse", r.geometry.x, r.geometry.y, KINDS["new_greenhouse"][3],
                          "OSMの農地＋施設と需要は仮定 / OSM farmland + assumed facility"))
    fx, fy = _offset(dc.lon, dc.lat, 1200, -900)
    sites.append(Site("fish", "陸上養殖の候補（位置は仮置き）", "Fish farm (assumed, location placeholder)",
                      "aquaculture", fx, fy, KINDS["aquaculture"][3], "仮定 / assumption"))
    sx, sy = _offset(dc.lon, dc.lat, -700, -1500)
    sites.append(Site("snow1", "新港地区の道路融雪（2万m²・仮定）", "Port-area road heating (20,000 m2, assumed)",
                      "snow", sx, sy, 20_000 * SNOW_MWH_PER_M2, "仮定 / assumption"))
    th = pois[(pois["kind"] == "townhall") & pois["name"].fillna("").str.contains("石狩市役所")]
    if len(th):
        r = th.iloc[0]
        sites.append(Site("snow2", "市役所前の融雪（3千m²・仮定）", "Snow melting at City Hall (3,000 m2, assumed)",
                          "snow", r.geometry.x, r.geometry.y, 3_000 * SNOW_MWH_PER_M2, "仮定 / assumption"))
    for s in [dc] + sites:
        s.node = snap(s.lon, s.lat, AREA)
    return dc, sites


@dataclass
class Design:
    sites: list[Site]                       # users considered (index i+1 in nodes)
    edges: list[tuple[int, int, float]]     # built pipes (a, b, metres); node 0 is the data center
    edge_flow: dict[tuple[int, int], float]  # annual MWh through each built pipe
    served: np.ndarray                      # users x 12, MWh
    supply_used: np.ndarray                 # 12, waste heat used, MWh
    waste_heat: list[float]
    A: Assumptions
    status: str
    seconds: float = 0.0
    paths: dict = field(default_factory=dict)
    edge_flow_month: dict = field(default_factory=dict)   # (a, b) -> 12 monthly MWh

    @property
    def delivered(self) -> float:
        return float(self.served.sum())

    @property
    def pipe_m(self) -> float:
        return sum(m for _, _, m in self.edges)

    @property
    def capex(self) -> float:
        return self.pipe_m * self.A.pipe_yen_m

    @property
    def annual_value(self) -> float:
        return self.delivered * self.A.value_yen_per_mwh

    @property
    def own_capex(self) -> float:
        """The investment left to the project after the subsidy."""
        return self.capex * (1 - self.A.subsidy)

    @property
    def subsidy_yen(self) -> float:
        return self.capex * self.A.subsidy

    @property
    def carbon_value(self) -> float:
        """The part of the annual value that comes from the carbon price."""
        return self.delivered * self.A.carbon_yen_per_mwh

    @property
    def annual_net(self) -> float:
        return self.annual_value - self.own_capex * self.A.crf

    @property
    def payback_years(self) -> float:
        return self.own_capex / self.annual_value if self.annual_value > 0 else math.inf

    @property
    def abatement_yen_t(self) -> float:
        """Cost of a tonne of CO2 avoided with no carbon price and no subsidy: annual pipe cost minus
        the fuel saving, per tonne. Negative when the plan pays for itself."""
        if self.co2_t <= 0:
            return math.inf
        return (self.capex * self.A.crf - (self.annual_value - self.carbon_value)) / self.co2_t

    def co2_scenarios(self) -> dict[str, float]:
        """t CO2 avoided a year by this plan under each electricity scenario of GRID_SCENARIOS."""
        return {key: self.delivered * self.A.co2_t_per_mwh_at(f) for key, (_, _, f) in GRID_SCENARIOS.items()}

    @property
    def co2_t(self) -> float:
        return self.delivered * self.A.co2_t_per_mwh

    @property
    def connected(self) -> list[int]:
        return [i for i in range(len(self.sites)) if self.served[i].sum() > 1e-6]


def design(dc: Site, sites: list[Site], A: Assumptions, k: int = 4, kinds: set[str] | None = None,
           links: list[tuple[int, int]] | None = None, time_limit: float = 30.0) -> Design:
    """Optimal network (links=None) or the given links built and used as well as possible.

    Prize-collecting Steiner tree with monthly supply limits, in the strong multi-commodity form:
    x_u connects user u, a unit of commodity u flows from the data center to u along built pipes
    (g_ua <= y_e per user and pipe), and u is served s_ut <= D_ut x_u each month.
    """
    import time
    t0 = time.perf_counter()
    users = [s for s in sites if kinds is None or s.kind in kinds]
    nodes = [dc] + users
    n, T = len(nodes), 12
    dist = road_distance_matrix([s.node for s in nodes], AREA)
    if links is None:
        cand = set()
        for i in range(n):
            order = [j for j in np.argsort(dist[i]) if j != i and dist[i, j] <= A.max_link_m]
            for j in order[:k]:
                cand.add((min(i, j), max(i, j)))
        for j in range(1, n):
            if dist[0, j] <= A.max_link_m:
                cand.add((0, j))
        E = sorted(cand)
    else:
        E = sorted({(min(a, b), max(a, b)) for a, b in links})
    E = [e for e in E if np.isfinite(dist[e])]
    demand = np.array([u.monthly() for u in users]) if users else np.zeros((0, T))
    W = A.waste_heat_mwh()
    nE, nU = len(E), len(users)
    arcs = [(a, b, e) for e, (a, b) in enumerate(E)] + [(b, a, e) for e, (a, b) in enumerate(E)]
    nA = len(arcs)
    # variable layout: y[e] | x[u] | g[u, arc] | s[u, t]
    iy = lambda e: e
    ix = lambda u: nE + u
    ig = lambda u, a: nE + nU + u * nA + a
    isv = lambda u, t: nE + nU + nU * nA + u * T + t
    nv = nE + nU + nU * nA + nU * T
    c = np.zeros(nv)
    for e, (a, b) in enumerate(E):
        c[iy(e)] = A.own_pipe_yen_m * dist[a, b] * A.crf
    for u in range(nU):
        for t in range(T):
            c[isv(u, t)] = -A.value_yen_per_mwh
    rows, cols, vals, lo, hi = [], [], [], [], []
    r = 0

    def add(entries, lb, ub):
        nonlocal r
        for col, v in entries:
            rows.append(r); cols.append(col); vals.append(v)
        lo.append(lb); hi.append(ub); r += 1

    out_arcs = {i: [a for a, (p, q, _) in enumerate(arcs) if p == i] for i in range(n)}
    in_arcs = {i: [a for a, (p, q, _) in enumerate(arcs) if q == i] for i in range(n)}
    for u in range(nU):
        target = u + 1
        for i in range(n):                         # unit flow of commodity u from node 0 to its user
            ent = [(ig(u, a), 1.0) for a in out_arcs[i]] + [(ig(u, a), -1.0) for a in in_arcs[i]]
            if i == 0:
                ent.append((ix(u), -1.0))
            elif i == target:
                ent.append((ix(u), 1.0))
            add(ent, 0.0, 0.0)
        for e in range(nE):                        # g_u(a->b) + g_u(b->a) <= y_e
            add([(ig(u, e), 1.0), (ig(u, e + nE), 1.0), (iy(e), -1.0)], -np.inf, 0.0)
        for t in range(T):                         # served only when connected
            add([(isv(u, t), 1.0), (ix(u), -demand[u, t])], -np.inf, 0.0)
    for t in range(T):                             # waste heat available that month
        add([(isv(u, t), 1 - 1 / A.cop) for u in range(nU)], -np.inf, W[t])
    Amat = sp.csr_matrix((vals, (rows, cols)), shape=(r, nv))
    lb = np.zeros(nv)
    ub = np.full(nv, np.inf)
    ub[:nE + nU] = 1
    ub[nE + nU:nE + nU + nU * nA] = 1
    if links is not None:
        lb[:nE] = 1
    integrality = np.zeros(nv)
    integrality[:nE + nU] = 1
    res = milp(c, constraints=LinearConstraint(Amat, lo, hi), integrality=integrality, bounds=Bounds(lb, ub),
               options={"time_limit": time_limit, "mip_rel_gap": 0.005})
    if res.x is None:
        raise RuntimeError(f"heat network model has no solution: {res.message}")
    x = res.x
    served = np.array([[max(0.0, x[isv(u, t)]) for t in range(T)] for u in range(nU)]) if nU else np.zeros((0, T))
    used = served.sum(axis=0) * (1 - 1 / A.cop)
    built = [(a, b, float(dist[a, b])) for e, (a, b) in enumerate(E) if x[iy(e)] > 0.5]
    flow: dict[tuple[int, int], float] = {(a, b): 0.0 for a, b, _ in built}
    monthly: dict[tuple[int, int], list[float]] = {}
    for e, (a, b) in enumerate(E):
        if x[iy(e)] > 0.5:
            share = [x[ig(u, e)] + x[ig(u, e + nE)] for u in range(nU)]
            monthly[a, b] = [float(sum(served[u, t] * share[u] for u in range(nU))) for t in range(T)]
            flow[a, b] = float(sum(monthly[a, b]))
    d = Design(users, built, flow, served, used, W, A, res.message, time.perf_counter() - t0)
    d.edge_flow_month = monthly
    d.paths = {(a, b): road_path(nodes[a].node, nodes[b].node, AREA) for a, b, _ in built}
    return d


def pairwise(dc: Site, sites: list[Site], A: Assumptions, top: int = 5, kinds: set[str] | None = None) -> Design:
    """The intuitive approach: score each user alone with its own pipe from the data center
    (value of its full demand minus pipe cost), take the best `top`, then see what they deliver."""
    users = [s for s in sites if kinds is None or s.kind in kinds]
    dist = road_distance_matrix([dc.node] + [u.node for u in users], AREA)[0, 1:]
    score = [(u.annual_mwh * A.value_yen_per_mwh - A.own_pipe_yen_m * d * A.crf, i)
             for i, (u, d) in enumerate(zip(users, dist)) if d <= A.max_link_m]
    best = [i for s, i in sorted(score, reverse=True)[:top] if s > 0]
    return design(dc, users, A, links=[(0, i + 1) for i in best])


def standalone_and_shared(d: Design, dc: Site) -> list[dict]:
    """For every user of the design: its result alone (own pipe from the data center, full demand)
    and inside the network (the cost of each built pipe shared by the users downstream of it,
    in proportion to the heat they take)."""
    A = d.A
    dist0 = road_distance_matrix([dc.node] + [s.node for s in d.sites], AREA)[0, 1:]
    adj: dict[int, list[tuple[int, float]]] = {}
    for a, b, m in d.edges:
        adj.setdefault(a, []).append((b, m))
        adj.setdefault(b, []).append((a, m))
    parent, order, seen = {0: (None, 0.0)}, [0], {0}
    for node in order:                                   # breadth-first tree from the data center
        for nb, m in adj.get(node, []):
            if nb not in seen:
                seen.add(nb)
                parent[nb] = (node, m)
                order.append(nb)
    served = {i + 1: float(d.served[i].sum()) for i in range(len(d.sites))}
    below = {n: served.get(n, 0.0) for n in order}
    for n in reversed(order[1:]):                        # heat taken downstream of each node
        below[parent[n][0]] = below.get(parent[n][0], 0.0) + below[n]
    shared_cost = {i + 1: 0.0 for i in range(len(d.sites))}
    for n in order[1:]:                                  # the pipe into n serves everything below n
        p, m = parent[n]
        if below[n] <= 0:
            continue
        stack = [n]
        while stack:                                     # users in the subtree of n
            x = stack.pop()
            if served.get(x, 0.0) > 0:
                shared_cost[x] += A.own_pipe_yen_m * m * A.crf * served[x] / below[n]
            stack += [c for c, (pp, _) in parent.items() if pp == x]
    out = []
    for i, s in enumerate(d.sites):
        alone = s.annual_mwh * A.value_yen_per_mwh - A.own_pipe_yen_m * dist0[i] * A.crf
        shared = served[i + 1] * A.value_yen_per_mwh - shared_cost[i + 1]
        out.append({"site": s, "connected": served[i + 1] > 1e-6, "alone": alone, "shared": shared,
                    "own_pipe_m": float(dist0[i])})
    return out
