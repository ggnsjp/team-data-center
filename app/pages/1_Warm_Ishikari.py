"""Warm Ishikari: data-center waste heat for the town (idea 17), on Ishikari's real map.

A page of the main app (uv run streamlit run app/streamlit_app.py). The language comes from the
app-level switch (session key app_lang), not from a control on this page.
"""
from __future__ import annotations

import math

import altair as alt
import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dcopt.common.geo import paths
from dcopt.heat.v1 import (JMA_SOURCE, KINDS, MONTHS_EN, MONTHS_JA, Assumptions, design,
                         ishikari_sites, pairwise, standalone_and_shared)
from dcopt.common.style import FONT, GRID, INK, INK2, SLOTS, SURFACE
from dcopt.common.style import GSI_ATTR, GSI_PALE

lang = st.session_state.get("app_lang", "日本語")
ja = lang == "日本語"

KIND_ORDER = ["greenhouse", "new_greenhouse", "aquaculture", "onsen", "pool", "hospital", "school", "snow"]
KIND_COLOUR = dict(zip(KIND_ORDER, SLOTS))        # fixed palette order, one colour per kind
ASSUMED = {"new_greenhouse", "aquaculture", "snow"}


def pick(a, b):
    return a if ja else b


@st.cache_resource(show_spinner=False)
def load_sites():
    return ishikari_sites()


@st.cache_resource(show_spinner=False)
def solve(A: Assumptions, assumed: bool, k: int):
    dc, sites = load_sites()
    kinds = set(KIND_ORDER) if assumed else set(KIND_ORDER) - ASSUMED
    return design(dc, sites, A, k=k, kinds=kinds, time_limit=60), pairwise(dc, sites, A, kinds=kinds)


with st.sidebar:
    st.subheader(pick("前提（すべて仮定・変更可）", "Assumptions (all adjustable)"))
    it = st.slider(pick("データセンターのIT負荷（MW）", "Data-center IT load (MW)"), 2, 50, 10, 1, key="it_load")
    rec = st.slider(pick("回収できる廃熱の割合", "Share of heat recovered"), 0.3, 0.9, 0.6, 0.05, key="recovery")
    cop = st.slider(pick("ヒートポンプのCOP", "Heat pump COP"), 2.5, 6.0, 4.0, 0.1, key="hp_cop")
    kero = st.slider(pick("灯油価格（円/L）", "Kerosene (yen/L)"), 70, 170, 115, 5, key="kerosene")
    power = st.slider(pick("電気料金（円/kWh）", "Electricity (yen/kWh)"), 10, 40, 25, 1, key="power_price")
    pipe = st.slider(pick("導管の工事費（万円/m）", "Pipe cost (10k yen per m)"), 3, 30, 10, 1, key="pipe_cost")
    years = st.slider(pick("償却年数", "Lifetime (years)"), 15, 40, 30, 5, key="lifetime")
    rate = st.slider(pick("割引率（%）", "Discount rate (%)"), 0.0, 8.0, 3.0, 0.5, key="discount_rate")
    renew = st.toggle(pick("ヒートポンプは再エネ電力", "Heat pumps on renewable power"), value=True, key="renewable")
    assumed = st.toggle(pick("仮定の候補地も含める（温室新設・陸上養殖・融雪）", "Include assumed sites"), value=True, key="assumed_sites")
    k = st.select_slider(pick("候補の導管（近い順に何本）", "Candidate pipes per site"), options=[2, 3, 4], value=3, key="k_pipes")

A = Assumptions(it_load_mw=float(it), recovery=float(rec), cop=float(cop), kerosene_yen_l=float(kero),
                power_yen_kwh=float(power), pipe_yen_m=float(pipe) * 10_000, years=int(years), rate=rate / 100,
                renewable_power=renew)


with st.spinner(pick("石狩市の地図と施設を読み込み中…", "Loading Ishikari's map and facilities…")):
    dc, _ = load_sites()
with st.spinner(pick("熱導管ネットワークを最適化中…", "Optimizing the heat network…")):
    opt, pw = solve(A, assumed, k)

st.title("Warm Ishikari · " + pick("データセンターの排熱を、まちの熱に", "Data-center heat for the town"))
st.caption(pick("石狩市のデータセンターの廃熱を、温室・病院・プール・学校・融雪へ。どこに導管を引けば最も得かを、"
                "実際の道路網と月別の熱需要で最適化します。",
                "Waste heat from Ishikari's data center to greenhouses, hospitals, pools, schools and snow melting. "
                "Which pipes pay off is optimized on the real road network with monthly heat demand."))

