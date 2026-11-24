"""Grid hosting capacity (theme 2): how much added load a bus can take, as a certified bracket.

A page of the main app (uv run streamlit run app/streamlit_app.py); the language comes from the
app-level switch. The systems are public benchmark networks and three small built-in ones, not the
Hokkaido grid. Every number on the page is computed by dcopt.grid when the page runs.
"""
from __future__ import annotations

import altair as alt
import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st

from dcopt.common.style import AXIS, FONT, GRID, INK, INK2, MUTED, SLOTS, SURFACE
from dcopt.grid import cases
from dcopt.grid.hosting import Hosting, HostingModel, summarize

lang = st.session_state.get("app_lang", "日本語")
ja = lang == "日本語"
LEVELS = (0.6, 0.7, 0.8, 0.9, 1.0)
ALL_BUSES_MAX = 120                    # the all-bus view runs live up to this size
SYSTEMS = {"ring5": ("5母線の環状系統（例）", "5-bus ring (illustration)"),
           "feeder8": ("8母線の放射状フィーダー（例）", "8-bus radial feeder (illustration)"),
           "two_bus": ("2母線（教科書の例）", "two buses (textbook example)")}
KIND = {"thermal": ("線路の熱容量", "thermal rating"), "voltage": ("電圧", "voltage"),
        "generation (P)": ("発電機の出力", "generator output"), "reactive (Q)": ("無効電力", "reactive power"),
        "angle": ("位相角差", "angle difference")}


def pick(a, b):
    return a if ja else b


def system_name(key: str) -> str:
    if key in SYSTEMS:
        return SYSTEMS[key][0 if ja else 1]
    return pick(f"{key}（PGLib-OPF）", f"{key} (PGLib-OPF)")


def element(text: str) -> str:
    if not ja:
        return text
    return (text.replace("generator at bus ", "発電機（母線").replace("branch ", "線路 ").replace("bus ", "母線 ")
            + ("）" if text.startswith("generator") else ""))


@st.cache_resource(show_spinner=False)
def model_for(name: str, level: float) -> HostingModel:
    case = cases.load(name, download=False)
    return HostingModel(case if level == 1.0 else case.scaled_loads(level))


@st.cache_data(show_spinner=False)
def bracket(name: str, level: float, bus: int, pf: float) -> Hosting:
    return model_for(name, level).evaluate(bus, pf)


@st.cache_data(show_spinner=False)
def all_buses(name: str, level: float, pf: float) -> list[Hosting]:
    model = model_for(name, level)
    return [model.evaluate(b, pf) for b in range(model.case.n)]


@st.cache_data(show_spinner=False)
def layout(name: str) -> np.ndarray:
    case = cases.load(name, download=False)
    g = nx.Graph()
    g.add_nodes_from(range(case.n))
    g.add_edges_from(zip(case.f.tolist(), case.t.tolist()))
    pos = nx.kamada_kawai_layout(g) if case.n > 2 else {0: (0.0, 0.0), 1: (1.0, 0.0)}
    return np.array([pos[i] for i in range(case.n)])


def mw(x: float | None) -> str:
    return "—" if x is None else f"{x:,.1f}"


st.title(pick("系統の受け入れ余地", "Grid hosting capacity"))
st.caption(pick(
    "ある母線に負荷（データセンターなど）を足したとき、電圧・線路の容量・発電機の制約を守ったまま、何MWまで受け入れられるか。"
    "交流の潮流で実際に成り立つ点（下限）と、凸緩和による上限ではさみます。"
    "系統は公開の試験系統と小さな例で、北海道の系統ではありません。",
    "How many MW of added load (a data center, say) a bus can take while voltages, branch ratings and generator "
    "limits hold. An AC operating point that passes every check gives the lower end, and a convex relaxation the "
    "upper end. The networks are public benchmark systems and small examples, not the Hokkaido grid."))

