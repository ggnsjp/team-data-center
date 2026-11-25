"""The input-evidence pages: current, sourced, and covering every assumption of the heat-network model."""
from dcopt.common import evidence
from dcopt.heat.network import Params, assumptions_table


def test_pages_are_current():
    for lang, path in evidence.PAGES.items():
        assert path.exists() and path.read_text(encoding="utf-8") == evidence.render(lang), \
            f"{path.name} is stale: uv run python -m dcopt.common.evidence --write"


def test_every_assumption_of_the_heat_model_has_an_entry():
    need = {r["key"] for r in assumptions_table(Params()) if r["basis"].startswith("assumption")} - evidence.NOT_INPUTS
    assert need <= evidence.covered_keys(), sorted(need - evidence.covered_keys())


def test_keys_name_rows_of_the_model():
    assert evidence.covered_keys() <= {r["key"] for r in assumptions_table(Params())}


def test_entries_are_complete_in_both_languages():
    for x in evidence.ITEMS:
        for pair in (x.name, x.model, x.published):
            assert all(s.strip() for s in pair), x.name[1]
        if isinstance(x.verdict, str):
            assert x.verdict in evidence.VERDICT, x.name[1]
        else:
            assert all(s.strip() for s in x.verdict), x.name[1]
        assert bool(x.effect[0]) == bool(x.effect[1]) and "@" not in x.effect[1], x.name[1]
        for title, url in x.sources:
            assert title and url.startswith("https://"), x.name[1]
        if x.verdict in ("measured", "inside", "cautious", "optimistic", "low", "high"):
            assert x.sources, f"{x.name[1]}: a comparison with published values names its source"


def test_both_pages_list_the_same_entries():
    ja, en = evidence.render("ja"), evidence.render("en")
    assert ja.count("\n| ") == en.count("\n| ") and ja.count("https://") == en.count("https://")
