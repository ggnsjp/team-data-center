"""The user_connection='decided' model: connection DNs are decisions."""
import pytest
from synthetic import small_two_dc

from dcopt.heat import network as N


def _solve(**kw):
    opts = dict(mode="ambient", formulation="extended")
    opts.update(kw)
    inst = small_two_dc()
    return inst, N.solve(inst, N.Params(**opts), N.default_scenarios())


def test_decided_with_published_floor_matches_the_sized_model():
    # the sizing convention becomes a floor on the connection binaries; with the published floor
    # the decided model must reproduce the sized model exactly (same plan, same value).
    _, sized = _solve()
    _, decided = _solve(user_connection="decided")
    assert decided.status == "Optimal"
    assert decided.expected_net == pytest.approx(sized.expected_net, abs=1e-6)
    assert decided.pipe_m == pytest.approx(sized.pipe_m, abs=1e-6)
    cap_k = [s.capacity_mw(decided.P.dT) for s in decided.P.sizes]
    for u in range(decided.inst.U):
        if decided.x[u] > 0.5:
            assert cap_k[decided.conn[u]] >= decided.ud.q[u] - 1e-9


def test_decided_free_may_downsize_and_never_loses():
    # without the floor the optimizer trades pipe cost against cold-year shedding; its feasible
    # set is a superset of the floored model's, so its optimum can only be higher.
    _, floored = _solve(user_connection="decided")
    _, free = _solve(user_connection="decided", sizing="free")
    assert free.status == "Optimal"
    assert free.expected_net >= floored.expected_net - 1e-6
    assert free.conn is not None and (free.conn >= 0).any()


def test_decided_requires_the_extended_formulation():
    with pytest.raises(ValueError):
        _solve(user_connection="decided", formulation="aggregated")


def test_evaluate_pins_the_connection_and_throttles_out_of_sample():
    inst, free = _solve(user_connection="decided", sizing="free")
    mild = [N.Scenario("mild", "温暖", "mild", 1.0, 115.0, it_level="low")]
    ev = N.evaluate(free, mild)
    assert ev.conn is not None and list(ev.conn) == list(free.conn)
    assert ev.expected_net <= free.expected_net + 1e-6