with st.sidebar:
    st.subheader(pick("系統と負荷", "Network and load"))
    names = cases.available()
    if "grid_case" not in st.session_state and st.query_params.get("case") in names:
        st.session_state["grid_case"] = st.query_params["case"]         # a link can open a given network
    name = st.selectbox(pick("系統", "Network"), names, format_func=system_name, key="grid_case")
    missing = [c for c in cases.PGLIB_CASES if c not in names]
    if missing and st.button(pick("公開の試験系統をダウンロード", "Download the benchmark systems"), key="grid_fetch"):
        with st.spinner(pick("PGLib-OPFから取得中…", "Fetching from PGLib-OPF…")):
            got = [c for c in missing if cases.ensure_pglib(c) is not None]
        if len(got) < len(missing):
            st.warning(pick(f"{len(missing) - len(got)}件は取得できませんでした。手元の系統で続けられます。",
                            f"{len(missing) - len(got)} could not be fetched. The page carries on with what it has."))
        if got:
            st.rerun()
    case = cases.load(name, download=False)
    buses = list(range(case.n))
    default = int(np.argmax(case.pd)) if case.pd.max() > 0 else case.n - 1
    bus = st.selectbox(pick("負荷を足す母線", "Bus that takes the added load"), buses, index=default, key=f"grid_bus_{name}",
                       format_func=lambda i: pick(f"母線 {case.label(i)}（今の負荷 {case.pd[i] * case.base_mva:,.0f} MW）",
                                                  f"bus {case.label(i)} (load now {case.pd[i] * case.base_mva:,.0f} MW)"))
    pf = st.slider(pick("足す負荷の力率", "Power factor of the added load"), 0.85, 1.0, 0.95, 0.01, key="grid_pf")
    level = st.select_slider(pick("既存の負荷の水準", "Level of the existing loads"), options=list(LEVELS), value=1.0,
                             format_func=lambda a: f"×{a:g}", key="grid_level")
    st.caption(pick("既存の負荷はそのまま、発電機は自由に出力を変えられる前提（系統にとって最も有利な場合）です。",
                    "Existing loads stay fixed and every generator may redispatch: the best case for the network."))

with st.spinner(pick("潮流を計算中…", "Solving the power flow…")):
    h = bracket(name, level, bus, pf)

c = st.columns(5)
c[0].metric(pick("受け入れ可能（MW）", "Hostable (MW)"), mw(h.ac),
            help=pick("交流の潮流で成り立つことを確認した運転点", "an AC operating point that passes every check"))
c[1].metric(pick("上限：SDP（MW）", "Upper bound, SDP (MW)"), mw(h.sdp))
c[2].metric(pick("上限：SOCP（MW）", "Upper bound, SOCP (MW)"), mw(h.socp))
c[3].metric(pick("DC簡易評価（MW）", "DC screening (MW)"), mw(h.dc))
c[4].metric(pick("上限と下限の差", "Gap of the bracket"), "—" if h.gap is None else f"{h.gap:.2%}")

if h.ac is None:
    st.warning(pick("この条件では、交流で成り立つ点が見つかりませんでした。上限だけを表示しています。",
                    "No AC operating point was found for this setting. Only the upper bounds are shown."))
elif h.upper is not None:
    closed = h.gap is not None and h.gap < 1e-3
    dc_note = ""
    if h.dc is not None and h.dc > h.upper * 1.01:
        dc_note = pick(f"DC潮流の簡易評価（{mw(h.dc)} MW）は上限を超えています。この母線では、簡易評価は受け入れ余地を過大に見積もります。",
                       f" DC screening ({mw(h.dc)} MW) lies above the upper bound: at this bus it overstates the capacity.")
    st.markdown(pick(
        f"**母線 {h.bus} は {mw(h.ac)} MW まで受け入れられます。** "
        + ("上限と一致したので、これがこのモデルでの正確な値です。" if closed else
           f"上限は {mw(h.upper)} MW で、真の値はこのあいだにあります。") + dc_note,
        f"**Bus {h.bus} can take {mw(h.ac)} MW.** "
        + ("The upper bound agrees, so this is the exact value in this model." if closed else
           f"The upper bound is {mw(h.upper)} MW; the true value lies in between.") + dc_note))

