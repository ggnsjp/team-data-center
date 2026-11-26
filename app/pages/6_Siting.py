"""Siting (theme 3): where the waste heat of a new data center is worth most, and what the grid
connection costs there.

A page of the main app; the language comes from the app-level switch. The heat values are read from
out/siting/siting.json (`uv run python scripts/export_siting.py`, about a quarter of an hour); the
location model on top of them solves when the page runs.
"""
from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dcopt.common.style import AXIS, FONT, GRID, GSI_ATTR, GSI_PALE, INK, INK2, MUTED, SLOTS, SURFACE, map_tip
from dcopt.siting.model import annuity, choose_sites, pareto

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "out" / "siting" / "siting.json"
M = 1e6
LINE = {275000: ("#B3541E", 5), 187000: ("#14213D", 4), 66000: ("#3987E5", 3)}
RATE, YEARS = 0.03, 30                 # the annuity of the heat model, used for the grid connection too
# Connection line, M yen per km: the middle and the range of the standard unit costs for a two-circuit
# tower line that OCCTO published in March 2026 (land excluded); "66" is its 66/77 kV class and
# "187" its 154/187 kV class. Source and reading: docs/input-evidence.md.
LINE_COST = {"66": (410, 140, 670), "187": (510, 190, 830)}

lang = st.session_state.get("app_lang", "日本語")
ja = lang == "日本語"


def pick(a, b):
    return a if ja else b


@st.cache_data(show_spinner=False)
def load_siting(path: str, stamp: float) -> dict:
    # Streamlit runs every page as __main__ and keys the cache by function name and source, so the
    # name is unique across pages and the path is part of the key (tests/test_app_cache_keys.py).
    return json.loads(Path(path).read_text(encoding="utf-8"))


st.title(pick("次のデータセンターの立地", "Siting the next data center"))
st.caption(pick(
    "新しいデータセンターをどこに置くと、その排熱が地域でいちばん役に立つか。候補地ごとに、テーマ1の導管網モデルを"
    "「その場所にデータセンターがある場合」で解き直し、ない場合との差を排熱の価値とします。系統への接続は、公開の地図にある"
    "変電所までの距離で見積もります。用途地域・土地・災害リスクは見ていない、最初のふるい分けです。",
    "Where would the waste heat of a new data center be of most use? For every candidate site the heat-network model of "
    "theme 1 is solved again with a data center there, and the gain over the plan without it is the value of its waste "
    "heat. The grid connection is estimated from the distance to a substation on the public map. This is a first "
    "screen: zoning, land and hazards are not checked."))
if not DATA.exists():
    st.warning(pick("立地のデータがありません。先に `uv run python scripts/export_siting.py` を実行してください（15分ほどかかります）。",
                    "The siting data is missing. Run `uv run python scripts/export_siting.py` first (about a quarter of an hour)."))
    st.stop()

data = load_siting(str(DATA), DATA.stat().st_mtime)
cands = data["candidates"]
has_grid = data.get("power") is not None and all("grid_66" in c for c in cands)

