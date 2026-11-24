"""Heat-supply proposals for one data center and one partner (theme 1, model v2).

The idea starter ends its demo with: pick a data center, see five ranked heat partners and open the
proposal for the best one. `rank_partners` (network.py) ranks the partners of a data center in the
regional plan; `proposal_data` collects every number for one of them; `render_html` lays it out as a
printable A4 proposal followed by a calculation sheet in which every input shows its source or is marked
as an assumption.

Heat price. A pair happens only at a price for the heat that leaves both sides better off. Let H be the
heat delivered per year (MWh), F the kerosene it replaces (yen/yr) and E the heat pumps' electricity
(yen/yr). With the pipe owned by the supplier (the data center or a heat company), annuities as in the
model and operation and maintenance left out:

    ambient loop   supplier pays the pipe                       p_min = CRF * pipe / H
                   partner pays its own heat pump and power     p_max = (F - E - CRF_hp * hp) / H
    central        supplier pays the pipe, the central heat     p_min = (CRF * pipe + CRF_hp * hp + E) / H
                   pump and its power; partner only the price   p_max = F / H

Either way p_max - p_min = (the pair's expected net benefit per year) / H, so a price range exists
exactly when the pair pays for itself. Splitting the gain equally (the Nash bargaining price with
linear utilities) gives the midpoint.
"""
from __future__ import annotations

import html as _html
import math
import re
from datetime import date

import numpy as np

from dcopt.heat.network import KEROSENE_LOW, KEROSENE_SURVEY, MODES, T, URL, Plan, pair_calculator, pair_score
from dcopt.heat.v1 import KEROSENE_KWH_PER_L, KINDS, MONTHS_EN

REPO = "https://github.com/ggnsjp/team-data-center"
ASSUMED_KINDS = {"new_greenhouse", "aquaculture", "snow"}
GROUP = {"greenhouse": "farm", "new_greenhouse": "farm", "aquaculture": "farm", "snow": "snow"}
GROUP_COLOR = {"farm": "#0CA30C", "building": "#D55181", "snow": "#3987E5"}
DC_SHORT = {"isrd1": ("第1号", "No. 1"), "sakura": ("さくらインターネット", "Sakura"), "zed": ("ZED石狩", "ZED"),
            "nttme": ("NTT-ME", "NTT-ME")}
TAGS = {"source": ("出典", "Source"), "assumption": ("仮定", "Assumption"), "calculated": ("計算", "Calculated")}
DN_WIDTH = {50: 1.3, 80: 1.6, 100: 1.9, 150: 2.4, 200: 2.9, 250: 3.4}

# colours: ink and accent tokens of the project; heat and rest validated for the monthly chart
INK, INK2, MUTED, LINE = "#14213D", "#4A5568", "#6B7486", "#DADFE7"
ACCENT, HEAT, REST = "#B3541E", "#E07B39", "#CDD3DD"


# ------------------------------------------------------------------------------------------- data
def _f(x) -> float:
    return float(x) if x is not None else math.nan


def _dc_short(key: str, name: str, name_en: str) -> tuple[str, str]:
    return DC_SHORT.get(key, (name, name_en))


def proposal_data(plan: Plan, d: int, u: int, *, rank: int | None = None, loss: float | None = None,
                  route: list | None = None, today: date | None = None) -> dict:
    """Every number of the proposal from data center d to user u, as plain JSON-ready values.

    plan: the regional plan (its instance, parameters and scenarios are used for the pair as well).
    loss: expected net benefit the regional plan loses without u (rank_partners), if u is in it.
    route: [[lon, lat], ...] of the dedicated pipe along the roads; a straight line when not given."""
    inst, P, scens = plan.inst, plan.P, plan.scens
    ud, Wc, p = plan.ud, plan.W, plan.p
    src, site = inst.sources[d], inst.users[u]
    nW = len(scens)
    demand = ud.demand[u]
    if route is None:
        route = [[src.lon, src.lat], [site.lon, site.lat]]
    group = GROUP.get(site.kind, "building")
    out: dict = {
        "date": (today or date.today()).isoformat(), "mode": P.mode, "mode_text": list(MODES[P.mode]),
        "rank": rank, "candidates": inst.U, "data_centers": inst.D,
        "dc": {"key": src.key, "name": src.name, "name_en": src.name_en, "short": list(_dc_short(src.key, src.name, src.name_en)),
               "lon": src.lon, "lat": src.lat, "status": src.status, "it_mw": dict(src.it_mw)},
        "others": [{"key": s.key, "short": list(_dc_short(s.key, s.name, s.name_en)), "lon": s.lon, "lat": s.lat}
                   for i, s in enumerate(inst.sources) if i != d],
        "site": {"key": site.key, "name": site.name, "name_en": site.name_en, "kind": site.kind,
                 "kind_text": list(KINDS[site.kind][:2]), "group": group, "assumed": site.kind in ASSUMED_KINDS,
                 "lon": site.lon, "lat": site.lat, "annual_mwh": float(demand.sum()),
                 "supply_c": P.supply_c[site.kind], "cop": ud.cop[u]},
        "route": [[round(float(a), 5), round(float(b), 5)] for a, b in route],
        "demand_month": [float(x) for x in demand],
        "scenarios": [{"key": s.key, "ja": s.ja, "en": s.en, "prob": s.prob, "kerosene": s.kerosene_yen_l,
                       "it_mw": s.it_load(src)} for s in scens],
        "assumptions": {"recovery": P.recovery, "waste_c": P.waste_c, "boiler_eff": P.boiler_eff,
                        "crf": P.crf, "crf_hp": P.crf_hp, "years": P.years, "hp_years": P.hp_years, "rate": P.rate},
    }
    rows = pair_calculator(inst, P, scens, d, u)
    pair = pair_score(inst, P, scens, d, u, ud, Wc)
    heat_tw = (np.array([[min(ud.cap[u, t], Wc[d, t, w] / ud.r[u]) for w in range(nW)] for t in range(T)])
               if pair else np.zeros((T, nW)))
    heat_w = heat_tw.sum(axis=0)
    H = float(p @ heat_w)
    if pair and H > 0:
        fuel_w = np.array([P.fuel_yen_per_mwh(s.kerosene_yen_l) for s in scens])
        F = float(p @ (heat_w * fuel_w))
        V = float(p @ (heat_w * ud.v[u]))
        E = F - V
        hp = float(ud.hp[u])
        pipe = float(pair["capex"]) - hp
        if P.mode == "central":
            p_min, p_max = (P.crf * pipe + P.crf_hp * hp + E) / H, F / H
        else:
            p_min, p_max = P.crf * pipe / H, (V - P.crf_hp * hp) / H
        save_w = heat_w * ud.v[u]
        out["pair"] = {
            "dist_m": float(pair["dist_m"]), "dn": int(pair["size"]), "pipe": pipe, "hp": hp, "capex": pipe + hp,
            "heat": H, "share": H / float(demand.sum()) if demand.sum() > 0 else 0.0,
            "month": [float(x) for x in heat_tw @ p], "value": V, "fuel": F, "elec": E,
            "saving_w": [float(x) for x in save_w], "net": float(pair["score"]),
            "payback": (pipe + hp) / V if V > 0 else None,
            "kerosene_l": H * 1000 / (KEROSENE_KWH_PER_L * P.boiler_eff), "co2": H * float(ud.co2[u]),
            "p_min": p_min, "p_max": p_max, "p_mid": (p_min + p_max) / 2,
            "fuel_mwh": [P.fuel_yen_per_mwh(KEROSENE_LOW), P.fuel_yen_per_mwh(KEROSENE_SURVEY)],
        }
    else:
        out["pair"] = None
    in_plan = bool(plan.x[u] > 0.5)
    served = int(plan.assign[u]) if in_plan else None
    out["regional"] = {
        "in_plan": in_plan, "served_by": inst.sources[served].key if served is not None else None,
        "served_by_short": list(_dc_short(inst.sources[served].key, inst.sources[served].name,
                                          inst.sources[served].name_en)) if served is not None else None,
        "heat": float(plan.s[u].sum(axis=(0, 1)) @ p) if in_plan else 0.0,
        "month": [float(x) for x in plan.s[u].sum(axis=0) @ p] if in_plan else [0.0] * T,
        "loss": _f(loss) if loss is not None else None,
        "dc_sites": int(((plan.assign == d) & (plan.x > 0.5)).sum()),
        "sites": len(plan.connected), "km": plan.pipe_m / 1000, "net": plan.expected_net,
    }
    out["rows"] = _rows(out, rows, P, src)
    return out


