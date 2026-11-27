"""Warm Ishikari, model v2: several data centers, pipe sizes, network temperature, uncertain inputs.

A mixed-integer program that routes data-center waste heat to nearby users (greenhouses, a fish farm,
snow melting, baths, pools, hospitals, schools) along Ishikari's streets. It builds on dcopt.heat.v1
and adds:

  Sources      Several data centers, each with its own monthly waste-heat limit. Every connected user is
               served by exactly one of them; pipes may be shared and may link data centers.
  Pipe sizes   Each built link gets one standard size (DN50-DN250). Its capacity (MW) must cover the
               peak heat of every user whose heat it carries, and its cost per metre grows with size.
  Temperature  "ambient": the network carries the waste heat at about 30 C; each user lifts it with its
               own heat pump, or uses it directly when it needs 27 C or less. "central": one heat pump
               per data center sends about 60 C water; small temperature drop, so larger pipe flows.
  Scenarios    Pipes and connections are decided once; heat deliveries adapt to each scenario of IT load
               and kerosene price, and (when the scenario carries a weather year, dcopt.heat.weather)
               of the year's own temperature and snowfall, which reshape and scale each user's months.
               Objectives (OBJECTIVES): the expected net benefit (two-stage stochastic),
               the worst scenario's net benefit (max-min), or the largest regret (min-max regret), the last
               two through one epigraph variable. `ccg` adds the two-stage adjustable robust plan over a
               budgeted interval set of IT loads by column-and-constraint generation.
  Solving      HiGHS by default (DCOPT_SOLVER=gurobi to use Gurobi when installed). On the full Ishikari
               instance `solve_kernel` (LP-guided kernel search, optional warm-started full MILP) is used,
               because the pipe-size choice makes the full MILP slow to close.

Symbols (see `solve`). Users u, data centers d, candidate links e (arcs a, both directions), pipe
sizes k, months t, scenarios w with probability p_w.

  y_ek in {0,1}   link e built with size k          x_u in {0,1}    user u connected
  z_ud in {0,1}   user u served by data center d    g_ua in [0,1]   share of user u's commodity on arc a
  s_udtw >= 0     MWh delivered to u from d in month t of scenario w

  max  sum_w p_w sum_{u,d,t} v_uw s_udtw  -  CRF sum_{e,k} c_k l_e y_ek  -  CRF_hp sum_u h_u x_u
  s.t. out_i(g_u) - in_i(g_u) = z_ud at data center i = d, -x_u at user u's node, 0 elsewhere  (flow)
       sum_d z_ud = x_u                                                    (exactly one data center)
       g_u(a->b) + g_u(b->a) <= sum_k y_ek                                 (heat only on built pipes)
       sum_k y_ek <= 1                                                     (one size per link)
       sum_u q_u (g_u(a->b) + g_u(b->a)) <= sum_k cap_k y_ek               (pipe capacity at peak)
       s_udtw <= cap_ut z_ud                                               (demand and coverage)
       sum_u r_u s_udtw <= W_dtw                                           (waste heat per month)

  v_uw   yen per MWh delivered: avoided kerosene minus heat-pump electricity
  r_u    MWh of waste heat drawn per MWh delivered (heat pump lift and network loss)
  q_u    MW the user's heat adds to every pipe on its path at peak (alpha x peak x network share)
  W_dtw  IT load x hours x recoverable share
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import numpy as np
import scipy.sparse as sp

from dcopt.heat.v1 import (
    DAYS,
    GRID_KG_CO2_PER_KWH,
    GRID_SCENARIOS,
    KEROSENE_KG_CO2_PER_L,
    KEROSENE_KWH_PER_L,
    KINDS,
    Site,
    _offset,
    capital_recovery,
)

if TYPE_CHECKING:
    from dcopt.heat.weather import WeatherYear

AREA = "ishikari"
T = 12
HOURS = [24 * d for d in DAYS]

# ---------------------------------------------------------------- sources of the numbers used below
URL = {
    "isrd": "https://www.bbtower.co.jp/ir/pr/docs/20251128_ishikari_release.pdf",
    "isrd_mw": "https://cloud.watch.impress.co.jp/docs/news/2097920.html",
    "isrd_site": "https://prtimes.jp/main/html/rd/p/000000693.000006953.html",
    "gsi": "https://msearch.gsi.go.jp/address-search/AddressSearch?q=石狩市新港中央1丁目",
    "sakura": "https://www.sakura.ad.jp/corporate/corp/datacenter/",
    "sakura_racks": "https://cloud.watch.impress.co.jp/docs/news/723209.html",
    "zed": "https://cloud.watch.impress.co.jp/docs/news/1627835.html",
    "zed_heat": "https://www.env.go.jp/content/900514282.pdf",
    "nttme": "https://cloud.watch.impress.co.jp/docs/news/2057156.html",
    "kerosene": "https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/xlsx/261118.xlsx",
    "pipe": "https://ynu.repo.nii.ac.jp/record/12712/files/tachibana_masaya-thesis.pdf",
    "co2": "https://policies.env.go.jp/earth/ghg-santeikohyo/files/calc/ichiran_2025r.pdf",
    "grid_co2": "https://policies.env.go.jp/earth/ghg-santeikohyo/files/calc/r08_denki_coefficient_rev4.pdf",
    "grid_2030": "https://www.env.go.jp/content/000290553.pdf",
    "osm": "https://www.openstreetmap.org/copyright",
}

MODES = {
    "ambient": ("低温の導管網（約30℃）＋利用先ごとのヒートポンプ", "Ambient loop (~30 C) + a heat pump at each user"),
    "central": ("データセンターのヒートポンプで約60℃にして送る", "Central heat pump at the data center, ~60 C network"),
}

# Supply temperature each kind of user needs (C). All assumptions; the rationale is in SUPPLY_BASIS.
SUPPLY_C = {"greenhouse": 45.0, "new_greenhouse": 45.0, "aquaculture": 22.0, "snow": 25.0,
            "pool": 40.0, "onsen": 60.0, "hospital": 60.0, "school": 45.0,
            "public": 45.0, "hotel": 60.0, "factory": 60.0}
SUPPLY_BASIS = {
    "greenhouse": "assumption: hot-water pipe heating in greenhouses runs at about 40-50 C",
    "new_greenhouse": "assumption: as existing greenhouses",
    "aquaculture": "assumption: rearing water 15-28 C by species (eel 25-28 C in the Bibai case); 22 C as a middle value",
    "snow": "assumption: low-temperature hydronic snow melting can run on 20-30 C water",
    "pool": "assumption: pool water about 28-30 C plus hall heating about 40 C",
    "onsen": "assumption: hot water stored at 60 C or more against Legionella",
    "hospital": "assumption: hot water at 60 C or more; space heating 45-60 C",
    "school": "assumption: low-temperature radiators or floor heating about 45 C",
    "public": "assumption: space heating with low-temperature radiators about 45 C",
    "hotel": "assumption: hot water stored at 60 C or more against Legionella",
    "factory": "assumption: process and wash water about 60 C",
}
# Design-hour peak divided by the average load of the coldest (or snowiest) month. All assumptions.
PEAK_FACTOR = {"greenhouse": 2.5, "new_greenhouse": 2.5, "aquaculture": 1.2, "snow": 3.0,
               "pool": 1.4, "onsen": 1.4, "hospital": 1.8, "school": 2.0,
               "public": 2.0, "hotel": 1.4, "factory": 1.2}
PEAK_BASIS = ("assumption: greenhouses heat mostly at night (2.5); snow melting follows snowfall events (3.0); "
              "space heating 1.8-2.0 (hospitals, schools, public buildings); pools, baths and hotels are steady (1.4); "
              "fish farms and factories very steady (1.2)")

RHO, CP = 990.0, 4.18          # water at 30-60 C: kg/m3, kJ/(kg K)
SUBSIDY_RATES = (1 / 3, 1 / 2, 2 / 3)   # scenario rates shown on the proposals (no claim about a scheme)


@dataclass(frozen=True)
class PipeSize:
    """A pre-insulated twin pipe (supply and return) of one nominal size."""
    dn: int
    inner_m: float       # inner diameter of carbon steel pipe, JIS G 3452 (SGP)
    velocity: float      # design velocity, m/s (assumption: 1.0 m/s at DN50 rising to 2.2 m/s at DN250)
    yen_m: float         # installed cost per metre of route, both pipes (see PIPE_COST_BASIS)

    def capacity_mw(self, dT: float) -> float:
        return RHO * self.velocity * math.pi * self.inner_m ** 2 / 4 * CP * dT / 1000


def pipe_cost_yen_m(dn: float) -> float:
    """Direct cost per metre on a straight line through 25A = 40,000 and 250A = 250,000 yen/m, plus 33 %."""
    return (40_000 + (dn - 25) * (250_000 - 40_000) / (250 - 25)) * 1.33


PIPE_COST_BASIS = ("assumption: straight line through the 2019 quotes for small two-pipe pre-insulated steel "
                   "networks (25A about 40,000, 250A about 250,000 yen per metre of route, direct cost) plus "
                   "about 33 % overhead, read off the charts in " + URL["pipe"])
HP_COST_BASIS = ("users: assumption for small heat pumps (100 kW to 2 MW), to check with makers; central: about "
                 "EUR 0.65M per MW of heat at Odense (two ammonia heat pumps, 44.6 MW, DKK 215M; Dansk Fjernvarme, "
                 "https://danskfjernvarme.dk/media/eqbhcqlv/inspirationskatalog-for-store-varmepumper-2022.pdf), "
                 "taken as 100M yen/MW (assumption, including the exchange rate)")
TIE_BASIS = ("assumption, not a real cost: a tie-break so that equal-cost users go to the nearer data center "
             "(solver-independent); about 2 millionths of the annuity of the cheapest pipe (DN50, about 4,300 "
             "yen/m/yr), so the plan's net benefit moves by at most this times the distances of connected users")
PIPE_SIZES = tuple(PipeSize(dn, d / 1000, v, pipe_cost_yen_m(dn)) for dn, d, v in [
    (50, 52.9, 1.0), (80, 80.7, 1.2), (100, 105.3, 1.5), (150, 155.2, 1.8), (200, 204.7, 2.0), (250, 254.2, 2.2)])


@dataclass(frozen=True)
class Params:
    mode: str = "ambient"            # "ambient" or "central" (see MODES)
    waste_c: float = 30.0            # assumption: waste heat collected at 30-35 C (liquid or rear-door cooling)
    network_c: float = 30.0          # assumption: ambient loop supply temperature, about the waste-heat level
    central_c: float = 60.0          # assumption: central network supply temperature, enough for hot water
    approach_k: float = 5.0          # assumption: heat-exchanger and evaporator temperature approach
    direct_margin_k: float = 3.0     # assumption: users needing <= network - 3 K take the heat directly
    carnot_eff: float = 0.5          # assumption: water-to-water heat pumps reach about 45-55 % of Carnot
    cop_cap: float = 8.0             # assumption: upper end of manufacturer data for small lifts
    dT_ambient: float = 10.0         # assumption: supply-return difference of a low-temperature loop
    dT_central: float = 30.0         # assumption: 60/30 C network
    loss_ambient: float = 0.02       # assumption: a near-ground-temperature loop loses little heat
    loss_central: float = 0.08       # assumption: small 60 C networks lose about 5-10 % a year
    recovery: float = 0.6            # assumption (as v1): share of IT heat recoverable at 30-35 C
    boiler_eff: float = 0.85         # assumption (as v1): kerosene boiler the heat replaces
    power_yen_kwh: float = 25.0      # assumption (as v1): electricity for the heat pumps
    years: int = 30                  # assumption (as v1): pipe life for the annuity
    rate: float = 0.03               # assumption (as v1): real discount rate
    hp_years: int = 20               # assumption: heat-pump life for the annuity
    hp_yen_per_mw_user: float = 150e6   # heat pumps at the users, yen per MW of heat (HP_COST_BASIS)
    hp_yen_per_mw_central: float = 100e6  # central heat pump, yen per MW of heat (HP_COST_BASIS)
    alpha: float = 1.0               # share of each user's peak the pipes and heat pumps are sized for
    sizing: str = "published"        # "published": alpha x the worst month of the worst scenario; "robust":
                                     # also cover the worst DAY of weather-bearing scenarios (daily_peak_mw).
                                     # "free": no sizing floor — the optimizer trades pipe cost against
                                     # cold-year shedding (needs user_connection='decided').
                                     # 管やヒートポンプのサイズ根拠：「公表」は最悪月、「頑健」は最悪日まで
    user_connection: str = "sized"   # "sized": each user's draw is hard-wired to the sizing peak (the
                                     # published convention); "decided" (extended formulation only): the
                                     # user's connection DN is a decision — a smaller connection throttles
                                     # the user in cold years instead of excluding the build.
                                     # 需要家の引込管サイズを決定変数にする（extended 計算式のみ）
    sizes: tuple = PIPE_SIZES
    supply_c: dict = field(default_factory=lambda: dict(SUPPLY_C))
    peak_factor: dict = field(default_factory=lambda: dict(PEAK_FACTOR))
    cop_override: float | None = None   # one COP for every user (validation against v1)
    loss_override: float | None = None
    renewable_central: bool = True   # assumption (as v1): the central heat pump runs on the data center's renewable power
    grid_t_per_mwh: float = GRID_KG_CO2_PER_KWH   # t CO2 per MWh: Hokkaido Electric, standard plans (URL["grid_co2"])
    carbon_yen_t: float = 0.0        # scenario: a price on the CO2 avoided, on top of today's fuel taxes
    subsidy: float = 0.0             # scenario: share of the pipe and heat-pump investment paid by a subsidy
    k: int = 3                       # candidate links: k nearest neighbours of every node
    dc_links: int = 1                # and each user's nearest data center(s); data centers link to each other
    max_link_m: float = 8_000.0      # no candidate link longer than this
    time_limit: float = 60.0
    mip_rel_gap: float = 0.005
    formulation: str = "aggregated"  # "aggregated": shares per arc (fast LP); "extended": per arc and size (larger, barely tighter here)
    solver: str | None = None        # "highs" (default) or "gurobi"; else DCOPT_SOLVER
    heuristic_effort: float = 0.3    # HiGHS mip_heuristic_effort (default 0.05): more incumbent search
    tie_yen_m: float = 0.01          # assumption: tie-break, yen per metre per year from data center to user (TIE_BASIS)

    @property
    def crf(self) -> float:
        return capital_recovery(self.rate, self.years)

    @property
    def crf_hp(self) -> float:
        return capital_recovery(self.rate, self.hp_years)

    @property
    def own(self) -> float:
        """Share of the investment left to the project after the subsidy."""
        return 1.0 - self.subsidy

    @property
    def loss(self) -> float:
        if self.loss_override is not None:
            return self.loss_override
        return self.loss_ambient if self.mode == "ambient" else self.loss_central

    @property
    def dT(self) -> float:
        return self.dT_ambient if self.mode == "ambient" else self.dT_central

    def fuel_yen_per_mwh(self, kerosene_yen_l: float) -> float:
        return kerosene_yen_l / (KEROSENE_KWH_PER_L * self.boiler_eff) * 1000

    def carnot_cop(self, hot_c: float, cold_c: float) -> float:
        lift = max(hot_c - cold_c, 1.0)
        return min(self.cop_cap, self.carnot_eff * (hot_c + 273.15) / lift)

    def cop(self, kind: str) -> float | None:
        """Heat-pump COP serving this kind of user; None when it takes the waste heat directly."""
        if self.cop_override is not None:
            return self.cop_override
        if self.mode == "central":
            return self.carnot_cop(self.central_c, self.waste_c - self.approach_k)
        need = self.supply_c[kind]
        if need <= self.network_c - self.direct_margin_k:
            return None
        return self.carnot_cop(need, self.network_c - self.approach_k)

    def per_kind(self, kind: str) -> dict:
        """Electricity, network share and waste heat drawn, each per MWh delivered to this kind of user."""
        cop, loss = self.cop(kind), self.loss
        if self.mode == "central":
            elec = (1 + loss) / cop
            return {"cop": cop, "elec": elec, "share": 1.0, "r": (1 + loss) * (1 - 1 / cop), "hp_user": False}
        if cop is None:
            return {"cop": None, "elec": 0.0, "share": 1.0, "r": 1 + loss, "hp_user": False}
        return {"cop": cop, "elec": 1 / cop, "share": 1 - 1 / cop, "r": (1 - 1 / cop) * (1 + loss), "hp_user": True}


# ------------------------------------------------------------------------------------ data centers
@dataclass
class Source:
    key: str
    name: str
    name_en: str
    lon: float
    lat: float
    it_mw: dict                  # IT load in MW per level: {"low": ..., "high": ...}
    status: str                  # "operating" or "planned"
    where: tuple[str, str]       # how the point was set (ja, en)
    basis: str                   # sources of the capacity, or "assumption: ..."
    node: int = -1


GSI_POINT = (141.2948, 43.1797)  # GSI geocoder, 石狩市新港中央1丁目 (district point, not a building)


ISHIKARI_PLAN = ("Ishikari City and Tokyu Land, decarbonization-leading-area plan, revised 2025-07-04: "
                 "https://www.city.ishikari.hokkaido.jp/_res/projects/default_project/_page_/001/002/422/senko20250704.pdf")


def ishikari_sources(sakura: Site) -> list[Source]:
    """The data centers in Ishikari Bay New Port (all in 新港中央). Only Sakura is mapped in OSM;
    the others sit at labelled approximate points (two Overpass queries for buildings timed out)."""
    zed = _offset(*GSI_POINT, 350, 250)
    ntt = _offset(*GSI_POINT, -650, -250)
    return [
        Source("isrd1", "石狩再エネデータセンター第1号", "Ishikari Renewable Energy Data Center No. 1",
               *GSI_POINT, {"low": 6.0, "high": 10.0}, "operating",
               ("おおよその位置：新港中央1丁目722番1（地番）の地区代表点（国土地理院）",
                "Approximate: GSI district point for lot 新港中央1丁目722番1"),
               f"source: 15,000 kVA, ≥10 MW supplied from Aug 2026 ({URL['isrd']} ; {URL['isrd_mw']}); "
               "high = 10 MW matches the city plan's 87.6 GWh/yr (" + ISHIKARI_PLAN + "); "
               "low = 6 MW (part-filled halls) is an assumption"),
        Source("sakura", sakura.name, sakura.name_en, sakura.lon, sakura.lat, {"low": 5.0, "high": 10.0},
               "operating", ("OpenStreetMapの建物", "OpenStreetMap building"),
               f"assumption: MW not published; up to about 3,000 racks in 3 buildings ({URL['sakura_racks']})"),
        Source("zed", "京セラコミュニケーションシステム ZED石狩", "KCCS ZED Ishikari", *zed,
               {"low": 0.9, "high": 3.0}, "operating",
               ("仮の位置：新港中央1丁目内（建物は地図に未登録）", "Placeholder inside 新港中央1丁目 (building not mapped)"),
               f"source: 2-3 MW, 400 racks, operating since Oct 2024 ({URL['zed']}); "
               f"already uses its waste heat for floor and road heating ({URL['zed_heat']}); "
               "low = 0.9 MW from the city plan's 8.1 GWh/yr for the KCCS data center (" + ISHIKARI_PLAN + ")"),
        Source("nttme", "NTT-MEのコンテナ型データセンター（計画）", "NTT-ME container data centers (planned)", *ntt,
               {"low": 0.0, "high": 1.5}, "planned",
               ("仮の位置：港湾地区内（場所は未公表）", "Placeholder in the port area (site not published)"),
               f"source: up to 14 x 2 MW units, IT about 1.5 MW each, first unit April 2027 at the earliest "
               f"({URL['nttme']}); low = not yet built, high = one unit"),
    ]


# --------------------------------------------------------------------------------------- scenarios
@dataclass(frozen=True)
class Scenario:
    key: str
    ja: str
    en: str
    prob: float
    kerosene_yen_l: float
    it_level: str | None = "high"                 # "low" or "high" IT load at every data center
    it_mw: tuple | None = None                    # explicit ((source key, MW), ...) instead
    weather: WeatherYear | None = None            # a weather.WeatherYear (None: climate normals)

    def it_load(self, src: Source) -> float:
        return dict(self.it_mw)[src.key] if self.it_mw is not None else src.it_mw[self.it_level]


KEROSENE_LOW = 115.0     # assumption: conservative bulk price for large users (v1 value)
KEROSENE_SURVEY = 156.8  # source: Hokkaido, at the station, ANRE survey of 2026-11-16 (URL["kerosene"])


def default_scenarios() -> list[Scenario]:
    out = []
    for lv, lja, len_ in [("low", "IT負荷 低", "IT load low"), ("high", "IT負荷 高", "IT load high")]:
        for price, pja, pen in [(KEROSENE_LOW, "灯油115円/L", "kerosene 115 yen/L"),
                                (KEROSENE_SURVEY, "灯油156.8円/L", "kerosene 156.8 yen/L")]:
            out.append(Scenario(f"{lv}-{price:g}", f"{lja}・{pja}", f"{len_}, {pen}", 0.25, price, lv))
    return out


def mean_scenario(scens: list[Scenario], sources: list[Source]) -> Scenario:
    p = np.array([s.prob for s in scens])
    p = p / p.sum()
    it = tuple((src.key, float(sum(pi * s.it_load(src) for pi, s in zip(p, scens)))) for src in sources)
    price = float(sum(pi * s.kerosene_yen_l for pi, s in zip(p, scens)))
    return Scenario("mean", "平均のシナリオ", "Mean scenario", 1.0, price, None, it)


# ---------------------------------------------------------------------------------------- instance
@dataclass
class Instance:
    sources: list[Source]
    users: list[Site]
    dist: np.ndarray             # metres between nodes: sources first, then users
    road: bool = True            # False for synthetic instances with straight-line distances
    parent: list | None = None   # node index in the instance this one was cut from (subset)

    @property
    def D(self) -> int:
        return len(self.sources)

    @property
    def U(self) -> int:
        return len(self.users)

    @property
    def n(self) -> int:
        return self.D + self.U

    def demand(self) -> np.ndarray:
        return np.array([u.monthly() for u in self.users]) if self.users else np.zeros((0, T))

    def subset(self, src_idx: list[int], user_idx: list[int]) -> Instance:
        idx = list(src_idx) + [self.D + u for u in user_idx]
        return Instance([self.sources[i] for i in src_idx], [self.users[u] for u in user_idx],
                        self.dist[np.ix_(idx, idx)], self.road, idx)

    def lift(self, edges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Edges of a sub-instance in the node numbering of the instance it was cut from."""
        if self.parent is None:
            return list(edges)
        return [tuple(sorted((int(self.parent[a]), int(self.parent[b])))) for a, b in edges]


