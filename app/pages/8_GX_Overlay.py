"""The GX overlay: the zone's energy portfolio (theme 1 x the GX strategic zone).

A page of the main app; the language comes from the app-level switch. The Ishikari Bay New Port
area is part of a METI-certified GX strategic zone (data-center cluster type, certified
2026-09-11). This page draws the area's energy portfolio: the renewables already operating
(offshore and onshore wind, solar), the ones planned or under construction, the data centers
standing and planned, the plots with pre-filed grid applications, and the fossil plants still
running -- every marker with its source. The heat network of theme 1 stays a footnote there.

The dark canvas is the same as web/heat_story. Its data comes from
`uv run python scripts/export_gx_zone.py` (out/gx_zone/gx.json); the same portfolio as Excel workbooks
(one sheet per area, ja and en) from `uv run python scripts/export_gx_portfolio_xlsx.py`; the shared
base map from `uv run python scripts/export_heat_story.py`.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web" / "gx_zone" / "index.html"
DATA = {"gx.json": ROOT / "out" / "gx_zone" / "gx.json",
        "base.json": ROOT / "out" / "heat_story" / "base.json"}

lang = st.session_state.get("app_lang", "日本語")
ja = lang == "日本語"


def pick(a, b):
    return a if ja else b


st.markdown("<style>.block-container{padding-top:1rem;padding-bottom:0}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def page_html(stamp: float) -> str:
    body = PAGE.read_text(encoding="utf-8")
    data = ",".join(f'"{name}":{path.read_text(encoding="utf-8")}' for name, path in DATA.items())
    data = data.replace("</", "<\\/")                      # keep the JSON from closing the script tag
    shim = ("<script>window.__DATA__={" + data + "};"
            "const __fetch=window.fetch.bind(window);"
            "window.fetch=(u,o)=>(u in window.__DATA__)"
            "?Promise.resolve(new Response(JSON.stringify(window.__DATA__[u]))):__fetch(u,o);</script>")
    head = ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<style>body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style></head><body>")
    return head + shim + body + "</body></html>"


st.title(pick("GXオーバーレイ：GXの街は電力で伸びる", "The GX overlay: powered and ready to grow"))
st.caption(
    pick(
        "石狩湾新港地域は経済産業省のGX戦略地域（データセンター集積型、2026年9月11日認定・第1弾）です。"
        "このページは、この地域の電力の姿を地図に描きます：すでに動いている再エネ、建設中・計画の再エネ、"
        "動いているデータセンターとその計画、そしてまだ稼働する火力。地図の印はすべて出典つきです（下の表）。",
        "Ishikari Bay New Port is part of a METI-certified GX strategic zone (data-center cluster "
        "type, certified 2026-09-11, first round). This page maps the area's power: the "
        "renewables already operating, the ones under construction or planned, the data centers standing and "
        "planned, and the fossil plants still running. Every marker carries its source (table below).",
    )
)

missing = [str(p.relative_to(ROOT)) for p in [PAGE, *DATA.values()] if not p.exists()]
if missing:
    missing_txt = "、".join(missing) if ja else ", ".join(missing)
    st.warning(pick("地図のデータがありません：", "Data for the map is missing: ") + missing_txt
               + pick("。先に `uv run python scripts/export_gx_zone.py` と "
                      "`uv run python scripts/export_heat_story.py` を実行してください。",
                      ". Run `uv run python scripts/export_gx_zone.py` and "
                      "`uv run python scripts/export_heat_story.py` first."))
else:
    stamp = max(p.stat().st_mtime for p in [PAGE, *DATA.values()])
    components.html(page_html(stamp), height=2600, scrolling=True)

st.caption(
    pick(
        "GX戦略地域の認定：経済産業省（2026-09-11、データセンター集積型・第1弾）。"
        "再エネの出力・計画：TSH GX事業情報（tsh-gxpf.jp）、各事業者のプレスリリース、石狩市の脱炭素先行地域計画。"
        "道が電力申込済みの用地：北海道の公募要領（2026年10月、石狩市5か所590MW）。"
        "位置が公表されていない施設は地区点または湾内の代表点に置き、表にその旨を記載しています。",
        "GX strategic zone certification: METI (2026-09-11, data-center cluster type, first round). "
        "Renewable capacity and plans: the TSH GX Information Platform (tsh-gxpf.jp), operator press "
        "releases, Ishikari's decarbonization-leading-area plan. Reserved plots: Hokkaido's recruitment "
        "guideline (Oct 2026; 5 sites, 590 MW in Ishikari). Unpublished locations sit at district points "
        "or bay representative points, and the table below says so for each.",
    )
)
