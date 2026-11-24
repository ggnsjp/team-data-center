# Contributing

## Workflow

- Work on a branch and open a pull request. Another member reviews it before it is merged into `main`.
- Keep `uv run pytest` passing. CI runs it on every push.
- Write code, comments and commit messages in English. Text shown to users is in Japanese and English.

## Numbers and sources

- Every parameter has a source (URL), or it is marked as an assumption with a one-line reason. Record it in `docs/data-sources.md`.
- Add a paper to `docs/references.bib` only after checking that it exists, by opening its DOI or publisher page.

## Data and licenses

- The repository is under the MIT license. Commit only data that may be shared under MIT, such as our own compilations of facts with their sources.
- Scripts download OpenStreetMap (ODbL) and other licensed data into `data/raw/` and `data/cache/`, which git ignores. Any output that shows OSM data credits "© OpenStreetMap contributors".
- Never commit solver license files, API keys or `.env` files.
- Every dataset has an entry in `data/register.toml` (where it is stored, its terms, how it is made and processed, what checks it). After changing committed data, run `uv run python -m dcopt.common.provenance --write` and say why in the commit. See `docs/data-accountability.md`.
- `data/jma/` is the one committed dataset not under MIT: JMA's terms allow it with credit (see `data/jma/README.md`).

## Solvers

- The defaults are open source: HiGHS for MILP/LP, and Clarabel or SCS for conic problems. A commercial solver may be offered as an option, but code must never require one.

## Experiments

- An experiment is a config file plus a script in `experiments/`. Its outputs go to `results/`, which is not committed. Save them together with the git commit, the solver and its version, and the run time.
