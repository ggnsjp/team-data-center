"""Team Data Center demo app: `uv run streamlit run app/streamlit_app.py`.

One language switch for the whole app, declared here so it renders once in the sidebar on every
page; the navigation labels follow the selection. Defining pages with st.navigation makes
Streamlit ignore the pages/ directory convention, so the pages are listed explicitly.
"""
import streamlit as st

st.set_page_config(page_title="Team Data Center", layout="wide", initial_sidebar_state="expanded")


def pick_for(lang: str):
    return (lambda a, b: a) if lang == "日本語" else (lambda a, b: b)


def home() -> None:
    lang = st.session_state.get("app_lang", "日本語")
    p = pick_for(lang)
    st.title("Team Data Center")
    if lang == "日本語":
        st.markdown("石狩（北海道）のデータセンターの最適化")
        st.markdown("""
| | テーマ | ページ |
|---|---|---|
| 1 | 排熱の導管網 | 排熱の導管網・アニメーション・提案書・気象年で試す |
| 2 | 系統の受け入れ余地 | 系統の受け入れ余地（公開の試験系統で検証） |
| 3 | 次のデータセンターの立地 | 立地（排熱の価値と系統への距離による最初のふるい分け） |
| 4 | 時間ごとに見た再エネ利用 | 再エネの一致（北海道エリアの30分ごとの需給実績で数える） |
""")
    else:
        st.markdown("Optimization for data centers in Ishikari, Hokkaido")
        st.markdown("""
| | Theme | Page |
|---|---|---|
| 1 | Waste-heat networks | Waste-heat network, Animation, Proposals, Weather years |
| 2 | Grid hosting capacity | Grid hosting capacity (checked on benchmark systems) |
| 3 | Siting the next data center | Siting (a first screen by heat value and distance to the grid) |
| 4 | Renewable electricity, slot by slot | Renewable matching (counted on the area's 30-minute supply and demand records) |
""")


pick = pick_for(st.session_state.get("app_lang") or st.query_params.get("lang") or "日本語")
if "app_lang" not in st.session_state:                 # a reload starts a fresh session: seed it
    st.session_state["app_lang"] = st.query_params.get("lang") or "日本語"
lang = st.sidebar.radio(pick("表示言語", "Language"), ["日本語", "English"], horizontal=True,
                        key="app_lang", label_visibility="collapsed")
if st.query_params.get("lang") != lang:                # keep the URL in sync so reloads keep the choice
    st.query_params["lang"] = lang
pick = pick_for(lang)

pages = [
    st.Page(home, title=pick("ホーム", "Home"), url_path="", default=True),
    st.Page("pages/1_Warm_Ishikari.py", title=pick("排熱の導管網", "Waste-heat network"),
            url_path="Warm_Ishikari"),
    st.Page("pages/2_Warm_Ishikari_Map.py", title=pick("アニメーション", "Animation"),
            url_path="Warm_Ishikari_Map"),
    st.Page("pages/3_Warm_Ishikari_Proposals.py", title=pick("提案書", "Proposals"),
            url_path="Warm_Ishikari_Proposals"),
    st.Page("pages/4_Warm_Ishikari_Weather.py", title=pick("気象年で試す", "Weather years"),
            url_path="Warm_Ishikari_Weather"),
    st.Page("pages/5_Grid_Hosting.py", title=pick("系統の受け入れ余地", "Grid hosting capacity"),
            url_path="Grid_Hosting"),
    st.Page("pages/6_Siting.py", title=pick("立地", "Siting"), url_path="Siting"),
    st.Page("pages/7_Matching.py", title=pick("再エネの一致", "Renewable matching"), url_path="Matching"),
]
st.navigation(pages).run()
st.caption(pick("地図データ © OpenStreetMap contributors（ODbL）", "Map data © OpenStreetMap contributors (ODbL)"))