def _rows(out: dict, rows: list[dict], P, src) -> list[dict]:
    """The calculator's rows plus the proposal's own numbers, each tagged source, assumption or calculated."""
    rows = [dict(r) for r in rows]
    for r in rows:
        if r["key"] == "dc":
            link = URL["gsi"] if "GSI" in src.where[1] else URL["osm"] if "OpenStreetMap" in src.where[1] else ""
            r["basis"] = f"{src.where[0]} / position: {src.where[1]}" + (f" ({link})" if link else "")
            r["tag"] = "source" if link else "assumption"
    lo, hi = src.it_mw["low"], src.it_mw["high"]
    rows.insert(1, {"key": "it", "ja": "IT負荷（低／高）", "en": "IT load (low / high)", "value": f"{lo:g} / {hi:g}",
                    "unit": "MW", "tag": "source" if src.basis.startswith("source") else "assumption",
                    "basis": src.basis})
    rows.insert(2, {"key": "waste", "ja": "回収できる廃熱（期待値）", "en": "Recoverable waste heat (expected)",
                    "value": round(sum(s["prob"] * s["it_mw"] for s in out["scenarios"]) * 8760 * P.recovery),
                    "unit": "MWh/yr", "tag": "calculated",
                    "basis": f"IT load x 8,760 hours x {P.recovery:.0%} recoverable at about {P.waste_c:g} C (assumption)"})
    pr = out["pair"]
    if pr:
        rows += [
            {"key": "kerosene", "ja": "置き換える灯油（期待値）", "en": "Kerosene replaced (expected)",
             "value": round(pr["kerosene_l"] / 1000, 1), "unit": "kL/yr", "tag": "calculated",
             "basis": f"heat delivered / ({KEROSENE_KWH_PER_L:g} kWh/L lower heating value x boiler {P.boiler_eff:.0%}, "
                      "assumptions)"},
            {"key": "fuel_mwh", "ja": "灯油でつくる熱の単価（156.8円/L）", "en": "Cost of heat from kerosene (156.8 yen/L)",
             "value": round(pr["fuel_mwh"][1]), "unit": "yen/MWh", "tag": "calculated",
             "basis": f"156.8 yen/L, Hokkaido, ANRE survey of 2026-11-16 ({URL['kerosene']}) / "
                      f"({KEROSENE_KWH_PER_L:g} kWh/L x {P.boiler_eff:.0%})"},
            {"key": "p_min", "ja": "供給側に必要な熱の価格（下限）", "en": "Heat price the supplier needs (lower end)",
             "value": round(pr["p_min"]), "unit": "yen/MWh", "tag": "calculated",
             "basis": ("supplier's annual cost per MWh delivered: pipe annuity"
                       + (", central heat pump annuity and its electricity" if out["mode"] == "central" else "")
                       + f" (annuity factors {P.crf:.4f} for {P.years} years and {P.crf_hp:.4f} for {P.hp_years} years "
                       f"at {P.rate:.0%}, assumptions); operation and maintenance not included")},
            {"key": "p_max", "ja": "需要家が得をする熱の価格（上限）", "en": "Heat price below which the partner gains (upper end)",
             "value": round(pr["p_max"]), "unit": "yen/MWh", "tag": "calculated",
             "basis": ("partner's avoided kerosene per MWh delivered (expected)"
                       + ("" if out["mode"] == "central" or pr["hp"] == 0 else
                          " minus its heat pump's electricity and annuity"))},
            {"key": "p_mid", "ja": "利益を半分ずつ分ける価格", "en": "Price that splits the gain equally",
             "value": round(pr["p_mid"]), "unit": "yen/MWh", "tag": "calculated",
             "basis": "midpoint of the two ends (Nash bargaining price with equal weights)"},
        ]
    rg = out["regional"]
    if rg["in_plan"]:
        rows.append({"key": "plan_heat", "ja": "共有ネットワークで届く熱（期待値）", "en": "Heat delivered in the shared network (expected)",
                     "value": round(rg["heat"]), "unit": "MWh/yr", "tag": "calculated",
                     "basis": f"regional plan of model v2 ({rg['sites']} sites, {rg['km']:.1f} km of pipe, "
                              "kernel search with HiGHS)"})
    if rg["loss"] is not None:
        rows.append({"key": "plan_loss", "ja": "この相手が地域にもたらす純便益", "en": "Net benefit this partner adds to the region",
                     "value": round(rg["loss"]), "unit": "yen/yr", "tag": "calculated",
                     "basis": "expected net benefit of the regional plan minus that of the same pipes without this "
                              "partner, deliveries re-optimised"})
    for i, r in enumerate(rows, 1):
        r["no"] = i
    return rows


# ------------------------------------------------------------------------------------- formatting
def _esc(s) -> str:
    return _html.escape(str(s), quote=True)


def _num(x, nd: int = 0) -> str:
    return f"{x:,.{nd}f}"


def _yen(x: float, lang: str) -> str:
    if lang == "ja":
        if abs(x) >= 1e8:
            return f"{x / 1e8:,.2f}億円"
        if abs(x) >= 1e4:
            return f"{x / 1e4:,.0f}万円"
        return f"{x:,.0f}円"
    if abs(x) >= 1e8:
        return f"{x / 1e6:,.0f}M yen"
    if abs(x) >= 1e6:
        return f"{x / 1e6:,.1f}M yen"
    return f"{x:,.0f} yen"