def build_instance(sources: list[Source], users: list[Site], area: str = AREA) -> Instance:
    from dcopt.common.geo import road_distance_matrix, snap
    for s in sources:
        s.node = snap(s.lon, s.lat, area)
    for u in users:
        if u.node < 0:
            u.node = snap(u.lon, u.lat, area)
    dist = road_distance_matrix([s.node for s in sources] + [u.node for u in users], area)
    return Instance(sources, users, dist, True)


def ishikari_instance(kinds: set[str] | None = None) -> Instance:
    from dcopt.heat.v1 import ishikari_sites
    sakura, sites = ishikari_sites()
    users = [s for s in sites if kinds is None or s.kind in kinds]
    return build_instance(ishikari_sources(sakura), users)


def candidate_edges(inst: Instance, P: Params) -> list[tuple[int, int]]:
    """k nearest neighbours of every node, each user's nearest data centers, and data center pairs."""
    dist, D, n = inst.dist, inst.D, inst.n
    cand: set[tuple[int, int]] = set()
    for i in range(n):
        order = [j for j in np.argsort(dist[i], kind="stable") if j != i and dist[i, j] <= P.max_link_m]
        for j in order[:P.k]:
            cand.add((min(i, j), max(i, j)))
    for u in range(D, n):
        order = [d for d in np.argsort(dist[u, :D], kind="stable") if dist[u, d] <= P.max_link_m]
        for d in order[:P.dc_links]:
            cand.add((int(d), u))
    for a in range(D):
        for b in range(a + 1, D):
            if dist[a, b] <= P.max_link_m:
                cand.add((a, b))
    return sorted((int(a), int(b)) for a, b in cand if np.isfinite(dist[a, b]))


