"""Team Data Center demo app: `uv run streamlit run app/streamlit_app.py`."""
import streamlit as st

st.set_page_config(page_title="Team Data Center", layout="wide")
st.title("Team Data Center")
st.markdown("石狩（北海道）のデータセンターの最適化  \nOptimization for data centers in Ishikari, Hokkaido")
st.markdown("""
| | テーマ / Theme | ページ / Page |
|---|---|---|
| 1 | 排熱の導管網 / Waste-heat networks | Warm Ishikari, Warm Ishikari Map, Warm Ishikari Proposals, Warm Ishikari Weather |
| 2 | 系統の受け入れ余地 / Grid hosting capacity | 作成中 / in progress |
| 3 | 次のデータセンターの立地 / Siting | 作成中 / in progress |
""")
st.caption("地図データ / Map data: © OpenStreetMap contributors (ODbL)")