def _value(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if isinstance(v, float) and not math.isfinite(v):
            return "—"
        if isinstance(v, float) and v != round(v) and abs(v) < 100:
            return f"{v:,.2f}".rstrip("0").rstrip(".")
        return _num(v)
    return str(v)


def _date(iso: str, lang: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    if lang == "ja":
        return f"{y}年{m}月{d}日"
    return f"{d} {['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][m - 1]} {y}"


CJK = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]")


def _bilingual(text: str, L: int) -> str:
    """'日本語 / English' -> the part for the language; other text unchanged."""
    left, sep, right = str(text).partition(" / ")
    if not sep or not CJK.search(left):
        return str(text)
    return left if L == 0 else right


URL_RE = re.compile(r"https?://[^\s;,)]+[^\s;,).]")


def _sources(rows: list[dict]) -> tuple[list[str], dict[str, int]]:
    urls: list[str] = []
    for r in rows:
        for u in URL_RE.findall(r["basis"]):
            if u not in urls:
                urls.append(u)
    return urls, {u: i + 1 for i, u in enumerate(urls)}


def _basis_html(text: str, refs: dict[str, int]) -> str:
    out, last = [], 0
    for m in URL_RE.finditer(text):
        out.append(_esc(text[last:m.start()]))
        n = refs[m.group(0)]
        out.append(f'<a href="{_esc(m.group(0))}">[{n}]</a>')
        last = m.end()
    out.append(_esc(text[last:]))
    return "".join(out)


# ------------------------------------------------------------------------------------------ figures
class BaseMap:
    """OpenStreetMap layers of out/heat_story/base.json (scripts/export_heat_story.py), decoded once."""

    def __init__(self, base: list[dict]):
        meta = next(r for r in base if r["layer"] == "meta")
        ext, scale = meta["extent"], meta["scale"]

        def dec(seq):
            return np.cumsum(np.asarray(seq, dtype=float).reshape(-1, 2), axis=0) / scale + np.array(ext[:2])

        self.polys = [(r["layer"], dec(ring)) for r in base if r["layer"] in ("sea", "river") for ring in r["rings"]]
        self.lines = [(r["layer"], r.get("class", 0), dec(line)) for r in base if r["layer"] in ("road", "coast", "city")
                      for line in r["lines"]]
        self.labels = [r for r in base if r["layer"] == "label"]
        self.bb = np.array([[a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()] for _, _, a in self.lines])

    def lines_in(self, lon0: float, lat0: float, lon1: float, lat1: float) -> list:
        hit = (self.bb[:, 2] >= lon0) & (self.bb[:, 0] <= lon1) & (self.bb[:, 3] >= lat0) & (self.bb[:, 1] <= lat1)
        return [self.lines[i] for i in np.flatnonzero(hit)]


class _View:
    """Local equirectangular projection fitted to a box of w x h SVG units (4 units per mm)."""

    def __init__(self, pts: np.ndarray, W: float, H: float, fill: float = 0.58, min_km: float = 0.8):
        self.lon0, self.lat0 = float(pts[:, 0].mean()), float(pts[:, 1].mean())
        self.kx, self.ky = 111.32 * math.cos(math.radians(self.lat0)), 110.57
        x, y = self.km(pts[:, 0], pts[:, 1])
        sx, sy = max(float(x.max() - x.min()), min_km), max(float(y.max() - y.min()), min_km)
        w, h = sx / fill, sy / fill
        if w / h < W / H:
            w = h * W / H
        else:
            h = w * H / W
        cx, cy = (float(x.max()) + float(x.min())) / 2, (float(y.max()) + float(y.min())) / 2
        self.x0, self.y0, self.w, self.h, self.W, self.H = cx - w / 2, cy - h / 2, w, h, W, H

    def km(self, lon, lat):
        return (np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * self.ky

    def px(self, lon, lat):
        x, y = self.km(lon, lat)
        return (x - self.x0) / self.w * self.W, self.H - (y - self.y0) / self.h * self.H

    def lonlat_box(self) -> tuple[float, float, float, float]:
        return (self.lon0 + self.x0 / self.kx, self.lat0 + self.y0 / self.ky,
                self.lon0 + (self.x0 + self.w) / self.kx, self.lat0 + (self.y0 + self.h) / self.ky)


def _d(xs, ys) -> str:
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


def map_svg(data: dict, lang: str, base: BaseMap | None = None, network: list | None = None,
            w_mm: float = 96, h_mm: float = 64) -> str:
    """The dedicated route (and the shared network around it) on OpenStreetMap roads, coast and water."""
    W, H = w_mm * 4, h_mm * 4
    route = np.array(data["route"], dtype=float)
    dc, site = data["dc"], data["site"]
    v = _View(np.vstack([route, [[dc["lon"], dc["lat"]], [site["lon"], site["lat"]]]]), W, H)
    L = 0 if lang == "ja" else 1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{w_mm}mm" height="{h_mm}mm" '
             f'role="img" aria-label="{_esc(("導管ルートの地図", "Map of the pipe route")[L])}">',
             f'<defs><clipPath id="clip"><rect width="{W:.0f}" height="{H:.0f}" rx="6"/></clipPath></defs>',
             f'<g clip-path="url(#clip)"><rect width="{W:.0f}" height="{H:.0f}" fill="#F5F3EE"/>']
    if base is not None:
        from shapely import box as sbox
        from shapely.geometry import LineString, Polygon
        frame = sbox(-4, -4, W + 4, H + 4)
        for layer, ring in base.polys:
            xs, ys = v.px(ring[:, 0], ring[:, 1])
            g = Polygon(np.c_[xs, ys]).buffer(0).intersection(frame)
            for geom in getattr(g, "geoms", [g]):
                if geom.is_empty or geom.geom_type != "Polygon":
                    continue
                cx, cy = geom.exterior.xy
                parts.append(f'<path d="{_d(cx, cy)}Z" fill="#D9E6F1"/>')
        lon0, lat0, lon1, lat1 = v.lonlat_box()
        roads: dict = {}
        for layer, cls, line in base.lines_in(lon0, lat0, lon1, lat1):
            xs, ys = v.px(line[:, 0], line[:, 1])
            seg = LineString(np.c_[xs, ys]).intersection(frame) if len(xs) > 1 else None
            if seg is None or seg.is_empty:
                continue
            for geom in getattr(seg, "geoms", [seg]):
                if geom.geom_type != "LineString":
                    continue
                cx, cy = geom.xy
                roads.setdefault((layer, cls), []).append(_d(cx, cy))
        style = {("coast", 0): ('#9AB0C6', 1.2, ""), ("city", 0): ("#C2C8D2", 1.0, ' stroke-dasharray="5 4"')}
        for (layer, cls), ds in sorted(roads.items(), key=lambda kv: (kv[0][0] != "road", kv[0][1])):
            if layer == "road":
                col, wd, extra = "#C4CAD4", [0.5, 0.7, 1.0, 1.4, 1.9][cls], ""
            else:
                col, wd, extra = style.get((layer, 0), ("#C2C8D2", 1.0, ""))
            parts.append(f'<path d="{"".join(ds)}" fill="none" stroke="{col}" stroke-width="{wd}" '
                         f'stroke-linecap="round" stroke-linejoin="round"{extra}/>')
        for r in base.labels:
            x, y = v.px(r["lon"], r["lat"])
            if 30 < x < W - 30 and 14 < y < H - 14:
                italic = ' font-style="italic"' if r["kind"] in ("water", "sea") else ""
                parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="10" fill="#8A93A6" text-anchor="middle"{italic}>'
                             f'{_esc(r["ja"] if L == 0 else r["en"])}</text>')
    for pipe in network or []:
        pts = np.array(pipe["path"], dtype=float)
        xs, ys = v.px(pts[:, 0], pts[:, 1])
        if xs.max() < -10 or xs.min() > W + 10 or ys.max() < -10 or ys.min() > H + 10:
            continue
        parts.append(f'<path d="{_d(xs, ys)}" fill="none" stroke="#E9B48A" stroke-width="{DN_WIDTH.get(pipe["dn"], 2)}" '
                     'stroke-linecap="round" stroke-linejoin="round"/>')
    xs, ys = v.px(route[:, 0], route[:, 1])
    parts.append(f'<path d="{_d(xs, ys)}" fill="none" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" '
                 'stroke-linejoin="round"/>')
    parts.append(f'<path d="{_d(xs, ys)}" fill="none" stroke="{HEAT}" stroke-width="3.6" stroke-linecap="round" '
                 'stroke-linejoin="round"/>')
    for o in data["others"]:
        x, y = v.px(o["lon"], o["lat"])
        if 6 < x < W - 6 and 6 < y < H - 6:
            parts.append(f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" fill="#8A93A6" stroke="#FFFFFF" stroke-width="1.5"/>'
                         f'<text x="{x + 7:.1f}" y="{y + 3.5:.1f}" font-size="10" fill="{MUTED}">{_esc(o["short"][L])}</text>')
    dx, dy = v.px(dc["lon"], dc["lat"])
    sx, sy = v.px(site["lon"], site["lat"])
    parts.append(f'<rect x="{dx - 6:.1f}" y="{dy - 6:.1f}" width="12" height="12" fill="{INK}" stroke="#FFFFFF" stroke-width="2"/>')
    parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="6.5" fill="{GROUP_COLOR[site["group"]]}" stroke="#FFFFFF" stroke-width="2"/>')
    halo = 'stroke="#F5F3EE" stroke-width="3.5" paint-order="stroke"'
    near = abs(dx - sx) < 120 and abs(dy - sy) < 18           # keep the two labels apart

    def label(x, y, text, dy_):
        right = x < W / 2                                        # write toward the middle of the map
        return (f'<text x="{x + (10 if right else -10):.1f}" y="{y + 4 + dy_:.1f}" font-size="12" font-weight="700" '
                f'fill="{INK}" text-anchor="{"start" if right else "end"}" {halo}>{_esc(text)}</text>')

    parts.append(label(dx, dy, dc["short"][L], -10 if near and dy <= sy else 10 if near else 0))
    name = site["name"] if L == 0 else site["name_en"]
    parts.append(label(sx, sy, name, 10 if near and dy <= sy else -10 if near else 0))
    # scale bar, north arrow, legend, credit
    for km in (0.25, 0.5, 1.0, 2.0, 5.0):
        if km / v.w * W >= 0.14 * W:
            break
    sl = km / v.w * W
    parts.append(f'<g transform="translate(14,{H - 16:.0f})" font-size="10" fill="{INK2}">'
                 f'<path d="M0,-5V0H{sl:.1f}V-5" fill="none" stroke="{INK2}" stroke-width="1.4"/>'
                 f'<text x="{sl + 5:.1f}" y="0">{_num(km * 1000) + " m" if km < 1 else f"{km:g} km"}</text></g>')
    parts.append(f'<g transform="translate({W - 18:.0f},20)" fill="{INK2}" font-size="10" text-anchor="middle">'
                 '<path d="M0,-12L5,2L0,-2L-5,2Z"/><text y="14">N</text></g>')
    leg = [(HEAT, 3.6, ("この組の専用管", "Dedicated pipe for this pair")[L])]
    if network:
        leg.append(("#E9B48A", 2.4, ("地域全体の計画の共有導管", "Shared network of the regional plan")[L]))
    lw = 40 + max(len(t) for _, _, t in leg) * (10.2 if L == 0 else 5.6)
    parts.append(f'<g transform="translate(10,10)"><rect width="{lw:.0f}" height="{10 + 14 * len(leg)}" rx="4" '
                 'fill="#FFFFFF" fill-opacity="0.9"/>')
    for i, (col, wd, text) in enumerate(leg):
        y = 12 + 14 * i
        parts.append(f'<path d="M8,{y}H26" stroke="{col}" stroke-width="{wd}" stroke-linecap="round"/>'
                     f'<text x="32" y="{y + 3.5}" font-size="10" fill="{INK}">{_esc(text)}</text>')
    parts.append("</g>")
    if base is not None:
        parts.append(f'<text x="{W - 8:.0f}" y="{H - 8:.0f}" font-size="9" fill="{MUTED}" text-anchor="end">'
                     '© OpenStreetMap contributors</text>')
    parts.append(f'</g><rect width="{W:.0f}" height="{H:.0f}" rx="6" fill="none" stroke="{LINE}" stroke-width="1"/></svg>')
    return "".join(parts)