c = st.columns(6)
c[0].metric(pick("つながる需要家", "Users connected"), f"{len(opt.connected)}", f"{len(opt.connected) - len(pw.connected):+d}")
c[1].metric(pick("供給熱量（MWh/年）", "Heat delivered (MWh/yr)"), f"{opt.delivered:,.0f}",
            f"{opt.delivered - pw.delivered:+,.0f}")
c[2].metric(pick("導管（km）", "Pipes (km)"), f"{opt.pipe_m / 1000:.1f}", f"{(opt.pipe_m - pw.pipe_m) / 1000:+.1f}",
            delta_color="off")
c[3].metric(pick("年間の純便益（百万円）", "Net benefit (M yen/yr)"), f"{opt.annual_net / 1e6:,.1f}",
            f"{(opt.annual_net - pw.annual_net) / 1e6:+,.1f}")
c[4].metric(pick("回収年数", "Payback (years)"), f"{opt.payback_years:.1f}",
            f"{opt.payback_years - pw.payback_years:+.1f}", delta_color="inverse")
c[5].metric(pick("CO2削減（t/年）", "CO2 cut (t/yr)"), f"{opt.co2_t:,.0f}", f"{opt.co2_t - pw.co2_t:+,.0f}")
st.caption(pick(f"差分は「1件ずつ採算順に上位5件を選ぶ」方法との比較。投資額 {opt.capex / 1e8:,.1f} 億円、"
                f"最適化 {opt.seconds:.1f} 秒（{opt.status.split('.')[0]}）。",
                f"Deltas against picking the top five users one by one. Investment {opt.capex / 1e8:,.1f} "
                f"hundred-million yen; optimized in {opt.seconds:.1f} s."))

left, right = st.columns([7, 5], gap="medium")
with left:
    view = st.radio(pick("地図に表示", "Show on the map"),
                    [pick("最適化したネットワーク", "Optimized network"), pick("ペアの採算順で上位5件", "Top five pairs")],
                    horizontal=True, key="heat_view")
    shown = opt if view.startswith(("最適", "Optim")) else pw
    nodes = [dc] + shown.sites
    m = folium.Map(location=[dc.lat - 0.01, dc.lon + 0.03], zoom_start=12, tiles=None, control_scale=True)
    folium.TileLayer(GSI_PALE, attr=GSI_ATTR, name=pick("地理院 淡色", "GSI pale")).add_to(m)
    p = paths("ishikari")
    import geopandas as gpd
    folium.GeoJson(gpd.read_file(p["boundary"]), name=pick("石狩市（南部）", "Ishikari (south)"),
                   style_function=lambda f: {"color": "#222", "weight": 2, "fillOpacity": 0}).add_to(m)
    top = max(shown.edge_flow.values(), default=1.0)
    for (a, b, metres) in shown.edges:
        flow = shown.edge_flow.get((a, b), 0.0)
        folium.PolyLine(shown.paths[a, b], color="#c0392b", weight=2 + 8 * math.sqrt(flow / top), opacity=0.85,
                        tooltip=pick(f"導管 {metres / 1000:.2f} km・年 {flow:,.0f} MWh",
                                     f"Pipe {metres / 1000:.2f} km, {flow:,.0f} MWh/yr")).add_to(m)
    connected = set(shown.connected)
    for i, s in enumerate(shown.sites):
        kja, ken, _, _ = KINDS[s.kind]
        served = shown.served[i].sum()
        folium.CircleMarker(
            [s.lat, s.lon], radius=4 + 2.2 * math.sqrt(s.annual_mwh / 250), color=KIND_COLOUR[s.kind],
            weight=2, fill=True, fill_color=KIND_COLOUR[s.kind], fill_opacity=0.9 if i in connected else 0.15,
            tooltip=(f"{s.name if ja else s.name_en}<br>{kja if ja else ken}<br>"
                     + pick(f"需要 {s.annual_mwh:,.0f} MWh/年・供給 {served:,.0f} MWh/年",
                            f"Demand {s.annual_mwh:,.0f} MWh/yr, served {served:,.0f}")
                     + f"<br>{s.source}")).add_to(m)
    folium.Marker([dc.lat, dc.lon], icon=folium.Icon(color="black", icon="flash"),
                  tooltip=pick(f"{dc.name}（熱源）", f"{dc.name_en} (heat source)")).add_to(m)
    components.html(m.get_root().render(), height=620)
    st.caption(pick("塗りつぶし＝つながる、薄い＝今回はつながない。円の大きさ＝年間の熱需要。赤い線＝導管（太さ＝熱量）。",
                    "Filled: connected; faint: not connected. Circle size: annual heat demand. Red: pipes "
                    "(width = heat carried)."))

