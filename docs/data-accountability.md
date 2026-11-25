# Data accountability

This page answers five questions about the data behind every result and proposal: where the data is stored, how it is kept, how it is processed, how the calculations are kept accurate, and how to show all of this to someone else. Every answer is checked by a test, so this page cannot quietly go out of date.

| Question | Where the answer lives | What keeps it true |
|---|---|---|
| What data do we use, and where is it? | [`data/register.toml`](../data/register.toml): one entry per dataset | `tests/test_data_register.py` fails if a committed data file is missing from the register, or if a file the register names does not exist |
| Is the committed data the data we think it is? | [`data/SHA256SUMS`](../data/SHA256SUMS): the SHA-256 of every committed data file | The same test fails on any byte change. Anyone can check without our code: `cd data && shasum -a 256 -c SHA256SUMS` |
| Where does each number come from? | [`docs/data-sources.md`](data-sources.md): a URL or "assumption" for every value | `tests/test_data_and_docs.py` and `tests/test_proposal.py` (every number on a proposal is marked as a source, an assumption or a calculation) |
| Are the calculations right? | The checks below, in layers | CI runs them on every push |
| Which code and data produced a result? | The `provenance` block saved with each result | `dcopt.common.provenance.stamp()` |

## Where the data is stored

The register uses three kinds of storage:

- **git**: committed to the repository. Its exact bytes are pinned in `data/SHA256SUMS`.
- **code**: values written in a source file. Each one has its source or assumption in `docs/data-sources.md`.
- **local**: downloaded or generated on each machine into a folder git ignores. It is rebuilt by the command in the register entry's `made_by` field. It is never committed.

| Dataset | Storage | Where | Terms |
|---|---|---|---|
| Ishikari data centers (operators, status, IT load range) | git | `data/curated/ishikari_data_centers.csv` | MIT, our own compilation |
| JMA daily observations, Sapporo 47412, 1976–2025 | git | `data/jma/` (50 CSVs, about 200 KB) | JMA Public Data Terms of Use 1.0: credit 「出典：気象庁ホームページ」 and state the processing (`data/jma/README.md`) |
| JMA climate normals 1991–2020 | code | `src/dcopt/heat/v1.py` (`TEMP`, `SNOW`) | JMA terms, source cited in the code |
| Model parameters (prices, efficiencies, pipe costs, peak factors) | code | `src/dcopt/heat/network.py` (`Params`), `v1.py` | MIT, each value with its source or assumption |
| OpenStreetMap for the study area | local | `data/cache/`, `data/raw/` | ODbL 1.0, © OpenStreetMap contributors. Never committed |
| Results, proposal and map exports | local | `results/`, `out/` | Our numbers are MIT. Anything that draws OSM data credits it |

To see the live version of this table, with the checksum status, run `uv run python -m dcopt.common.provenance --report`.

## How it is kept

- **Pinned, not just committed.** Git records who changed a file. `SHA256SUMS` also makes a change fail CI until someone re-pins it on purpose with `--write`, so every change to the data shows up in a pull request.
- **Licensed data stays local.** OSM data is under ODbL and is never committed. `.gitignore` excludes `data/raw/` and `data/cache/`, and a test checks that nothing in those folders is tracked.
- **Data under other terms says how to credit it.** A committed dataset that isn't MIT must have an `attribution` field in the register, and a test enforces this.
- **No secrets.** Solver licences, API keys and `.env` files are ignored and never committed (CONTRIBUTING).

## How it is processed

Each register entry has a `processing` field in plain words, and a `code` field naming the module that does the processing. In short:

- **JMA daily data.** `dcopt.heat.weather` parses each month's daily table from JMA's site and writes one CSV per year, with the values unchanged. When the CSVs are loaded, a day with no temperature is filled with its month's mean and counted in `WeatherYear.n_missing_t`. The Weather page shows which years have filled-in days.
- **OSM.** `scripts/fetch_data.py` downloads the data through osmnx, clips it to the study area, and computes floor and land areas from the polygons.
- **Curated table.** Compiled by hand. Every row names its URLs and says when its IT load is an assumption.