left, right = st.columns([5, 7], gap="medium")
with left:
    st.markdown("**" + pick("4つの見積もり", "Four estimates") + "**")
    rows = [(pick("交流で確認した点", "AC point (checked)"), h.ac, "ac"),
            (pick("上限：SDP緩和", "Upper bound: SDP"), h.sdp, "bound"),
            (pick("上限：SOCP緩和", "Upper bound: SOCP"), h.socp, "bound"),
            (pick("DC潮流の簡易評価", "DC screening"), h.dc, "dc")]
    df = pd.DataFrame([{"method": m, "mw": v, "role": r, "label": mw(v)} for m, v, r in rows if v is not None])
    order = [m for m, _, _ in rows]
    base = alt.Chart(df).encode(
        y=alt.Y("method:N", sort=order, title=None, axis=alt.Axis(labelColor=INK, labelLimit=220, ticks=False,
                                                                  domain=False, labelPadding=8)),
        x=alt.X("mw:Q", title="MW", scale=alt.Scale(domain=[0, 1.18 * float(df["mw"].max())], nice=False),
                axis=alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2, domainColor=AXIS)))
    bars = base.mark_bar(height=18, cornerRadiusEnd=4).encode(
        color=alt.Color("role:N", scale=alt.Scale(domain=["ac", "bound", "dc"], range=[SLOTS[0], MUTED, SLOTS[1]]),
                        legend=None),
        tooltip=[alt.Tooltip("method:N", title=pick("見積もり", "Estimate")), alt.Tooltip("mw:Q", title="MW", format=",.1f")])
    text = base.mark_text(align="left", dx=6, color=INK).encode(text="label:N")
    st.altair_chart((bars + text).properties(height=170).configure(background=SURFACE, font=FONT)
                    .configure_view(stroke=None), width="stretch", theme=None)
    st.caption(pick("青：実際に成り立つ運転点（下限）。灰色：これ以上は受け入れられないという上限。橙：損失・無効電力・電圧を無視した簡易評価で、上限でも下限でもありません。",
                    "Blue: an operating point that holds (lower end). Grey: bounds that no operating point can exceed. "
                    "Orange: the screening estimate without losses, reactive power or voltages; it is neither a bound "
                    "nor a feasible point."))

    st.markdown("**" + pick("どの制約が効いているか", "Which limit binds") + "**")
    if h.binding:
        st.dataframe(pd.DataFrame([
            {pick("制約", "Limit"): KIND[b["kind"]][0 if ja else 1], pick("場所", "Where"): element(b["element"]),
             pick("1%緩和で（MW）", "MW per 1 %"): f"{b['gain']:,.2f}"}
            for b in h.binding[:6]]), hide_index=True, width="stretch")
        st.caption(pick("右の列は、その制約を1%ゆるめたときに増える受け入れ余地（交流の点での感度）です。値が大きい制約ほど、余地を強く抑えています。",
                        "The last column is the hostable load gained by relaxing that limit by 1 % (a sensitivity at the AC "
                        "point): the larger the value, the more that limit holds the capacity down."))
    else:
        st.caption(pick("効いている制約は特定できませんでした。", "No binding limit could be identified."))

with right:
    st.markdown("**" + pick("負荷を足したときの系統", "The network with the added load") + "**")
    xy = layout(name)
    if h.voltages is not None:
        yff, yft, ytf, ytt = case.admittances()
        vf, vt = h.voltages[case.f], h.voltages[case.t]
        s = np.maximum(np.abs(vf * np.conj(yff * vf + yft * vt)), np.abs(vt * np.conj(ytf * vf + ytt * vt)))
        loading = np.where(np.isfinite(case.rate), s / np.where(np.isfinite(case.rate), case.rate, 1.0), np.nan)
        vm = np.abs(h.voltages)
    else:
        loading, vm = np.full(case.m, np.nan), np.full(case.n, np.nan)
    lines = pd.DataFrame({"x": xy[case.f, 0], "y": xy[case.f, 1], "x2": xy[case.t, 0], "y2": xy[case.t, 1],
                          "branch": [f"{case.label(a)}–{case.label(b)}" for a, b in zip(case.f, case.t)],
                          "loading": np.round(100 * loading, 1)})
    gens = set(case.gen_bus.tolist())
    nodes = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1], "bus": [case.label(i) for i in range(case.n)],
                          "v": np.round(vm, 4), "load": np.round(case.pd * case.base_mva, 1),
                          "role": [pick("負荷を足す母線", "bus with the added load") if i == bus else
                                   pick("発電機のある母線", "generator bus") if i in gens else pick("母線", "bus")
                                   for i in range(case.n)]})
    hidden = alt.Axis(labels=False, ticks=False, domain=False, grid=False, title=None)
    roles = [pick("負荷を足す母線", "bus with the added load"), pick("発電機のある母線", "generator bus"), pick("母線", "bus")]
    edge = alt.Chart(lines).mark_rule(strokeWidth=2.5, strokeCap="round").encode(
        x=alt.X("x:Q", axis=hidden), y=alt.Y("y:Q", axis=hidden), x2="x2:Q", y2="y2:Q",
        color=alt.Color("loading:Q", scale=alt.Scale(domain=[0, 100], range=["#dfe7f3", SLOTS[0], "#0d2f66"], clamp=True),
                        legend=alt.Legend(title=pick("線路の負荷率（%）", "Branch loading (%)"), orient="bottom",
                                          gradientLength=220, labelColor=INK2, titleColor=INK2)),
        tooltip=[alt.Tooltip("branch:N", title=pick("線路", "Branch")),
                 alt.Tooltip("loading:Q", title=pick("負荷率（%）", "Loading (%)"))])
    node = alt.Chart(nodes).mark_point(filled=True, opacity=1, stroke=SURFACE, strokeWidth=1.5).encode(
        x="x:Q", y="y:Q",
        size=alt.Size("role:N", scale=alt.Scale(domain=roles, range=[260, 90, 45]), legend=None),
        shape=alt.Shape("role:N", scale=alt.Scale(domain=roles, range=["circle", "square", "circle"]), legend=None),
        color=alt.Color("role:N", scale=alt.Scale(domain=roles, range=[SLOTS[1], INK2, MUTED]), legend=None),
        tooltip=[alt.Tooltip("bus:N", title=pick("母線", "Bus")), alt.Tooltip("role:N", title=pick("種類", "Kind")),
                 alt.Tooltip("v:Q", title=pick("電圧（p.u.）", "Voltage (p.u.)")),
                 alt.Tooltip("load:Q", title=pick("既存の負荷（MW）", "Existing load (MW)"))])
    chart = (edge + node).resolve_scale(color="independent", shape="independent", size="independent")
    st.altair_chart(chart.properties(height=430, padding=14).configure(background=SURFACE, font=FONT)
                    .configure_view(stroke=None), width="stretch", theme=None)
    st.caption(pick("橙の丸：負荷を足す母線。四角：発電機のある母線。線の色：負荷を足した運転点での線路の負荷率。"
                    "試験系統には座標がないので、配置は接続関係から自動で決めています。",
                    "Orange circle: the bus with the added load. Squares: generator buses. Branch color: loading at the "
                    "operating point with the added load. The benchmark systems have no coordinates, so the layout is "
                    "computed from the connections."))