# --------------------------------------------------------------------------------- per-user numbers
def duration_energy(mean_mw: float, hours: float, f: float, c_mw: float) -> float:
    """MWh a connection of c_mw delivers in a month whose hourly load is spread evenly between
    mean x (1 - b) and mean x (1 + b), b = min(f - 1, 1). Equals the month's demand when c covers the top."""
    if mean_mw <= 0:
        return 0.0
    b = min(max(f - 1.0, 0.0), 1.0)
    lo, hi = mean_mw * (1 - b), mean_mw * (1 + b)
    if c_mw >= hi:
        return mean_mw * hours
    if c_mw <= lo:
        return c_mw * hours
    return ((c_mw ** 2 - lo ** 2) / 2 + c_mw * (hi - c_mw)) / (hi - lo) * hours


@dataclass
class UserData:
    demand: np.ndarray      # U x T x W, MWh (weather-year scenarios vary; normals otherwise)
    peak: np.ndarray        # U, MW delivered at the design hour of the worst scenario
    peak_w: np.ndarray      # U x W, each scenario's own design peak
    cap: np.ndarray         # U x T x W, MWh deliverable with pipes sized for alpha x peak
    r: np.ndarray           # U, waste heat drawn per MWh delivered
    elec: np.ndarray        # U, MWh of electricity per MWh delivered
    q: np.ndarray           # U, MW on each pipe of the user's path at peak
    v: np.ndarray           # U x W, yen per MWh delivered
    co2: np.ndarray         # U, t CO2 avoided per MWh delivered
    hp: np.ndarray          # U, heat-pump investment in yen (0 when off or not needed)
    cop: list               # U, COP or None (direct use)


def user_data(inst: Instance, P: Params, scens: list[Scenario],
              design_peak: np.ndarray | None = None) -> UserData:
    """Per-user numbers. Demand varies by scenario when the scenario carries a WeatherYear: the
    year's own daily temperatures and snowfall reshape the months and scale the annual demand
    (dcopt.heat.weather). Pipes and heat pumps are sized once, for the worst scenario's worst
    month (the published convention; see the sizing note below).

    `design_peak` evaluates a FIXED build: the pipes exist, so their design peak (and the q and
    deliverable energy derived from it) stays the plan's own; only the demand follows the new
    scenarios. Without it the peak would be re-derived from the evaluation scenarios — letting a
    plan evaluated on colder years quietly grow pipes it never built."""
    U, Wn = inst.U, len(scens)
    dem = np.empty((U, T, Wn))
    normals = inst.demand()                                   # U x T, from the climate normals
    for w, sc in enumerate(scens):
        dem[:, :, w] = normals if sc.weather is None else \
            [sc.weather.monthly_demand(u.kind, u.annual_mwh) for u in inst.users]
    fs = np.array([P.peak_factor[site.kind] for site in inst.users])
    means = dem / np.array(HOURS)[None, :, None]              # U x T x W
    peak_w = means.max(axis=1) * fs[:, None]                  # U x W: each year's design peak
    if P.sizing == "robust":
        # cover the worst DAY of every weather-bearing scenario (daily_peak_mw), not just its worst
        # month; kinds without a daily peak (snow-melting, flat) keep their monthly peak.
        # 「頑健」サイズ：気象つきシナリオの最悪日まで管・HPを sizing する（雪融・フラットは月単位のまま）
        for w, sc in enumerate(scens):
            if sc.weather is None:
                continue
            for u, site in enumerate(inst.users):
                dp = sc.weather.daily_peak_mw(site.kind, float(dem[u, :, w].sum()))
                if dp is not None:
                    peak_w[u, w] = max(peak_w[u, w], dp)
    # Sized for the worst MONTH of the worst scenario by default (the published convention);
    # `sizing="robust"` extends this to the worst DAY of weather-bearing scenarios. Either way,
    # `evaluate` now judges every plan by the same physical rule (the smaller of the built pipes'
    # capacity and the evaluation set's own convention), so plans built on different sets compare
    # cleanly and the daily-peak data is usable (dcopt.heat.weather.daily_peak_mw).
    peak = peak_w.max(axis=1) if design_peak is None else np.asarray(design_peak, float)
    c = P.alpha * peak
    cap = np.empty((U, T, Wn))
    for w in range(Wn):
        for u in range(U):
            cap[u, :, w] = [duration_energy(means[u, t, w], HOURS[t], fs[u], c[u]) for t in range(T)]
    r, elec, q, co2, hp = (np.zeros(U) for _ in range(5))
    fuel_t = KEROSENE_KG_CO2_PER_L / (KEROSENE_KWH_PER_L * P.boiler_eff)      # t CO2 per MWh of heat
    for u, site in enumerate(inst.users):
        k = P.per_kind(site.kind)
        r[u], elec[u] = k["r"], k["elec"]
        q[u] = c[u] * k["share"] * (1 + P.loss)
        grid = P.grid_t_per_mwh if (P.mode == "ambient" or not P.renewable_central) else 0.0
        co2[u] = fuel_t - elec[u] * grid
        if P.mode == "central":
            hp[u] = P.hp_yen_per_mw_central * c[u]
        elif k["hp_user"]:
            hp[u] = P.hp_yen_per_mw_user * c[u]
    v = np.array([[P.fuel_yen_per_mwh(s.kerosene_yen_l) - P.power_yen_kwh * 1000 * elec[u] + P.carbon_yen_t * co2[u]
                   for s in scens] for u in range(U)]).reshape(U, len(scens))
    return UserData(dem, peak, peak_w, cap, r, elec, q, v, co2, hp,
                    [P.per_kind(u.kind)["cop"] for u in inst.users])


def waste_heat(inst: Instance, P: Params, scens: list[Scenario]) -> np.ndarray:
    """D x T x W, MWh of recoverable waste heat."""
    return np.array([[[s.it_load(src) * HOURS[t] * P.recovery for s in scens] for t in range(T)]
                     for src in inst.sources]).reshape(inst.D, T, len(scens))


# -------------------------------------------------------------------------------------------- plan
@dataclass
class Plan:
    inst: Instance
    P: Params
    scens: list[Scenario]
    E: list[tuple[int, int]]     # candidate links the model saw
    y: np.ndarray                # len(E) x K, 0/1
    x: np.ndarray                # U, 0/1
    assign: np.ndarray           # U, data center index or -1
    s: np.ndarray                # U x D x T x W, MWh
    g: np.ndarray                # U x 2E, commodity shares
    ud: UserData
    W: np.ndarray                # D x T x W
    status: str
    seconds: float
    gap: float | None
    objective: str = "expected"      # see OBJECTIVES
    bound: float | None = None       # epigraph value: worst net (max-min) or largest regret
    own_opt: list | None = None      # each scenario's own optimum, for min-max regret
    dual_bound: float | None = None  # solver bound: net benefit (expected, worst) or regret
    kernel: dict | None = None       # kernel-search details when solved by solve_kernel
    conn: np.ndarray | None = None   # U, each user's connection size index (-1 off; user_connection='decided')

    @property
    def p(self) -> np.ndarray:
        return np.array([s.prob for s in self.scens])

    @property
    def built(self) -> list[tuple[int, int, float, int]]:
        """(a, b, metres, size index) of every built link."""
        return [(a, b, float(self.inst.dist[a, b]), int(np.argmax(self.y[e])))
                for e, (a, b) in enumerate(self.E) if self.y[e].max() > 0.5]

    @property
    def capex_pipes(self) -> float:
        return sum(m * self.P.sizes[k].yen_m for _, _, m, k in self.built)

    @property
    def capex_hp(self) -> float:
        if self.conn is None:
            return float(self.ud.hp @ self.x)
        # user_connection='decided': the heat pump is sized to the chosen connection capped by the
        # user's design load (the same min the model's objective charges).
        cap_k = np.array([s.capacity_mw(self.P.dT) for s in self.P.sizes])
        share = np.array([self.P.per_kind(u.kind)["share"] * (1 + self.P.loss) for u in self.inst.users])
        conn = np.maximum(self.conn, 0)
        c = np.minimum(self.P.alpha * self.ud.peak, cap_k[conn] / share) * (self.conn >= 0)
        rate = np.divide(self.ud.hp, self.P.alpha * self.ud.peak,
                         out=np.zeros(self.inst.U), where=(self.P.alpha * self.ud.peak) > 1e-9)
        return float(rate @ c)

    @property
    def capex(self) -> float:
        return self.capex_pipes + self.capex_hp

    @property
    def own_capex(self) -> float:
        """The investment left to the project after the subsidy."""
        return self.P.own * self.capex

    @property
    def subsidy_yen(self) -> float:
        return self.P.subsidy * self.capex

    @property
    def annual_cost(self) -> float:
        return self.P.own * (self.P.crf * self.capex_pipes + self.P.crf_hp * self.capex_hp)

    @property
    def delivered(self) -> np.ndarray:        # W
        return self.s.sum(axis=(0, 1, 2))

    @property
    def value(self) -> np.ndarray:            # W
        return np.einsum("udtw,uw->w", self.s, self.ud.v)

    @property
    def net(self) -> np.ndarray:              # W
        return self.value - self.annual_cost

    @property
    def expected_net(self) -> float:
        return float(self.p @ self.net)

    @property
    def expected_value(self) -> float:
        return float(self.p @ self.value)

    @property
    def payback(self) -> float:
        return self.own_capex / self.expected_value if self.expected_value > 0 else math.inf

    @property
    def co2(self) -> np.ndarray:              # W, t per year
        return np.einsum("udtw,u->w", self.s, self.ud.co2)

    @property
    def carbon_value(self) -> np.ndarray:     # W, yen per year: the part of `value` that is the carbon price
        return self.P.carbon_yen_t * self.co2

    @property
    def electricity(self) -> np.ndarray:      # W, MWh per year drawn by the heat pumps
        return np.einsum("udtw,u->w", self.s, self.ud.elec)

    def co2_at(self, grid_t_per_mwh: float) -> np.ndarray:
        """W, t per year avoided if every heat pump drew electricity of this emission factor."""
        fuel_t = KEROSENE_KG_CO2_PER_L / (KEROSENE_KWH_PER_L * self.P.boiler_eff)
        return fuel_t * self.delivered - grid_t_per_mwh * self.electricity

    def co2_scenarios(self) -> dict[str, float]:
        """Expected t per year avoided under each electricity scenario of GRID_SCENARIOS."""
        return {key: float(self.p @ self.co2_at(f)) for key, (_, _, f) in GRID_SCENARIOS.items()}

    @property
    def abatement_yen_t(self) -> float:
        """Expected cost of a tonne of CO2 avoided with no carbon price and no subsidy: the full annual
        cost minus the fuel saving, per tonne. Negative when the plan pays for itself."""
        co2 = float(self.p @ self.co2)
        if co2 <= 0:
            return math.inf
        full_cost = self.P.crf * self.capex_pipes + self.P.crf_hp * self.capex_hp
        return (full_cost - float(self.p @ (self.value - self.carbon_value))) / co2

    @property
    def connected(self) -> list[int]:
        return [u for u in range(self.inst.U) if self.x[u] > 0.5]

    @property
    def pipe_m(self) -> float:
        return sum(m for _, _, m, _ in self.built)

    def sites_per_dc(self) -> dict[str, int]:
        return {src.key: int((self.assign == d).sum()) for d, src in enumerate(self.inst.sources)}

    def km_by_dn(self) -> dict[int, float]:
        out: dict[int, float] = {}
        for _, _, m, k in self.built:
            out[self.P.sizes[k].dn] = out.get(self.P.sizes[k].dn, 0.0) + m / 1000
        return dict(sorted(out.items()))

    def waste_used(self) -> np.ndarray:       # D x T x W
        return np.einsum("udtw,u->dtw", self.s, self.ud.r)

    def user_value(self) -> np.ndarray:       # U, expected yen per year
        return np.einsum("udtw,uw,w->u", self.s, self.ud.v, self.p)

    def build(self) -> dict:
        fix = {"y": self.y.copy(), "x": self.x.copy(), "assign": self.assign.copy()}
        if self.conn is not None:
            fix["yu"] = np.asarray(self.conn, int)
        return fix