def _bar(x: float, y: float, w: float, h: float, r: float) -> str:
    """A bar with its top (data end) rounded and its foot square."""
    r = min(r, w / 2, h)
    if h <= 0:
        return ""
    return (f'M{x:.1f},{y + h:.1f}V{y + r:.1f}Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f}H{x + w - r:.1f}'
            f'Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f}V{y + h:.1f}Z')


def chart_svg(demand: list, delivered: list, lang: str, w_mm: float = 82, h_mm: float = 50) -> str:
    """Monthly heat: what the data center delivers (bottom) and what still comes from the boiler (top)."""
    W, H = w_mm * 4, h_mm * 4
    L = 0 if lang == "ja" else 1
    left, right, top, bottom = 40, 6, 34, 22
    pw, ph = W - left - right, H - top - bottom
    ymax = max(max(demand), 1e-9)
    step = 10 ** math.floor(math.log10(ymax / 3))
    for m in (1, 2, 2.5, 5, 10):
        if ymax / (m * step) <= 4:
            step *= m
            break
    top_v = step * math.ceil(ymax / step)
    sy = ph / top_v
    bw = pw / 12
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{w_mm}mm" height="{h_mm}mm" '
             f'role="img" aria-label="{_esc(("月ごとの熱量", "Heat per month")[L])}">']
    k = 0
    while k * step <= top_v + 1e-9:
        y = top + ph - k * step * sy
        parts.append(f'<path d="M{left},{y:.1f}H{W - right}" stroke="{"#B8BFCB" if k == 0 else "#ECEEF2"}" stroke-width="1"/>'
                     f'<text x="{left - 5}" y="{y + 3.5:.1f}" font-size="9.5" fill="{MUTED}" text-anchor="end">{_num(k * step)}</text>')
        k += 1
    months = MONTHS_EN if L == 1 else [str(m) for m in range(1, 13)]
    for t in range(12):
        x = left + t * bw + bw * 0.16
        w = bw * 0.68
        got, need = delivered[t], demand[t]
        rest = max(need - got, 0.0)
        h1 = got * sy
        tip = (f"{months[t]}{'月' if L == 0 else ''}: "
               + (f"需要 {_num(need)} MWh、データセンターから {_num(got)} MWh" if L == 0 else
                  f"demand {_num(need)} MWh, from the data center {_num(got)} MWh"))
        parts.append(f"<g><title>{_esc(tip)}</title>")
        y1 = top + ph - h1
        if rest * sy >= 2.5:
            parts.append(f'<path d="{_bar(x, top + ph - h1 - rest * sy, w, rest * sy - (2 if h1 > 0 else 0), 2.5)}" fill="{REST}"/>')
            parts.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{w:.1f}" height="{h1:.1f}" fill="{HEAT}"/>' if h1 > 0 else "")
        elif h1 > 0:
            parts.append(f'<path d="{_bar(x, y1, w, h1, 2.5)}" fill="{HEAT}"/>')
        parts.append("</g>")
        parts.append(f'<text x="{x + w / 2:.1f}" y="{H - bottom + 13}" font-size="9.5" fill="{MUTED}" text-anchor="middle">'
                     f'{_esc(months[t][0] if L == 1 else months[t])}</text>')
    legend = [(HEAT, ("データセンターの排熱", "From the data center")[L]), (REST, ("ボイラーのまま", "Still from the boiler")[L])]
    x = left
    for col, text in legend:
        parts.append(f'<rect x="{x}" y="6" width="11" height="11" rx="2" fill="{col}"/>'
                     f'<text x="{x + 15}" y="15.5" font-size="10.5" fill="{INK}">{_esc(text)}</text>')
        x += 15 + len(text) * (10.5 if L == 0 else 5.9) + 16
    parts.append(f'<text x="{left - 5}" y="{top - 8}" font-size="9.5" fill="{MUTED}" text-anchor="end">MWh</text></svg>')
    return "".join(parts)