with st.sidebar:
    st.subheader(pick("立地の条件", "Siting settings"))
    sizes = [f"{s:g}" for s in data["sizes_mw"]]
    size = sizes[0] if len(sizes) == 1 else st.select_slider(pick("新しいデータセンターのIT負荷（MW）", "IT load of the new data center (MW)"),
                                                             options=sizes, value=sizes[0], key="siting_mw")
    n = st.slider(pick("新しく置く数", "Number of new data centers"), 1, 3, 1, key="siting_n")
    level = st.radio(pick("系統への接続先", "Grid connection at"), ["66", "187"], horizontal=True, key="siting_kv",
                     format_func=lambda k: pick(f"{k} kV以上の変電所", f"a substation of {k} kV or more"), disabled=not has_grid)
    mid, low, high = LINE_COST[level]
    cost = st.slider(pick("接続線の費用（百万円/km）", "Connection line cost (M yen per km)"), 0, 900, mid, 10,
                     key=f"siting_cost_{level}", disabled=not has_grid,
                     help=pick(f"初期値は、電力広域的運営推進機関が公表している標準的な単価（2026年3月、鉄塔2回線の架空線、土地代を除く）の範囲"
                               f" {low / 100:.1f}〜{high / 100:.1f}億円/km の中央です。距離に比例する費用を、30年・3 %の年賦に直して"
                               "排熱の価値から引きます。",
                               f"The default is the middle of the standard unit costs published by OCCTO (March 2026, two-circuit "
                               f"tower line, land excluded): {low} to {high} M yen per km. The cost grows with distance and is "
                               "turned into an annuity (30 years, 3 %) before it is taken off the heat value."))
    spacing = st.slider(pick("新しいデータセンターどうしの最小間隔（km）", "Minimum spacing between new data centers (km)"),
                        0.0, 8.0, 3.0, 0.5, key="siting_spacing",
                        help=pick("排熱の価値は1か所ずつ計算しているので、同じ需要家を取り合う近い2か所の価値は足せません。その組を除くための間隔です。",
                                  "The heat values are computed one site at a time, so two nearby sites that would feed the "
                                  "same users do not add up. The spacing keeps such pairs apart."))
    cap = st.number_input(pick("接続点ごとの受け入れ余地（MW、0は制限なし）", "Headroom per connection point (MW, 0 = no limit)"),
                          0.0, 500.0, 0.0, 10.0, key="siting_cap", disabled=not has_grid,
                          help=pick("シナリオの値です。北海道の系統モデルができれば、テーマ2の結果に置き換えます。",
                                    "A scenario value. Once a network model of the Hokkaido grid exists, the result of "
                                    "theme 2 takes its place."))

mw = float(size)
heat = [c["by_mw"][size]["value"] for c in cands]
gkey = f"grid_{level}"
km = [(c.get(gkey) or {}).get("substation_km") if has_grid else None for c in cands]
group = [(c.get(gkey) or {}).get("substation_id") if has_grid else None for c in cands]
per_km_year = annuity(RATE, YEARS) * cost * M if has_grid else 0.0
headroom = {g: cap for g in set(group) if g is not None} if cap > 0 and has_grid else None
choice = choose_sites(heat, [k if k is not None else float("nan") for k in km], [(c["x"], c["y"]) for c in cands], n=n,
                      yen_per_km_year=per_km_year, spacing_m=spacing * 1000, mw=mw, group=group, headroom=headroom)
rank = {j: r + 1 for r, j in enumerate(choice.chosen)}


def site_name(j: int) -> str:
    near = cands[j].get("near")
    return cands[j]["id"] + (pick(f"（{near}付近）", f" (near {near})") if near else "")


positive = sum(1 for h in heat if h > 1.0)
best = max(range(len(cands)), key=lambda j: heat[j])

c = st.columns(4)
c[0].metric(pick("候補地", "Candidate sites"), f"{len(cands)}", help=pick(f"{data['spacing_m'] / 1000:g} km間隔の格子点を、近くの道路に寄せたもの",
                                                                        f"points of a {data['spacing_m'] / 1000:g} km grid, moved to the nearest road"))
c[1].metric(pick("排熱に価値が出る候補地", "Sites where the heat has value"), f"{positive}")
c[2].metric(pick("最も高い排熱の価値（百万円/年）", "Highest heat value (M yen/yr)"), f"{heat[best] / M:,.1f}")
c[3].metric(pick("選んだ場所の正味（百万円/年）", "Net of the chosen sites (M yen/yr)"), "—" if not choice.chosen else f"{choice.net / M:,.1f}",
            help=pick("排熱の価値の合計 − 系統への接続線の年経費", "sum of the heat values minus the annual cost of the grid connections"))

if not choice.chosen:
    st.warning(pick("この条件では、指定した数の場所を選べません。間隔か受け入れ余地の条件をゆるめてください。",
                    "No choice satisfies these settings. Relax the spacing or the headroom."))