## How the calculations are kept accurate

The checks come in layers, from the input data up to the printed proposal. All of them run in CI on every push.

| Layer | What is checked | Test |
|---|---|---|
| Input data vs. its own publisher | The committed JMA years, averaged over 1991–2020, reproduce JMA's published monthly normals: within 0.1 °C and 8 cm per month, and the daily constants within 1 %. Every year is complete, with at most 5 filled-in days | `test_data_register.py` |
| Input data integrity | Every committed byte matches `SHA256SUMS` | `test_data_register.py` |
| Parameters vs. documents | Every parameter has a basis; curated IT loads match the model; every user type has its parameters; demand profiles sum to 1 | `test_data_and_docs.py` |
| Formulas vs. the math page | Every worked number in `docs/formulations/heat-model.md` (COP, pipe capacities, costs, CO₂, the worked pairs) is recomputed from the code | `test_coefficients.py` |
| Optimiser vs. brute force | On small instances, the MILP finds the same optimum as trying every possible build | `test_bruteforce.py` |
| Properties any correct plan must have | More waste heat never lowers the optimum; a dearer pipe never raises it; every plan meets every constraint; worst ≤ expected ≤ best | `test_properties.py` |
| Solver vs. solver | HiGHS and Gurobi agree (runs only where Gurobi is installed) | `test_solvers.py` |
| Proposals | Every number shows its source or is marked; the pair numbers add up; prices are consistent with the pair's gain | `test_proposal.py` |

Known gap: the JMA page parser (`parse_month`) has no fixture test yet, so a change in JMA's page layout would only be caught by the normals check after a fresh download.

## Tracing a result to its code and data

`dcopt.common.provenance.stamp()` returns a block that experiments save in their `results.json`:

```json
"provenance": {
  "created_utc": "2026-11-24T09:12:03+00:00",
  "git_commit": "5eedbb7…",
  "uncommitted_changes": false,
  "data_fingerprint": "7aa24e83fe765039",
  "data_problems": [],
  "python": "3.12.8",
  "packages": {"dcopt": "0.1.0", "numpy": "…", "highspy": "…"},
  "solver": "highs (default)"
}
```

The `data_fingerprint` is the SHA-256 of `SHA256SUMS`, which covers all the committed data in one value. If two results have the same commit and fingerprint and `uncommitted_changes` is false, they came from the same code and the same data. `experiments/weather_years/run.py` records this block. The other experiments and the export scripts should adopt it next.

## Showing it to someone in two minutes

```bash
uv run python -m dcopt.common.provenance --report
```

```bash
cd data && shasum -a 256 -c SHA256SUMS
```

```bash
uv run pytest -q tests/test_data_register.py tests/test_data_and_docs.py tests/test_coefficients.py
```

Then open the lineage diagram below.

## Lineage

This diagram is generated from the register. `--write` refreshes it, and a test fails if it is stale. Datasets are drawn as cylinders, sources as flags, tests as diamonds and licences as rounded boxes.

