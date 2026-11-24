"""Team Data Center demo app: `uv run streamlit run app/streamlit_app.py`."""
import streamlit as st

st.set_page_config(page_title="Team Data Center", layout="wide")
lang = st.sidebar.radio("表示言語 / Language", ["日本語", "English"], horizontal=True, key="app_lang")

st.title("Team Data Center")
if lang == "日本語":
    st.markdown("石狩（北海道）のデータセンターの最適化")
    st.markdown("""
| | テーマ | ページ |
|---|---|---|
| 1 | 排熱の導管網 | Warm Ishikari, Warm Ishikari Map, Warm Ishikari Proposals, Warm Ishikari Weather |
| 2 | 系統の受け入れ余地 | 作成中 |
| 3 | 次のデータセンターの立地 | 作成中 |
""")
else:
    st.markdown("Optimization for data centers in Ishikari, Hokkaido")
    st.markdown("""
| | Theme | Page |
|---|---|---|
| 1 | Waste-heat networks | Warm Ishikari, Warm Ishikari Map, Warm Ishikari Proposals, Warm Ishikari Weather |
| 2 | Grid hosting capacity | in progress |
| 3 | Siting the next data center | in progress |
""")
st.caption("地図データ / Map data: © OpenStreetMap contributors (ODbL)" if lang == "日本語"
           else "Map data: © OpenStreetMap contributors (ODbL)")
