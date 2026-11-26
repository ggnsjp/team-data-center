"""Warm Ishikari Weather: the heat network against 50 years of real weather (v2 model).

Run with the main app: uv run streamlit run streamlit_app.py  (this is its third page).
The robustness panel reads the latest results/weather_years/<timestamp>/results.json written by
experiments/weather_years/run.py; the year selector solves the v2 network for one chosen year.
The years ship in data/jma; a chosen year missing or unreadable there is downloaded from JMA (that
year only). If the download fails, the page says so and shows the nearest year it has, or the climate
normals when it has none.
"""
from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from dcopt.common.geo import fetch_command, missing_map_data
from dcopt.common.style import FONT, GRID, INK, INK2, SURFACE
from dcopt.heat import weather as W
from dcopt.heat.network import Params, Scenario, build_instance, ishikari_sources, plan_for
from dcopt.heat.v1 import DAYS, KINDS, SNOW, TEMP, HeatSourceMissing, ishikari_sites

M = 1e6
YEARS = list(range(W.YEARS[0], W.YEARS[1] + 1))   # the weather years of the experiment and the selector
RUN = "uv run python experiments/weather_years/run.py ambient both --bound"
BAD_RESULTS = (KeyError, TypeError, ValueError, IndexError, AttributeError)   # a results.json of another shape

lang = st.session_state.get("app_lang", "日本語")
ja = lang == "日本語"


def pick(a, b):
    return a if ja else b


@st.cache_resource(show_spinner=False)
def load_instance():
    from dcopt.common.geo import use_overpass_mirror
    use_overpass_mirror()
    sakura, sites = ishikari_sites()
    return build_instance(ishikari_sources(sakura), sites), sites


@st.cache_resource(show_spinner=False)
def weather_years(stamp: tuple) -> list[W.WeatherYear]:
    """The usable years in data/jma; missing or unreadable files are left out. `stamp` lists the files
    and their modification times, so a year downloaded since the last load is picked up."""
    return W.load_cached(YEARS)[0]


def cache_stamp() -> tuple:
    out = []
    for y in YEARS:
        try:
            out.append((y, W.year_csv(y).stat().st_mtime_ns))
        except OSError:                               # not there (yet)
            pass
    return tuple(out)


@st.cache_resource(show_spinner=False)
def solve_year(year: int | None, it_level: str, price: float, _w: W.WeatherYear | None):
    """The network for one weather year (_w is that year's weather; the year is the cache key), or for
    the climate normals when year is None: the monthly demand of the model's default scenarios."""
    if year is None:
        sc = Scenario("normals", f"平年値・IT{it_level}・{price:g}円/L", f"Normals, IT {it_level}, {price:g} yen/L",
                      1.0, price, it_level)
    else:
        sc = Scenario(f"y{year}", f"{year}年・IT{it_level}・{price:g}円/L", f"{year}, IT {it_level}, {price:g} yen/L",
                      1.0, price, it_level, None, _w)
    inst, _ = load_instance()
    return plan_for(inst, Params(mode="ambient", time_limit=60.0), [sc])