<!-- lineage:start (generated by --write) -->
```mermaid
flowchart LR
  n0[("Ishikari data centers: operators, status and IT load range")]
  n1(["MIT"])
  n2>"docs/data-sources.md#data-centers-in-ishikari"]
  n4["src/dcopt/heat/network.py"]
  n5{"tests/test_data_and_docs.py"}
  n6[/"data/SHA256SUMS"/]
  n7[("JMA daily mean temperature and snowfall, Sapporo (station 47412), 1976-2025")]
  n8(["JMA-PDTU-1.0"])
  n9>"www.data.jma.go.jp/obd/stats/etrn/view/daily_…"]
  n10>"www.jma.go.jp/jma/kishou/info/coment.html"]
  n12["src/dcopt/heat/weather.py"]
  n13["src/dcopt/heat/proposal.py"]
  n14["experiments/weather_years/run.py"]
  n15["app/pages/4_Warm_Ishikari_Weather.py"]
  n16{"tests/test_data_register.py"}
  n17{"tests/test_weather.py"}
  n18{"tests/test_weather_fallback.py"}
  n19[("JMA climate normals 1991-2020, Sapporo: monthly mean temperature and snowfall")]
  n20>"www.data.jma.go.jp/obd/stats/etrn/view/nml_sf…"]
  n22["src/dcopt/heat/v1.py"]
  n23{"tests/test_coefficients.py"}
  n24[("Model parameters: prices, efficiencies, temperatures, pipe costs, peak factors")]
  n25>"docs/data-sources.md"]
  n26>"docs/input-evidence.md"]
  n28["experiments/input_sensitivity/run.py"]
  n29["experiments/heat_loss_check/run.py"]
  n30{"tests/test_evidence.py"}
  n31{"tests/test_heat_loss.py"}
  n32[("OpenStreetMap: boundary, road network, facilities and candidate heat users for the study area")]
  n33(["ODbL-1.0"])
  n34>"www.openstreetmap.org/copyright"]
  n37["scripts/fetch_data.py"]
  n38["src/dcopt/common/geo.py"]
  n39["app/pages/1_Warm_Ishikari.py"]
  n40["app/pages/2_Warm_Ishikari_Map.py"]
  n41[("PGLib-OPF benchmark power systems (six cases, 14 to 300 buses)")]
  n42(["CC-BY-4.0"])
  n43>"github.com/power-grid-lib/pglib-opf"]
  n44>"arxiv.org/abs/1908.02788"]
  n46["src/dcopt/grid/cases.py"]
  n47["src/dcopt/grid/hosting.py"]
  n48["experiments/grid_hosting/run.py"]
  n49["app/pages/5_Grid_Hosting.py"]
  n50["scripts/render_theme_animations.py"]
  n51{"tests/test_grid_cases.py"}
  n52{"tests/test_grid_hosting.py"}
  n53[("Built-in illustrative power systems: a two-bus line, a five-bus ring and an eight-bus feeder")]
  n55{"tests/test_grid_app.py"}
  n56[("OpenStreetMap: transmission lines, substations and power plants around the study area")]
  n58["src/dcopt/siting/gridmap.py"]
  n59["scripts/export_siting.py"]
  n60["app/pages/6_Siting.py"]
  n61{"tests/test_siting.py"}
  n62[("Siting study: candidate sites, the heat value of each and its distance to the grid")]
  n63(["MIT + ODbL-1.0"])
  n65["src/dcopt/siting/candidates.py"]
  n66["src/dcopt/siting/heat_value.py"]
  n67["src/dcopt/siting/model.py"]
  n68{"tests/test_siting_app.py"}
  n69[("Generated results: experiment outputs, proposal exports and map exports")]
  n70(["MIT + ODbL-1.0 where maps are drawn"])
  n73["scripts/export_proposals.py"]
  n74["scripts/export_heat_story.py"]
  n75["app/pages/3_Warm_Ishikari_Proposals.py"]
  n76{"tests/test_proposal.py"}
  n77{"tests/test_properties.py"}
  n78{"tests/test_bruteforce.py"}
  n0 -->|under| n1
  n2 -->|feeds| n0
  n0 -->|used_by| n4
  n5 -->|checks| n0
  n6 -->|pins| n0
  n7 -->|under| n8
  n9 -->|feeds| n7
  n10 -->|feeds| n7
  n12 -->|makes| n7
  n7 -->|used_by| n12
  n7 -->|used_by| n13
  n7 -->|used_by| n14
  n7 -->|used_by| n15
  n16 -->|checks| n7
  n17 -->|checks| n7
  n18 -->|checks| n7
  n6 -->|pins| n7
  n19 -->|under| n8
  n20 -->|feeds| n19
  n19 -->|used_by| n22
  n19 -->|used_by| n12
  n19 -->|used_by| n4
  n16 -->|checks| n19
  n23 -->|checks| n19
  n24 -->|under| n1
  n25 -->|feeds| n24
  n26 -->|feeds| n24
  n24 -->|used_by| n4
  n24 -->|used_by| n13
  n24 -->|used_by| n28
  n24 -->|used_by| n29
  n5 -->|checks| n24
  n23 -->|checks| n24
  n30 -->|checks| n24
  n31 -->|checks| n24
  n32 -->|under| n33
  n34 -->|feeds| n32
  n37 -->|makes| n32
  n38 -->|makes| n32
  n32 -->|used_by| n22
  n32 -->|used_by| n4
  n32 -->|used_by| n39
  n32 -->|used_by| n40
  n5 -->|checks| n32
  n41 -->|under| n42
  n43 -->|feeds| n41
  n44 -->|feeds| n41
  n46 -->|makes| n41
  n41 -->|used_by| n47
  n41 -->|used_by| n48
  n41 -->|used_by| n49
  n41 -->|used_by| n50
  n51 -->|checks| n41
  n52 -->|checks| n41
  n53 -->|under| n1
  n53 -->|used_by| n47
  n53 -->|used_by| n49
  n51 -->|checks| n53
  n52 -->|checks| n53
  n55 -->|checks| n53
  n56 -->|under| n33
  n34 -->|feeds| n56
  n58 -->|makes| n56
  n56 -->|used_by| n59
  n56 -->|used_by| n60
  n56 -->|used_by| n50
  n61 -->|checks| n56
  n62 -->|under| n63
  n59 -->|makes| n62
  n65 -->|makes| n62
  n66 -->|makes| n62
  n67 -->|makes| n62
  n62 -->|used_by| n60
  n62 -->|used_by| n50
  n61 -->|checks| n62
  n68 -->|checks| n62
  n69 -->|under| n70
  n14 -->|makes| n69
  n73 -->|makes| n69
  n74 -->|makes| n69
  n69 -->|used_by| n75
  n69 -->|used_by| n50
  n76 -->|checks| n69
  n77 -->|checks| n69
  n78 -->|checks| n69
```
<!-- lineage:end -->