else:
    names = ("、" if ja else ", ").join(site_name(j) for j in choice.chosen)
    st.markdown(pick(
        f"**選ばれた場所：{names}。** 排熱の価値は合計で年{choice.heat / M:,.1f}百万円、接続線の年経費は{choice.grid / M:,.1f}百万円です。"
        f"比べると、新しいデータセンターを置かない今の計画の純便益は年{data['base']['net'] / M:,.1f}百万円です。",
        f"**Chosen: {names}.** Their waste heat is worth {choice.heat / M:,.1f} M yen a year in total, and the grid "
        f"connections cost {choice.grid / M:,.1f} M yen a year. For comparison, the regional plan without a new data center "
        f"earns {data['base']['net'] / M:,.1f} M yen a year."))

left, right = st.columns([7, 5], gap="medium")
with left:
    focus = [cands[j] for j in (choice.chosen or [best])] + data["data_centers"]
    lat0 = sum(x["lat"] for x in focus) / len(focus)
    lon0 = sum(x["lon"] for x in focus) / len(focus)
    m = folium.Map(location=[lat0, lon0], zoom_start=12, tiles=None, control_scale=True)
    folium.TileLayer(GSI_PALE, attr=GSI_ATTR, name=pick("地理院 淡色", "GSI pale")).add_to(m)
    power = data.get("power")
    if power:
        for ln in sorted(power["lines"], key=lambda r: r["kv"]):
            color, weight = LINE[ln["kv"]]
            folium.PolyLine([(y, x) for x, y in ln["path"]], color=color, weight=weight, opacity=0.9,
                            tooltip=map_tip(f"{ln['name'] or ''} {ln['kv'] // 1000} kV".strip())).add_to(m)
        for s in power["substations"]:
            if not s["generation"]:
                folium.CircleMarker([s["lat"], s["lon"]], radius=5 if s["kv"] < 187000 else 7, color=INK, weight=2, fill=True,
                                    fill_color="#ffffff", fill_opacity=1.0,
                                    tooltip=map_tip(f"{s['name'] or pick('変電所', 'substation')} {s['kv'] // 1000} kV")).add_to(m)
    for u in data["users"]:
        folium.CircleMarker([u["lat"], u["lon"]], radius=2.5, color=MUTED, weight=1, fill=True, fill_color=MUTED,
                            fill_opacity=0.9 if u["in_base_plan"] else 0.25,
                            tooltip=map_tip((u["name"] if ja else u["name_en"]) + pick("（熱の需要家）", " (heat user)"))).add_to(m)
    top = max(max(heat), 1.0)
    for j, x in enumerate(cands):
        share = max(heat[j], 0.0) / top
        chosen = j in rank
        tip = map_tip(site_name(j),
                      pick(f"排熱の価値 年{heat[j] / M:,.1f}百万円", f"heat value {heat[j] / M:,.1f} M yen/yr"),
                      pick(f"変電所まで {km[j]:.1f} km", f"{km[j]:.1f} km to the substation") if km[j] is not None else None,
                      pick(f"選んだ場所（{rank[j]}番目）", f"chosen (no. {rank[j]})") if chosen else None)
        if heat[j] <= 1.0 and not chosen:                  # no value here: a small grey dot
            folium.CircleMarker([x["lat"], x["lon"]], radius=4, color=INK2, weight=1, fill=True, fill_color="#ffffff",
                                fill_opacity=0.9, tooltip=tip).add_to(m)
            continue
        folium.CircleMarker([x["lat"], x["lon"]], radius=6 + 14 * share ** 0.5, color=INK if chosen else SLOTS[1],
                            weight=4 if chosen else 1.5, fill=True, fill_color=SLOTS[1], fill_opacity=0.25 + 0.6 * share,
                            tooltip=tip).add_to(m)
    for d in data["data_centers"]:
        folium.Marker([d["lat"], d["lon"]], icon=folium.Icon(color="black", icon="flash"),
                      tooltip=map_tip((d["name"] if ja else d["name_en"]) + pick("（既存・計画中）", " (existing or planned)"))).add_to(m)
    components.html(m.get_root().render(), height=600)
    st.caption(pick("橙の円：排熱に価値が出る候補地（大きく濃いほど価値が高い）。小さな白い点：価値が出ない候補地。太い縁：選ばれた場所。"
                    "灰色の点：熱の需要家（濃い点は今の計画でつながる施設）。線：送電線（橙275 kV、紺187 kV、青66 kV）。白丸：変電所。",
                    "Orange circles: candidate sites where the heat has value (larger and darker = more). Small white dots: "
                    "candidates with no value. Thick ring: chosen. Grey dots: heat users (dark = connected in today's plan). "
                    "Lines: transmission lines (orange 275 kV, navy 187 kV, blue 66 kV). White circles: substations."))