with right:
    st.markdown("**" + pick("月別の熱の需給", "Heat by month") + "**")
    rows = []
    for i, s in enumerate(opt.sites):
        for t in range(12):
            if opt.served[i, t] > 1e-6:
                rows.append({"month": t, "kind": KINDS[s.kind][0 if ja else 1], "mwh": opt.served[i, t]})
    df = pd.DataFrame(rows)
    deliverable = [w / (1 - 1 / A.cop) for w in opt.waste_heat]
    demand = [sum(s.monthly()[t] for s in opt.sites) for t in range(12)]
    month_labels = MONTHS_JA if ja else MONTHS_EN
    kinds_present = [KINDS[k][0 if ja else 1] for k in KIND_ORDER if any(s.kind == k for s in opt.sites)]
    colours = [KIND_COLOUR[k] for k in KIND_ORDER if any(s.kind == k for s in opt.sites)]
    df["label"] = df["month"].map(lambda t: month_labels[t])
    bars = alt.Chart(df).mark_bar(size=18, stroke=SURFACE, strokeWidth=1).encode(
        x=alt.X("label:N", sort=month_labels, title=None, axis=alt.Axis(labelColor=INK2, labelAngle=0)),
        y=alt.Y("sum(mwh):Q", title="MWh", axis=alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2)),
        color=alt.Color("kind:N", sort=kinds_present, scale=alt.Scale(domain=kinds_present, range=colours),
                        title=pick("供給先", "Delivered to"), legend=alt.Legend(orient="bottom", columns=2)),
        tooltip=[alt.Tooltip("label:N", title=pick("月", "Month")), alt.Tooltip("kind:N", title=pick("種類", "Type")),
                 alt.Tooltip("sum(mwh):Q", title="MWh", format=",.0f")])
    lines = pd.DataFrame({"label": month_labels * 2,
                          "mwh": deliverable + demand,
                          "series": [pick("供給できる熱（廃熱＋ヒートポンプ）", "Heat available")] * 12
                          + [pick("候補全体の需要", "Demand of all candidates")] * 12})
    line = alt.Chart(lines).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=36, filled=True)).encode(
        x=alt.X("label:N", sort=month_labels), y="mwh:Q",
        strokeDash=alt.StrokeDash("series:N", title=None, legend=alt.Legend(orient="bottom")),
        color=alt.value(INK), tooltip=[alt.Tooltip("series:N"), alt.Tooltip("mwh:Q", format=",.0f")])
    st.altair_chart((bars + line).properties(height=360).configure(background=SURFACE, font=FONT)
                    .configure_view(stroke=None), use_container_width=True, theme=None)
    used = sum(opt.supply_used) / sum(opt.waste_heat)
    st.caption(pick(f"廃熱の利用率 {used:.0%}。冬は需要が供給を上回り、夏は熱が余る。夏に熱を使う需要家（陸上養殖など）が"
                    "採算を押し上げる。月の形は気象庁の平年値（札幌、1991〜2020年）の気温と降雪量から。",
                    f"{used:.0%} of the waste heat is used. Winter demand exceeds supply; summer heat is left over, "
                    "so summer users such as fish farms lift the whole network. Monthly shapes come from JMA "
                    "1991-2020 normals for Sapporo (temperature and snowfall)."))

st.subheader(pick("なぜペアの順位付けでは足りないのか", "Why ranking pairs is not enough"))
st.markdown(pick(
    "1. **導管は共有できる。** ペアごとの採点は需要家ごとにデータセンターから専用の管を引く前提なので、小口は単独では必ず赤字に見える。"
    "幹線から枝を出せば安くつながる。  \n"
    "2. **熱は有限で、季節で取り合いになる。** 冬は暖房需要がそろって伸びて足りず、夏は余る。冬型どうしを足しても冬の熱を二重に数えるだけで、"
    "夏に使う相手と組んで初めて設備が年中働く。  \n"
    "3. **組み合わせの価値はペアの足し算にならない。** 誰をつなぎ、どこまで幹線を延ばすかは、Steiner木と月ごとの容量を同時に解く組み合わせの問題。",
    "1. **Pipes can be shared.** Scoring pairs assumes a separate pipe from the data center to each user, so small "
    "users always look unprofitable alone; a branch off a trunk connects them cheaply.  \n"
    "2. **Heat is limited and seasonal.** In winter all heating demand peaks together and heat runs short; in summer it "
    "is left over. Adding winter users double-counts winter heat; pairing them with summer users keeps the plant busy all year.  \n"
    "3. **The value of a set is not the sum of its pairs.** Whom to connect and how far to run the trunk is a combinatorial "
    "problem: a Steiner tree with monthly capacity, solved at once."))
