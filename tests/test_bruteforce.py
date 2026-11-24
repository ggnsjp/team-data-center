"""The MILP against complete enumeration on instances small enough to try every build.

For each build (every candidate link off, or built with one size) and every assignment of users to a data
center (or to none), the enumeration checks that the users' heat can be routed (a multi-commodity flow LP with
the same per-user size rule and pipe capacities as the model), then computes the best monthly deliveries.
Deliveries separate by data center, month and scenario into continuous knapsacks, solved exactly by ratio.
"""
from __future__ import annotations

import itertools
from collections import deque

import numpy as np
import pytest
from scipy.optimize import linprog

from dcopt.heat.network import Params, solve, user_data, waste_heat
from synthetic import SCENS, small_one_dc, small_shared, small_two_dc


def deliveries(ud, Wc, assign, d, t, w):
    """Best value at data center d in month t, scenario w: max sum v s, sum r s <= W, 0 <= s <= cap."""
    users = sorted((u for u, a in assign.items() if a == d and ud.v[u, w] > 0), key=lambda u: -ud.v[u, w] / ud.r[u])
    left, value = Wc[d, t, w], 0.0
    for u in users:
        s = min(ud.cap[u, t, w], left / ud.r[u])
        value += s * ud.v[u, w]
        left -= s * ud.r[u]
        if left <= 1e-12:
            break
    return value


def routable(inst, P, ud, E, sizes_on, assign) -> bool:
    """Can every assigned user's commodity reach it from its data center over built links that fit it,
    within pipe capacities (fractional paths allowed, as in the model)?"""
    users = [u for u, d in assign.items() if d is not None]
    if not users:
        return True
    cap = [P.sizes[k].capacity_mw(P.dT) if k is not None else 0.0 for k in sizes_on]
    fits = lambda u, e: sizes_on[e] is not None and cap[e] >= ud.q[u] - 1e-9
    # quick reachability check by graph search
    for u in users:
        adj: dict[int, list[int]] = {}
        for e, (a, b) in enumerate(E):
            if fits(u, e):
                adj.setdefault(a, []).append(b)
                adj.setdefault(b, []).append(a)
        start, goal = assign[u], inst.D + u
        seen, queue = {start}, deque([start])
        while queue:
            node = queue.popleft()
            for nb in adj.get(node, []):
                if nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        if goal not in seen:
            return False
    # capacity: one LP over all assigned users' flows
    arcs = [(a, b, e) for e, (a, b) in enumerate(E)] + [(b, a, e) for e, (a, b) in enumerate(E)]
    var = {(u, i): j for j, (u, i) in enumerate((u, i) for u in users for i in range(len(arcs)) if fits(u, arcs[i][2]))}
    nv = len(var)
    A_eq, b_eq = [], []
    for u in users:
        for node in range(inst.n):
            row = np.zeros(nv)
            for i, (a, b, _) in enumerate(arcs):
                if (u, i) in var:
                    if a == node:
                        row[var[u, i]] += 1
                    if b == node:
                        row[var[u, i]] -= 1
            A_eq.append(row)
            b_eq.append(1.0 if node == assign[u] else (-1.0 if node == inst.D + u else 0.0))
    A_ub, b_ub = [], []
    for e in range(len(E)):
        if sizes_on[e] is None:
            continue
        row = np.zeros(nv)
        for u in users:
            for i in (e, e + len(E)):
                if (u, i) in var:
                    row[var[u, i]] += ud.q[u]
        A_ub.append(row)
        b_ub.append(cap[e])
    res = linprog(np.zeros(nv), A_ub=np.array(A_ub) if A_ub else None, b_ub=b_ub or None,
                  A_eq=np.array(A_eq), b_eq=b_eq, bounds=[(0, 1)] * nv, method="highs")
    return res.status == 0


