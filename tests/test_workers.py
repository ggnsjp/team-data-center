"""Workers that ask for one solver thread still solve after the parent has solved with the default number."""
import os
import sys
import types

import pytest

from dcopt.common.workers import pool

highspy = pytest.importorskip("highspy")


def _solve(_=None) -> str:
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    threads = int(os.environ.get("DCOPT_THREADS", "0") or 0)
    if threads:
        h.setOptionValue("threads", threads)
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = 1, 0
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = [-1.0], [0.0], [1.0]
    h.passModel(lp)
    h.run()
    return h.modelStatusToString(h.getModelStatus())


def _one_thread() -> None:
    os.environ["DCOPT_THREADS"] = "1"


def test_workers_with_one_thread_solve_after_the_parent_used_the_default(monkeypatch):
    monkeypatch.delenv("DCOPT_THREADS", raising=False)
    # A page test may have left a Streamlit page as the main module; a worker would run it on start.
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))
    assert _solve() == "Optimal"                                   # the parent's solve sets up the solver's threads
    for _ in range(2):                                             # a second pool, after the parent solved again
        with pool(2, initializer=_one_thread) as workers:
            assert list(workers.map(_solve, range(4))) == ["Optimal"] * 4
        assert _solve() == "Optimal"