def price_svg(pr: dict, lang: str, w_mm: float = 84, h_mm: float = 24) -> str:
    """The range of heat prices that leaves both sides better off, against the cost of heat from kerosene."""
    W, H = w_mm * 4, h_mm * 4
    L = 0 if lang == "ja" else 1
    lo, hi, fuel = pr["p_min"], pr["p_max"], pr["fuel_mwh"][1]
    vmax = max(fuel, hi, lo) * 1.08
    sx = (W - 20) / vmax

    def X(v):
        return 10 + max(v, 0) * sx

    y = 40
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{w_mm}mm" height="{h_mm}mm" '
             f'role="img" aria-label="{_esc(("熱の価格の範囲", "Range of heat prices")[L])}">',
             f'<path d="M10,{y}H{W - 10}" stroke="{LINE}" stroke-width="6" stroke-linecap="round"/>']
    if hi > lo:
        parts.append(f'<path d="M{X(lo):.1f},{y}H{X(hi):.1f}" stroke="{HEAT}" stroke-width="10" stroke-linecap="butt"/>')
        mid = (lo + hi) / 2
        parts.append(f'<path d="M{X(mid):.1f},{y - 8}l6,8l-6,8l-6,-8Z" fill="{INK}"/>')
    unit = ("円/MWh", "yen/MWh")[L]
    for v_, text, dy in [(lo, ("供給側に必要", "supplier needs")[L], -14), (hi, ("需要家が得をする上限", "partner gains below")[L], 26)]:
        x = X(v_)
        anchor = "start" if x < 0.22 * W else "end" if x > 0.78 * W else "middle"
        parts.append(f'<path d="M{x:.1f},{y - 7}V{y + 7}" stroke="{INK}" stroke-width="1.6"/>'
                     f'<text x="{x:.1f}" y="{y + dy}" font-size="9.5" fill="{INK2}" text-anchor="{anchor}">'
                     f'{_esc(text)} {_num(v_)}</text>')
    parts.append(f'<path d="M{X(fuel):.1f},{y - 12}V{y + 12}" stroke="{ACCENT}" stroke-width="1.4" stroke-dasharray="3 2"/>'
                 f'<path d="M10,{H - 6}h14" stroke="{ACCENT}" stroke-width="1.4" stroke-dasharray="3 2"/>'
                 f'<text x="29" y="{H - 2.5}" font-size="9.5" fill="{ACCENT}">'
                 f'{_esc(("灯油でつくる熱（156.8円/L）", "heat from kerosene (156.8 yen/L)")[L])} {_num(fuel)} {_esc(unit)}</text>'
                 + (f'<path d="M{W - 112},{H - 9}l4,4l-4,4l-4,-4Z" fill="{INK}"/><text x="{W - 104}" y="{H - 2.5}" font-size="9.5" '
                    f'fill="{INK2}">{_esc(("利益を半分ずつ", "equal split")[L])}</text>' if hi > lo else "")
                 + "</svg>")
    return "".join(parts)


