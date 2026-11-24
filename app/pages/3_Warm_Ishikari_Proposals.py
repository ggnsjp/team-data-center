"""Warm Ishikari proposals: pick a data center, see its five ranked heat partners, open a one-page proposal.

Data: `uv run python scripts/export_proposals.py` (out/proposals/proposals.json; solving the regional plan
takes a few minutes). The proposal page itself is drawn here from that data, in the chosen language.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dcopt.heat.proposal import BaseMap, render_html

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "out" / "proposals" / "proposals.json"
BASE = ROOT / "out" / "heat_story" / "base.json"

st.set_page_config(page_title="Warm Ishikari Proposals", layout="wide")
lang = st.radio("表示言語 / Language", ["日本語", "English"], horizontal=True, key="proposal_lang")
L = "ja" if lang == "日本語" else "en"


def pick(ja: str, en: str) -> str:
    return ja if L == "ja" else en


@st.cache_data(show_spinner=False)
def load(stamp: float) -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


@st.cache_resource(show_spinner=False)
def base_map(stamp: float) -> BaseMap | None:
    return BaseMap(json.loads(BASE.read_text(encoding="utf-8"))) if BASE.exists() else None


st.title("Warm Ishikari · " + pick("提案書", "Proposals"))
st.caption(pick("データセンターを選ぶと、地域全体の計画での貢献が大きい順に相手が5件並びます。相手を選ぶと、1枚の提案書と、"
                "すべての数字の根拠（出典・仮定・計算）を示す計算表が開きます。",
                "Pick a data center to see five partners, ranked by what each adds to the regional plan. Pick a partner "
                "to open a one-page proposal and a calculation sheet in which every number shows its source, or is "
                "marked as an assumption."))
if not DATA.exists():
    st.warning(pick("提案書のデータがありません。先に `uv run python scripts/export_proposals.py` を実行してください。",
                    "The proposal data is missing. Run `uv run python scripts/export_proposals.py` first."))
    st.stop()

data = load(DATA.stat().st_mtime)
dcs = {d["key"]: d for d in data["dcs"]}
key = st.selectbox(pick("データセンター", "Data center"), list(dcs),
                   format_func=lambda k: dcs[k]["name"] if L == "ja" else dcs[k]["name_en"])
rows = data["partners"][key]
if not rows:
    st.info(pick("このデータセンターには相手の候補がありません。", "No partner candidates for this data center."))
    st.stop()


def plan_text(r: dict) -> str:
    rg = r["proposal"]["regional"]
    if not rg["in_plan"]:
        return pick("つながない", "not connected")
    if rg["served_by"] == key:
        return pick("このデータセンターから", "from this data center")
    return pick("他のデータセンターから", "from another data center")


table = []
for r in rows:
    p, pr = r["proposal"], r["proposal"]["pair"]
    site = p["site"]
    table.append({
        pick("順位", "Rank"): r["rank"],
        pick("相手", "Partner"): site["name"] if L == "ja" else site["name_en"],
        pick("種類", "Kind"): site["kind_text"][0 if L == "ja" else 1],
        pick("地域の計画", "Regional plan"): plan_text(r),
        pick("地域への貢献（百万円/年）", "Adds to the region (M yen/yr)"):
            round(r["loss"] / 1e6, 1) if r["loss"] is not None else None,
        pick("専用管", "Dedicated pipe"): f"{pr['dist_m'] / 1000:.1f} km, DN{pr['dn']}" if pr else "—",
        pick("ペア単独の純便益（百万円/年）", "Pair alone, net (M yen/yr)"): round(pr["net"] / 1e6, 1) if pr else None,
        pick("回収年数", "Payback (years)"): round(pr["payback"], 1) if pr and pr["payback"] else None,
        pick("双方が得をする熱の価格（円/MWh）", "Heat price that works for both (yen/MWh)"):
            (f"{pr['p_min']:,.0f}–{pr['p_max']:,.0f}" if pr["p_max"] > pr["p_min"] else pick("なし", "none")) if pr else "—",
    })
st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
st.caption(pick("地域への貢献＝地域全体の計画の純便益（期待値）から、同じ導管でこの相手を外した場合の純便益を引いた値。"
                "ペア単独＝データセンターからこの相手だけに専用管を引いた場合。",
                "Adds to the region = the regional plan's expected net benefit minus that of the same pipes without this "
                "partner. Pair alone = a dedicated pipe from the data center to this partner only."))

i = st.selectbox(pick("提案書を開く相手", "Open the proposal for"), range(len(rows)),
                 format_func=lambda j: f"#{rows[j]['rank']} "
                 + (rows[j]["proposal"]["site"]["name"] if L == "ja" else rows[j]["proposal"]["site"]["name_en"]))
doc = render_html(rows[i]["proposal"], L, base_map(BASE.stat().st_mtime if BASE.exists() else 0.0), data["network"])
st.download_button(pick("提案書をダウンロード（HTML、ブラウザで印刷するとPDF）", "Download the proposal (HTML; print it to PDF)"),
                   doc.encode("utf-8"), file_name=f"proposal-{key}-{rows[i]['rank']}-{L}.html", mime="text/html")
components.html(doc, height=1250, scrolling=True)
st.caption(pick("地図データ © OpenStreetMap contributors（ODbL）", "Map data © OpenStreetMap contributors (ODbL)"))
