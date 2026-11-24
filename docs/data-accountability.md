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
  n27[("OpenStreetMap: boundary, road network, facilities and candidate heat users for the study area")]
  n28(["ODbL-1.0"])
  n29>"www.openstreetmap.org/copyright"]
  n32["scripts/fetch_data.py"]
  n33["src/dcopt/common/geo.py"]
  n34["app/pages/1_Warm_Ishikari.py"]
  n35["app/pages/2_Warm_Ishikari_Map.py"]
  n36[("PGLib-OPF benchmark power systems (six cases, 14 to 300 buses)")]
  n37(["CC-BY-4.0"])
  n38>"github.com/power-grid-lib/pglib-opf"]
  n39>"arxiv.org/abs/1908.02788"]
  n41["src/dcopt/grid/cases.py"]
  n42["src/dcopt/grid/hosting.py"]
  n43["experiments/grid_hosting/run.py"]
  n44["app/pages/5_Grid_Hosting.py"]
  n45{"tests/test_grid_cases.py"}
  n46{"tests/test_grid_hosting.py"}
  n47[("Built-in illustrative power systems: a two-bus line, a five-bus ring and an eight-bus feeder")]
  n49{"tests/test_grid_app.py"}
  n50[("Generated results: experiment outputs, proposal exports and map exports")]
  n51(["MIT + ODbL-1.0 where maps are drawn"])
  n54["scripts/export_proposals.py"]
  n55["scripts/export_heat_story.py"]
  n56["app/pages/3_Warm_Ishikari_Proposals.py"]
  n57{"tests/test_proposal.py"}
  n58{"tests/test_properties.py"}
  n59{"tests/test_bruteforce.py"}
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
  n24 -->|used_by| n4
  n24 -->|used_by| n13
  n5 -->|checks| n24
  n23 -->|checks| n24
  n27 -->|under| n28
  n29 -->|feeds| n27
  n32 -->|makes| n27
  n33 -->|makes| n27
  n27 -->|used_by| n22
  n27 -->|used_by| n4
  n27 -->|used_by| n34
  n27 -->|used_by| n35
  n5 -->|checks| n27
  n36 -->|under| n37
  n38 -->|feeds| n36
  n39 -->|feeds| n36
  n41 -->|makes| n36
  n36 -->|used_by| n42
  n36 -->|used_by| n43
  n36 -->|used_by| n44
  n45 -->|checks| n36
  n46 -->|checks| n36
  n47 -->|under| n1
  n47 -->|used_by| n42
  n47 -->|used_by| n44
  n45 -->|checks| n47
  n46 -->|checks| n47
  n49 -->|checks| n47
  n50 -->|under| n51
  n14 -->|makes| n50
  n54 -->|makes| n50
  n55 -->|makes| n50
  n50 -->|used_by| n56
  n57 -->|checks| n50
  n58 -->|checks| n50
  n59 -->|checks| n50
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