def enumerate_best(inst, P, scens, E, objective: str):
    ud, Wc = user_data(inst, P, scens), waste_heat(inst, P, scens)
    prob = np.array([s.prob for s in scens])
    length = np.array([inst.dist[a, b] for a, b in E])
    best, best_users = -np.inf, 0
    for sizes_on in itertools.product([None, *range(len(P.sizes))], repeat=len(E)):
        pipe = P.crf * sum(length[e] * P.sizes[k].yen_m for e, k in enumerate(sizes_on) if k is not None)
        for choice in itertools.product([None, *range(inst.D)], repeat=inst.U):
            assign = dict(enumerate(choice))
            hp = P.crf_hp * sum(ud.hp[u] for u, d in assign.items() if d is not None)
            nets = np.array([sum(deliveries(ud, Wc, assign, d, t, w) for d in range(inst.D) for t in range(12))
                             for w in range(len(scens))]) - pipe - hp
            score = float(prob @ nets) if objective == "expected" else float(nets.min())
            if score > best + 1e-9 and routable(inst, P, ud, E, sizes_on, assign):
                best, best_users = score, sum(d is not None for d in choice)
    return best, best_users


ONE_DC_EDGES = [(0, 1), (1, 2), (0, 3), (2, 3)]
TWO_DC_EDGES = [(0, 2), (1, 3), (2, 3), (0, 4)]


@pytest.mark.parametrize("mode", ["ambient", "central"])
@pytest.mark.parametrize("objective", ["expected", "worst"])
def test_milp_matches_enumeration_one_dc(mode, objective):
    inst = small_one_dc()
    P = Params(mode=mode, mip_rel_gap=0.0, sizes=(Params().sizes[0], Params().sizes[3]))   # DN50, DN150
    best, users = enumerate_best(inst, P, SCENS, ONE_DC_EDGES, objective)
    plan = solve(inst, P, SCENS, objective=objective, edges=ONE_DC_EDGES)
    got = plan.expected_net if objective == "expected" else float(plan.net.min())
    assert users >= 1, "the instance should connect someone, or the test proves little"
    assert got == pytest.approx(best, rel=1e-6, abs=1.0)


@pytest.mark.parametrize("objective", ["expected", "worst"])
def test_milp_matches_enumeration_two_dcs(objective):
    inst = small_two_dc()
    P = Params(mode="ambient", mip_rel_gap=0.0, sizes=(Params().sizes[3],))                # DN150 only
    best, users = enumerate_best(inst, P, SCENS, TWO_DC_EDGES, objective)
    plan = solve(inst, P, SCENS, objective=objective, edges=TWO_DC_EDGES)
    got = plan.expected_net if objective == "expected" else float(plan.net.min())
    assert users >= 1
    assert got == pytest.approx(best, rel=1e-6, abs=1.0)


def test_enumeration_sees_capacity_limits():
    """With only DN50 (0.09 MW at 10 K) the greenhouse cannot connect; the enumeration and the MILP agree."""
    inst = small_one_dc()
    P = Params(mode="ambient", mip_rel_gap=0.0, sizes=(Params().sizes[0],))
    ud = user_data(inst, P, SCENS)
    assert ud.q[0] > P.sizes[0].capacity_mw(P.dT)
    best, _ = enumerate_best(inst, P, SCENS, ONE_DC_EDGES, "expected")
    plan = solve(inst, P, SCENS, edges=ONE_DC_EDGES)
    assert 0 not in plan.connected
    assert plan.expected_net == pytest.approx(best, rel=1e-6, abs=1.0)


@pytest.mark.parametrize("objective", ["expected", "worst"])
@pytest.mark.parametrize("mode", ["central", "ambient"])
def test_milp_matches_enumeration_with_a_shared_trunk(objective, mode):
    """Enough heat, close users and cheap heat pumps: several connect, sharing a trunk of two sizes."""
    inst = small_shared()
    P = Params(mode=mode, mip_rel_gap=0.0, sizes=(Params().sizes[1], Params().sizes[4]),   # DN80, DN200
               hp_yen_per_mw_user=30e6, hp_yen_per_mw_central=30e6)
    min_users = 2
    best, users = enumerate_best(inst, P, SCENS, ONE_DC_EDGES, objective)
    plan = solve(inst, P, SCENS, objective=objective, edges=ONE_DC_EDGES)
    got = plan.expected_net if objective == "expected" else float(plan.net.min())
    assert users >= min_users
    assert got == pytest.approx(best, rel=1e-6, abs=1.0)