# ------------------------------------------------------------------------------------------- solve
OBJECTIVES = {
    "expected": ("期待値を最大化（確率計画）", "Maximise the expected net benefit (stochastic programme)"),
    "worst": ("最悪シナリオの純便益を最大化（max-min）", "Maximise the worst scenario's net benefit (max-min)"),
    "regret": ("最大の後悔を最小化（min-max regret）", "Minimise the largest regret (min-max regret)"),
}


@dataclass
class Model:
    """The MILP before an objective is chosen. First stage: pipes y, connections x, data center z
    (and the commodity shares g that route them). Second stage: one block of monthly deliveries s per
    scenario, an LP once the first stage is fixed. `cost[w] @ v` is minus the net benefit of
    scenario w, so every objective is built from these rows."""
    cost: np.ndarray          # W x nv
    A: sp.csr_matrix
    lo: np.ndarray
    hi: np.ndarray
    lb: np.ndarray
    ub: np.ndarray
    integrality: np.ndarray
    off: dict                 # first index of y, x, z, g, s and the number of variables n
    E: list
    ud: UserData
    Wc: np.ndarray
    tie: np.ndarray           # nv: tie-break cost on z (tie_cost), added to every objective but not to `cost`


def build_model(inst: Instance, P: Params, scens: list[Scenario], *, edges: list[tuple[int, int]] | None = None,
                force_edges: bool = False, fix: dict | None = None, off: tuple | list = (),
                design_peak: np.ndarray | None = None) -> Model:
    D, U, n, Wn = inst.D, inst.U, inst.n, len(scens)
    E = list(edges) if edges is not None else candidate_edges(inst, P)
    E = [(a, b) for a, b in E if np.isfinite(inst.dist[a, b])]
    nE, K, A = len(E), len(P.sizes), 2 * len(E)
    ud = user_data(inst, P, scens, design_peak)
    Wc = waste_heat(inst, P, scens)
    a_from = np.array([a for a, b in E] + [b for a, b in E], dtype=int)
    a_to = np.array([b for a, b in E] + [a for a, b in E], dtype=int)
    length = np.array([inst.dist[a, b] for a, b in E], dtype=float)
    cap_k = np.array([s.capacity_mw(P.dT) for s in P.sizes])
    cost_k = np.array([s.yen_m for s in P.sizes])

    ext = P.formulation == "extended"
    decided = P.user_connection == "decided"
    if decided and not ext:
        raise ValueError("user_connection='decided' needs the extended formulation")
    G = K if ext else 1                   # commodity shares per arc and size (extended) or per arc
    oy, ox = 0, nE * K
    oz = ox + U
    og = oz + U * D
    osv = og + U * A * G
    oyu = osv + U * D * T * Wn            # connection-size binaries (user_connection='decided')
    nv = oyu + (U * K if decided else 0)

    cost = np.zeros((Wn, nv))
    cost[:, oy:ox] = P.own * P.crf * np.outer(length, cost_k).ravel()
    share_l = np.array([P.per_kind(u.kind)["share"] * (1 + P.loss) for u in inst.users])
    if decided:
        # The user never draws more than its design load: with connection k the network sees
        # min(q_u, cap_k) at peak and the user can take min(alpha x peak, cap_k/share) of heat.
        # With the published floor the min is q_u exactly, so the sized and decided models agree.
        draw_uk = np.minimum(ud.q[:, None], cap_k[None, :])              # U x K, MW on the pipes
        c_uk = draw_uk / share_l[:, None]                                # U x K, MW at the user
        hp_rate = np.divide(ud.hp, P.alpha * ud.peak, out=np.zeros(U), where=(P.alpha * ud.peak) > 1e-9)
        cost[:, oyu:oyu + U * K] = ((P.own * P.crf_hp) * (hp_rate[:, None] * c_uk)).ravel()[None, :]
        cost[:, ox:oz] = 0.0
    else:
        draw_uk = None
        cost[:, ox:oz] = P.own * P.crf_hp * ud.hp
    for w in range(Wn):
        blockv = np.zeros((U, D, T, Wn))
        blockv[..., w] = -ud.v[:, w][:, None, None]
        cost[w, osv:oyu] = blockv.ravel()

    R, C, V, lo, hi = [], [], [], [], []
    r0 = 0

    def block(rows, cols, vals, nrows, lb_, ub_):
        nonlocal r0
        R.append(np.asarray(rows, dtype=np.int64) + r0)
        C.append(np.asarray(cols, dtype=np.int64))
        V.append(np.broadcast_to(np.asarray(vals, dtype=float), np.shape(rows)).ravel())
        lo.append(np.broadcast_to(np.asarray(lb_, dtype=float), (nrows,)).ravel())
        hi.append(np.broadcast_to(np.asarray(ub_, dtype=float), (nrows,)).ravel())
        r0 += nrows

    fits = (cap_k[None, :] >= ud.q[:, None] - 1e-9).astype(float)          # U x K: size k can carry u alone
    ud_u, ud_d = np.repeat(np.arange(U), D), np.tile(np.arange(D), U)
    uu = np.repeat(np.arange(U), A * G)
    aa = np.tile(np.repeat(np.arange(A), G), U)
    kg = np.tile(np.arange(G), U * A)
    gcol = og + (uu * A + aa) * G + kg                                     # g index: og + (u A + a) G + k
    # (flow) out - in - z_ud [i = d] + x_u [i = user node] = 0, one row per user and node
    rows = np.concatenate([uu * n + a_from[aa], uu * n + a_to[aa], ud_u * n + ud_d, np.arange(U) * n + D + np.arange(U)])
    cols = np.concatenate([gcol, gcol, oz + ud_u * D + ud_d, ox + np.arange(U)])
    vals = np.concatenate([np.ones(gcol.size), -np.ones(gcol.size), -np.ones(U * D), np.ones(U)])
    block(rows, cols, vals, U * n, 0.0, 0.0)
    # (one source) sum_d z_ud - x_u = 0
    block(np.concatenate([ud_u, np.arange(U)]), np.concatenate([oz + ud_u * D + ud_d, ox + np.arange(U)]),
          np.concatenate([np.ones(U * D), -np.ones(U)]), U, 0.0, 0.0)
    # (one size) sum_k y_ek <= 1, or = 1 when every given edge must be built
    block(np.repeat(np.arange(nE), K), oy + np.arange(nE * K), 1.0, nE, 1.0 if force_edges else 0.0, 1.0)
    if ext:
        if decided:
            # g rides at the user's CONNECTION size k; the connection binary gates it and the
            # heat drawn on a pipe equals that connection's capacity cap_k (a constant), so the
            # trunk capacity rows stay linear. The sizing convention becomes a floor on yu.
            ue = np.repeat(np.arange(U), nE * K)
            ee = np.tile(np.repeat(np.arange(nE), K), U)
            ke = np.tile(np.arange(K), U * nE)
            rr = np.arange(ue.size)
            # (connection link) g_uk(a->b) + g_uk(b->a) - yu_uk <= 0
            block(np.concatenate([rr, rr, rr]),
                  np.concatenate([og + (ue * A + ee) * K + ke, og + (ue * A + ee + nE) * K + ke,
                                  oyu + ue * K + ke]),
                  np.concatenate([np.ones(ue.size), np.ones(ue.size), -np.ones(ue.size)]),
                  ue.size, -np.inf, 0.0)
            # (capacity, one row per edge) sum_{u,k} cap_k g_u,e,k(both) - sum_j cap_j y_ej <= 0:
            # g's size index is the user's connection, so the trunk sees each user's draw at that
            # connection's capacity, and the built size (sum_j y <= 1) sets the edge's capacity.
            ue = np.repeat(np.arange(U), A * K)
            aa = np.tile(np.repeat(np.arange(A), K), U)
            kk = np.tile(np.arange(K), U * A)
            erow = np.where(aa < nE, aa, aa - nE)
            block(np.concatenate([erow, np.repeat(np.arange(nE), K)]),
                  np.concatenate([og + (ue * A + aa) * K + kk, oy + np.arange(nE * K)]),
                  np.concatenate([draw_uk[ue, kk], -np.tile(cap_k, nE)]), nE, -np.inf, 0.0)
            # (one connection per connected user) sum_k yu_uk - x_u = 0
            uu3, kk3 = np.repeat(np.arange(U), K), np.tile(np.arange(K), U)
            block(np.concatenate([uu3, np.arange(U)]),
                  np.concatenate([oyu + uu3 * K + kk3, ox + np.arange(U)]),
                  np.concatenate([np.ones(U * K), -np.ones(U)]), U, 0.0, 0.0)
            # (sizing floor) yu_uk = 0 below the smallest size that carries the sizing peak.
            # sizing='free' drops the floor: the optimizer trades pipe cost against cold-year
            # shedding, and 'cover the worst year in the set' becomes an inspectable choice.
            # (delivered energy) s_udtw <= sum_k capE_utwk yu_uk: the connection's duration curve
            idxs = np.arange(U * D * T * Wn)
            su2, st2, sw2 = idxs // (D * T * Wn), (idxs // Wn) % T, idxs % Wn
            means_ud = ud.demand / np.array(HOURS)[None, :, None]        # U x T x W
            capE = np.empty((U, T, Wn, K))
            for w in range(Wn):
                for u in range(U):
                    fs_u = P.peak_factor[inst.users[u].kind]
                    for t in range(T):
                        capE[u, t, w] = [duration_energy(means_ud[u, t, w], HOURS[t], fs_u, c_uk[u, k])
                                         for k in range(K)]
            kcols = np.tile(np.arange(K), idxs.size)
            ridx = np.repeat(idxs, K)
            block(np.concatenate([idxs, ridx]),
                  np.concatenate([osv + idxs, oyu + np.repeat(su2, K) * K + kcols]),
                  np.concatenate([np.ones(idxs.size), -capE[su2, st2, sw2, :].ravel()]),
                  idxs.size, -np.inf, 0.0)
        else:
            # (built pipes, per size) g_uk(a->b) + g_uk(b->a) - y_ek <= 0, for the sizes that can carry u
            ue = np.repeat(np.arange(U), nE * K)
            ee = np.tile(np.repeat(np.arange(nE), K), U)
            ke = np.tile(np.arange(K), U * nE)
            keep = fits[ue, ke] > 0
            ue, ee, ke = ue[keep], ee[keep], ke[keep]
            rr = np.arange(ue.size)
            block(np.concatenate([rr, rr, rr]),
                  np.concatenate([og + (ue * A + ee) * K + ke, og + (ue * A + ee + nE) * K + ke, oy + ee * K + ke]),
                  np.concatenate([np.ones(ue.size), np.ones(ue.size), -np.ones(ue.size)]), ue.size, -np.inf, 0.0)
            # (capacity, per size) sum_u q_u (g_uk(a->b) + g_uk(b->a)) - cap_k y_ek <= 0
            u2, ek = np.repeat(np.arange(U), nE * K), np.tile(np.arange(nE * K), U)
            e2, k2 = ek // K, ek % K
            block(np.concatenate([ek, ek, np.arange(nE * K)]),
                  np.concatenate([og + (u2 * A + e2) * K + k2, og + (u2 * A + e2 + nE) * K + k2, oy + np.arange(nE * K)]),
                  np.concatenate([ud.q[u2], ud.q[u2], -np.tile(cap_k, nE)]), nE * K, -np.inf, 0.0)
    else:
        # (built pipes) g_u(a->b) + g_u(b->a) - sum_{k: cap_k >= q_u} y_ek <= 0: a user's heat only runs
        # on pipes big enough for it alone (valid, and tighter than sum_k y_ek when sizes differ)
        ue, ee = np.repeat(np.arange(U), nE), np.tile(np.arange(nE), U)
        lk = ue * nE + ee
        kk = np.tile(np.arange(K), U * nE)
        block(np.concatenate([lk, lk, np.repeat(lk, K)]),
              np.concatenate([og + ue * A + ee, og + ue * A + ee + nE, oy + np.repeat(ee, K) * K + kk]),
              np.concatenate([np.ones(2 * U * nE), -fits[np.repeat(ue, K), kk]]), U * nE, -np.inf, 0.0)
        # (capacity) sum_u q_u (g_u(a->b) + g_u(b->a)) - sum_k cap_k y_ek <= 0
        block(np.concatenate([ee, ee, np.repeat(np.arange(nE), K)]),
              np.concatenate([og + ue * A + ee, og + ue * A + ee + nE, oy + np.arange(nE * K)]),
              np.concatenate([ud.q[ue], ud.q[ue], -np.tile(cap_k, nE)]), nE, -np.inf, 0.0)
    # (demand and coverage) s_udtw - cap_utw z_ud <= 0
    idx = np.arange(U * D * T * Wn)
    su, sd, st = idx // (D * T * Wn), (idx // (T * Wn)) % D, (idx // Wn) % T
    sw = idx % Wn
    block(np.concatenate([idx, idx]), np.concatenate([osv + idx, oz + su * D + sd]),
          np.concatenate([np.ones(idx.size), -ud.cap[su, st, sw]]), idx.size, -np.inf, 0.0)
    # (waste heat) sum_u r_u s_udtw <= W_dtw
    block((sd * T + st) * Wn + sw, osv + idx, ud.r[su], D * T * Wn, -np.inf, Wc.ravel())

    Amat = sp.csr_matrix((np.concatenate(V), (np.concatenate(R), np.concatenate(C))), shape=(r0, nv))
    lb, ub = np.zeros(nv), np.full(nv, np.inf)
    ub[:osv] = 1.0
    if decided:
        ub[oyu:] = 1.0                                   # connection binaries
        if P.sizing != "free":
            below = np.argwhere(fits == 0)               # (u, k): smaller than the sizing peak needs
            ub[oyu + below[:, 0] * K + below[:, 1]] = 0.0
    if ext and not decided:
        nofit = np.argwhere(fits == 0)                                  # (u, k) pairs
        for u, k in nofit:
            ub[og + (u * A + np.arange(A)) * K + k] = 0.0
    for u in off:
        ub[ox + u] = 0.0
        ub[oz + u * D: oz + (u + 1) * D] = 0.0
    if fix is not None:
        lb[oy:ox] = ub[oy:ox] = np.asarray(fix["y"], float).ravel()
        xs = np.asarray(fix["x"], float).copy()
        zs = np.zeros((U, D))
        for u, d in enumerate(fix["assign"]):
            if d >= 0:
                zs[u, d] = 1.0
        for u in off:
            xs[u], zs[u] = 0.0, 0.0
        lb[ox:oz] = ub[ox:oz] = xs
        lb[oz:og] = ub[oz:og] = zs.ravel()
        if decided and fix.get("yu") is not None:
            yu = np.zeros((U, K))
            for u, k in enumerate(np.asarray(fix["yu"], int)):
                if k >= 0:
                    yu[u, k] = 1.0
            lb[oyu:] = ub[oyu:] = yu.ravel()
    integrality = np.zeros(nv)
    integrality[:og] = 1
    if decided:
        integrality[oyu:] = 1
    offs = {"y": oy, "x": ox, "z": oz, "g": og, "s": osv, "n": nv}
    if decided:
        offs["yu"] = oyu
    return Model(cost, Amat, np.concatenate(lo), np.concatenate(hi), lb, ub, integrality, offs, E, ud, Wc,
                 tie_cost(inst, P, nv, oz))