## Optional: the lineage graph in Neo4j

The same graph can be loaded into Neo4j for questions that are awkward to answer by reading files. Neo4j is optional: no code or test needs it, and the export uses only the standard library.

```bash
uv run python -m dcopt.common.provenance --cypher > lineage.cypher
```

Then paste the file into the Neo4j Browser, or run `cypher-shell -f lineage.cypher`. The script uses `MERGE` throughout, so re-running it updates the graph in place. Neo4j Community Edition (GPLv3) or a free AuraDB instance both work. All the data in the graph is public.

The graph model:

- `(:Source)-[:FEEDS]->(:Dataset)`
- `(:Code)-[:MAKES]->(:Dataset)`
- `(:Dataset)-[:USED_BY]->(:Code|:App|:Experiment)`
- `(:Test)-[:CHECKS]->(:Dataset)`
- `(:Dataset)-[:UNDER]->(:Licence)`
- `(:Dataset)-[:STORED_IN]->(:Location)`
- `(:Checksums)-[:PINS]->(:Dataset)`

Questions it answers:

```cypher
// Impact: if a JMA year is corrected, which code, pages and experiments are affected?
MATCH (d:Dataset {id: "jma-daily-sapporo"})-[:USED_BY]->(x) RETURN labels(x)[0] AS kind, x.path;

// Licence: which pages and experiments use ODbL data, and so must credit OpenStreetMap?
MATCH (:Licence {name: "ODbL-1.0"})<-[:UNDER]-(d)-[:USED_BY]->(x) RETURN d.title, x.path;

// Gaps: datasets that nothing tests, or that are committed but not pinned.
MATCH (d:Dataset) WHERE NOT (d)<-[:CHECKS]-() RETURN d.id AS untested;
MATCH (d:Dataset {storage: "git"}) WHERE NOT (d)<-[:PINS]-() RETURN d.id AS unpinned;

// Audit: everything one test vouches for.
MATCH (t:Test {path: "tests/test_data_register.py"})-[:CHECKS]->(d) RETURN d.title;
```

## Changing or adding data

1. Change the data, or add the dataset with an entry in `data/register.toml` and a row in `docs/data-sources.md`.
2. Run `uv run python -m dcopt.common.provenance --write`. This re-pins the checksums and refreshes the diagram.
3. Say why the data changed in the commit message. The checksum diff in the pull request shows the reviewer exactly which files changed.
