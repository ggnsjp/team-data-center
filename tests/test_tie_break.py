"""Ties between data centers that serve a user at the same cost are broken the same way every time:
by the nearer data center, then by key (Params.tie_yen_m, network.tie_cost)."""
from dataclasses import replace

import numpy as np
import pytest
from synthetic import SCENS, equidistant_two_dc, instance, permuted_sources, tiny

from dcopt.heat.network import Params, build_model, solve

P = Params(mip_rel_gap=0.0, time_limit=60, solver="highs")


def served_by(plan) -> dict[str, str | None]:
    """User key -> key of the data center serving it (None when not connected)."""
    return {u.key: (plan.inst.sources[d].key if d >= 0 else None) for u, d in zip(plan.inst.users, plan.assign)}


def test_tie_cost_prefers_the_nearer_data_center_then_the_smaller_key():
    inst = instance([(0, 0), (500, 0), (-500, 0)], [("gh", "greenhouse", (2000, 0), 2500.0)])
    m = build_model(inst, P, SCENS)
    tie = m.tie[m.off["z"]:m.off["g"]].reshape(inst.U, inst.D)[0]
    assert tie[1] < tie[0] < tie[2]                              # dc1 is nearest, dc2 farthest
    eq = build_model(equidistant_two_dc(), P, SCENS)
    t2 = eq.tie[eq.off["z"]:eq.off["g"]]
    assert 0 < t2[1] - t2[0] < P.tie_yen_m                      # same distance: dc0 (smaller key) first
    assert not build_model(inst, replace(P, tie_yen_m=0.0), SCENS).tie.any()
    assert m.tie[:m.off["z"]].sum() == 0 and m.tie[m.off["g"]:].sum() == 0      # only on z


@pytest.mark.parametrize("objective", ["expected", "worst"])
def test_equidistant_tie_is_the_same_across_solves_and_source_orders(objective):
    inst = equidistant_two_dc()
    plans = [solve(inst, P, SCENS, objective=objective) for _ in range(3)]
    plans += [solve(permuted_sources(inst, [1, 0]), P, SCENS, objective=objective) for _ in range(2)]
    assert served_by(plans[0]) == {"fish": "dc0"}
    for p in plans[1:]:
        assert served_by(p) == served_by(plans[0])
        assert p.expected_net == pytest.approx(plans[0].expected_net, rel=1e-9, abs=1e-3)


def test_forced_shared_pipe_goes_to_the_nearer_data_center():
    """Both pipes are built (smallest size either way), so dc0 and dc1 serve the school at the same
    cost; dc1 is nearer."""
    inst = instance([(0, 0), (100, 0)], [("school", "school", (500, 0), 100.0)])
    for perm in ([0, 1], [1, 0]):
        pi = permuted_sources(inst, perm)
        edges = [(0, 1), (perm.index(0), 2)]                    # dc0-dc1 and dc0-school
        plan = solve(pi, P, SCENS, edges=edges, force_edges=True)
        assert served_by(plan) == {"school": "dc1"}


def test_tie_break_barely_moves_the_plan():
    inst = tiny()
    with_tie = solve(inst, P, SCENS)
    without = solve(inst, replace(P, tie_yen_m=0.0), SCENS)
    bound = P.tie_yen_m * (inst.dist[:inst.D, inst.D:].max() + 1) * inst.U
    assert with_tie.expected_net == pytest.approx(without.expected_net, abs=bound)
    assert [b[:2] for b in with_tie.built] == [b[:2] for b in without.built]
    assert np.isclose(with_tie.dual_bound or 0.0, without.dual_bound or 0.0, rtol=1e-6, atol=bound)