def tie_cost(inst: Instance, P: Params, nv: int, oz: int) -> np.ndarray:
    """Tie-break cost on the assignment z_ud: tie_yen_m x (distance from data center d to user u, plus
    less than one metre for d's place in the order of the data center keys). When two data centers can
    serve a user at the same cost, the nearer one wins (the one with the smaller key if they are equally
    far), whatever the solver or the column order. It is kept out of `cost`, so the reported net benefit
    and the rows of the robust objectives do not include it; it moves the objective by at most
    tie_yen_m x the distances of the connected users (TIE_BASIS)."""
    D, U = inst.D, inst.U
    tie = np.zeros(nv)
    if P.tie_yen_m == 0 or not U or not D:
        return tie
    dist = np.array(inst.dist[:D, D:D + U], dtype=float).T                 # U x D
    finite = np.isfinite(dist)
    dist = np.where(finite, dist, dist[finite].max() if finite.any() else 0.0)
    order = np.argsort(np.argsort([s.key for s in inst.sources], kind="stable"), kind="stable")
    tie[oz:oz + U * D] = (P.tie_yen_m * (dist + order[None, :] / D)).ravel()
    return tie


def _with_objective(m: Model, scens: list[Scenario], objective: str, own_opt, eps: float):
    """Objective, matrix and bounds for one objective; robust ones add one epigraph variable t."""
    prob = np.array([s.prob for s in scens])
    Wn = len(scens)
    if objective == "expected":
        return prob @ m.cost + m.tie, m.A, m.lo, m.hi, m.lb, m.ub, m.integrality
    if objective == "worst":              # t + cost_w . v <= 0   (t <= net_w)
        col, rhi, tlb = np.ones((Wn, 1)), np.zeros(Wn), -np.inf
        c = np.r_[eps * (prob @ m.cost) + m.tie, -1.0]
    elif objective == "regret":           # cost_w . v - t <= -own_opt_w   (t >= own_opt_w - net_w)
        if own_opt is None or len(own_opt) != Wn:
            raise ValueError("objective='regret' needs own_opt, each scenario's own optimum")
        col, rhi, tlb = -np.ones((Wn, 1)), -np.asarray(own_opt, float), 0.0
        c = np.r_[eps * (prob @ m.cost) + m.tie, 1.0]
    else:
        raise ValueError(f"unknown objective {objective!r}; use one of {list(OBJECTIVES)}")
    A = sp.vstack([sp.hstack([m.A, sp.csr_matrix((m.A.shape[0], 1))]),
                   sp.hstack([sp.csr_matrix(m.cost), sp.csr_matrix(col)])]).tocsr()
    return (c, A, np.r_[m.lo, np.full(Wn, -np.inf)], np.r_[m.hi, rhi], np.r_[m.lb, tlb], np.r_[m.ub, np.inf],
            np.r_[m.integrality, 0.0])


def solver_name(P: Params) -> str:
    """HiGHS by default; DCOPT_SOLVER=gurobi (or Params.solver) uses Gurobi when gurobipy is installed."""
    import os
    name = (P.solver or os.environ.get("DCOPT_SOLVER", "highs")).lower()
    if name not in ("highs", "gurobi"):
        raise ValueError(f"solver must be highs or gurobi, got {name!r}")
    return name


def solver_threads() -> int:
    """Threads per solve from DCOPT_THREADS (0 or unset: the solver's default). Set it when several
    solves run side by side, so that their time limits mean the same thing on a busy machine."""
    import os
    return max(0, int(os.environ.get("DCOPT_THREADS", "0") or 0))


def _run(c, A, lo, hi, lb, ub, integ, P: Params, start: np.ndarray | None, relax: bool = False) -> dict:
    """Solve min c.v s.t. lo <= A v <= hi, lb <= v <= ub; returns v, status, gap and bound (minimisation)."""
    integ = np.zeros_like(integ) if relax else integ
    if solver_name(P) == "gurobi":
        try:
            import gurobipy as gp
        except ImportError as e:  # pragma: no cover - depends on the environment
            raise RuntimeError("gurobipy is not installed: run `uv sync --extra gurobi`") from e
        with gp.Env(params={"OutputFlag": 0}) as env, gp.Model("heatnet", env=env) as g:
            v = g.addMVar(len(c), lb=lb, ub=ub, vtype=np.where(integ > 0, "I", "C"))
            g.setObjective(c @ v)
            eq = lo == hi
            if eq.any():
                g.addMConstr(A[eq], v, "=", lo[eq])
            up, dn = ~eq & np.isfinite(hi), ~eq & np.isfinite(lo)
            if up.any():
                g.addMConstr(A[up], v, "<", hi[up])
            if dn.any():
                g.addMConstr(A[dn], v, ">", lo[dn])
            g.Params.TimeLimit, g.Params.MIPGap = P.time_limit, P.mip_rel_gap
            if solver_threads():
                g.Params.Threads = solver_threads()
            if start is not None and not relax:
                v.Start = start
            g.optimize()
            if g.SolCount == 0:
                raise RuntimeError(f"heat network model v2: Gurobi found no solution (status {g.Status})")
            mip = integ.any()
            return {"x": np.array(v.X), "status": f"Gurobi status {g.Status}", "obj": g.ObjVal,
                    "gap": g.MIPGap if mip else 0.0, "bound": g.ObjBound if mip else g.ObjVal}
    import highspy
    Ac = A.tocsc()
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = len(c), Ac.shape[0]
    lp.col_cost_ = np.asarray(c, float)
    lp.col_lower_, lp.col_upper_ = np.asarray(lb, float), np.asarray(ub, float)
    lp.row_lower_, lp.row_upper_ = np.asarray(lo, float), np.asarray(hi, float)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = Ac.indptr, Ac.indices, Ac.data
    if integ.any():
        kinds = [highspy.HighsVarType.kContinuous, highspy.HighsVarType.kInteger]
        lp.integrality_ = [kinds[int(i > 0)] for i in integ]
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(P.time_limit))
    h.setOptionValue("mip_rel_gap", float(P.mip_rel_gap))
    h.setOptionValue("mip_heuristic_effort", float(P.heuristic_effort))
    if solver_threads():
        h.setOptionValue("threads", solver_threads())
    h.passModel(lp)
    if start is not None and not relax:
        sol = highspy.HighsSolution()
        sol.col_value = list(np.asarray(start, float))
        sol.value_valid = True
        h.setSolution(sol)
    h.run()
    info = h.getInfo()
    if info.primal_solution_status == 0:
        raise RuntimeError(f"heat network model v2 has no solution: {h.modelStatusToString(h.getModelStatus())}")
    mip = integ.any()
    obj = info.objective_function_value
    return {"x": np.array(h.getSolution().col_value), "status": h.modelStatusToString(h.getModelStatus()),
            "obj": obj, "gap": info.mip_gap if mip else 0.0, "bound": info.mip_dual_bound if mip else obj}


