# Optional add-ons

[日本語](optional-addons.ja.md)

Nothing in this repository needs the add-ons on this page. Without their settings the app, the scripts and the tests run as the [README](../README.md) describes.

## A router for the language model (OrcaRouter)

The what-if box of the Warm Ishikari page calls one OpenAI-compatible language model directly (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`; see the README). It can instead send its calls through [OrcaRouter](https://docs.orcarouter.ai/) with an ordered chain of models, so that an outage or a 429 of one model does not stop the box. Without `ORCAROUTER_API_KEY` nothing changes.

1. In the OrcaRouter console, add your model service under BYOK as a custom OpenAI-compatible endpoint, with its base URL and key, and import the model.
2. Optionally add guardrails (console → Guardrails, attached to the key), for example a `max_chars` input rule and a PII mask. They screen inputs; the number check of the what-if box covers the outputs.
3. Set the environment variables below. The first entry of `LLM_MODELS` is the model id as the console shows it after the import. Any model id of OrcaRouter can be in the chain: `LLM_MODELS=orcarouter/fusion-flash`, for example, uses its own router model and needs no import.

| Variable | Meaning |
| --- | --- |
| `ORCAROUTER_API_KEY` | OrcaRouter key (`sk-orca-...`); turns router mode on |
| `ORCAROUTER_BASE_URL` | default `https://api.orcarouter.ai/v1` |
| `LLM_MODELS` | comma-separated fallback chain, at most 5 |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | the direct service, called when the router cannot be reached or answers 5xx/429 |

The router fails over to the next model only on a 5xx, 429 or network error; a 401/403 or a guardrail block is shown as an error, not retried. Privacy: in this mode the prompts (the question and the model's numbers) pass through the router as well as the model provider. The caption under an answer says whether it came through the router or directly.

During the hackathon the direct service was CarbonForge (base URL `https://endpoint.carbonforge.ai/v1`, model `carbonforge-flash`). Its settings still work: `CF_API_KEY` alone uses that endpoint and model, `CARBONFORGE_BASE_URL` and `LLM_MODEL` change them, and `LLM_API_KEY` takes precedence when both keys are set.

## The plan graph in Neo4j

`uv run python scripts/export_plan_graph.py` builds the plan graph with NetworkX and needs nothing else (README, *The plan as a graph*). With a Neo4j database (`uv sync --extra graph`, then `NEO4J_URI`, `NEO4J_USERNAME` and `NEO4J_PASSWORD`), `--neo4j` loads the same graph, asks the same questions in Cypher and checks that the answers agree. The app and every other script run without Neo4j.

The lineage graph of the data register can also be loaded into Neo4j: [data-accountability.md](data-accountability.md), section *Optional: the lineage graph in Neo4j*.
