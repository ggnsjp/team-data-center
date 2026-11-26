"""Cached functions on different app pages must not share a cache.

Streamlit runs every page script as ``__main__`` and keys st.cache_data by module, name and source
code, so two pages with an identical cached function (and equal arguments) get each other's result.
That made the GX overlay page show the heat map. This test keeps such twins from coming back.
"""
import ast
from collections import defaultdict
from pathlib import Path

PAGES = sorted((Path(__file__).resolve().parents[1] / "app").rglob("*.py"))


def cached_functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Attribute) and target.attr in ("cache_data", "cache_resource"):
                    yield node.name, ast.unparse(node)


def test_no_identical_cached_functions_across_pages():
    seen = defaultdict(list)
    for page in PAGES:
        for name, source in cached_functions(page):
            seen[(name, source)].append(page.name)   # what Streamlit keys the cache by, besides __main__
    twins = {key[0]: pages for key, pages in seen.items() if len(pages) > 1}
    assert not twins, f"identical cached functions share one Streamlit cache: {twins}"