rows2 = []
for r in standalone_and_shared(opt, dc):
    if not r["connected"]:
        continue
    s_ = r["site"]
    verdict = (pick("単独では赤字 → ネットワークで黒字", "Loses money alone, pays in the network")
               if r["alone"] < 0 <= r["shared"] else
               pick("単独でも黒字", "Pays alone too") if r["alone"] >= 0 else pick("ネットワークでも赤字", "Loses money either way"))
    rows2.append({pick("施設", "Site"): s_.name if ja else s_.name_en, pick("種類", "Type"): KINDS[s_.kind][0 if ja else 1],
                  pick("専用管の長さ（km）", "Own pipe (km)"): round(r["own_pipe_m"] / 1000, 1),
                  pick("単独の損益（万円/年）", "Alone (10k yen/yr)"): round(r["alone"] / 1e4),
                  pick("ネットワーク内の損益（万円/年）", "In the network (10k yen/yr)"): round(r["shared"] / 1e4),
                  pick("判定", "Verdict"): verdict})
st.dataframe(pd.DataFrame(rows2), hide_index=True, width="stretch")
st.caption(pick("単独の損益＝年間需要を全部供給した場合の節約額 − 専用管の年経費。ネットワーク内の損益＝実際に届く熱の節約額 − "
                "下流で使う熱量に応じて分けた導管の年経費。",
                "Alone: saving on the full annual demand minus a pipe of its own. In the network: saving on the heat "
                "actually delivered minus a share of every pipe upstream, in proportion to the heat taken."))

st.subheader(pick("つながる需要家", "Connected users"))
tbl = []
for i in opt.connected:
    s = opt.sites[i]
    tbl.append({pick("施設", "Site"): s.name if ja else s.name_en, pick("種類", "Type"): KINDS[s.kind][0 if ja else 1],
                pick("年間需要（MWh）", "Demand (MWh/yr)"): round(s.annual_mwh),
                pick("供給（MWh/年）", "Served (MWh/yr)"): round(opt.served[i].sum()),
                pick("充足率", "Share served"): f"{opt.served[i].sum() / s.annual_mwh:.0%}",
                pick("節約額（万円/年）", "Saving (10k yen/yr)"): round(opt.served[i].sum() * A.value_yen_per_mwh / 1e4),
                pick("出典", "Source"): s.source})
st.dataframe(pd.DataFrame(tbl), hide_index=True, width="stretch")

with st.expander(pick("前提と出典", "Assumptions and sources")):
    st.dataframe(pd.DataFrame([
        [pick("熱の価値", "Value of heat"), f"{A.value_yen_per_mwh:,.0f} 円/MWh",
         pick("灯油ボイラーの燃料費 − ヒートポンプの電気代", "Kerosene boiler fuel minus heat pump power")],
        [pick("導管の年経費", "Pipe cost per year"), f"{A.pipe_yen_m * A.crf:,.0f} 円/m",
         pick(f"工事費 × 資本回収係数（{A.years}年・{A.rate:.1%}）", f"Cost x capital recovery ({A.years} y, {A.rate:.1%})")],
        [pick("CO2削減係数", "CO2 factor"), f"{A.co2_t_per_mwh:.3f} t/MWh",
         pick("灯油 2.49 kg-CO2/L（環境省）、ボイラー効率85%", "Kerosene 2.49 kg-CO2/L (MOE), boiler 85%")],
        [pick("温室の熱需要", "Greenhouse heat"), "0.40 MWh/m²・年", pick("仮定", "Assumption")],
        [pick("融雪の熱需要", "Snow melting heat"), "0.12 MWh/m²・年", pick("仮定（降雪479cm/年）", "Assumption (479 cm snow/yr)")],
        [pick("施設の熱需要", "Facility heat"), pick("温泉2,000・病院1,500・プール800・学校250 MWh/年",
                                                    "Bath 2,000, hospital 1,500, pool 800, school 250 MWh/yr"),
         pick("仮定", "Assumption")],
        [pick("月別の形", "Monthly shape"), pick("暖房度日・降雪量", "Degree-days, snowfall"), JMA_SOURCE],
        [pick("施設の位置", "Sites"), "OpenStreetMap", "© OpenStreetMap contributors"],
    ], columns=[pick("項目", "Item"), pick("値", "Value"), pick("根拠", "Basis")]), hide_index=True, width="stretch")
    st.caption(pick("「仮定」の値は確認できる出典がないもの。データセンター事業者や市と確かめる前提です。",
                    "Values marked as assumptions have no verified source yet; they are to be checked with the "
                    "data-center operator and the city."))
