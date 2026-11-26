"""Warm Ishikari map: the animated heat-network page (web/heat_story) inside the Streamlit demo.

The page draws its own map, so it needs no map tiles. Its data comes from
`uv run python scripts/export_heat_story.py` (out/heat_story/story.json and base.json),
embedded into the page here instead of being fetched.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web" / "heat_story" / "index.html"
DATA = {"story.json": ROOT / "out" / "heat_story" / "story.json",
        "base.json": ROOT / "out" / "heat_story" / "base.json"}

lang = st.session_state.get("app_lang", "日本語")
ja = lang == "日本語"


def pick(a, b):
    return a if ja else b


st.markdown("<style>.block-container{padding-top:1rem;padding-bottom:0}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def map_page_html(page: str, stamp: float) -> str:
    # Streamlit runs every page as __main__ and keys the cache by function name and source, so the
    # name is unique across pages and the page path is part of the key (tests/test_app_cache_keys.py).
    body = Path(page).read_text(encoding="utf-8")
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


missing = [str(p.relative_to(ROOT)) for p in [PAGE, *DATA.values()] if not p.exists()]
if missing:
    missing_txt = "、".join(missing) if ja else ", ".join(missing)
    st.warning(pick("地図のデータがありません：", "Data for the map is missing: ") + missing_txt
               + pick("。先に `uv run python scripts/export_heat_story.py` を実行してください。",
                      ". Run `uv run python scripts/export_heat_story.py` first."))
else:
    stamp = max(p.stat().st_mtime for p in [PAGE, *DATA.values()])
    components.html(map_page_html(str(PAGE), stamp), height=3400, scrolling=True)
