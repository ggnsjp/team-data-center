"""Renewable electricity, slot by slot (theme 4): three ways of counting the same year.

A page of the main app; the language comes from the app-level switch. Every number is computed by
dcopt.matching when the page runs, from the 30-minute area records that Hokkaido Electric Power
Network publishes. The records are downloaded into data/cache/hepco_area/ and are not part of the
repository (`uv run python -m dcopt.matching.records 2024 2025`).
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from dcopt.common.style import AXIS, FONT, GRID, INK, INK2, SLOTS, SURFACE
from dcopt.matching import records, score, system
from dcopt.matching.portfolio import Costs, cheapest, solver_name

lang = st.session_state.get("app_lang", "日本語")
ja = lang == "日本語"
YEARS = (2024, 2025)
BLUES = ["#a9c9ee", "#6ea3e0", "#2a78d6", "#0d2f66"]      # one hue, light to dark: more solar and wind
PAD = {"left": 14, "right": 14, "top": 14, "bottom": 14}


def pick(a, b):
    return a if ja else b


def pct(x: float, digits: int = 0) -> str:
    return f"{100 * x:.{digits}f} %"


def axis(**kw):
    return alt.Axis(gridColor=GRID, labelColor=INK2, titleColor=INK2, domainColor=AXIS, **kw)


def show(chart, height: int) -> None:
    st.altair_chart(chart.properties(height=height, padding=PAD).configure(background=SURFACE, font=FONT)
                    .configure_view(stroke=None), width="stretch", theme=None)


@st.cache_data(show_spinner=False)
def table(fy: int, stamp: float) -> pd.DataFrame:
    return records.load_fiscal_year(fy, download=False)


@st.cache_data(show_spinner=False)
def solve(fy: int, stamp: float, target: float, battery: bool, costs: Costs):
    df = table(fy, stamp)
    load = score.flat_load(len(df), 1.0)
    r = cheapest(load, score.shaped(df["solar"], load), score.shaped(df["wind"], load), target, costs, battery)
    return r.feasible, r.solar, r.wind, r.battery_mw, r.battery_h, r.yen_per_kwh_used, r.solver


def stamp_of() -> float:
    return max((p.stat().st_mtime for p in records.DIR.glob("*.csv")), default=0.0) if records.DIR.exists() else 0.0


st.title(pick("時間ごとに見た再エネ利用", "Renewable electricity, slot by slot"))
st.caption(pick(
    "データセンターの電力調達を考える事業者と、地域の再エネ計画に関わる自治体・電力の担当者が、「再エネ100%」の中身を同じ数字で"
    "確かめるためのページです。北海道電力ネットワークが公表している30分ごとの需給実績を使い、同じ1年を3つの数え方で並べます。"
    "数値はすべて試算です。",
    "For operators deciding how to buy power for a data center, and for municipalities and grid planners working on "
    "renewable plans: a common set of numbers behind the words \"100 % renewable\". The page uses the 30-minute area "
    "records published by Hokkaido Electric Power Network and counts the same year in three ways. All numbers are "
    "estimates."))

have = [fy for fy in records.cached_fiscal_years() if fy in YEARS]
if not have:
    st.warning(pick(
        "需給実績のデータがまだありません。下のボタンで北海道電力ネットワークのサイトから取得するか、"
        "`uv run python -m dcopt.matching.records 2024 2025` を実行してください（24ファイル、約4 MB）。",
        "The area records are not here yet. Download them from the operator's site with the button below, or run "
        "`uv run python -m dcopt.matching.records 2024 2025` (24 files, about 4 MB)."))
    if st.button(pick("需給実績を取得する", "Download the records"), key="match_fetch"):
        with st.spinner(pick("取得しています…", "Downloading…")):
            got = [fy for fy in YEARS if all(records.ensure_month(y, m) for y, m in records.fiscal_year(fy))]
        if got:
            st.rerun()
        st.error(pick("取得できませんでした。ネットワーク接続を確認してください。",
                      "The download failed. Check the network connection."))
    st.stop()

stamp = stamp_of()
with st.sidebar:
    st.subheader(pick("データセンターと契約", "Data center and contract"))
    fy = st.radio(pick("年度（4月〜翌3月）", "Fiscal year (April to March)"), have, index=len(have) - 1, horizontal=True,
                  key="match_fy", format_func=lambda y: pick(f"{y}年度", f"FY{y}"))
    df = table(fy, stamp)
    fleet = score.fleet_solar_share(df)
    mw = st.slider(pick("データセンターの使用電力（MW、一定）", "Power drawn by the data center (MW, constant)"),
                   10, 1000, 100, 10, key="match_mw",
                   help=pick("1年を通して一定という仮定です。実測の負荷曲線が得られれば置き換えます。",
                             "Constant through the year: an assumption, to be replaced by measured load profiles."))
    volume = st.slider(pick("契約する再エネの量（年間使用量の何倍か）", "Renewable energy contracted (times the yearly use)"),
                       0.0, 4.0, 1.0, 0.1, key="match_volume")
    solar_pct = st.slider(pick("そのうち太陽光の割合（%）。残りは風力", "Share of it from solar (%); the rest is wind"),
                          0, 100, round(100 * fleet), 1, key="match_solar",
                          help=pick(f"初期値は、この年度の北海道エリアの太陽光と風力の発電量の比（太陽光 {100 * fleet:.0f} %）です。",
                                    f"The default is the area's own solar-to-wind energy ratio in this year ({100 * fleet:.0f} % solar)."))
    hours = st.slider(pick("蓄電池の容量（使用電力の何時間分か）", "Battery capacity (hours of the data center's power)"),
                      0.0, 24.0, 0.0, 0.5, key="match_hours",
                      help=pick("出力は使用電力と同じ、充放電の往復効率は85 %（仮定）。契約した再エネの余りだけを充電します。",
                                "Power equal to the data center's; round-trip efficiency 85 % (assumption). It charges "
                                "only from the contract's own surplus."))
    st.subheader(pick("系統での数え方", "Counting on the grid"))
    floor0 = system.thermal_floor(df)
    floor = st.slider(pick("火力がこれ以上は下げられない出力（MW）", "Level below which thermal plants cannot turn down (MW)"),
                      0, 1500, int(round(floor0, -1)), 10, key=f"match_floor_{fy}",
                      help=pick(f"初期値は、この年度に太陽光・風力が抑制されていたコマの火力出力のうち、低いほうの値（下から10 %の位置、{floor0:.0f} MW）です。"
                                f"1年の最小値は {records.thermal(df).min():.0f} MW でした。",
                                f"The default is the low end (10th percentile) of thermal output in the slots where solar "
                                f"or wind was curtailed in this year ({floor0:.0f} MW). The lowest value of the year was "
                                f"{records.thermal(df).min():.0f} MW."))

n = len(df)
load = score.flat_load(n, float(mw))
gen = score.contracted(df, load, volume, solar_pct / 100.0)
got = score.with_storage(load, gen, float(mw), float(mw) * hours) if hours > 0 else np.minimum(load, gen)
sc = score.score(load, got, gen)
old = system.replay(df, load, 0.0, floor)
new = system.replay(df, load, gen, floor)
used_gwh = system.gwh(load)

# ------------------------------------------------------------------ three ways of counting
st.subheader(pick("同じ1年を、3つの数え方で", "One year, counted three ways"))
c = st.columns(4)
c[0].metric(pick("① 年間の量で", "1. By the year"), pct(sc.volume),
            help=pick("契約した再エネの年間発電量 ÷ 年間使用量。証書による「再エネ100%」はこの数え方です。",
                      "Renewable energy contracted over the year / energy used. \"100 % renewable\" by certificates "
                      "is counted this way."))
c[1].metric(pick("② 30分ごとに", "2. By 30-minute slot"), pct(sc.matched),
            help=pick("使った電力のうち、同じ30分のコマに契約の再エネが発電していた分（蓄電池を置いた場合は、ためて返した分を含む）。",
                      "The share of the energy used that the contract generated in the same 30-minute slot "
                      "(with a battery: including what it stored and returned)."))
c[2].metric(pick("③ 系統：既存の発電所から", "3. Grid: existing plants"),
            pct(old.thermal_per_added_load),
            help=pick("データセンターが加わったことで増える火力の発電量 ÷ 使用量。発電所が増えなければ、増えた需要のほぼ全部を火力が賄います。"
                      "差し引かれるのは、抑制されていた太陽光・風力を使えた分だけです。",
                      "Extra thermal generation caused by the data center / energy used. With no new plant, thermal "
                      "plants cover nearly all of the added demand; only the curtailed solar and wind it could use "
                      "is taken off."))
c[3].metric(pick("③ 系統：新しい発電所を建設", "3. Grid: new plants built"),
            ("+" if new.thermal_change_gwh >= 0 else "−") + pct(abs(new.thermal_per_added_load)),
            help=pick("契約の分だけ太陽光・風力が新しく建つ場合の、火力の発電量の増減 ÷ 使用量。マイナスは、火力が減ることを示します。",
                      "Change in thermal generation / energy used, when the contracted solar and wind are newly "
                      "built. A minus sign means thermal generation falls."))
st.markdown(pick(
    f"{mw} MWのデータセンターは1年に **{used_gwh:,.0f} GWh** を使います。契約した再エネは年間で使用量の **{pct(sc.volume)}** ですが、"
    f"同じ30分に届いていたのは **{pct(sc.matched)}** です。残りの **{pct(sc.unmatched)}** は、ほかの電源が賄いました。"
    f"系統全体で見ると、既存の発電所から買うだけなら火力が **{old.thermal_change_gwh:,.0f} GWh** 増え、"
    f"同じ量の発電所を新しく建てれば火力の増減は **{new.thermal_change_gwh:+,.0f} GWh** です。",
    f"A {mw} MW data center uses **{used_gwh:,.0f} GWh** a year. The contract covers **{pct(sc.volume)}** of that over "
    f"the year, but only **{pct(sc.matched)}** arrived in the same 30-minute slot; other plants supplied the remaining "
    f"**{pct(sc.unmatched)}**. On the grid as a whole, buying from existing plants raises thermal generation by "
    f"**{old.thermal_change_gwh:,.0f} GWh**; building new plants of the same volume changes it by "
    f"**{new.thermal_change_gwh:+,.0f} GWh**."))

# ------------------------------------------------------------------ one week
st.subheader(pick("1週間を30分ごとに見る", "One week, slot by slot"))
days = n // records.SLOTS_PER_DAY
per_day = np.minimum(load, got)[: days * 48].reshape(days, 48).sum(axis=1)
week_sum = np.convolve(per_day, np.ones(7), mode="valid")
choice = st.radio(pick("表示する週", "Week shown"), ["low", "high", "pick"], horizontal=True, key="match_week",
                  format_func=lambda k: {"low": pick("一致がいちばん低い週", "the week with the lowest match"),
                                         "high": pick("一致がいちばん高い週", "the week with the highest match"),
                                         "pick": pick("日付で選ぶ", "choose a date")}[k], label_visibility="collapsed")
if choice == "pick":
    day0 = st.date_input(pick("週のはじめの日", "First day of the week"), df.index[0].date(), min_value=df.index[0].date(),
                         max_value=df.index[(days - 7) * 48].date(), key=f"match_day_{fy}")
    d0 = int((pd.Timestamp(day0) - df.index[0].normalize()).days)
else:
    d0 = int(np.argmin(week_sum) if choice == "low" else np.argmax(week_sum))
sl = slice(d0 * 48, (d0 + 7) * 48)
names = [pick("同じコマに届いた再エネ", "Matched in the same slot"),
         pick("ほかの電源が賄った分", "Supplied by other plants"),
         pick("契約の発電量", "Output of the contract")]
colors = alt.Scale(domain=names, range=[SLOTS[0], GRID, SLOTS[1]])
legend = alt.Legend(title=None, orient="bottom", labelColor=INK2, symbolType="square", labelLimit=320)
wk = pd.DataFrame({"slot": df.index[sl], names[0]: np.minimum(load, got)[sl],
                   names[1]: (load - np.minimum(load, got))[sl]})
out = pd.DataFrame({"slot": df.index[sl], "mw": gen[sl], "series": names[2]})
area = alt.Chart(wk.melt("slot", names[:2], "series", "mw").assign(
    rank=lambda d: (d["series"] == names[1]).astype(int))).mark_area(interpolate="step-after").encode(
    x=alt.X("slot:T", title=None, axis=axis(format=pick("%m/%d", "%b %d"), tickCount="day", grid=False)),
    y=alt.Y("mw:Q", stack="zero", title="MW", axis=axis()),
    color=alt.Color("series:N", scale=colors, legend=legend), order=alt.Order("rank:Q"),
    tooltip=[alt.Tooltip("slot:T", title=pick("コマの開始", "Slot start"), format="%Y-%m-%d %H:%M"),
             alt.Tooltip("series:N", title=pick("内訳", "Part")), alt.Tooltip("mw:Q", title="MW", format=",.0f")])
line = alt.Chart(out).mark_line(strokeWidth=2, interpolate="step-after").encode(
    x="slot:T", y="mw:Q", color=alt.Color("series:N", scale=colors, legend=legend),
    tooltip=[alt.Tooltip("slot:T", title=pick("コマの開始", "Slot start"), format="%Y-%m-%d %H:%M"),
             alt.Tooltip("mw:Q", title=names[2] + " (MW)", format=",.0f")])
show(alt.layer(area, line), 300)
wk_share = float(np.minimum(load, got)[sl].sum() / load[sl].sum())
st.caption(pick(
    f"{df.index[sl][0]:%Y年%m月%d日} からの7日間。この週の一致は {pct(wk_share)}。橙の線が使用電力（{mw} MW）より上にある時間は再エネが余り、"
    "下にある時間はほかの電源が賄っています。年間の量が足りていても、風の弱い日が続く週はこうなります。",
    f"Seven days from {df.index[sl][0]:%d %B %Y}; the match over this week is {pct(wk_share)}. Where the orange line is "
    f"above the data center's power ({mw} MW) the contract has a surplus; where it is below, other plants fill in. "
    "This is what a week of weak wind looks like even when the yearly volume is enough."))

# ------------------------------------------------------------------ what raises the match
st.subheader(pick("30分ごとの一致を上げるには", "What raises the slot-by-slot match"))
left, right = st.columns(2, gap="medium")
with left:
    st.markdown("**" + pick("契約量を増やす", "Contracting more") + "**")
    xs = np.round(np.arange(0.0, 4.01, 0.25), 2)
    kinds = [(pick("風力だけ", "wind only"), 0.0), (pick("太陽光だけ", "solar only"), 1.0),
             (pick("エリアの構成比", "the area's mix"), fleet)]
    rows = [{"x": float(x), "series": k, "share": score.score(load, score.contracted(df, load, x, a)).matched}
            for k, a in kinds for x in xs]
    order = [k for k, _ in kinds]
    curve = alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2).encode(
        x=alt.X("x:Q", title=pick("契約量（年間使用量の何倍か）", "Contracted volume (times the yearly use)"), axis=axis()),
        y=alt.Y("share:Q", title=pick("30分ごとの一致", "Slot-by-slot match"), scale=alt.Scale(domain=[0, 1]),
                axis=axis(format=".0%")),
        color=alt.Color("series:N", sort=order, scale=alt.Scale(domain=order, range=SLOTS[:3]),
                        legend=alt.Legend(title=None, orient="bottom", labelColor=INK2)),
        tooltip=[alt.Tooltip("series:N", title=pick("構成", "Mix")),
                 alt.Tooltip("x:Q", title=pick("契約量（倍）", "Volume (times)")),
                 alt.Tooltip("share:Q", title=pick("一致", "Match"), format=".1%")])
    here = pd.DataFrame([{"x": volume, "share": score.score(load, gen).matched,
                          "label": pick("いまの設定", "your setting")}])
    dot = alt.Chart(here).mark_point(size=110, filled=True, color=INK, stroke=SURFACE, strokeWidth=2).encode(
        x="x:Q", y="share:Q", tooltip=[alt.Tooltip("label:N", title=" "),
                                       alt.Tooltip("share:Q", title=pick("一致", "Match"), format=".1%")])
    show(alt.layer(curve, dot), 300)
    st.caption(pick("黒い点がいまの設定（蓄電池なし）。量を増やすほど一致は上がりますが、上がり方は鈍くなります。余った分は、ほかの需要家が使うか、抑制されます。",
                    "The black dot is your setting (without the battery). More volume raises the match, with "
                    "diminishing returns. The surplus is used by others or curtailed."))
with right:
    st.markdown("**" + pick("蓄電池を置く", "Adding a battery") + "**")
    hs = [0, 1, 2, 4, 6, 8, 12, 16, 24]
    rows = [{"h": h, "share": score.score(load, score.with_storage(load, gen, float(mw), float(mw) * h), gen).matched}
            for h in hs]
    bat = alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2, color=SLOTS[0],
                                                  point=alt.OverlayMarkDef(size=60, filled=True, color=SLOTS[0])).encode(
        x=alt.X("h:Q", title=pick("蓄電池の容量（使用電力の何時間分か）", "Battery capacity (hours of the data center's power)"),
                axis=axis()),
        y=alt.Y("share:Q", title=pick("30分ごとの一致", "Slot-by-slot match"), scale=alt.Scale(domain=[0, 1]),
                axis=axis(format=".0%")),
        tooltip=[alt.Tooltip("h:Q", title=pick("容量（時間）", "Capacity (hours)")),
                 alt.Tooltip("share:Q", title=pick("一致", "Match"), format=".1%")])
    show(bat, 300)
    st.caption(pick("いまの契約に蓄電池を足した場合。数時間分までは効きますが、風の弱い日が何日も続く分は、電池では埋まりません。",
                    "Your contract with a battery added. The first hours help; the days of weak wind in a row are "
                    "beyond what a battery covers."))

st.markdown("**" + pick("仕事の時間をずらす", "Moving work within the day") + "**")
f1, f2 = st.columns(2, gap="medium")
flexible = f1.slider(pick("同じ日の中でずらせる仕事の割合（%）", "Share of the day's work that can move within the day (%)"),
                     0, 100, 20, 5, key="match_flex") / 100.0
headroom = f2.slider(pick("そのために余分に持つ設備（%）", "Spare equipment kept for it (%)"), 0, 300, 25, 5,
                     key="match_headroom") / 100.0
moved = score.shifted_share(load, gen, flexible, headroom)
st.markdown(pick(
    f"契約はそのまま（蓄電池なし）で、1日の仕事の {pct(flexible)} を再エネの多い時間に寄せると、一致は **{pct(score.score(load, gen).matched)} → "
    f"{pct(moved)}** になります。そのかわり、設備を {pct(headroom)} 余分に持つことになり、設備の平均利用率は **{pct(1 / (1 + headroom))}** に下がります。"
    "高価な計算機を止めておく時間が増えるため、事業者には動機が生まれにくい方法です。",
    f"With the same contract and no battery, moving {pct(flexible)} of each day's work towards the slots with more "
    f"renewable output takes the match from **{pct(score.score(load, gen).matched)} to {pct(moved)}**. The price is "
    f"{pct(headroom)} more equipment, whose mean use falls to **{pct(1 / (1 + headroom))}**. Expensive computers stand "
    "idle for longer, which gives an operator little reason to do it."))

# ------------------------------------------------------------------ the area as data centers and renewables grow
st.subheader(pick("データセンターと再エネがともに増えると、火力は減るか", "More data centers and more renewables: does thermal generation fall?"))
factors = [1.0, 1.5, 2.0, 3.0]
label = {k: pick(f"太陽光・風力 ×{k:g}", f"solar and wind ×{k:g}") for k in factors}
loads = list(range(0, 1001, 100))
rows = [{"mw": d, "series": label[k], "twh": system.replay(df, float(d), system.scaled_fleet(df, k, k), floor).thermal_gwh / 1000}
        for k in factors for d in loads]
order = [label[k] for k in factors]
grow = alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2).encode(
    x=alt.X("mw:Q", title=pick("増えるデータセンターの電力（MW、一定）", "Added data-center load (MW, constant)"), axis=axis()),
    y=alt.Y("twh:Q", title=pick("火力の年間発電量（TWh）", "Thermal generation in the year (TWh)"), scale=alt.Scale(zero=False),
            axis=axis()),
    color=alt.Color("series:N", sort=order, scale=alt.Scale(domain=order, range=BLUES),
                    legend=alt.Legend(title=None, orient="bottom", labelColor=INK2)),
    tooltip=[alt.Tooltip("series:N", title=pick("再エネ", "Renewables")), alt.Tooltip("mw:Q", title="MW"),
             alt.Tooltip("twh:Q", title="TWh", format=".2f")])
today = pd.DataFrame([{"twh": old.base_thermal_gwh / 1000}])
rule = alt.Chart(today).mark_rule(color=INK2, strokeDash=[5, 4]).encode(
    y="twh:Q", tooltip=[alt.Tooltip("twh:Q", title=pick("この年度の実績（TWh）", "This year's record (TWh)"), format=".2f")])
show(alt.layer(grow, rule), 320)
even = [(k, system.break_even_load(df, system.scaled_fleet(df, k, k), floor)) for k in factors[1:]]
st.markdown(pick(
    f"点線は、この年度の火力の実績（{old.base_thermal_gwh / 1000:.1f} TWh）です。それより上では、火力がいまより増えます。"
    "太陽光・風力が増えても、一定で動く需要がこれだけ増えると、火力の発電量はいまと同じになります： "
    + "、".join(f"×{k:g} で **{v:,.0f} MW**" for k, v in even) + "。",
    f"The dashed line is this year's recorded thermal generation ({old.base_thermal_gwh / 1000:.1f} TWh); above it "
    "thermal plants generate more than today. Even with more solar and wind, this much added round-the-clock load "
    "brings thermal generation back to today's level: "
    + ", ".join(f"×{k:g}: **{v:,.0f} MW**" for k, v in even) + "."))
st.caption(pick(
    "公表された1年分のコマをそのまま使い、水力・バイオマス・揚水・連系線は実績のまま、火力だけが上下すると置いた再計算です。"
    "送電線の制約、連系線や揚水の使い方の変化、発電所の起動停止、原子力の再稼働は入っていません。方向と大きさの目安として読んでください。",
    "A replay of the published slots of one year: hydro, biomass, pumped storage and the interconnection stay as "
    "recorded and only thermal plants move. Network limits, changes in exports or pumping, plant commitment and a "
    "nuclear restart are not included. Read it as the direction and rough size of the effect."))

# ------------------------------------------------------------------ the cheapest portfolio
st.subheader(pick("目標の一致率を、いちばん安く満たす組み合わせ", "The cheapest portfolio for a target match"))
with st.expander(pick("費用の前提（変更できます）", "Cost inputs (editable)")):
    k = st.columns(4)
    c_solar = k[0].number_input(pick("太陽光の契約単価（円/kWh）", "Solar contract price (yen/kWh)"), 1.0, 60.0,
                                Costs().solar_yen_kwh, 0.5, key="match_c_solar")
    c_wind = k[1].number_input(pick("風力の契約単価（円/kWh）", "Wind contract price (yen/kWh)"), 1.0, 60.0,
                               Costs().wind_yen_kwh, 0.5, key="match_c_wind")
    c_batt = k[2].number_input(pick("蓄電池の建設費（円/kWh）", "Battery cost (yen per kWh of capacity)"), 5_000.0, 300_000.0,
                               Costs().battery_yen_kwh, 5_000.0, key="match_c_batt")
    c_sell = k[3].number_input(pick("余った電力の価値（円/kWh）", "Value of the surplus (yen/kWh)"), 0.0, 30.0,
                               Costs().surplus_value_yen_kwh, 0.5, key="match_c_sell")
    st.caption(pick("出典と根拠は docs/data-sources.md にあります。蓄電池は15年・3 %で年額に直し、往復効率85 %、容量は出力の3時間分以上としています。",
                    "Sources and reasons are in docs/data-sources.md. The battery is annualized over 15 years at 3 %, "
                    "with 85 % round-trip efficiency and a capacity of at least three hours of its power."))
t1, t2 = st.columns([3, 2], gap="medium")
target = t1.slider(pick("目標とする30分ごとの一致（%）", "Target slot-by-slot match (%)"), 50, 100, 90, 5, key="match_target") / 100.0
use_battery = t2.toggle(pick("蓄電池を使ってよい", "A battery may be used"), True, key="match_lp_battery")
fast = solver_name() == "gurobi"
if st.button(pick("最適化を解く（数秒）", "Solve (a few seconds)") if fast else
             pick("最適化を解く（30秒〜1分）", "Solve (half a minute to a minute)"), key="match_solve"):
    with st.spinner(pick("線形計画を解いています…", "Solving the linear program…")):
        st.session_state["match_result"] = (fy, target, use_battery) + solve(
            fy, stamp, target, use_battery, Costs(solar_yen_kwh=c_solar, wind_yen_kwh=c_wind, battery_yen_kwh=c_batt,
                                                  surplus_value_yen_kwh=c_sell))
res = st.session_state.get("match_result")
if res:
    r_fy, r_target, r_batt, ok, x_s, x_w, b_mw, b_h, yen, used = res
    if not ok:
        st.warning(pick("この目標は、この条件では満たせません。", "This target cannot be met under these inputs."))
    else:
        st.dataframe(pd.DataFrame([{
            pick("年度", "Fiscal year"): r_fy, pick("目標", "Target"): pct(r_target),
            pick("太陽光（年間使用量の倍数）", "Solar (times the yearly use)"): round(x_s, 2),
            pick("風力（同）", "Wind (same)"): round(x_w, 2),
            pick("契約量の合計（同）", "Contract in total (same)"): round(x_s + x_w, 2),
            pick("蓄電池の出力（使用電力の倍数）", "Battery power (times the load)"): round(b_mw, 2),
            pick("蓄電池の容量（使用電力の時間分）", "Battery capacity (hours of the load)"): round(b_h, 1),
            pick("契約と蓄電池の費用（円/使用kWh）", "Contract and battery (yen per kWh used)"): round(yen, 1)}]),
            hide_index=True, width="stretch")
        name = {"highs": "HiGHS", "gurobi": "Gurobi"}[used]
        st.caption(pick("費用は、契約した再エネの全量と蓄電池の年額を、データセンターの年間使用量で割った値です。一致しなかった分の電力の購入費は含みません。"
                        f"この結果は {name} で解きました（Gurobiは任意で、なくても同じ結果が得られます。あれば数秒で解けます）。",
                        "The cost is the whole contracted energy plus the battery's yearly cost, divided by the energy "
                        "the data center uses. Buying the unmatched energy is not included. "
                        f"Solved with {name} (Gurobi is optional: the result is the same without it, and with it the "
                        "program solves in a few seconds)."))

with st.expander(pick("計算の中身、入力の根拠、限界", "What is computed, where the inputs come from, and the limits")):
    st.markdown(pick(
        "- **データ：** 北海道電力ネットワーク「北海道エリアの需給実績」の30分値（送電端、MW平均）。ここでは値を変えずに使っています。"
        f"この年度は {n:,} コマで、欠けはありません。\n"
        "- **契約の再エネの形：** エリア全体の太陽光・風力の実績と同じ形で発電すると置いています。1つの発電所はエリア全体より変動が大きいので、"
        "実際の一致はこれより低くなります。\n"
        "- **データセンターの負荷：** 1年を通して一定（仮定）。\n"
        "- **蓄電池：** 契約の余りだけを充電し、足りないコマで放電します。往復効率85 %（仮定）。\n"
        "- **系統での数え方：** 需要が増えた分は、抑制されていた太陽光・風力をまず使い、残りは火力が賄うと置いています。"
        "新しい再エネは、火力を下限まで下げ、それでも余れば抑制されます。\n"
        "- **限界：** 1年分の実績をなぞる再計算であり、需給の運用を解いた結果ではありません。数式は docs/formulations/matching.md にあります。",
        "- **Data:** the 30-minute values of Hokkaido Electric Power Network's area supply and demand records (sending "
        f"end, mean MW), used unchanged. This fiscal year has {n:,} slots and no gaps.\n"
        "- **Shape of the contracted renewables:** the same as the area's whole solar and wind fleets. One plant varies "
        "more than the whole area, so a real contract matches less.\n"
        "- **Data-center load:** constant through the year (assumption).\n"
        "- **Battery:** charges only from the contract's surplus and discharges in the slots that fall short; 85 % "
        "round-trip efficiency (assumption).\n"
        "- **Counting on the grid:** added demand first uses solar and wind that were being curtailed, and thermal "
        "plants cover the rest. New renewables turn thermal plants down to their floor and are curtailed beyond that.\n"
        "- **Limits:** a replay of one year's records, not an operating model of the power system. Formulas: "
        "docs/formulations/matching.md."))
st.caption(pick("データ：北海道電力ネットワーク「北海道エリアの需給実績」。このページの計算と解釈は本プロジェクトによるものです。",
                "Data: Hokkaido Electric Power Network, area supply and demand records. The calculations and their "
                "reading on this page are this project's own."))