def _start(m: Model, plan: Plan, objective: str, own_opt, P: Params) -> np.ndarray:
    """A full start vector for model m from a plan on a subset of m's links (same scenarios)."""
    o, U, D = m.off, plan.inst.U, plan.inst.D
    K, nE = len(P.sizes), len(m.E)
    v = np.zeros(o["n"])
    pos = {e: i for i, e in enumerate(m.E)}
    G = K if P.formulation == "extended" else 1
    pn = len(plan.E)
    for j, e in enumerate(plan.E):
        i = pos[e]
        v[o["y"] + i * K: o["y"] + (i + 1) * K] = plan.y[j]
        k = int(np.argmax(plan.y[j])) if G > 1 else 0
        for u in range(U):
            v[o["g"] + (u * 2 * nE + i) * G + k] = plan.g[u, j]
            v[o["g"] + (u * 2 * nE + i + nE) * G + k] = plan.g[u, j + pn]
    v[o["x"]:o["z"]] = plan.x
    for u, d in enumerate(plan.assign):
        if d >= 0:
            v[o["z"] + u * D + d] = 1.0
    if plan.conn is not None and "yu" in o:
        for u, k in enumerate(np.asarray(plan.conn, int)):
            if k >= 0:
                v[o["yu"] + u * K + k] = 1.0
    v[o["s"]:o["n"]] = plan.s.ravel()
    if objective == "worst":
        v = np.r_[v, float(plan.net.min())]
    elif objective == "regret":
        v = np.r_[v, max(0.0, float(max(np.asarray(own_opt) - plan.net)))]
    return v


def solve(inst: Instance, P: Params, scens: list[Scenario], *, objective: str = "expected",
          own_opt: list[float] | None = None, eps: float = 1e-4, edges: list[tuple[int, int]] | None = None,
          force_edges: bool = False, fix: dict | None = None, off: tuple | list = (),
          start: Plan | None = None, design_peak: np.ndarray | None = None) -> Plan:
    """Build and solve (HiGHS by default, see `solver_name`). objective:
      "expected"  max sum_w p_w net_w                                      (two-stage stochastic)
      "worst"     max t  s.t. t <= net_w for every w                         (max-min, epigraph t)
      "regret"    min t  s.t. t >= own_opt_w - net_w for every w             (min-max regret)
    The robust objectives add eps x the expected net benefit to break ties among equally robust plans.
    Every objective adds the tiny cost of `tie_cost`, so that a user two data centers can serve at the
    same cost always goes to the same one.
    `fix` holds a plan's build (y on the same `edges`, x, assign) to evaluate it on other scenarios;
    `design_peak` keeps the evaluated plan's own pipe sizing (see user_data); `off` lists users that
    may not connect; `force_edges` builds every given edge (pair by pair); `start` is a plan on a
    subset of the links and the same scenarios, used as a MIP start."""
    t0 = time.perf_counter()
    m = build_model(inst, P, scens, edges=edges, force_edges=force_edges, fix=fix, off=off,
                    design_peak=design_peak)
    c, A, lo, hi, lb, ub, integ = _with_objective(m, scens, objective, own_opt, eps)
    v0 = _start(m, start, objective, own_opt, P) if start is not None else None
    res = _run(c, A, lo, hi, lb, ub, integ, P, v0)
    xv, nv = res["x"], m.off["n"]
    o = m.off
    U, D, nE, K, Wn = inst.U, inst.D, len(m.E), len(P.sizes), len(scens)
    y = (xv[o["y"]:o["x"]].reshape(nE, K) > 0.5).astype(float)
    xs = (xv[o["x"]:o["z"]] > 0.5).astype(float)
    z = xv[o["z"]:o["g"]].reshape(U, D)
    assign = np.where(xs > 0.5, z.argmax(axis=1), -1) if U else np.zeros(0, int)
    s_end = o.get("yu", nv)
    s = np.clip(xv[o["s"]:s_end].reshape(U, D, T, Wn), 0.0, None)
    g = xv[o["g"]:o["s"]].reshape(U, 2 * nE, -1).sum(axis=2) if nE else np.zeros((U, 0))
    plan = Plan(inst, P, list(scens), m.E, y, xs, assign, s, g, m.ud, m.Wc, res["status"],
                time.perf_counter() - t0, res["gap"], objective,
                float(xv[nv]) if objective != "expected" else None, list(own_opt) if own_opt is not None else None)
    plan.dual_bound = -res["bound"] if objective != "regret" else res["bound"]
    if "yu" in o:                                    # user_connection='decided'
        conn = xv[o["yu"]:].reshape(U, K)
        plan.conn = np.where(xs > 0.5, conn.argmax(axis=1), -1)
    return plan


def lp_relaxation(inst: Instance, P: Params, scens: list[Scenario], *, objective: str = "expected",
                  own_opt: list[float] | None = None, eps: float = 1e-4, edges: list[tuple[int, int]] | None = None,
                  off: tuple | list = ()) -> tuple[float, list[tuple[int, int]], np.ndarray]:
    """LP bound (net benefit for "expected"/"worst", regret for "regret"), the links and their
    total fractional build sum_k y_ek."""
    m = build_model(inst, P, scens, edges=edges, off=off)
    c, A, lo, hi, lb, ub, integ = _with_objective(m, scens, objective, own_opt, eps)
    res = _run(c, A, lo, hi, lb, ub, integ, P, None, relax=True)
    K = len(P.sizes)
    ysum = res["x"][:len(m.E) * K].reshape(len(m.E), K).sum(axis=1)
    bound = -res["obj"] if objective != "regret" else res["obj"]
    return bound, m.E, ysum


def solve_kernel(inst: Instance, P: Params, scens: list[Scenario], *, objective: str = "expected",
                 own_opt: list[float] | None = None, kernel_time: float | None = None,
                 full_time: float | None = 0.0, threshold: float = 1e-6, off: tuple | list = (),
                 extra_edges: list[tuple[int, int]] | None = None) -> Plan:
    """LP-guided kernel search. 1) LP relaxation on all candidate links (its value bounds the optimum).
    2) MILP on the links the LP uses (the kernel). 3) Optionally (full_time > 0) the full MILP
    warm-started from that plan, for a better plan and a tighter bound. Never worse than step 2.
    The gap reported in plan.kernel is against the best bound found (LP or full MILP)."""
    t0 = time.perf_counter()
    extra = {e for e in (extra_edges or []) if np.isfinite(inst.dist[e])}
    E = sorted(set(candidate_edges(inst, P)) | extra)            # seed links join the candidate set
    lp_bound, _, ysum = lp_relaxation(inst, P, scens, objective=objective, own_opt=own_opt, edges=E, off=off)
    kernel = [e for e, v in zip(E, ysum) if v > threshold or e in extra]
    Pk = replace(P, time_limit=kernel_time if kernel_time is not None else P.time_limit)
    best = solve(inst, Pk, scens, objective=objective, own_opt=own_opt, edges=kernel, off=off)
    first_value, first_seconds = _score(best, objective), best.seconds
    bound = lp_bound if objective != "regret" else -lp_bound      # in the units of _score (larger is better)
    full_gap = None
    if full_time is None or full_time > 0:
        Pf = replace(P, time_limit=full_time if full_time is not None else P.time_limit)
        full = solve(inst, Pf, scens, objective=objective, own_opt=own_opt, edges=E, off=off, start=best)
        fb = full.dual_bound if objective != "regret" else -full.dual_bound
        bound, full_gap = min(bound, fb), full.gap
        if _score(full, objective) >= first_value - 1e-6:
            best = full
    value = _score(best, objective)
    scale = max(abs(value), 1e-9) if objective == "regret" else max(abs(bound), 1e-9)
    best.kernel = {"links": len(kernel), "of": len(E), "kernel_value": first_value, "kernel_seconds": first_seconds,
                   "bound": bound, "gap": (bound - value) / scale, "full_gap": full_gap}
    best.seconds = time.perf_counter() - t0
    return best


def _score(plan: Plan, objective: str) -> float:
    """Larger is better: expected net, worst-case net, or minus the largest regret."""
    if objective == "expected":
        return plan.expected_net
    if objective == "worst":
        return float(plan.net.min())
    return -float(max(np.asarray(plan.own_opt) - plan.net))


def evaluate(plan: Plan, scens: list[Scenario] | None = None, off: tuple | list = ()) -> Plan:
    """The plan's pipes and connections kept fixed; deliveries re-optimised (on other scenarios, or
    with some users switched off). The built pipes set the physics: each user draws the smaller of
    what its connection was built to carry and what the evaluation set's own sizing would provide —
    a plan built on mild years throttles honestly in cold years while staying inside the
    evaluation set's feasible set, and every plan is judged by one rule however it was sized. On
    the set the plan was built for the two capacities coincide (the published numbers do not
    move). With user_connection='decided' the plan's own capacities come from its chosen
    connection sizes and `fix` pins them."""
    target = user_data(plan.inst, plan.P, scens if scens is not None else plan.scens)
    peak = plan.ud.peak
    if plan.conn is not None:
        K = len(plan.P.sizes)
        cap_k = np.array([s.capacity_mw(plan.P.dT) for s in plan.P.sizes])
        share = np.array([plan.P.per_kind(u.kind)["share"] * (1 + plan.P.loss) for u in plan.inst.users])
        own = np.where(plan.conn >= 0, cap_k[np.maximum(plan.conn, 0)] / share, np.nan)
        peak = np.where(np.isfinite(own), np.minimum(own, target.peak), target.peak)
    else:
        peak = np.minimum(plan.ud.peak, target.peak)
    return solve(plan.inst, plan.P, scens if scens is not None else plan.scens, edges=plan.E,
                 fix=plan.build(), off=off, design_peak=peak / plan.P.alpha)


# ------------------------------------------------------------------------------------- uncertainty
def plan_for(inst: Instance, P: Params, scens: list[Scenario], *, method: str = "kernel",
             objective: str = "expected", own_opt: list[float] | None = None, off: tuple | list = (),
             full_time: float | None = 0.0, extra_edges: list[tuple[int, int]] | None = None) -> Plan:
    """One entry point. method "kernel": LP-guided kernel search (fast on the real instance, see
    solve_kernel); "direct": the full MILP within P.time_limit."""
    if method == "kernel":
        return solve_kernel(inst, P, scens, objective=objective, own_opt=own_opt, off=off, full_time=full_time,
                            extra_edges=extra_edges)
    if method == "direct":
        return solve(inst, P, scens, objective=objective, own_opt=own_opt, off=off)
    raise ValueError(f"method must be kernel or direct, got {method!r}")


def own_optima(inst: Instance, P: Params, scens: list[Scenario], method: str = "kernel",
               extra_edges: list[tuple[int, int]] | None = None) -> list[Plan]:
    """Each scenario's own optimum (wait-and-see)."""
    return [plan_for(inst, P, [replace(sc, prob=1.0)], method=method, extra_edges=extra_edges) for sc in scens]


def scenario_nets(plan: Plan, own_opt: list[float] | None = None) -> dict:
    """Expected net, worst-case net and (given each scenario's optimum) the regrets of a plan."""
    net = plan.net
    out = {"expected": plan.expected_net, "worst": float(net.min()), "per": [float(v) for v in net]}
    if own_opt is not None:
        reg = [float(o) - float(v) for o, v in zip(own_opt, net)]
        out["regret"] = reg
        out["max_regret"] = float(max(reg))
    return out


