"""A discount rate of zero is a valid setting: the undiscounted case (review issue #45)."""
import pytest
from synthetic import SCENS, tiny

from dcopt.heat.network import Params, solve
from dcopt.heat.v1 import Assumptions, capital_recovery


def test_without_interest_the_factor_is_one_over_the_years():
    assert capital_recovery(0.0, 30) == pytest.approx(1 / 30)
    assert Assumptions(rate=0.0).crf == pytest.approx(1 / Assumptions().years)
    P = Params(rate=0.0)
    assert P.crf == pytest.approx(1 / P.years)
    assert P.crf_hp == pytest.approx(1 / P.hp_years)


def test_the_factor_is_continuous_at_zero_and_unchanged_elsewhere():
    assert capital_recovery(1e-6, 30) == pytest.approx(1 / 30, rel=1e-4)
    r, n = 0.03, 30
    assert capital_recovery(r, n) == r * (1 + r) ** n / ((1 + r) ** n - 1)      # the published plans rest on this
    assert Assumptions().crf == capital_recovery(Assumptions().rate, Assumptions().years)


def test_the_network_model_solves_without_discounting():
    inst = tiny()
    zero = solve(inst, Params(rate=0.0, time_limit=30), SCENS)
    near = solve(inst, Params(rate=1e-4, time_limit=30), SCENS)
    assert zero.expected_net == pytest.approx(near.expected_net, rel=1e-2, abs=1.0)
