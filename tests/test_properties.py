"""Properties any correct plan must have, on synthetic instances (no map data)."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from dcopt.heat.network import BudgetSet, Params, Scenario, ccg, evaluate, pairwise, solve, solve_kernel
from synthetic import SCENS, complete_edges, scaled_it, tiny

P0 = Params(mip_rel_gap=0.0, time_limit=60)
TOL = 1e-6


def close(a, b):
    return 1e-6 * max(1.0, abs(a), abs(b)) + 1.0          # 1 yen absolute slack on top of a relative one


@pytest.fixture(scope="module")
def inst():
    return tiny()


@pytest.fixture(scope="module")
def base(inst):
    return solve(inst, P0, SCENS)


def test_more_waste_heat_never_lowers_the_optimum(inst, base):
    more = solve(scaled_it(inst, 1.5), P0, SCENS)
    assert more.expected_net >= base.expected_net - close(more.expected_net, base.expected_net)


def test_a_higher_kerosene_price_never_lowers_the_optimum(inst, base):
    dearer = [replace(s, kerosene_yen_l=s.kerosene_yen_l + 30.0) for s in SCENS]
    plan = solve(inst, P0, dearer)
    assert plan.expected_net >= base.expected_net - close(plan.expected_net, base.expected_net)


def test_a_higher_pipe_cost_never_raises_the_optimum(inst, base):
    dear = replace(P0, sizes=tuple(replace(s, yen_m=1.5 * s.yen_m) for s in P0.sizes))
    plan = solve(inst, dear, SCENS)
    assert plan.expected_net <= base.expected_net + close(plan.expected_net, base.expected_net)


def test_adding_a_candidate_user_never_lowers_the_optimum(inst):
    sub = inst.subset(list(range(inst.D)), list(range(inst.U - 1)))
    full_plan = solve(inst, P0, SCENS, edges=complete_edges(inst))
    sub_plan = solve(sub, P0, SCENS, edges=complete_edges(sub))
    assert full_plan.expected_net >= sub_plan.expected_net - close(full_plan.expected_net, sub_plan.expected_net)


@pytest.mark.parametrize("objective", ["expected", "worst"])
def test_worst_le_expected_le_best_scenario(inst, objective):
    plan = solve(inst, P0, SCENS, objective=objective)
    net = plan.net
    assert net.min() <= plan.expected_net + TOL <= net.max() + 2 * TOL


def test_regret_is_nonnegative_and_bounded_by_each_scenarios_optimum(inst):
    own = [solve(inst, P0, [replace(s, prob=1.0)]).expected_net for s in SCENS]
    plan = solve(inst, P0, SCENS, objective="regret", own_opt=own)
    assert plan.bound >= -TOL
    for w, opt in enumerate(own):
        assert plan.net[w] <= opt + close(plan.net[w], opt)                 # nobody beats a scenario's own optimum
        assert opt - plan.net[w] <= plan.bound + close(opt, plan.net[w])


def test_robust_value_does_not_rise_with_the_budget(inst):
    values, plans = [], []
    for gamma in range(inst.D + 1):
        out = ccg(inst, P0, BudgetSet(budget=gamma), method="direct")
        values.append(out["value"])
        plans.append(out["plan"])
    for a, b in zip(values, values[1:]):
        assert b <= a + close(a, b)
    nominal = BudgetSet(0).nominal(inst.sources)
    nom = [evaluate(p, [nominal]).expected_net for p in plans]
    for v in nom[1:]:                                                        # price of robustness >= 0
        assert v <= nom[0] + close(v, nom[0])


@pytest.mark.parametrize("d", [0, 1])
def test_pairwise_never_beats_the_optimized_single_data_center_network(inst, d):
    one = inst.subset([d], list(range(inst.U)))
    pw = pairwise(inst, P0, SCENS, d)
    opt = solve(one, P0, SCENS)
    assert pw.expected_net <= opt.expected_net + close(pw.expected_net, opt.expected_net)


def check_plan(plan):
    """Re-check every constraint of the model from the plan's arrays."""
    inst, P, ud = plan.inst, plan.P, plan.ud
    nE = len(plan.E)
    yk = plan.y.max(axis=1)
    assert np.all(plan.y.sum(axis=1) <= 1 + TOL)                                        # one size per link
    assert np.all(plan.g >= -TOL) and np.all(plan.g <= 1 + TOL)
    assert np.all(plan.g[:, :nE] + plan.g[:, nE:] <= yk[None, :] + TOL)                 # only built links
    for e in range(nE):
        if yk[e] > 0.5:
            k = int(np.argmax(plan.y[e]))
            assert float(ud.q @ (plan.g[:, e] + plan.g[:, e + nE])) <= P.sizes[k].capacity_mw(P.dT) + 1e-6
            for u in range(inst.U):                                                     # sizes that fit the user
                if plan.g[u, e] + plan.g[u, e + nE] > 1e-6:
                    assert P.sizes[k].capacity_mw(P.dT) >= ud.q[u] - 1e-6
    assert np.all(plan.waste_used() <= plan.W + 1e-6)                                   # waste heat
    assert np.all(plan.s >= -1e-9)
    a_from = [a for a, b in plan.E] + [b for a, b in plan.E]
    a_to = [b for a, b in plan.E] + [a for a, b in plan.E]
    for u in range(inst.U):
        bal = np.zeros(inst.n)
        np.add.at(bal, a_from, plan.g[u])
        np.add.at(bal, a_to, -plan.g[u])
        expect = np.zeros(inst.n)
        if plan.x[u] > 0.5:
            d = int(plan.assign[u])
            expect[d], expect[inst.D + u] = 1.0, -1.0
            for dd in range(inst.D):                                                    # one data center
                if dd != d:
                    assert plan.s[u, dd].sum() <= 1e-6
            assert np.all(plan.s[u, d] <= ud.cap[u] + 1e-6)                             # delivery caps
        else:
            assert plan.s[u].sum() <= 1e-6
        assert np.allclose(bal, expect, atol=1e-6)                                      # flow balance


@pytest.mark.parametrize("mode", ["ambient", "central"])
@pytest.mark.parametrize("objective", ["expected", "worst"])
def test_plans_satisfy_every_constraint(inst, mode, objective):
    check_plan(solve(inst, replace(P0, mode=mode), SCENS, objective=objective))


def test_kernel_plans_satisfy_every_constraint(inst):
    check_plan(solve_kernel(inst, P0, SCENS))


def test_evaluate_on_new_scenarios_keeps_constraints(inst, base):
    cold = [Scenario("cold", "寒", "cold", 1.0, 180.0, "low")]
    check_plan(evaluate(base, cold))
