# Data

- `curated/` holds small tables we compiled ourselves from public sources. Every row names its source. They are shared under the repository's MIT license.
- `jma/` holds daily JMA observations for Sapporo, 1976–2025, used by the weather study. They are committed, but they are under JMA's terms (Public Data Terms of Use 1.0: credit the source, state the processing), not the MIT license. See `jma/README.md`.
- `raw/` and `cache/` hold data downloaded by scripts, such as OpenStreetMap (© OpenStreetMap contributors, ODbL 1.0). They are not in git. Rebuild them with the scripts; do not commit them.

When coordinates come from a licensed source, they are not stored in `curated/`. The scripts look them up at build time.

`register.toml` lists every dataset with its storage, terms, processing and checks, and `SHA256SUMS` pins the bytes of every committed file (`shasum -a 256 -c SHA256SUMS` verifies them). See `../docs/data-accountability.md`.