# ------------------------------------------------------------------------------------------- page
CSS = """
@page { size: A4; margin: 0; }
:root { --ink: #14213D; --ink2: #4A5568; --muted: #6B7486; --line: #DADFE7; --soft: #F6F3EC;
        --accent: #B3541E; --heat: #E07B39; --paper: #FFFFFF; --bg: #E8EBF0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 9pt/1.45 Inter, "Noto Sans JP", "Hiragino Sans", "Yu Gothic UI", Meiryo, Arial, sans-serif; }
.page { width: 210mm; height: 297mm; margin: 6mm auto; padding: 11mm 13mm 0; background: var(--paper);
        box-shadow: 0 0.6mm 3mm rgba(20, 33, 61, .18); position: relative; overflow: hidden; }
.page.sheet { height: auto; min-height: 297mm; overflow: visible; padding-top: 9mm; padding-bottom: 10mm; }
@page sheet { size: A4; margin: 9mm 0 8mm; }
@media print { body { background: none; } .page { margin: 0; box-shadow: none; break-after: page; }
               .page.sheet { page: sheet; padding-top: 0; padding-bottom: 0; min-height: 0; } }
a { color: var(--accent); text-decoration: none; }
.top { display: flex; justify-content: space-between; font-size: 7.2pt; letter-spacing: .08em; text-transform: uppercase;
       color: var(--accent); font-weight: 700; }
h1 { font-family: "Space Grotesk", Inter, "Noto Sans JP", sans-serif; font-size: 16.5pt; line-height: 1.18; margin: 2.4mm 0 1.8mm; }
h2 { font-family: "Space Grotesk", Inter, "Noto Sans JP", sans-serif; font-size: 10.5pt; margin: 0 0 1.4mm; }
.lede { font-size: 9.6pt; color: var(--ink2); margin: 0 0 3.2mm; }
.kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 2mm; margin-bottom: 3.6mm; }
.kpi { background: var(--soft); border-radius: 2mm; padding: 2.2mm 2.4mm 2mm; }
.kpi .v { font-family: "Space Grotesk", Inter, "Noto Sans JP", sans-serif; font-size: 13pt; font-weight: 700;
          color: var(--accent); line-height: 1.1; white-space: nowrap; }
.kpi .v small { font-size: 7.5pt; font-weight: 600; margin-left: .6mm; }
.kpi .l { font-size: 7.4pt; color: var(--ink); margin-top: .8mm; line-height: 1.25; }
.kpi .s { font-size: 6.6pt; color: var(--muted); margin-top: .5mm; line-height: 1.25; }
.figs { display: grid; grid-template-columns: 96mm 1fr; gap: 4mm; align-items: start; }
figure { margin: 0; }
figcaption { font-size: 7.2pt; color: var(--muted); margin-top: 1mm; line-height: 1.35; }
.boxes { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; margin-top: 3mm; }
.box { border-top: 0.6mm solid var(--line); padding-top: 2mm; }
.box.hot { border-top-color: var(--heat); }
.box p { margin: 0 0 1.4mm; }
.note { font-size: 7.2pt; color: var(--muted); }
ul.check { margin: 0; padding-left: 4mm; columns: 2; column-gap: 7mm; }
ul.check li { margin: 0 0 .9mm; break-inside: avoid; }
footer { position: absolute; left: 13mm; right: 13mm; bottom: 7mm; font-size: 6.6pt; color: var(--muted);
         border-top: 0.3mm solid var(--line); padding-top: 1.4mm; line-height: 1.4; }
table { width: 100%; border-collapse: collapse; }
table.calc { font-size: 6.8pt; line-height: 1.3; table-layout: fixed; }
table.calc th { text-align: left; font-weight: 700; color: var(--ink2); border-bottom: 0.4mm solid var(--ink); padding: 1mm 1.2mm; }
table.calc td { border-bottom: 0.2mm solid var(--line); padding: .4mm 1.2mm; vertical-align: top; }
table.calc td.no { color: var(--muted); width: 5mm; }
td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.txt { text-align: right; overflow-wrap: anywhere; }
td.basis { overflow-wrap: anywhere; }
td.basis { color: var(--ink2); }
.tag { display: inline-block; border-radius: 1mm; padding: 0 1.2mm; font-size: 6.4pt; font-weight: 700; white-space: nowrap; }
.tag.source { background: #E1F0E6; color: #1F6B40; }
.tag.assumption { background: #FBE9D6; color: #8A4A12; }
.tag.calculated { background: #E6EAF2; color: #33415C; }
.legend-tags { font-size: 7pt; color: var(--ink2); margin: 0 0 1.4mm; }
ol.sources { font-size: 6.4pt; color: var(--ink2); padding-left: 5mm; margin: 1mm 0 0; word-break: break-all; columns: 2; column-gap: 6mm; }
table.scen { font-size: 6.9pt; margin: 1mm 0 2mm; }
table.scen th, table.scen td { border-bottom: 0.2mm solid var(--line); padding: .5mm 1.2mm; text-align: right; }
table.scen th:first-child, table.scen td:first-child { text-align: left; }
"""


def _kpis(data: dict, lang: str) -> list[tuple[str, str, str, list[int]]]:
    """(value html, label, sub-label, calculation-sheet numbers) for the six cards."""
    L = 0 if lang == "ja" else 1
    pr = data["pair"]
    no = {r["key"]: r["no"] for r in data["rows"]}
    sav = pr["saving_w"]
    return [
        (f'{_num(pr["heat"])}<small>MWh</small>', ("年間に届く熱", "Heat delivered a year")[L],
         (f"需要の{pr['share']:.0%}", f"{pr['share']:.0%} of the demand")[L], [no["heat"]]),
        (f'{_num(pr["kerosene_l"] / 1000)}<small>kL</small>', ("置き換える灯油（年）", "Kerosene replaced a year")[L],
         (f"ドラム缶{_num(pr['kerosene_l'] / 200)}本分", f"{_num(pr['kerosene_l'] / 200)} drums of 200 L")[L], [no["kerosene"]]),
        (_yen(pr["value"], lang), ("年間の節約（期待値）", "Saving a year (expected)")[L],
         (f"シナリオにより{_yen(min(sav), lang)}〜{_yen(max(sav), lang)}",
          f"{_yen(min(sav), lang)} to {_yen(max(sav), lang)} by scenario")[L], [no["saving"]]),
        (_yen(pr["capex"], lang), ("投資額", "Investment")[L],
         (f"導管{_yen(pr['pipe'], lang)}＋ヒートポンプ{_yen(pr['hp'], lang)}" if pr["hp"] > 0 else "導管のみ（ヒートポンプ不要）",
          f"pipe {_yen(pr['pipe'], lang)} + heat pump {_yen(pr['hp'], lang)}" if pr["hp"] > 0 else "pipe only (no heat pump)")[L],
         [no["capex"], no["hp"]]),
        ((f'{pr["payback"]:.1f}<small>{("年", "years")[L]}</small>' if pr["payback"] else "—"),
         ("単純回収年数", "Simple payback")[L], ("投資額÷年間の節約", "investment / annual saving")[L], [no["payback"]]),
        (f'{_num(pr["co2"])}<small>t</small>', ("CO₂削減（年）", "CO₂ avoided a year")[L],
         ("灯油の削減分から", "from the kerosene not burned")[L], [no["co2"]]),
    ]


