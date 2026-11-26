"""Export the GX-zone portfolio (out/gx_zone/gx.json) for web/gx_zone/index.html.

The page paints the zone's energy portfolio, not the heat network: what renewable capacity already
runs in Ishikari, what is under construction or planned, where the data centers stand, the plots
with pre-filed grid applications, and the fossil plants still operating.

Every marker traces to a source. The sources:
- `data/curated/ishikari_data_centers.csv` via ishikari_sources() (the records page 1 uses),
- the TSH GX Information Platform (tsh-gxpf.jp, the prefecture-side official project registry),
- OpenStreetMap (ODbL) for turbine positions, solar plants, fossil plants and the grid,
- press releases and the prefecture's recruitment guideline for the rest.
- the five plots come from data/curated/ishikari_gx_plots.csv (registered in data/register.toml).

Unpublished locations keep the repo's convention: a GSI district point with a `where` note saying
so. Nothing is drawn at an invented location.

Run: uv run python scripts/export_gx_zone.py
"""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from dcopt.heat.network import Params, ishikari_sources

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "gx_zone"

# the one view: Ishikari Bay New Port and its bay (the wind parks)
VIEW = (141.13, 43.09, 141.45, 43.28)

METI_RELEASE = "https://www.meti.go.jp/press/2026/09/20260911006.html"
ISHIKARI_ZONE = "https://www.city.ishikari.hokkaido.jp/sangyo/yuchi/1007457.html"
KOBO = "https://www.pref.hokkaido.lg.jp/kz/ssg/272100.html"
KOBO_LABEL = ("道の公募要領 2026-10", "Hokkaido guidelines, Oct 2026")
CITY_PLAN_URL = "https://www.city.ishikari.hokkaido.jp/_res/projects/default_project/_page_/001/002/422/senko20250704.pdf"
GXPF = "https://tsh-gxpf.jp/en/business/"
GXPF_LABEL = ("TSH GX事業情報", "TSH GX platform")
MARUBENI = "https://www.marubeni.com/ja/news/2024/release/00092/"
HOKUDEN = "https://www.hokkaido-electric.co.jp/pressrelease/detail/4319"
OSM = ("© OpenStreetMap contributors (ODbL)", "© OpenStreetMap contributors (ODbL)")
CITY_PLAN = ("石狩市 脱炭素先行地域計画 2025-07改定", "Ishikari leading-area plan, rev. 2025-07")

r5 = lambda x: round(float(x), 5)

# label offsets in px: the two parcels inside lot 40-10 would overlap otherwise
OFFSETS = {"chuo40_15": -28}


def S(ja, en):
    return {"ja": ja, "en": en}


def get_json(url: str, tries: int = 4):
    """GET a JSON API with backoff: the Overpass mirror rate-limits and often answers 504."""
    import time
    import urllib.request

    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dcopt/1.0 (gx zone overlay)"})
            return json.loads(urllib.request.urlopen(req, timeout=150).read().decode())
        except Exception as e:                     # noqa: BLE001 - retry any transport error
            last = e
            time.sleep(10 * (i + 1))
    raise last