def latest_results() -> tuple[dict | None, str | None]:
    """The newest experiment run's results.json and its folder name: (None, None) when the experiment
    has not run yet, (None, folder) when that file cannot be read."""
    root = Path(__file__).resolve().parents[2] / "results" / "weather_years"
    runs = sorted(root.glob("*/results.json"))
    if not runs:
        return None, None
    try:
        res = json.loads(runs[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        res = None
    return (res if isinstance(res, dict) else None), runs[-1].parent.name


def stage_a(res: dict) -> tuple[list[int], dict]:
    """The weather years of an experiment run (all 50 for runs that predate the list) and its stage A plans."""
    plans = ((res.get("stages") or {}).get("a") or {}).get("plans") or {}
    return [int(y) for y in res.get("weather_years") or YEARS], plans


def rp_net(res: dict | None, year: int | None) -> float | None:
    """What the experiment's 50-year plan earns in that year, or None when the run has no such number."""
    if res is None or year is None:
        return None
    try:
        years_axis, plans = stage_a(res)
        nets = plans["rp"]["per_scenario"]
        return float(nets[years_axis.index(year)]) if len(nets) == len(years_axis) else None
    except BAD_RESULTS:
        return None


with st.sidebar:
    st.subheader(pick("シナリオ", "Scenario"))
    year = st.select_slider(pick("気象年", "Weather year"), options=YEARS, value=1984, key="weather_year")
    it_level = st.radio(pick("データセンターのIT負荷", "Data-center IT load"), ["high", "low"], horizontal=True,
                        key="weather_it")
    price = st.slider(pick("灯油価格（円/L）", "Kerosene (yen/L)"), 70.0, 170.0, 156.8, 0.2, key="weather_price")


def weather_for(year: int, cached: list[W.WeatherYear]) -> tuple[W.WeatherYear | None, str | None]:
    """The year's weather from data/jma, downloading that year when it is missing or unreadable there;
    (None, why) when it stays unavailable. A failed download is remembered for the session, so reruns
    (every widget change) do not repeat it; the notice offers a button to try again."""
    w = next((c for c in cached if c.year == year), None)
    if w is not None:
        return w, None
    failed = st.session_state.setdefault("weather_failed", {})
    if year not in failed:
        with st.spinner(pick(f"{year}年の気象データを気象庁から取得中（12か月分、10秒ほど）...",
                             f"Downloading the {year} weather data from JMA (12 monthly pages, about 10 s)...")):
            got, missing = W.ensure_years([year])
        if got:
            return got[0], None
        failed[year] = missing[year]
    return None, failed[year]


def results_panel(res: dict, rule_year: int) -> None:
    """The experiment's tables and its 50-year chart, read-only; parts the run does not have are left out."""
    rep = res["published_replication"]
    recipe = rep.get("eev_recipe") or {}
    eev_note = (pick(f"（公表 79.0。種なしの同じ探索では {recipe.get('no_seeds', 0) / M:.1f}："
                     f"式の違いではなく探索の描画差）",
                     f"(published 79.0; without the seeded links the same search gives "
                     f"{recipe.get('no_seeds', 0) / M:.1f} — a search draw, not a formula)")
                if recipe else pick("（公表 79.0、未解決 / open）", "(published 79.0, open)"))
    st.subheader(pick("実験の結果（読み取り専用）", "Experiment results (read-only)"))
    st.caption(pick(f"出典：commit {res.get('git_commit', '?')}、results/weather_years の直近の実行。"
                    f"公表値の再現：RP {rep['rp'] / M:.1f}（公表 93.8）、"
                    f"EEV {rep['eev'] / M:.1f}{eev_note}。",
                    f"Source: commit {res.get('git_commit', '?')}, latest run in results/weather_years. "
                    f"Replication of the published numbers: RP {rep['rp'] / M:.1f} (published 93.8), "
                    f"EEV {rep['eev'] / M:.1f}{eev_note}."))
    gaps = [int(y) for y in res.get("missing_years") or {}]
    if gaps:                        # the run went on without the years it could not download
        used = len(res.get("weather_years") or [])
        st.warning(pick(f"この実行で使えた気象年は {used} 年分です（欠けている年: {W.year_spans(gaps)}）。全50年で"
                        f"計算し直すには `{W.COMMAND}` のあと、実験をもう一度実行してください。",
                        f"This run used {used} weather years (missing: {W.year_spans(gaps)}). To recompute on all "
                        f"50, run `{W.COMMAND}`, then the experiment again."))

    stages = res.get("stages") or {}
    for stage, title in (("a", pick("50の気象年 × IT高負荷 × 156.8円/L", "50 weather years × IT high × 156.8 yen/L")),
                         ("b", pick("層化した10年 × 公表の4水準（40シナリオ）",
                                    "10 stratified years × the 4 published levels (40 scenarios)"))):
        if stage not in stages:
            continue
        st.markdown("**" + title + "**")
        rows = []
        for key, label in (("rp", pick("そのシナリオ集合に最適化", "Stochastic on the set")),
                           ("eev", pick("平均シナリオ用の計画", "Plan for the mean scenario")),
                           ("published-4-plan", pick("公表の4シナリオ計画", "Published 4-scenario plan")),
                           ("published-mean-plan", pick("公表の平均シナリオ計画", "Published mean-scenario plan"))):
            p = stages[stage]["plans"].get(key)
            if p is None:
                continue
            rows.append({pick("計画", "Plan"): label, pick("つながる需要家", "Users"): p["sites"],
                         pick("導管（km）", "Pipes (km)"): round(p["km"], 1),
                         pick("期待値（百万円/年）", "Expected (M yen/yr)"): round(p["expected"] / M, 1),
                         pick("最悪年（百万円/年）", "Worst year (M yen/yr)"): round(p["worst"] / M, 1),
                         pick("未供給（平均→最悪年）", "Unmet (avg → worst year)"):
                             f"{p['unmet_expected']:.1%} → {p['unmet_worst']:.1%}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    years_axis, a_plans = stage_a(res)
    series = [(key, label, color) for key, label, color in (
        ("rp", pick("50年に最適化した計画", "Stochastic plan"), INK),
        ("eev", pick("平均年用の計画", "Mean-year plan"), INK2),
        ("published-4-plan", pick("公表の4シナリオ計画", "Published plan"), "#c0392b"))
        if len((a_plans.get(key) or {}).get("per_scenario") or []) == len(years_axis)]
    if series:
        lines = pd.DataFrame([{"year": y, "plan": label, "net": v / M}
                              for key, label, _ in series
                              for y, v in zip(years_axis, a_plans[key]["per_scenario"])])
        rule = pd.DataFrame([{"year": rule_year}])
        chart = (alt.Chart(lines).mark_line(strokeWidth=2).encode(
            x=alt.X("year:Q", title=None, axis=alt.Axis(labelColor=INK2, gridColor=GRID)),
            y=alt.Y("net:Q", title=pick("年の純便益（百万円）", "Net in that year (M yen)"),
                    axis=alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2)),
            color=alt.Color("plan:N", sort=[label for _, label, _ in series],
                            scale=alt.Scale(domain=[label for _, label, _ in series],
                                            range=[c for _, _, c in series]),
                            title=None, legend=alt.Legend(orient="bottom", labelColor=INK2)),
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


res, run = latest_results()
st.title("Warm Ishikari Weather · " + pick("50年の気象で試す導管網", "The heat network against 50 years of weather"))
st.caption(pick("平年値だけの計画を、1976〜2025年の実際の毎日の気象（気象庁・札幌）で試します。上のセクションは実験の結果、"
                "下のセクションは選んだ年の気象で導管網を作り直した場合です。",
                "The plan built on climate normals, tested against the actual daily weather of 1976-2025 "
                "(JMA, Sapporo). The top section shows the experiment's results; the bottom re-optimizes "
                "the network for one chosen year."))

with st.spinner(pick("50年分の気象データを読み込み中…", "Loading 50 years of weather…")):
    cached = weather_years(cache_stamp())
w, why = weather_for(year, cached)
if w is None:                       # the nearest year it has instead, else the climate normals
    w = min(cached, key=lambda c: (abs(c.year - year), c.year), default=None)
shown = None if w is None else w.year
if why is not None:
    reason = why.removeprefix("download failed: ").replace("`", "'")[:200]
    if shown is not None:
        instead = pick(f"代わりに、手元にある最も近い年（{shown}年）を表示しています。",
                       f"Showing {shown} instead, the nearest year available here.")
    else:
        instead = pick("代わりに、平年値（気象年なし。モデルの既定のシナリオと同じ月別の需要）で導管網を作り直しています。",
                       "Showing the climate normals instead: the monthly demand of the model's default scenarios, "
                       "without a weather year.")
    st.warning(pick(f"{year}年の気象データ（気象庁・札幌の日別値）が `data/jma` になく、気象庁からの取得にも"
                    f"失敗しました（`{reason}`）。{instead}足りない年は次のコマンドで取得できます：",
                    f"The {year} weather data (JMA daily observations, Sapporo) is not in `data/jma`, and "
                    f"downloading it from JMA failed (`{reason}`). {instead} Fetch the missing years with:"))
    st.code(W.COMMAND)
    st.button(pick("もう一度取得する", "Try the download again"), key="weather_retry",
              on_click=st.session_state["weather_failed"].pop, args=(year, None))   # forget the failure, retry
known = cached + ([w] if w is not None and all(c.year != w.year for c in cached) else [])
imputed = [f"{c.year}年 {c.n_missing_t}日" if ja else f"{c.year} ({c.n_missing_t} d)" for c in known if c.n_missing_t]
if imputed:
    st.warning(pick("観測のない日は、同じ月の他の日の平均で補いました：",
                    "Days without a temperature observation were imputed from their month's other days: ")
               + ("、".join(imputed) if ja else ", ".join(imputed)))

if res is None and run is None:
    st.info(pick(f"実験結果がまだありません: `{RUN}`。下の年ごとの最適化は、実験結果がなくても使えます。",
                 f"No experiment results yet: `{RUN}`. The per-year optimization below works without them."))
elif res is None:
    st.warning(pick(f"実験結果 `results/weather_years/{run}/results.json` を読み込めません。実験をもう一度実行して"
                    f"ください: `{RUN}`。下の年ごとの最適化は、そのまま使えます。",
                    f"The experiment results in `results/weather_years/{run}/results.json` cannot be read. Run the "
                    f"experiment again: `{RUN}`. The per-year optimization below works without them."))
else:
    try:
        results_panel(res, year if shown is None else shown)
    except BAD_RESULTS as e:
        st.warning(pick(f"実験結果 `results/weather_years/{run}/results.json` の形式が想定と違うため、一部を表示"
                        f"できません（`{e!r}`）。実験をもう一度実行してください: `{RUN}`",
                        f"The experiment results in `results/weather_years/{run}/results.json` have an unexpected "
                        f"shape, so part of them cannot be shown (`{e!r}`). Run the experiment again: `{RUN}`"))

if w is None:
    st.subheader(pick("平年値の気象で導管網を作り直すと", "Re-optimizing the network for the climate normals"))
    t_mean = sum(t * d for t, d in zip(TEMP, DAYS)) / sum(DAYS)
    st.caption(pick(f"平年値（1991〜2020年）: 年平均気温 {t_mean:.1f} ℃、年降雪量 {sum(SNOW):.0f} cm、"
                    f"最寒月の平均 {min(TEMP):.1f} ℃。暖房度日指数・降雪指数は定義により 1.00。",
                    f"Climate normals (1991-2020): annual mean {t_mean:.1f} °C, snowfall {sum(SNOW):.0f} cm, "
                    f"coldest-month mean {min(TEMP):.1f} °C. Both indices are 1.00 by definition."))
else:
    st.subheader(pick(f"{shown}年の気象で導管網を作り直すと", f"Re-optimizing the network for {shown}"))
    st.caption(pick(f"年平均気温 {sum(w.t_day) / len(w.t_day):.1f} ℃、年降雪量 {sum(w.snow_day):.0f} cm、"
                    f"最寒月の平均 {min(w.t_month):.1f} ℃。暖房度日指数 {w.hdd18_index:.2f}、降雪指数 {w.snow_index:.2f}"
                    "（平年 = 1.00）。",
                    f"Annual mean {sum(w.t_day) / len(w.t_day):.1f} °C, snowfall {sum(w.snow_day):.0f} cm, "
                    f"coldest-month mean {min(w.t_month):.1f} °C. Heating-degree-day index {w.hdd18_index:.2f}, "
                    f"snow index {w.snow_index:.2f} (normals = 1.00)."))
if missing := missing_map_data():
    st.warning(pick(f"導管網を作り直すには石狩市の地図データが必要ですが、まだありません（未取得: "
                    f"{', '.join(f.name for f in missing)}）。上の気象の数字はそのまま使えます。地図データを取得してから、"
                    "このページを開き直してください（数分かかります）。",
                    f"Re-optimizing the network needs Ishikari's map data, which is not here yet (not fetched: "
                    f"{', '.join(f.name for f in missing)}). The weather figures above still apply. Fetch the map "
                    "data, then reload this page (it takes a few minutes)."))
    st.code(fetch_command(), language="bash")
    st.stop()
with st.spinner(pick("その年の気象で導管網を最適化中…", "Optimizing the network for this year…")):
    try:
        plan = solve_year(shown, it_level, price, w)
    except HeatSourceMissing as e:
        st.error(pick(e.ja, e.en))
        st.stop()
hedge = rp_net(res, shown)

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