def _texts(data: dict, lang: str) -> dict:
    L = 0 if lang == "ja" else 1
    dc, site, pr, rg = data["dc"], data["site"], data["pair"], data["regional"]
    dcn, dcs = (dc["name"], dc["name_en"])[L], dc["short"][L]
    sn = (site["name"], site["name_en"])[L]
    t: dict = {}
    t["eyebrow"] = ("Warm Ishikari・検討のための提案書（たたき台）", "Warm Ishikari · Draft proposal for discussion")[L]
    t["title"] = (f"{dcn}の排熱を{sn}へ", f"Waste heat from {dcn} for {sn}")[L]
    if pr:
        km = pr["dist_m"] / 1000
        if L == 0:
            t["lede"] = (f"公道沿いに{km:.1f} kmの導管（DN{pr['dn']}）を引くと、{dcs}から{sn}へ年に約{_num(pr['heat'])} MWhの熱を送れます。"
                         f"灯油にして年{_num(pr['kerosene_l'] / 1000)} kL分です。")
            t["lede"] += (f"投資額{_yen(pr['capex'], 'ja')}は約{pr['payback']:.1f}年で回収できる見込みです。" if pr["net"] > 0 else
                          f"ただし、この組だけでは節約額が導管の年経費に届きません（投資額{_yen(pr['capex'], 'ja')}）。")
        else:
            t["lede"] = (f"A DN{pr['dn']} pipe of {km:.1f} km along public roads would bring about {_num(pr['heat'])} MWh of heat a "
                         f"year from {dcs} to {sn}, replacing {_num(pr['kerosene_l'] / 1000)} kL of kerosene a year. ")
            t["lede"] += (f"The investment of {_yen(pr['capex'], 'en')} pays back in about {pr['payback']:.1f} years." if pr["net"] > 0 else
                          f"On its own, though, the saving does not cover the pipe's annual cost (investment {_yen(pr['capex'], 'en')}).")
    else:
        t["lede"] = (f"{sn}へ{dcs}から専用の導管を引くことはできません（距離または熱量が導管の上限を超えます）。共有ネットワークでのみ届けられます。",
                     f"A dedicated pipe from {dcs} cannot serve {sn} (too far, or more heat than the largest pipe carries); "
                     "only a shared network can.")[L]
    # the regional plan
    n_other = rg["dc_sites"] - (1 if rg["served_by"] == dc["key"] else 0)
    if rg["in_plan"] and rg["served_by"] == dc["key"]:
        loss = rg["loss"]
        t["network"] = (
            f"候補{data['candidates']}か所とデータセンター{data['data_centers']}か所をまとめて最適化した地域の計画では、"
            f"{sn}は{dcs}から他の{n_other}か所と導管を共有して熱を受け取り、年に約{_num(rg['heat'])} MWhが届きます。"
            + (f"{sn}が加わることで、地域全体の純便益（期待値）は年{_yen(loss, 'ja')}増えます（導管は同じまま、熱の配分を最適化し直して比較）。"
               if loss is not None else ""),
            f"In the regional plan, which optimizes all {data['candidates']} candidate sites and the {data['data_centers']} "
            f"data centers together, {sn} shares pipes from {dcs} with {n_other} other sites and receives about "
            f"{_num(rg['heat'])} MWh a year. "
            + (f"With {sn}, the region's expected net benefit is {_yen(loss, 'en')} a year higher than without it "
               "(same pipes, heat re-allocated)." if loss is not None else ""))[L]
    elif rg["in_plan"]:
        other = rg["served_by_short"][L]
        t["network"] = (f"地域の計画では、{sn}には{other}が熱を送ります。{dcs}から送ると、その供給と競合します。",
                        f"In the regional plan, {other} supplies {sn}; a pipe from {dcs} would compete with that supply.")[L]
    else:
        t["network"] = (f"地域の計画は{sn}をつないでいません。ほかの需要家と組み合わせると、熱と導管にもっと良い使い道があるためです。",
                        f"The regional plan does not connect {sn}: combined with the other sites, the heat and the pipes "
                        "have better uses.")[L]
    t["network"] += (f"（地域全体：{rg['sites']}か所、導管{rg['km']:.1f} km、純便益 年{_yen(rg['net'], 'ja')}）",
                     f" (Whole region: {rg['sites']} site{'s' if rg['sites'] != 1 else ''}, {rg['km']:.1f} km of pipe, "
                     f"net benefit {_yen(rg['net'], 'en')} a year.)")[L]
    if pr:
        owner = ("" if data["mode"] == "central" else
                 ("ヒートポンプは需要家が持つ前提です。" if pr["hp"] > 0 else "ヒートポンプは不要です（排熱をそのまま使えます）。",
                  "The partner owns its heat pump. " if pr["hp"] > 0 else "No heat pump is needed (the heat is used directly). ")[L])
        if pr["p_max"] > pr["p_min"]:
            t["price"] = (
                f"導管を{dcs}（または熱供給の事業者）が持ち、{sn}が熱を買う場合、1 MWhあたり{_num(pr['p_min'])}円から"
                f"{_num(pr['p_max'])}円のあいだの価格なら双方が得をします。{owner}利益を半分ずつ分けると{_num(pr['p_mid'])}円/MWhで、"
                f"灯油でつくる熱（156.8円/L）の{_num(pr['fuel_mwh'][1])}円/MWhより安くなります。",
                f"If {dcs} (or a heat company) owns the pipe and {sn} buys the heat, any price between {_num(pr['p_min'])} and "
                f"{_num(pr['p_max'])} yen per MWh leaves both better off. {owner}Splitting the gain equally gives "
                f"{_num(pr['p_mid'])} yen/MWh, against {_num(pr['fuel_mwh'][1])} yen/MWh for heat from kerosene at 156.8 yen/L.")[L]
        else:
            t["price"] = (
                f"この組だけでは、双方が得をする価格はありません。導管の年経費が1 MWhあたり{_num(pr['p_min'])}円かかるのに対し、"
                f"{sn}にとっての熱の価値は{_num(pr['p_max'])}円です。ほかの需要家と導管を共有するか、補助が必要です。",
                f"As a pair, no price leaves both sides better off: the pipe costs {_num(pr['p_min'])} yen per MWh delivered, while "
                f"the heat is worth {_num(pr['p_max'])} yen per MWh to {sn}. The pair needs a shared pipe or support.")[L]
        t["price_note"] = (f"年経費は割引率{data['assumptions']['rate']:.0%}、導管{data['assumptions']['years']}年・ヒートポンプ"
                           f"{data['assumptions']['hp_years']}年の年賦。運転・保守費は含みません。",
                           f"Annuities at {data['assumptions']['rate']:.0%} over {data['assumptions']['years']} years (pipe) and "
                           f"{data['assumptions']['hp_years']} years (heat pump); operation and maintenance not included.")[L]
    a = data["assumptions"]
    checks = [
        (f"{dcs}と：回収できる排熱の量・温度・時期（ここではIT負荷の{a['recovery']:.0%}を約{a['waste_c']:g}℃で回収と仮定）",
         f"With {dcs}: how much heat can be recovered, at what temperature and when (assumed: {a['recovery']:.0%} of the IT "
         f"load at about {a['waste_c']:g} °C)"),
        (f"{sn}と：実際の燃料使用量と暖房の温度（ここでは年{_num(site['annual_mwh'])} MWh、{site['supply_c']:g}℃と仮定）",
         f"With {sn}: actual fuel use and heating temperatures (assumed: {_num(site['annual_mwh'])} MWh a year at "
         f"{site['supply_c']:g} °C)"),
        ("石狩市・道路管理者と：公道での導管ルートと占用、冬期の工事",
         "With the city and road authorities: the route along public roads, road-occupancy permits and winter works"),
        ("両者で：熱の価格、契約期間、導管の所有、バックアップの熱源",
         "Between the two parties: heat price, contract length, ownership of the pipe and back-up heating"),
    ]
    if site["assumed"]:
        checks.insert(0, (f"{sn}は仮定の候補地で、既存の施設ではありません", f"{sn} is an assumed site, not an existing facility"))
    if dc["status"] == "planned":
        checks.insert(0, (f"{dcs}は計画中で、まだ稼働していません", f"{dcs} is planned and not yet operating"))
    t["checks"] = [c[L] for c in checks]
    sc = data["scenarios"]
    t["footer"] = (
        f"{_date(data['date'], 'ja')}作成。Warm Ishikari（{REPO}、MITライセンス）のモデルv2、方式：{data['mode_text'][0]}。"
        f"数値は{len(sc)}つのシナリオ（IT負荷 低・高 × 灯油 115・156.8円/L、各{sc[0]['prob']:.0%}）の期待値。"
        "見積りではなく、検討のための試算です。地図データ © OpenStreetMap contributors（ODbL）。",
        f"Prepared {_date(data['date'], 'en')} with Warm Ishikari ({REPO}, MIT license), model v2, {data['mode_text'][1].lower()}. "
        f"Figures are expected values over {len(sc)} scenarios (IT load low or high × kerosene 115 or 156.8 yen/L, "
        f"{sc[0]['prob']:.0%} each). Estimates for discussion, not a quotation. Map data © OpenStreetMap contributors (ODbL).")[L]
    return t