# kind: wind_offshore | wind_onshore | solar | biomass | storage | hydrogen | fossil
# status: operating | under_construction | planned | assessing
def energy_records() -> list[dict]:
    """The energy portfolio, with the source named per record. Offshore wind farms have no
    published turbine coordinates, so they sit at a bay representative point and say so; OSM-mapped
    objects (turbines, solar plants, fossil plants) carry their real geometry."""
    return [
        # ---- Ishikari: offshore wind, operating -------------------------------------------------
        {"kind": "wind_offshore", "status": "operating",
         "name": "石狩湾新港地域洋上風力発電施設", "name_en": "Ishikari Bay New Port Offshore Wind Farm",
         "lon": 141.250, "lat": 43.235, "mw": 112.0,
         "where": ("石狩湾の沖合（事業者は座標未公表のため湾内の代表点）", "Offshore in Ishikari Bay (no coordinates published; a bay representative point)"),
         "note": ("北海道電力子会社が運営。2024年7月から営業運転。",
                  "Operated by a Hokkaido Electric subsidiary; commercial operation from July 2024."),
         "source": S("北海道電力 プレスリリース", "Hokkaido Electric press release"), "url": HOKUDEN, "city": "ishikari"},
        {"kind": "wind_offshore", "status": "operating",
         "name": "石狩湾新港第2洋上風力発電所", "name_en": "Ishikari Bay New Port Offshore Wind Farm II",
         "lon": 141.230, "lat": 43.222, "mw": 83.0,
         "where": ("石狩市の沖合（事業者は座標未公表のため湾内の代表点）", "Offshore Ishikari (no coordinates published; a bay representative point)"),
         "note": ("丸紅・三井物産出資のSPC。2024年3月に運転開始（3.45MW×24基）。",
                  "SPC owned by Marubeni and Mitsui & Co.; operation from March 2024 (24 turbines of 3.45 MW)."),
         "source": S("丸紅 プレスリリース 2024-03-28", "Marubeni press release, 2024-03-28"), "url": MARUBENI, "city": "ishikari"},
        # ---- Ishikari: onshore wind -------------------------------------------------------------
        {"kind": "wind_onshore", "status": "operating",
         "name": "北ガス石狩風力発電所", "name_en": "Hokkaido Gas Ishikari Wind Farm",
         "lon": 141.3069, "lat": 43.1969, "mw": 2.35,
         "where": ("TSH GX事業情報：石狩市新港中央4丁目", "TSH GX platform: Shinko-Chuo 4-chome, Ishikari"),
         "note": ("北海道瓦斯。2,350kW。", "Hokkaido Gas; 2,350 kW."),
         "source": GXPF_LABEL, "url": GXPF + "info/9145/", "city": "ishikari"},
        {"kind": "wind_onshore", "status": "operating", "nodes": True,
         "name": "石狩湾新港地域の陸上風車群", "name_en": "Onshore wind turbines around the New Port",
         "lon": 141.28, "lat": 43.20, "mw": 60.0,
         "where": ("OpenStreetMapの風車38基（個別の点は地図に表示）", "38 wind turbines mapped in OpenStreetMap (drawn individually)"),
         "note": ("市の計画は「石狩湾新港地域を中心にすでに60MW超の風車が稼働」と記す。個別の風車はOSMの点から描く。",
                  "The city plan records more than 60 MW of wind turbines already operating around the New Port; the individual turbines are drawn from OSM nodes."),
         "source": S(CITY_PLAN[0] + "；© OpenStreetMap (ODbL)", CITY_PLAN[1] + "; © OpenStreetMap (ODbL)"),
         "url": CITY_PLAN_URL, "city": "ishikari"},
        {"kind": "wind_onshore", "status": "planned",
         "name": "（仮称）北海道厚田風力発電事業", "name_en": "Hokkaido Atsuta Wind Farm (planned)",
         "lon": 141.410, "lat": 43.318, "mw": 64.5,
         "where": ("TSH GX事業情報：石狩市（厚田地区の代表点）", "TSH GX platform: Ishikari (a representative point for the Atsuta district)"),
         "note": ("東急不動産。64,500kW。", "Tokyu Land; 64,500 kW."),
         "source": GXPF_LABEL, "url": GXPF + "info/9108/", "city": "ishikari"},
        # ---- Ishikari: solar, operating (OSM-mapped, named plants in the view) ------------------
        {"kind": "solar", "status": "operating", "nodes": True,
         "name": "太陽光発電所（石狩市内・OSM登録）", "name_en": "Solar plants in Ishikari (from OSM)",
         "lon": 141.32, "lat": 43.18, "mw": 12.0,
         "where": ("OpenStreetMapの発電所（個別に地図に描かれる）", "Solar plants mapped in OpenStreetMap (drawn individually)"),
         "note": ("OSMに名前と出力つきで登録された石狩市内の太陽光（例：IMCソーラー1.95MW、郵船商事の"
                  "新港南・新港西各1.92MW、ソーラーファーム石狩1.2MWほか）。合計はOSMの記載から集計。",
                  "Named solar plants mapped in OSM inside Ishikari (e.g. IMC Solar 1.95 MW, Yusen Cargo's Shinko-Minami "
                  "and Shinko-Nishi plants at 1.92 MW each, Solar Farm Ishikari 1.2 MW, among others); the total sums the OSM entries."),
         "source": OSM, "city": "ishikari"},
        # ---- Ishikari: storage, operating -------------------------------------------------------
        {"kind": "storage", "status": "operating",
         "name": "石狩蓄電所", "name_en": "Ishikari Power Storage Station",
         "lon": 141.3230, "lat": 43.1650, "mw": 30.0,
         "where": ("TSH GX事業情報：石狩市花川東641番1・674番1（地番の地区点）", "TSH GX platform: Hanakawa-Higashi 641-1/674-1, Ishikari (a district point)"),
         "note": ("アールスリー蓄電所合同会社。30,000kW。", "R3 Storage Stations GK; 30,000 kW."),
         "source": GXPF_LABEL, "url": GXPF + "info/8318/", "city": "ishikari"},
        # ---- Ishikari: fossil -------------------------------------------------------------------
        {"kind": "fossil", "status": "operating", "fuel": "gas",
         "name": "石狩湾新港発電所", "name_en": "Ishikariwan Shinko Power Station (gas)",
         "lon": 141.2753, "lat": 43.1936, "mw": 569.4,
         "where": ("OpenStreetMap way 931796255（北海道電力、2019年2月運転開始）", "OpenStreetMap way 931796255 (Hokkaido Electric, operating since Feb 2019)"),
         "note": ("ガス火力 569,400kW。隣接する石狩LNG基地が燃料を受け持つ。", "Gas-fired, 569,400 kW; the Ishikari LNG base next door supplies its fuel."),
         "source": OSM, "city": "ishikari"},
        {"kind": "fossil", "status": "operating", "fuel": "lng",
         "name": "石狩LNG基地", "name_en": "Ishikari LNG Base",
         "lon": 141.2955, "lat": 43.2067, "mw": None,
         "where": ("OpenStreetMap way 962283251（北海道ガス）", "OpenStreetMap way 962283251 (Hokkaido Gas)"),
         "note": ("LNGの受け入れ・貯蔵基地。発電所ではないが火力の燃料拠点。", "An LNG receiving and storage base; not a plant, but the fuel terminal of the gas plant."),
         "source": OSM, "city": "ishikari"},

    ]