st.subheader(pick("既存の負荷が軽い時間帯なら、どれだけ受け入れられるか", "How much more when the existing loads are lower"))
st.caption(pick("既存の負荷をすべて同じ割合で減らして、同じ母線の受け入れ余地を計算します。需要の高い時間だけ抑制できる負荷なら、"
                "常時つなぐ負荷より大きくできる、という見方の材料です。",
                "Every existing load is scaled by the same factor and the bracket is computed again for this bus. "
                "It shows how much larger a load could be if it can be curtailed in the highest-demand hours."))
if st.toggle(pick("負荷の水準ごとに計算する", "Compute for each load level"), key=f"grid_curve_{name}"):
    with st.spinner(pick("5つの水準で計算中…", "Solving five load levels…")):
        curve = [(a, bracket(name, a, bus, pf)) for a in LEVELS]
    rows = []
    for a, r in curve:
        rows.append({"level": f"×{a:g}", "series": pick("受け入れ可能（交流で確認）", "Hostable (AC point, checked)"), "mw": r.ac})
        rows.append({"level": f"×{a:g}", "series": pick("上限（緩和）", "Upper bound (relaxation)"), "mw": r.upper})
    cdf = pd.DataFrame(rows).dropna()
    series = [pick("受け入れ可能（交流で確認）", "Hostable (AC point, checked)"), pick("上限（緩和）", "Upper bound (relaxation)")]
    line = alt.Chart(cdf).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=70, filled=True)).encode(
        x=alt.X("level:N", sort=[f"×{a:g}" for a in LEVELS], title=pick("既存の負荷の水準", "Level of the existing loads"),
                axis=alt.Axis(labelAngle=0, labelColor=INK2, titleColor=INK2, domainColor=AXIS)),
        y=alt.Y("mw:Q", title="MW", axis=alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2, domainColor=AXIS)),
        color=alt.Color("series:N", sort=series, scale=alt.Scale(domain=series, range=[SLOTS[0], MUTED]),
                        legend=alt.Legend(title=None, orient="bottom", labelColor=INK2)),
        strokeDash=alt.StrokeDash("series:N", sort=series, scale=alt.Scale(domain=series, range=[[1, 0], [5, 4]]),
                                  legend=None),
        tooltip=[alt.Tooltip("level:N", title=pick("水準", "Level")), alt.Tooltip("series:N", title=pick("系列", "Series")),
                 alt.Tooltip("mw:Q", title="MW", format=",.1f")])
    st.altair_chart(line.properties(height=260).configure(background=SURFACE, font=FONT).configure_view(stroke=None),
                    width="stretch", theme=None)
    st.dataframe(pd.DataFrame([{pick("水準", "Level"): f"×{a:g}", pick("受け入れ可能（MW）", "Hostable (MW)"): mw(r.ac),
                                pick("上限（MW）", "Upper bound (MW)"): mw(r.upper),
                                pick("差", "Gap"): "—" if r.gap is None else f"{r.gap:.2%}"} for a, r in curve]),
                 hide_index=True, width="stretch")