def robust_report(inst: Instance, P: Params, scens: list[Scenario], method: str = "kernel",
                  own: list[Plan] | None = None, extra_edges: list[tuple[int, int]] | None = None) -> dict:
    """The stochastic, max-min and min-max-regret plans on the same scenarios. Every build found is
    re-evaluated with exact recourse (evaluate), each scenario's optimum is the best net known for
    it, and each criterion keeps the best build found for it by any of the solves ("found_by")."""
    own = own or own_optima(inst, P, scens, method, extra_edges)
    solved = {"expected": plan_for(inst, P, scens, method=method, extra_edges=extra_edges),
              "worst": plan_for(inst, P, scens, method=method, objective="worst", extra_edges=extra_edges)}
    opt = [max([o.expected_net] + [float(pl.net[w]) for pl in solved.values()]) for w, o in enumerate(own)]
    solved["regret"] = plan_for(inst, P, scens, method=method, objective="regret", own_opt=opt, extra_edges=extra_edges)
    builds = {k: evaluate(pl) for k, pl in solved.items()}
    for k, pl in builds.items():
        pl.seconds, pl.kernel, pl.objective = solved[k].seconds, solved[k].kernel, solved[k].objective
    opt = [max([v] + [float(pl.net[w]) for pl in builds.values()]) for w, v in enumerate(opt)]
    crit = {"expected": lambda pl: pl.expected_net, "worst": lambda pl: float(pl.net.min()),
            "regret": lambda pl: -max(np.asarray(opt) - pl.net)}
    plans, found_by = {}, {}
    for key, f in crit.items():
        src = max(builds, key=lambda k: f(builds[k]) + (1e-6 if k == key else 0.0))
        plans[key], found_by[key] = builds[src], src
    return {"own": own, "own_opt": opt, "plans": plans, "found_by": found_by, "solved": solved,
            "nets": {k: scenario_nets(pl, opt) for k, pl in plans.items()}}


def stochastic_report(inst: Instance, P: Params, scens: list[Scenario], rp: Plan | None = None,
                      own: list[Plan] | None = None, method: str = "kernel",
                      extra_edges: list[tuple[int, int]] | None = None) -> dict:
    """Recourse plan (RP) against the plan built for the mean scenario (EEV) and each scenario's own
    optimum (wait-and-see). VSS = RP - EEV; regret_w = optimum_w - RP's net in w; EVPI = WS - RP."""
    rp = rp or plan_for(inst, P, scens, method=method, extra_edges=extra_edges)
    mean = mean_scenario(scens, inst.sources)
    ev = plan_for(inst, P, [mean], method=method, extra_edges=extra_edges)
    eev = evaluate(ev, scens)
    own = own or own_optima(inst, P, scens, method, extra_edges)
    opt = [max(o.expected_net, float(rp.net[w]), float(eev.net[w])) for w, o in enumerate(own)]
    per = [{"scenario": sc, "rp_net": float(rp.net[w]), "own_net": opt[w], "regret": opt[w] - float(rp.net[w]),
            "eev_net": float(eev.net[w]), "own_sites": len(own[w].connected)} for w, sc in enumerate(scens)]
    ws = float(sum(sc.prob * v for sc, v in zip(scens, opt)))
    return {"rp": rp, "ev": ev, "eev": eev, "per": per, "own": own, "vss": rp.expected_net - eev.expected_net,
            "evpi": ws - rp.expected_net, "ws": ws}


# ------------------------------------------------- next step: two-stage adjustable robust (C&CG)
@dataclass(frozen=True)
class BudgetSet:
    """Budgeted interval set on IT loads: each data center's IT load lies in [low, high]; at most
    `budget` of them sit below their high value at once. Kerosene is held at one price."""
    budget: int
    kerosene_yen_l: float = KEROSENE_LOW

    def nominal(self, sources: list[Source]) -> Scenario:
        return Scenario("nominal", "全データセンターが高負荷", "All data centers at high IT load", 1.0,
                        self.kerosene_yen_l, None, tuple((s.key, s.it_mw["high"]) for s in sources))

    def vertices(self, sources: list[Source]) -> list[Scenario]:
        """Corners that can be worst: deliveries never fall when a data center has more waste heat, so a
        worst case drops exactly min(budget, D) data centers to their low value."""
        from itertools import combinations
        k = min(self.budget, len(sources))
        if k == 0:
            return [self.nominal(sources)]
        out = []
        for drop in combinations(range(len(sources)), k):
            it = tuple((s.key, s.it_mw["low"] if i in drop else s.it_mw["high"]) for i, s in enumerate(sources))
            names = "+".join(sources[i].key for i in drop) or "none"
            out.append(Scenario(f"low:{names}", f"低負荷：{names}", f"Low IT load at {names}", 1.0,
                                self.kerosene_yen_l, None, it))
        return out


def ccg(inst: Instance, P: Params, uset: BudgetSet, *, method: str = "kernel", max_iter: int = 10,
        tol: float = 5e-3, seed: list[Scenario] | None = None,
        extra_edges: list[tuple[int, int]] | None = None) -> dict:
    """Two-stage adjustable robust plan over `uset` by column-and-constraint generation
    (max over builds of the min over corners of the net benefit; the recourse is the monthly LP).
    Master: the stochastic model with the expectation replaced by an epigraph variable over the
    corners found so far (solve(objective="worst")); each corner adds its own block of monthly
    deliveries (columns) and an epigraph row (constraint). Its best bound is the upper bound UB.
    Subproblem: the worst corner of `uset` for the master's fixed build, by evaluate() on every
    corner (one LP each; exact because deliveries never fall when a data center has more heat).
    Its value is a lower bound LB. Stops when UB - LB <= tol |UB| or the worst corner is already in
    the master. `seed`: corners from a run at a smaller budget (U(G-1) is inside U(G))."""
    verts = uset.vertices(inst.sources)
    found = [uset.nominal(inst.sources)] + [v for v in (seed or []) if v.key != "nominal"]
    lower, upper, best, hist = -math.inf, math.inf, None, []
    for it in range(max_iter):
        scen = [replace(sc, prob=1.0 / len(found)) for sc in found]
        master = plan_for(inst, P, scen, method=method, objective="worst", extra_edges=extra_edges)
        bound = master.kernel["bound"] if master.kernel is not None else master.dual_bound
        upper = min(upper, bound)
        t_sub = time.perf_counter()
        vals = [evaluate(master, [replace(v, prob=1.0)]).expected_net for v in verts]
        t_sub = time.perf_counter() - t_sub
        w = int(np.argmin(vals))
        if vals[w] > lower:
            lower, best = vals[w], master
        hist.append({"iter": it + 1, "corners": [sc.key for sc in found], "master": float(master.net.min()),
                     "upper": upper, "robust_value": vals[w], "lower": lower, "worst": verts[w].key,
                     "sites": len(master.connected), "master_s": master.seconds, "sub_s": t_sub})
        if upper - lower <= tol * max(abs(upper), 1e-9) or any(sc.key == verts[w].key for sc in found):
            break
        found.append(verts[w])
    return {"plan": best, "value": lower, "upper": upper, "history": hist, "corners": found}


def worst_case(plan: Plan, uset: BudgetSet) -> tuple[float, str]:
    """W(x; G): the plan's net benefit at the worst corner of `uset` (pipes and connections fixed)."""
    vals = [(evaluate(plan, [replace(v, prob=1.0)]).expected_net, v.key) for v in uset.vertices(plan.inst.sources)]
    return min(vals)


def seeded_plan(inst: Instance, P: Params, scens: list[Scenario]) -> tuple[Plan, list[tuple[int, int]]]:
    """The regional plan behind the published results: kernel search with extra candidate links taken from
    each data center's own plan, seeded once under `scens` and once under the nominal scenario; the
    better of the two plans and its extra links."""
    candidates = []
    for seed_scens in (scens, [BudgetSet(0).nominal(inst.sources)]):
        extra: set = set()
        for d in range(inst.D):
            one = inst.subset([d], list(range(inst.U)))
            o = solve_kernel(one, P, seed_scens)
            extra |= set(one.lift([(a, b) for a, b, _, _ in o.built]))
        links = sorted(extra)
        candidates.append((solve_kernel(inst, P, scens, extra_edges=links), links))
    return max(candidates, key=lambda c: c[0].expected_net)


# ------------------------------------------------------------------- matchmaker and the calculator
def smallest_size(P: Params, q_mw: float) -> int | None:
    for k, s in enumerate(P.sizes):
        if s.capacity_mw(P.dT) >= q_mw - 1e-9:
            return k
    return None


def pair_score(inst: Instance, P: Params, scens: list[Scenario], d: int, u: int,
               ud: UserData | None = None, Wc: np.ndarray | None = None) -> dict | None:
    """The pair on its own: its own pipe from data center d, the data center's heat for this user only."""
    ud = ud or user_data(inst, P, scens)
    Wc = Wc if Wc is not None else waste_heat(inst, P, scens)
    dist = float(inst.dist[d, inst.D + u])
    k = smallest_size(P, ud.q[u])
    if k is None or not np.isfinite(dist) or dist > P.max_link_m:
        return None
    prob = np.array([s.prob for s in scens])
    heat = np.array([sum(min(ud.cap[u, t, w], Wc[d, t, w] / ud.r[u]) for t in range(T)) for w in range(len(scens))])
    value = float(prob @ (heat * ud.v[u]))
    pipe = P.sizes[k].yen_m * dist
    return {"u": u, "d": d, "dist_m": dist, "size": P.sizes[k].dn, "capex": pipe + ud.hp[u],
            "heat_mwh": float(prob @ heat), "value": value,
            "score": value - P.own * (P.crf * pipe + P.crf_hp * ud.hp[u])}


def pairwise(inst: Instance, P: Params, scens: list[Scenario], d: int, top: int = 5) -> Plan:
    """The intuitive approach for one data center: score every user alone, take the best `top`, give
    each its own pipe, then see what they deliver together."""
    ud, Wc = user_data(inst, P, scens), waste_heat(inst, P, scens)
    scores = [sc for u in range(inst.U) if (sc := pair_score(inst, P, scens, d, u, ud, Wc)) is not None]
    best = [sc["u"] for sc in sorted(scores, key=lambda r: -r["score"])[:top] if sc["score"] > 0]
    if not best:                                   # no pair pays for itself: nothing is built
        return solve(inst.subset([d], [0]), P, scens, edges=[], force_edges=True)
    sub = inst.subset([d], best)
    return solve(sub, P, scens, edges=[(0, 1 + i) for i in range(len(best))], force_edges=True)


def rank_partners(plan: Plan, d: int, top: int = 5, by: str = "marginal", full_top: int = 0,
                  method: str = "kernel") -> list[dict]:
    """Partners of data center d. by="marginal": the users the regional plan gives to d, ranked by
    how much expected net benefit is lost without them (pipes kept, deliveries re-optimised); the
    first `full_top` are also re-solved from scratch. Free slots are filled with the best remaining
    users by pair score (in_plan False). by="pair": every user ranked by its pair score."""
    inst, P, scens = plan.inst, plan.P, plan.scens
    ud, Wc = plan.ud, plan.W
    pair = {u: pair_score(inst, P, scens, d, u, ud, Wc) for u in range(inst.U)}
    rows: list[dict] = []
    if by == "marginal":
        uv = plan.user_value()
        for u in [u for u in range(inst.U) if plan.assign[u] == d]:
            ev = evaluate(plan, off=[u])
            rows.append({"u": u, "site": inst.users[u], "in_plan": True, "heat_mwh": float(plan.p @ plan.s[u].sum(axis=(0, 1))),
                         "value": float(uv[u]), "loss": plan.expected_net - ev.expected_net,
                         "pair": pair[u]})
        rows.sort(key=lambda r: -r["loss"])
        for row in rows[:full_top]:
            re = plan_for(inst, P, scens, method=method, off=[row["u"]])
            row["loss_full"] = plan.expected_net - re.expected_net
    rest = sorted((p for u, p in pair.items() if p is not None and not any(r["u"] == u for r in rows)),
                  key=lambda r: -r["score"])
    for p in rest:
        if len(rows) >= top:
            break
        if by == "marginal" and plan.x[p["u"]] > 0.5:
            continue                      # served by another data center in the regional plan
        rows.append({"u": p["u"], "site": inst.users[p["u"]], "in_plan": False, "heat_mwh": p["heat_mwh"],
                     "value": p["value"], "loss": None, "pair": p})
    return rows[:top]