def plot_records() -> list[dict]:
    """The five Ishikari plots with the prefecture's pre-filed grid applications, from the curated
    CSV (data/curated/ishikari_gx_plots.csv). What they are: industrial land with a reserved grid
    connection — no data center on them yet. Coordinates and their basis live in the CSV."""
    import csv
    path = ROOT / "data" / "curated" / "ishikari_gx_plots.csv"
    out = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append({
                "key": row["key"], "lot": row["lot_ja"], "lot_en": row["lot_en"],
                "mw": float(row["mw"]), "kv": int(row["kv"]), "year": row["connection_from"],
                "lon": float(row["lon"]), "lat": float(row["lat"]),
                "area_m2": float(row["area_m2"]), "offset_px": OFFSETS.get(row["key"], 0),
                "where": (row["location_ref"], row["location_basis"]),
                "note": (row["note"], row["note"]),
                "source": KOBO_LABEL, "url": KOBO, "city": "ishikari"})
    return out


def dc_records() -> list[dict]:
    """The data centers, from the curated Ishikari records, each with its source."""
    from dcopt.common.geo import use_overpass_mirror
    from dcopt.heat.v1 import ishikari_sites

    use_overpass_mirror()
    sakura, sites = ishikari_sites()
    from dcopt.heat.network import URL
    dc_urls = {"isrd1": URL["isrd"], "sakura": URL["sakura"], "zed": URL["zed"], "nttme": URL["nttme"]}
    dcs = []
    for s in ishikari_sources(sakura):
        dcs.append({"key": s.key, "kind": "dc", "name": s.name, "name_en": s.name_en,
                    "lon": r5(s.lon), "lat": r5(s.lat), "status": s.status,
                    "mw": s.it_mw, "where": list(s.where), "note": s.basis,
                    "source": S("関係企業の公表資料・報道", "Operator announcements and press"),
                    "url": dc_urls.get(s.key, ""),
                    "city": "ishikari"})
    return dcs


def grid_layer() -> dict:
    """The real grid near the port, from OpenStreetMap: the substations inside the view and the
    275 kV corridor of the Ishikariwan Shinko power station line. Plain lon/lat lists."""
    query = ("[out:json][timeout:90];"
             '(nwr["power"="substation"](43.14,141.20,43.26,141.42);'
             '(way(955800108);way(962272954);way(962272955);););'
             "out geom tags;")
    data = get_json("https://maps.mail.ru/osm/tools/overpass/api/interpreter?data=" + urllib.parse.quote(query))
    lines, substations = [], []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if tags.get("power") == "line":
            pts = [[r5(p["lon"]), r5(p["lat"])] for p in el.get("geometry", [])]
            if len(pts) >= 2:
                lines.append(pts)
        elif tags.get("power") == "substation":
            g = el.get("geometry", [])
            if g:
                lon = sum(p["lon"] for p in g) / len(g)
                lat = sum(p["lat"] for p in g) / len(g)
            else:
                c = el.get("center", {})
                lon, lat = c.get("lon", 0), c.get("lat", 0)
            substations.append({"lon": r5(lon), "lat": r5(lat),
                                "name": tags.get("name") or "", "kv": 66 if "66000" in (tags.get("voltage") or "") else 275})
    return {"lines": lines, "substations": substations}


