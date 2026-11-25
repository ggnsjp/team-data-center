# Experiments

Each experiment gets its own folder with a config file and a script: `experiments/<name>/config.toml` and `experiments/<name>/run.py`.
The script writes to `results/<name>/<timestamp>/`, which is not committed. Save the outputs there together with the config used, the git commit, the solver name and version, and the run times.
Copy the tables and figures the team wants to keep into `docs/`.

- `grid_global/run.py`: the global-solver (Gurobi) cross-check table of `docs/formulations/grid.md`. Gurobi is optional; without it the script prints a note and exits. Run: `uv run --extra gurobi python experiments/grid_global/run.py --download`