with right:
    st.markdown("**" + pick("排熱の価値と、変電所までの距離", "Heat value against the distance to a substation") + "**")
    if has_grid:
        front = set(pareto(heat, [k if k is not None else 1e9 for k in km]))
        df = pd.DataFrame([{"id": site_name(j), "km": km[j], "value": heat[j] / M,
                            "role": pick("選んだ場所", "chosen") if j in rank else
                            pick("ほかより劣らない場所", "not beaten by any site") if j in front else pick("ほかの候補地", "other sites")}
                           for j, x in enumerate(cands) if km[j] is not None])
        roles = [pick("選んだ場所", "chosen"), pick("ほかより劣らない場所", "not beaten by any site"), pick("ほかの候補地", "other sites")]
        dots = alt.Chart(df).mark_point(filled=True, opacity=1, stroke=SURFACE, strokeWidth=1.5).encode(
            x=alt.X("km:Q", title=pick("変電所までの距離（km）", "Distance to the substation (km)"),
                    axis=alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2, domainColor=AXIS)),
            y=alt.Y("value:Q", title=pick("排熱の価値（百万円/年）", "Heat value (M yen/yr)"),
                    axis=alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2, domainColor=AXIS)),
            color=alt.Color("role:N", sort=roles, scale=alt.Scale(domain=roles, range=[INK, SLOTS[1], MUTED]),
                            legend=alt.Legend(title=None, orient="bottom", labelColor=INK2, columns=1)),
            size=alt.Size("role:N", sort=roles, scale=alt.Scale(domain=roles, range=[190, 110, 50]), legend=None),
            shape=alt.Shape("role:N", sort=roles, scale=alt.Scale(domain=roles, range=["diamond", "circle", "circle"]), legend=None),
            tooltip=[alt.Tooltip("id:N", title=pick("候補地", "Site")), alt.Tooltip("value:Q", title=pick("排熱の価値", "Heat value"), format=",.1f"),
                     alt.Tooltip("km:Q", title="km", format=".1f")])
        labels = alt.Chart(df[df["role"] == roles[0]]).mark_text(align="left", dx=10, dy=-8, color=INK, fontWeight="bold").encode(
            x="km:Q", y="value:Q", text="id:N")
        st.altair_chart((dots + labels).properties(height=330).configure(background=SURFACE, font=FONT).configure_view(stroke=None),
                        width="stretch", theme=None)
        st.caption(pick("左上ほど良い場所です（排熱の価値が高く、変電所に近い）。「ほかより劣らない場所」は、価値と距離の両方で上回る候補地がない場所です。",
                        "Up and to the left is better: more heat value, closer to a substation. A site is \"not beaten\" when "
                        "no other site has both more value and a shorter distance."))
    else:
        st.info(pick("送電線のデータがないので、排熱の価値だけで選んでいます。", "The power-line data is missing, so the choice uses the heat values only."))
    order = sorted(range(len(cands)), key=lambda j: -choice.score[j])[:10]
    st.dataframe(pd.DataFrame([{
        pick("候補地", "Site"): ("★ " if j in rank else "") + site_name(j),
        pick("価値", "Value"): f"{heat[j] / M:,.1f}",
        pick("正味", "Net"): f"{choice.score[j] / M:,.1f}",
        pick("施設", "Sites"): cands[j]["by_mw"][size]["sites_from_candidate"],
        "km": "—" if km[j] is None else f"{km[j]:.1f}",
        pick("接続先", "Connection point"): (cands[j].get(gkey) or {}).get("substation") or "—"} for j in order]),
        hide_index=True, width="stretch")
    st.caption(pick("上位10か所。価値＝排熱の価値、正味＝価値 − 接続線の年経費（どちらも百万円/年）。施設＝新しいデータセンターから熱が届く施設の数。"
                    "km＝変電所までの距離。★は選ばれた場所。",
                    "Top ten. Value = heat value; net = value minus the annual cost of the connection line (both M yen a year). "
                    "Sites = sites served from the new data center. km = distance to the substation. ★ marks the chosen sites."))

