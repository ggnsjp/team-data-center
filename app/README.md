# App

The Streamlit demo: `uv run streamlit run app/streamlit_app.py`. Every page has a Japanese / English switch.

| Page | What it shows | Data it needs |
|---|---|---|
| Warm Ishikari | Model v1 for one data center: the optimized network against the top five pairs, with every assumption adjustable | `scripts/fetch_data.py --area ishikari` |
| Warm Ishikari Map | The animated heat-network map (web/heat_story) | `scripts/export_heat_story.py` |
| Warm Ishikari Proposals | Pick a data center, see its five ranked partners, open a one-page proposal and its calculation sheet (download as HTML, print to PDF) | `scripts/export_proposals.py` (a few minutes) and, for the base map, `scripts/export_heat_story.py` |
| Warm Ishikari Weather | The heat network against the daily weather of 1976-2025: the experiment's results, and the network re-optimized for one chosen year | `scripts/fetch_data.py --area ishikari`; the JMA years ship in `data/jma` (a missing one is downloaded when chosen; if that fails, the page shows the nearest year it has or the climate normals); for the results, `experiments/weather_years/run.py` |
| Grid hosting capacity | Theme 2: how much added load a bus can take, as a bracket between a checked AC point and convex relaxations, on benchmark and built-in systems | nothing for the built-in systems; PGLib-OPF cases are downloaded on request |
| Siting | Theme 3: the value of a new data center's waste heat at each candidate site, the distance to the grid, and a location model | `scripts/export_siting.py` (about a quarter of an hour) |
| Renewable matching | Theme 4: a data center's renewable share counted by the year, by 30-minute slot and on the grid; storage, shifting and the cheapest portfolio | `python -m dcopt.matching.records 2024 2025` (or the button on the page) |

The area supply and demand records of theme 4 come from Hokkaido Electric Power Network and are downloaded, not committed. Map data © OpenStreetMap contributors (ODbL); it is downloaded by the scripts and not committed.