def render_html(data: dict, lang: str = "en", base: BaseMap | None = None, network: list | None = None) -> str:
    """A printable A4 proposal (page 1) and its calculation sheet (page 2) as one self-contained HTML page."""
    L = 0 if lang == "ja" else 1
    t = _texts(data, lang)
    pr = data["pair"]
    rows = data["rows"]
    urls, refs = _sources(rows)
    month = pr["month"] if pr else data["regional"]["month"]
    p1 = [f'<section class="page"><div class="top"><span>{_esc(t["eyebrow"])}</span><span>{_esc(_date(data["date"], lang))}</span></div>',
          f'<h1>{_esc(t["title"])}</h1><p class="lede">{_esc(t["lede"])}</p>']
    if pr:
        p1.append('<div class="kpis">')
        for v, label, sub, nos in _kpis(data, lang):
            ref = ", ".join(f"#{n}" for n in nos)
            p1.append(f'<div class="kpi"><div class="v">{v}</div><div class="l">{_esc(label)}</div>'
                      f'<div class="s">{_esc(sub)} · {_esc(("計算表", "sheet")[L])} {ref}</div></div>')
        p1.append("</div>")
    cap_map = ("地図：専用管は道路沿いの最短経路。共有導管は地域全体の計画で建設される区間。",
               "Map: the dedicated pipe follows the shortest road path; the shared network is the regional plan's pipes.")[L]
    share = f"{pr['share']:.0%}" if pr else "—"
    cap_chart = (f"月ごとの熱量（期待値）。冬に多く、夏に少ない。データセンターの排熱で需要の{share}をまかないます。",
                 f"Heat per month (expected). The demand peaks in winter; the data center's heat covers {share} of it.")[L]
    p1.append(f'<div class="figs"><figure>{map_svg(data, lang, base, network)}<figcaption>{_esc(cap_map)}</figcaption></figure>'
              f'<figure><h2>{_esc(("月ごとの熱", "Heat per month")[L])}</h2>{chart_svg(data["demand_month"], month, lang)}'
              f'<figcaption>{_esc(cap_chart)}</figcaption></figure></div>')
    p1.append('<div class="boxes">')
    p1.append(f'<div class="box"><h2>{_esc(("共有ネットワークでは", "In a shared network")[L])}</h2><p>{_esc(t["network"])}</p></div>')
    if pr:
        p1.append(f'<div class="box hot"><h2>{_esc(("双方が得をする熱の価格", "A heat price that works for both")[L])}</h2>'
                  f'<p>{_esc(t["price"])}</p>{price_svg(pr, lang)}<p class="note">{_esc(t["price_note"])}</p></div>')
    p1.append("</div>")
    p1.append(f'<div class="box" style="margin-top:3mm"><h2>{_esc(("決める前に確かめること", "Before a decision, confirm")[L])}</h2>'
              '<ul class="check">' + "".join(f"<li>{_esc(c)}</li>" for c in t["checks"]) + "</ul></div>")
    p1.append(f'<footer>{_esc(t["footer"])}</footer></section>')
    # page 2: the calculation sheet
    p2 = [f'<section class="page sheet"><div class="top"><span>{_esc(t["eyebrow"])}</span><span>{_esc(("計算表", "Calculation sheet")[L])}</span></div>',
          f'<h1 style="font-size:13pt;margin-top:1.6mm">{_esc(("数字の根拠", "Where every number comes from")[L])}</h1>',
          '<p class="legend-tags">'
          + _esc(("すべての数字に印を付けています：", "Every number is marked: ")[L])
          + " ".join(f'<span class="tag {k}">{_esc(v[L])}</span> {_esc(d_[L])}' for k, v, d_ in [
              ("source", TAGS["source"], ("公表資料", "published source")),
              ("assumption", TAGS["assumption"], ("仮定（確認が必要）", "assumption, to be confirmed")),
              ("calculated", TAGS["calculated"], ("上の値からの計算", "calculated from the others"))]) + "</p>",
          '<table class="calc"><colgroup><col style="width:5mm"><col style="width:36mm"><col style="width:27mm">'
          '<col style="width:13mm"><col style="width:17mm"><col></colgroup><thead><tr><th>#</th><th>'
          + _esc(("項目", "Item")[L]) + '</th><th style="text-align:right">'
          + _esc(("値", "Value")[L]) + "</th><th>" + _esc(("単位", "Unit")[L]) + "</th><th>" + _esc(("種類", "Type")[L])
          + "</th><th>" + _esc(("根拠", "Basis")[L]) + "</th></tr></thead><tbody>"]
    for r in rows:
        val = r["value"]
        cls = "num" if isinstance(val, (int, float)) or re.fullmatch(r"[\d.,/ ]+|DN\d+", str(val)) else "txt"
        p2.append(f'<tr><td class="no">{r["no"]}</td><td>{_esc(r["ja"] if L == 0 else r["en"])}</td>'
                  f'<td class="{cls}">{_esc(_bilingual(_value(val), L))}</td><td>{_esc(r["unit"])}</td>'
                  f'<td><span class="tag {r["tag"]}">{_esc(TAGS[r["tag"]][L])}</span></td>'
                  f'<td class="basis">{_basis_html(_bilingual(r["basis"], L) if r["key"] in ("dc", "user") else r["basis"], refs)}</td></tr>')
    p2.append("</tbody></table>")
    p2.append(f'<h2 style="margin-top:2mm">{_esc(("出典", "Sources")[L])}</h2><ol class="sources">'
              + "".join(f'<li><a href="{_esc(u)}">{_esc(u)}</a></li>' for u in urls) + "</ol>")
    model = f"{REPO}/blob/main/docs/formulations/heat-model.md"
    p2.append('<p class="note" style="margin-top:1.2mm">'
              + _esc(("モデルの数式と全パラメータ：", "Model and every parameter: ")[L])
              + f'<a href="{model}">{_esc(model)}</a></p></section>')
    head = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{_esc(t["title"])}</title>'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Noto+Sans+JP:wght@400;700'
            '&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">'
            f"<style>{CSS}</style></head><body>")
    return head + "".join(p1) + "".join(p2) + "</body></html>"