def pair_calculator(inst: Instance, P: Params, scens: list[Scenario], d: int, u: int) -> list[dict]:
    """One pair, every number with where it comes from. tag: source, assumption or calculated."""
    ud, Wc = user_data(inst, P, scens), waste_heat(inst, P, scens)
    ps = pair_score(inst, P, scens, d, u, ud, Wc)
    site, src = inst.users[u], inst.sources[d]
    prob = np.array([s.prob for s in scens])
    if ps is None:
        return []
    heat_w = np.array([sum(min(ud.cap[u, t, w], Wc[d, t, w] / ud.r[u]) for t in range(T)) for w in range(len(scens))])
    save_w = heat_w * ud.v[u]
    k = smallest_size(P, ud.q[u])
    pipe = P.sizes[k].yen_m * ps["dist_m"]
    cop = ud.cop[u]
    rows = [
        ("dc", "データセンター", "Data center", f"{src.name} / {src.name_en}", "", "source", src.basis),
        ("user", "相手", "Partner", f"{site.name} / {site.name_en}", "", "source", site.source),
        ("dist", "道路沿いの距離", "Distance along roads", round(ps["dist_m"]), "m",
         "source" if inst.road else "calculated",
         f"OpenStreetMap road network, shortest path (© OpenStreetMap contributors, {URL['osm']})"),
        ("demand", "年間の熱需要", "Annual heat demand", round(float(ud.demand[u].mean(axis=1).sum())), "MWh", "assumption",
         f"{site.source}; monthly profile from JMA climate normals"
         + (" or the scenarios' weather years" if any(s.weather for s in scens) else "")),
        ("peak", "設計ピーク", "Design peak", round(float(ud.peak[u]), 2), "MW", "assumption", PEAK_BASIS),
        ("temp", "必要な温度", "Supply temperature needed", P.supply_c[site.kind], "C", "assumption",
         SUPPLY_BASIS[site.kind]),
        ("cop", "ヒートポンプのCOP", "Heat-pump COP", "直接利用 / direct" if cop is None else round(cop, 2), "",
         "calculated", f"{P.carnot_eff:.0%} of Carnot, capped at {P.cop_cap:g} (assumptions); mode {P.mode}"),
        ("size", "管の太さ", "Pipe size", f"DN{P.sizes[k].dn}", "", "calculated",
         f"smallest size carrying {ud.q[u]:.2f} MW at dT {P.dT:g} K; JIS G 3452 diameters, design velocities (assumption)"),
        ("capex", "導管の工事費", "Pipe investment", round(pipe), "yen", "assumption", PIPE_COST_BASIS),
        ("hp", "ヒートポンプの投資", "Heat-pump investment", round(float(ud.hp[u])), "yen", "assumption",
         HP_COST_BASIS),
        ("heat", "年間に届く熱（期待値）", "Heat delivered per year (expected)", round(float(prob @ heat_w)), "MWh",
         "calculated", "monthly demand, coverage and the data center's waste heat (IT load x recovery, assumptions)"),
    ]
    for w, sc in enumerate(scens):
        rows.append((f"saving_{sc.key}", f"年間の節約（{sc.ja}）", f"Annual saving ({sc.en})", round(float(save_w[w])),
                     "yen", "calculated",
                     (f"kerosene {sc.kerosene_yen_l:g} yen/L ({URL['kerosene'] if sc.kerosene_yen_l == KEROSENE_SURVEY else 'conservative bulk price, assumption'}); "
                     f"boiler {P.boiler_eff:.0%}, electricity {P.power_yen_kwh:g} yen/kWh (assumptions)")))
    exp_save = float(prob @ save_w)
    rows += [
        ("saving", "年間の節約（期待値）", "Annual saving (expected)", round(exp_save), "yen", "calculated", "probability-weighted"),
        ("co2", "CO2削減（期待値）", "CO2 avoided (expected)", round(float(prob @ heat_w) * ud.co2[u], 1), "t/yr", "calculated",
         (f"kerosene {KEROSENE_KG_CO2_PER_L:.2f} kg/L ({URL['co2']}); grid electricity {P.grid_t_per_mwh:g} t/MWh for user "
         f"heat pumps ({URL['grid_co2']})")),
        ("payback", "単純回収年数", "Simple payback",
         round(P.own * (pipe + ud.hp[u]) / exp_save, 1) if exp_save > 0 else None,
         "years", "calculated", "investment / expected annual saving"),
    ]
    # Policy scenarios for the pair: other electricity for the heat pump, the cost of a tonne, a subsidy.
    heat, elec = float(prob @ heat_w), float(prob @ heat_w) * ud.elec[u]
    fuel_t = KEROSENE_KG_CO2_PER_L / (KEROSENE_KWH_PER_L * P.boiler_eff)
    co2_by = [heat * fuel_t - elec * f for _, _, f in GRID_SCENARIOS.values()]
    co2_own = heat * ud.co2[u]
    full_cost = P.crf * pipe + P.crf_hp * ud.hp[u]
    save_plain = exp_save - P.carbon_yen_t * co2_own             # the saving without any carbon price
    rows += [
        ("co2_power", "CO2削減：ヒートポンプの電気が再エネ100%／2030年度目標／系統電力の場合",
         "CO2 avoided if the heat pump runs on renewable power / the FY2030 target mix / grid power",
         " / ".join(f"{x:,.0f}" for x in co2_by), "t/yr", "calculated",
         ("kerosene not burned minus heat-pump electricity x "
          + ", ".join(f"{f:g}" for _, _, f in GRID_SCENARIOS.values())
          + " t/MWh (scenarios; the same in every case when the heat is used directly)")),
        ("abatement", "CO2を1トン減らす費用（補助・炭素価格なし）", "Cost of a tonne of CO2 avoided (no subsidy, no carbon price)",
         round((full_cost - save_plain) / co2_own) if co2_own > 0 else None, "yen/t", "calculated",
         ("(annual cost of pipe and heat pump - expected annual saving) / CO2 avoided; negative when the pair "
          "pays for itself, otherwise the carbon price at which it breaks even")),
        ("payback_subsidy", "回収年数：補助率が1/3・1/2・2/3の場合", "Payback with a subsidy of 1/3, 1/2 or 2/3",
         " / ".join(f"{(1 - r) * (pipe + ud.hp[u]) / save_plain:.1f}" for r in SUBSIDY_RATES) if save_plain > 0 else None,
         "years", "calculated", "investment x (1 - subsidy rate) / expected annual saving (scenarios)"),
    ]
    return [{"key": a, "ja": b, "en": c_, "value": v, "unit": un, "tag": tg, "basis": bs}
            for a, b, c_, v, un, tg, bs in rows]


def assumptions_table(P: Params) -> list[dict]:
    """Every parameter of the model with its value and basis (source URL or assumption)."""
    rows = [
        ("recovery", "回収できる廃熱の割合", "Recoverable share of IT heat", P.recovery, "", "assumption (as v1): 30-35 C capture"),
        ("waste_c", "廃熱の温度", "Waste-heat temperature", P.waste_c, "C", "assumption: liquid or rear-door cooling"),
        ("network_c", "低温導管網の温度", "Ambient loop temperature", P.network_c, "C", "assumption"),
        ("central_c", "集中方式の送り温度", "Central network supply", P.central_c, "C", "assumption: enough for hot water"),
        ("carnot_eff", "カルノー効率に対する割合", "Share of Carnot COP", P.carnot_eff, "", "assumption: 45-55 % typical"),
        ("cop_cap", "COPの上限", "COP cap", P.cop_cap, "", "assumption: manufacturer range for small lifts"),
        ("dT", "往き還りの温度差", "Supply-return difference", f"{P.dT_ambient:g} / {P.dT_central:g}", "K", "assumption: ambient / central"),
        ("loss", "導管の熱損失", "Network heat loss", f"{P.loss_ambient:.0%} / {P.loss_central:.0%}", "", "assumption: ambient / central"),
        ("kerosene", "灯油価格", "Kerosene price", f"{KEROSENE_LOW:g} / {KEROSENE_SURVEY:g}", "yen/L",
         f"assumption (conservative bulk) / source: ANRE survey 2026-11-16, Hokkaido ({URL['kerosene']})"),
        ("boiler_eff", "置き換えるボイラーの効率", "Boiler efficiency replaced", P.boiler_eff, "", "assumption (as v1)"),
        ("power", "電気代", "Electricity price", P.power_yen_kwh, "yen/kWh", "assumption (as v1)"),
        ("co2_kerosene", "灯油のCO2排出係数", "Kerosene CO2 factor", KEROSENE_KG_CO2_PER_L, "kg/L", f"source: {URL['co2']}"),
        ("grid", "系統電力のCO2", "Grid electricity CO2", P.grid_t_per_mwh, "t/MWh",
         f"source: Hokkaido Electric Power, standard plans, FY2024 results ({URL['grid_co2']})"),
        ("grid_2030", "2030年度の電力のCO2（シナリオ）", "Grid electricity CO2 in FY2030 (scenario)", GRID_SCENARIOS["target2030"][2],
         "t/MWh", f"source: Plan for Global Warming Countermeasures, 2025 ({URL['grid_2030']})"),
        ("carbon", "炭素価格（シナリオ）", "Carbon price (scenario)", P.carbon_yen_t, "yen/t",
         "scenario, zero by default: a price on the CO2 avoided, on top of today's fuel taxes"),
        ("subsidy", "設備費の補助率（シナリオ）", "Investment subsidy (scenario)", P.subsidy, "",
         "scenario, zero by default: share of the pipe and heat-pump investment"),
        ("years", "導管の年数・割引率", "Pipe life, discount rate", f"{P.years} / {P.rate:.0%}", "", "assumption (as v1)"),
        ("hp_years", "ヒートポンプの年数", "Heat-pump life", P.hp_years, "years", "assumption"),
        ("hp_capex", "ヒートポンプの投資", "Heat-pump investment", f"{P.hp_yen_per_mw_user:,.0f} / {P.hp_yen_per_mw_central:,.0f}",
         "yen/MW", "user / central; " + HP_COST_BASIS),
        ("alpha", "管とヒートポンプの容量（ピーク比）", "Sized share of each user's peak", P.alpha, "", "assumption"),
        ("tie", "同じ費用のときの割り当て（タイブレーク）", "Tie-break between equal-cost data centers", P.tie_yen_m,
         "yen/m/yr", TIE_BASIS),
        ("peak", "ピーク係数", "Peak factors", ", ".join(f"{k} {v:g}" for k, v in P.peak_factor.items()), "", PEAK_BASIS),
        ("pipe_cost", "導管の単価", "Pipe cost per metre", ", ".join(f"DN{s.dn} {s.yen_m:,.0f}" for s in P.sizes), "yen/m", PIPE_COST_BASIS),
        ("pipe_cap", "導管の容量", "Pipe capacity", ", ".join(f"DN{s.dn} {s.capacity_mw(P.dT):.2f}" for s in P.sizes), "MW",
         f"water {RHO:g} kg/m3, {CP} kJ/kgK, dT {P.dT:g} K, velocities "
         + ", ".join(f"{s.velocity:g}" for s in P.sizes) + " m/s (assumption), JIS G 3452 inner diameters"),
    ]
    rows += [(f"supply_{k}", f"必要温度：{KINDS[k][0]}", f"Supply temperature: {KINDS[k][1]}", v, "C", SUPPLY_BASIS[k])
             for k, v in P.supply_c.items()]
    return [{"key": a, "ja": b, "en": c, "value": v, "unit": u, "basis": bs} for a, b, c, v, u, bs in rows]
