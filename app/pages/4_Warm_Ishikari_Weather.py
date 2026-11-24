"""Warm Ishikari Weather: the heat network against 50 years of real weather (v2 model).

Run with the main app: uv run streamlit run streamlit_app.py  (this is its third page).
The robustness panel reads the latest results/weather_years/<timestamp>/results.json written by
experiments/weather_years/run.py; the year selector solves the v2 network for one chosen year.
"""
from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from dcopt.common.style import FONT, GRID, INK, INK2, SURFACE
from dcopt.heat import weather as W
from dcopt.heat.network import Params, Scenario, build_instance, ishikari_sources, plan_for
from dcopt.heat.v1 import KINDS, ishikari_sites

st.set_page_config(page_title="Warm Ishikari Weather · 石狩の排熱と気象年", layout="wide",
                   initial_sidebar_state="expanded")

M = 1e6


@st.cache_resource(show_spinner="地図と施設を読み込み中 / Loading Ishikari's map and facilities...")
def load_instance():
    from dcopt.common.geo import use_overpass_mirror
    use_overpass_mirror()
    sakura, sites = ishikari_sites()
    return build_instance(ishikari_sources(sakura), sites), sites


@st.cache_resource(show_spinner="50年分の気象データを読み込み中 / Loading 50 years of weather...")
def weather_years() -> list[W.WeatherYear]:
    return W.load_years(1976, 2025)


@st.cache_resource(show_spinner="その年の気象で導管網を最適化中 / Optimizing the network for this year...")
def solve_year(year: int, it_level: str, price: float):
    w = next(w for w in weather_years() if w.year == year)
    sc = Scenario(f"y{year}", f"{year}年・IT{it_level}・{price:g}円/L", f"{year}, IT {it_level}, {price:g} yen/L",
                  1.0, price, it_level, None, w)
    inst, _ = load_instance()
    return plan_for(inst, Params(mode="ambient", time_limit=60.0), [sc])


def latest_results() -> dict | None:
    """The newest experiment run's results.json, or None when the experiment has not run yet."""
    root = Path(__file__).resolve().parents[2] / "results" / "weather_years"
    runs = sorted(root.glob("*/results.json"))
    return json.loads(runs[-1].read_text(encoding="utf-8")) if runs else None


def pick(a, b):
    return a if ja else b


with st.sidebar:
    lang = st.radio("表示言語 / Language", ["日本語", "English"], horizontal=True, key="weather_lang")
    ja = lang == "日本語"

res = latest_results()
st.title("Warm Ishikari Weather · " + pick("50年の気象で試す導管網", "The heat network against 50 years of weather"))
st.caption(pick("平年値だけの計画を、1976〜2025年の実際の毎日の気象（気象庁・札幌）で試します。上のセクションは実験の結果、"
                "下のセクションは選んだ年の気象で導管網を作り直した場合です。",
                "The plan built on climate normals, tested against the actual daily weather of 1976-2025 "
                "(JMA, Sapporo). The top section shows the experiment's results; the bottom re-optimizes "
                "the network for one chosen year."))

if not W.year_csv(W.YEARS[0]).exists():
    st.error(pick("気象データ（1976〜2025年）がまだダウンロードされていません。まず一度だけ実行してください（約10分）：",
                  "The weather years (1976-2025) are not downloaded yet. Run this once first (about 10 minutes):"))
    st.code("uv run python -m dcopt.heat.weather 1976 2025")
    st.stop()
missing = [f"{w.year}年 {w.n_missing_t}日" if ja else f"{w.year} ({w.n_missing_t} d)"
           for w in weather_years() if w.n_missing_t]
if missing:
    st.warning(pick("観測のない日は、同じ月の他の日の平均で補いました：",
                    "Days without a temperature observation were imputed from their month's other days: ")
               + ("、".join(missing) if ja else ", ".join(missing)))

with st.sidebar:
    st.subheader("シナリオ / Scenario")
    year = st.select_slider("気象年 / Weather year", options=[w.year for w in weather_years()], value=1984)
    it_level = st.radio("データセンターのIT負荷 / IT load", ["high", "low"], horizontal=True)
    price = st.slider("灯油価格（円/L） / Kerosene (yen/L)", 70.0, 170.0, 156.8, 0.2)

if res is None:
    st.info(pick("実験結果がまだありません: uv run python experiments/weather_years/run.py ambient both --bound",
                 "No experiment results yet: uv run python experiments/weather_years/run.py ambient both --bound"))