with st.expander(pick("読み方と限界", "How to read this, and its limits")):
    check = data.get("pair_check")
    extra = ""
    if check:
        extra = pick(
            f"\n- **2か所を同時に置いた場合の確認：** {'と'.join(check['ids'])} の価値は、1か所ずつなら合計で年{check['sum_of_single_values'] / M:,.1f}百万円、"
            f"2か所を同時に入れて解くと年{check['joint_value'] / M:,.1f}百万円でした。",
            f"\n- **A check with two sites at once:** the values of {' and '.join(check['ids'])} add up to "
            f"{check['sum_of_single_values'] / M:,.1f} M yen a year one at a time, and solving with both gives "
            f"{check['joint_value'] / M:,.1f} M yen a year.")
    st.markdown(pick(
        f"- **排熱の価値：** 既存のデータセンターに、IT負荷{mw:g} MW（低負荷シナリオではその{data['low_share']:.0%}）のデータセンターを1つ加えて導管網を最適化し直し、"
        "加えない場合との純便益の差をとった値です。既存のデータセンターのそばでは、熱はすでに余っているので価値はほぼ0です。"
        "まだ熱が届いていない需要家の近くで高くなります。\n"
        "- **系統への接続：** OpenStreetMapに載っている変電所までの直線距離に、1 kmあたりの費用を掛けています。費用は、公表されている標準的な単価の"
        "範囲の中央で、範囲は広く（66・77 kV級で1.4〜6.7億円/km）、土地代は含みません。変電所にどれだけ余地があるかは分かりません。"
        "北海道の系統モデルができれば、テーマ2の受け入れ余地を制約に入れます。\n"
        "- **見ていないもの：** 用途地域、土地の広さと価格、通信回線、洪水・津波・地盤、冷却用の水。候補地は格子点であり、実際の空き地ではありません。"
        + extra,
        f"- **Heat value:** the heat network is optimized again with one more data center of {mw:g} MW of IT load "
        f"({data['low_share']:.0%} of it in the low-load scenario), and the value is the gain in net benefit over the plan "
        "without it. Next to the existing data centers the heat is already in surplus, so the value is about zero. It is high "
        "near users that no heat reaches yet.\n"
        "- **Grid connection:** the straight-line distance to a substation mapped in OpenStreetMap, times a cost per km. The "
        "cost is the middle of the published standard unit costs, a wide range (140 to 670 M yen per km in the 66/77 kV "
        "class) that leaves out land. How much room the substation has is not known. Once a network model of the Hokkaido grid exists, the "
        "hosting capacity of theme 2 becomes a constraint here.\n"
        "- **Not considered:** zoning, the size and price of land, fibre, flood, tsunami and ground conditions, cooling "
        "water. The candidates are grid points, not vacant lots." + extra))
st.caption(pick("送電線・変電所：© OpenStreetMap contributors（ODbL）。記載のとおりで、系統運用者のデータとは照合していません。",
                "Lines and substations: © OpenStreetMap contributors (ODbL), as mapped; not checked against the grid operator's data."))
