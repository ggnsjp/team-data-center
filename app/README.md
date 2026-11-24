# App

The Streamlit demo: `uv run streamlit run app/streamlit_app.py`. Every page has a Japanese / English switch.

| Page | What it shows | Data it needs |
|---|---|---|
| Warm Ishikari | Model v1 for one data center: the optimized network against the top five pairs, with every assumption adjustable | `scripts/fetch_data.py --area ishikari` |
| Warm Ishikari Map | The animated heat-network map (web/heat_story) | `scripts/export_heat_story.py` |
| Warm Ishikari Proposals | Pick a data center, see its five ranked partners, open a one-page proposal and its calculation sheet (download as HTML, print to PDF) | `scripts/export_proposals.py` (a few minutes) and, for the base map, `scripts/export_heat_story.py` |

Themes 2 and 3 have no pages yet. Map data © OpenStreetMap contributors (ODbL); it is downloaded by the scripts and not committed.