else:
    rep = res["published_replication"]
    st.subheader(pick("実験の結果（読み取り専用）", "Experiment results (read-only)"))
    st.caption(pick(f"出典 / Source: commit {res.get('git_commit', '?')}、results/weather_years の直近の実行。"
                    f"公表値の再現 / replication: RP {rep['rp'] / M:.1f}（公表 / published 93.8）、"
                    f"EEV {rep['eev'] / M:.1f}（公表 / published 79.0、未解決 / open）。",
                    f"Source: commit {res.get('git_commit', '?')}, latest run in results/weather_years. "
                    f"Replication of the published numbers: RP {rep['rp'] / M:.1f} (published 93.8), "
                    f"EEV {rep['eev'] / M:.1f} (published 79.0, open)."))

    for stage, title in (("a", pick("50の気象年 × IT高負荷 × 156.8円/L", "50 weather years × IT high × 156.8 yen/L")),
                         ("b", pick("層化した10年 × 公表の4水準（40シナリオ）",
                                    "10 stratified years × the 4 published levels (40 scenarios)"))):
        st.markdown("**" + title + "**")
        rows = []
        for key, label in (("rp", pick("そのシナリオ集合に最適化", "Stochastic on the set")),
                           ("eev", pick("平均シナリオ用の計画", "Plan for the mean scenario")),
                           ("published-4-plan", pick("公表の4シナリオ計画", "Published 4-scenario plan")),
                           ("published-mean-plan", pick("公表の平均シナリオ計画", "Published mean-scenario plan"))):
            p = res["stages"][stage]["plans"].get(key)
            if p is None:
                continue
            rows.append({pick("計画", "Plan"): label, pick("つながる需要家", "Users"): p["sites"],
                         pick("導管（km）", "Pipes (km)"): round(p["km"], 1),
                         pick("期待値（百万円/年）", "Expected (M yen/yr)"): round(p["expected"] / M, 1),
                         pick("最悪年（百万円/年）", "Worst year (M yen/yr)"): round(p["worst"] / M, 1),
                         pick("未供給（平均→最悪年）", "Unmet (avg → worst year)"):
                             f"{p['unmet_expected']:.1%} → {p['unmet_worst']:.1%}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    years_axis = list(range(1976, 2026))
    a_plans = res["stages"]["a"]["plans"]
    series = (("rp", pick("50年に最適化した計画", "Stochastic plan"), INK),
              ("eev", pick("平均年用の計画", "Mean-year plan"), INK2),
              ("published-4-plan", pick("公表の4シナリオ計画", "Published plan"), "#c0392b"))
    lines = pd.DataFrame([{"year": y, "plan": label, "net": v / M}
                          for key, label, _ in series
                          for y, v in zip(years_axis, a_plans[key]["per_scenario"])])
    rule = pd.DataFrame([{"year": year}])
    chart = (alt.Chart(lines).mark_line(strokeWidth=2).encode(
        x=alt.X("year:Q", title=None, axis=alt.Axis(labelColor=INK2, gridColor=GRID)),
        y=alt.Y("net:Q", title=pick("年の純便益（百万円）", "Net in that year (M yen)"),
                axis=alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2)),
        color=alt.Color("plan:N", sort=[label for _, label, _ in series],
                        scale=alt.Scale(domain=[label for _, label, _ in series],
                                        range=[c for _, _, c in series]),
                        title=None, legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("year:Q", title=pick("年", "Year")),
                 alt.Tooltip("plan:N", title=pick("計画", "Plan")),
                 alt.Tooltip("net:Q", format=".1f")])
             + alt.Chart(rule).mark_rule(strokeDash=[4, 3]).encode(x="year:Q"))
    st.altair_chart(chart.properties(height=280).configure(background=SURFACE, font=FONT)
                    .configure_view(stroke=None), use_container_width=True, theme=None)
    st.caption(pick("50年のそれぞれの年で、3つの計画がいくら得るか。破線が下で選んだ年。平均年用の計画が冬に強いのは"
                    "導管が太めだから。公表の計画は平年値だけで作ったにもかかわらず、50年でも健闘している。",
                    "What each of the three plans earns in each of the 50 years; the dashed line is the year "
                    "chosen below. The mean-year plan does well in cold years because its pipes run larger; "
                    "the published plan, built on normals alone, still holds its own across the 50 years."))
    with st.expander(pick("なぜ「確率的計画の価値（VSS）」を気象年どうしで比められないのか（形式上の注記）",
                          "Why the weather-year VSS is not identifiable (formulation note)")):
        st.markdown(pick(
            "このモデルの「つながった需要家に届けられる熱量」は、シナリオ集合の設計ピーク（最も寒いシナリオの最悪月）から"
            "決まり、どの候補構成でも同じです。導管の太さは「その需要家の全ピークを流せるか」の全か無かで接続を決めます。"
            "需要側に揺らぎ（気象年）があると、広い集合で作る計画は太い導管を強制され、狭い集合で作った計画は評価時に"
            "有利になります。決定的な確認: 50年問題のLP緩和の上界は 134.4 で、平均年用の計画の評価値 149.7 を下回る"
            "——つまりその計画は50年問題の実行可能集合の外にあり、比較自体が成立しません。公表の4シナリオは需要が"
            "共通なのでこの制約は効かず、公表の数値はそのまま有効です。恒久的な直しは「届けられる熱量を敷設した"
            "導管の太さに結び付けること」です。",
            "The heat deliverable to a connected user comes from the scenario set's design peak (the worst month "
            "of the worst scenario) and is the same for every candidate build, while pipe sizes gate connectivity "
            "all-or-nothing. With demand-side spread, plans built on wide sets are forced into larger pipes while "
            "plans built on narrow sets are flattered at evaluation. The decisive check: the LP bound of the "
            "50-year model is 134.4, below the mean-year plan's evaluated 149.7 — that plan lies outside the "
            "model's feasible set, so the comparison is not meaningful. The published four scenarios share one "
            "demand, so the convention never bound there and the published numbers stand. The durable fix ties "
            "deliverable capacity to the built pipe size."))

st.subheader(pick(f"{year}年の気象で導管網を作り直すと", f"Re-optimizing the network for {year}"))
w = next(w for w in weather_years() if w.year == year)
st.caption(pick(f"年平均気温 {sum(w.t_day) / len(w.t_day):.1f} ℃、年降雪量 {sum(w.snow_day):.0f} cm、"
                f"最寒月の平均 {min(w.t_month):.1f} ℃。暖房度日指数 {w.hdd18_index:.2f}、降雪指数 {w.snow_index:.2f}"
                "（平年 = 1.00）。",
                f"Annual mean {sum(w.t_day) / len(w.t_day):.1f} °C, snowfall {sum(w.snow_day):.0f} cm, "
                f"coldest-month mean {min(w.t_month):.1f} °C. Heating-degree-day index {w.hdd18_index:.2f}, "
                f"snow index {w.snow_index:.2f} (normals = 1.00)."))
plan = solve_year(year, it_level, price)
hedge = None
if res is not None and len(a_plans["rp"]["per_scenario"]) == len(years_axis):
    hedge = a_plans["rp"]["per_scenario"][years_axis.index(year)]

c = st.columns(5)
c[0].metric(pick("この年の純便益（百万円）", "Net in this year (M yen/yr)"), f"{plan.expected_net / M:,.1f}",
            delta=None if hedge is None else f"{(plan.expected_net - hedge) / M:+,.1f}",
            delta_color="off" if hedge is not None else "normal")
c[1].metric(pick("つながる需要家", "Users connected"), str(len(plan.connected)))
c[2].metric(pick("導管（km）", "Pipes (km)"), f"{plan.pipe_m / 1000:.1f}")
c[3].metric(pick("投資額（億円）", "Investment (100M yen)"), f"{plan.capex / 1e8:,.1f}")
c[4].metric(pick("50年プランでの同じ年", "Same year, 50-year plan"),
            "—" if hedge is None else f"{hedge / M:,.1f}")
raw_gap = (plan.kernel or {}).get("gap")
kgap = float(raw_gap) if raw_gap is not None else (float(plan.gap) if plan.gap is not None else 0.0)
st.caption(pick(f"この年だけに合わせて作った網と、50年分の天候に備えて作った網（実験の計画）を同じ年で比べた差が"
                f"最初の△の値です。最適化 {plan.seconds:.1f} 秒、探索のギャップ {kgap:.0%}"
                "（リンク絞り込み込みのヒューリスティックのため、証明された最適解ではありません）。",
                f"The first delta compares a network built for this year alone with the experiment's plan built "
                f"for all 50 years, both operating in this year. Optimized in {plan.seconds:.1f} s, search gap "
                f"{kgap:.0%} (the link-restricted search is a heuristic: optimality is not certified)."))

rows = []
_, all_sites = load_instance()
for i in plan.connected:
    s = all_sites[i]
    served = float(plan.s[i].sum())
    asked = float(plan.ud.demand[i].sum())
    kja, ken, _, _ = KINDS[s.kind]
    rows.append({pick("施設", "Site"): s.name if ja else s.name_en,
                 pick("種類", "Type"): kja if ja else ken,
                 pick("この年の需要（MWh）", "Demand this year (MWh)"): round(asked),
                 pick("供給（MWh）", "Served (MWh)"): round(served),
                 pick("充足率", "Share served"): f"{served / max(asked, 1e-9):.0%}"})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption(pick("気象年ごとの需要は、平年値の年間需要をその年の毎日の気温と降雪量で再配分したもの"
                "（出典: 気象庁・札幌の観測、data-sources.md）。導管の太さの規約は公表のまま（最悪月ピーク基準）。",
                "Each year's demand re-shapes the normals-year annual demand by that year's daily temperature "
                "and snowfall (source: JMA Sapporo observations, see data-sources.md). The pipe-sizing "
                "convention is the published one (worst-month peak)."))