st.subheader(pick("すべての母線", "Every bus"))
if case.n > ALL_BUSES_MAX:
    st.caption(pick(f"この系統は{case.n}母線あり、全母線の計算には数分かかります。`uv run python experiments/grid_hosting/run.py` の結果を参照してください。",
                    f"This network has {case.n} buses and the full sweep takes minutes. See the results of "
                    "`uv run python experiments/grid_hosting/run.py`."))
elif st.toggle(pick("全母線を計算する", "Compute every bus"), key=f"grid_all_{name}"):
    with st.spinner(pick(f"{case.n}母線を計算中…", f"Solving {case.n} buses…")):
        every = all_buses(name, level, pf)
    sm = summarize(every)
    st.markdown(pick(
        f"- 交流で確認した点が見つかった母線：**{sm['ac_found']} / {sm['buses']}**\n"
        f"- 上限と下限の差が1%未満の母線：**{sm['gap_below_1%']}**\n"
        f"- DC潮流の簡易評価が上限を超えた母線：**{sm['dc_above_upper']}**（簡易評価が過大）",
        f"- Buses with a checked AC point: **{sm['ac_found']} of {sm['buses']}**\n"
        f"- Buses where the bracket is closed within 1 %: **{sm['gap_below_1%']}**\n"
        f"- Buses where DC screening exceeds the upper bound: **{sm['dc_above_upper']}** (screening overstates)"))
    table = pd.DataFrame([{pick("母線", "Bus"): r.bus, pick("受け入れ可能（MW）", "Hostable (MW)"): None if r.ac is None else round(r.ac, 1),
                           pick("上限（MW）", "Upper bound (MW)"): None if r.upper is None else round(r.upper, 1),
                           pick("DC簡易評価（MW）", "DC screening (MW)"): None if r.dc is None else round(r.dc, 1),
                           pick("差（%）", "Gap (%)"): None if r.gap is None else round(100 * r.gap, 2),
                           pick("効いている制約", "Binding limit"): KIND[r.limit][0 if ja else 1] if r.limit in KIND else "—"}
                          for r in every])
    st.dataframe(table, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(table)))

with st.expander(pick("計算の中身と限界", "What is computed, and its limits")):
    st.markdown(pick(
        "- **下限（交流で確認した点）：** 内点法で運転点を探し、別の計算で、電力の収支とすべての制約が成り立つこと（誤差10⁻⁶ p.u.以内）を確かめた点です。"
        "この量までは受け入れられます。局所解なので、最良とは限りません。\n"
        "- **上限（SDP・SOCP緩和）：** 交流の問題を凸にゆるめた問題の最適値です。どの運転点もこれを超えられません。上限と下限が一致すれば、値が確定します。\n"
        "- **DC潮流の簡易評価：** 損失・無効電力・電圧を無視した線形の計算です。上限でも下限でもありません。\n"
        "- **限界：** 試験系統であり北海道の系統ではありません。発電機が自由に出力を変える最も有利な場合で、N-1（設備1つの停止）や安定度は見ていません。"
        "数式と結果は docs/formulations/grid.md にあります。",
        "- **Lower end (checked AC point):** an interior-point method finds an operating point, and a separate routine "
        "confirms the power balance and every limit within 10⁻⁶ per unit. That much load can be hosted. The method is "
        "local, so the point need not be the best one.\n"
        "- **Upper end (SDP and SOCP relaxations):** the optimum of a convex relaxation of the AC problem. No operating "
        "point can exceed it. When the two ends meet, the value is exact.\n"
        "- **DC screening:** a linear calculation without losses, reactive power or voltages. It is not a bound.\n"
        "- **Limits:** benchmark systems, not the Hokkaido grid; generators redispatch freely (the best case); no N-1 "
        "outages and no stability limits. Formulas and results: docs/formulations/grid.md."))
st.caption(pick("試験系統：PGLib-OPF（IEEE PES Task Force、CC BY 4.0）。小さな例はこのプロジェクトで作った説明用のデータです。",
                "Benchmark systems: PGLib-OPF (IEEE PES Task Force, CC BY 4.0). The small examples are illustrative data "
                "made for this project."))