def osm_generators(west, south, east, north):
    """Wind turbines and solar plants mapped in OpenStreetMap inside the box."""
    query = ("[out:json][timeout:120];"
             f'(nwr["power"="generator"]["generator:source"~"wind|solar"]({south},{west},{north},{east});'
             f'nwr["power"="plant"]["plant:source"="solar"]({south},{west},{north},{east}););'
             "out geom tags center;")
    data = get_json("https://maps.mail.ru/osm/tools/overpass/api/interpreter?data=" + urllib.parse.quote(query))
    wind, solar = [], []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        src = tags.get("generator:source") or tags.get("plant:source")
        if src == "wind":
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat and lon:
                wind.append({"lon": r5(lon), "lat": r5(lat)})
        elif src == "solar":
            g = el.get("geometry") or []
            pts = [(p["lon"], p["lat"]) for p in g]
            if len(pts) >= 3:
                lon = sum(p[0] for p in pts) / len(pts)
                lat = sum(p[1] for p in pts) / len(pts)
            else:                                   # the mirror may drop geometry: fall back to the center
                c = el.get("center") or {}
                lon, lat = c.get("lon"), c.get("lat")
            if lon and lat:
                solar.append({"lon": r5(lon), "lat": r5(lat),
                              "mw_txt": tags.get("generator:output:electricity") or "",
                              "name": tags.get("name") or ""})
    return wind, solar


def build() -> dict:
    # the heat-network KPI stays as a footnote: theme 1 covers Ishikari only
    story = json.loads((ROOT / "out" / "heat_story" / "story.json").read_text(encoding="utf-8"))
    kpi = story["scenarios"]["base"]["opt"]["kpi"]

    dcs = dc_records()
    energy = energy_records()
    reserved = plot_records()

    return {
        "view": VIEW,
        "zone": {"certified": "2026-09-11",
                 "type": ("データセンター集積型", "data-center cluster type"),
                 "cities": {"ja": "石狩市", "en": "Ishikari, Hokkaido"},
                 "reserved_mw": sum(r["mw"] for r in reserved),
                 "source": f"{METI_RELEASE} ; {ISHIKARI_ZONE}"},
        "dcs": dcs,
        "energy": energy,
        "reserved": reserved,
        "heat": {"km": Params().max_link_m / 1000, "kpi": kpi,
                 "note": ("テーマ1の熱モデルは石狩が対象（導管1本8km上限）。公表している地域計画は13か所を"
                          "7.8kmの導管でつなぐ（推計）。このページの主役はエネルギーのポートフォリオで、導管網は補足。",
                          "The theme-1 heat model covers Ishikari (8 km candidate-link limit); its published regional "
                          "plan connects 13 sites with 7.8 km of pipe (an estimate). This page is about the energy "
                          "portfolio; the heat network is a footnote.")},
        "sources": {"meti": METI_RELEASE, "ishikari": ISHIKARI_ZONE, "kobo": KOBO, "gxpf": GXPF,
                    "marubeni": MARUBENI, "hokuden": HOKUDEN, "city_plan": CITY_PLAN_URL},
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = build()
    wind, solar_ish = osm_generators(*VIEW)
    data["osm_wind"] = wind
    data["osm_solar_ishikari"] = solar_ish
    (OUT / "gx.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    # base.json is shared with the heat story page; the grid record is appended, not rewritten
    base_path = ROOT / "out" / "heat_story" / "base.json"
    records = json.loads(base_path.read_text(encoding="utf-8"))
    grid = grid_layer()
    records = [r for r in records if r.get("layer") != "grid"] + [{"layer": "grid", **grid}]
    base_path.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")))
    re_mw = sum(e["mw"] for e in data["energy"] if e["kind"] != "fossil" and e["status"] == "operating" and e["mw"])
    fo_mw = sum(e["mw"] for e in data["energy"] if e["kind"] == "fossil" and e["mw"])
    print(f"gx.json: {len(data['energy'])} energy records (RE operating ≈{re_mw:.0f} MW, fossil {fo_mw:.0f} MW), "
          f"{len(data['dcs'])} data centers, {len(data['reserved'])} plots = {data['zone']['reserved_mw']} MW; "
          f"OSM: {len(wind)} wind nodes, {len(solar_ish)} solar plants; "
          f"grid layer: {len(grid['substations'])} substations, {len(grid['lines'])} line ways")


if __name__ == "__main__":
    main()
