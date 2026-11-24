"""Upper bounds on the hostable load: the DC screening LP and two convex relaxations of the AC
problem (second-order cone and semidefinite), built on the lifted model.

SOCP   For every connected pair i < j the 2 x 2 minor of W is positive semidefinite:
       c_i c_j >= wr^2 + wi^2 (Jabr 2006). Exact on radial networks under mild conditions.
SDP    W restricted to the cliques of a chordal extension of the network graph is positive
       semidefinite, which is equivalent to W having a positive semidefinite completion
       (Grone et al. 1984; used for power flow by Jabr 2012 and Molzahn et al. 2013). The entries
       of W on the fill edges are extra variables, so no linking constraints are needed.
       A Hermitian clique matrix X = R + jI is embedded as the real matrix [[R, -I], [I, R]].
DC     Linear power flow without losses, voltages or reactive power: the usual screening model.
       It is not a relaxation of the AC problem and can err on either side.

Both relaxations contain every AC-feasible point, so their optimal value is an upper bound on the
AC hosting capacity, and an infeasible relaxation proves that the load cannot be hosted.
The conic problems are solved with Clarabel (interior point, Apache-2.0).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import clarabel
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from dcopt.grid.cases import Case
from dcopt.grid.lifted import Lifted

SQRT2 = math.sqrt(2.0)
OK = ("Solved", "AlmostSolved")        # AlmostSolved: Clarabel's reduced tolerances (about 5e-5 relative)
REGULARIZATION = 1e-5                  # static KKT regularization; the default 1e-8 stalls on the SDPs


@dataclass
class Relaxed:
    """The outcome of one relaxation solve. Powers are per unit."""
    kind: str                          # "socp" or "sdp"
    status: str
    value: float | None                # the bound on lambda, None if the solve failed
    seconds: float
    z: np.ndarray | None = None        # the relaxed solution [y, u]
    rank_ratio: float | None = None    # largest second/first eigenvalue ratio over the cliques
    voltages: np.ndarray | None = None  # a voltage estimate recovered from W (exact if rank one)
    cycle_error: float | None = None   # largest |arg W_ij - (theta_i - theta_j)| off the spanning tree
    duality_gap: float | None = None   # |primal - dual| objective at termination, per unit

    @property
    def solved(self) -> bool:
        return self.value is not None


def chordal_cliques(n: int, edges: list[tuple[int, int]]) -> list[tuple[int, ...]]:
    """Maximal cliques of a chordal extension of the graph, by greedy minimum-degree elimination.
    Each clique is a sorted tuple of bus indices; together they cover every edge."""
    adj = [set() for _ in range(n)]
    for a, b in edges:
        if a != b:
            adj[a].add(b)
            adj[b].add(a)
    alive = set(range(n))
    cliques: list[frozenset[int]] = []
    member: list[list[int]] = [[] for _ in range(n)]
    while alive:
        v = min(alive, key=lambda u: (len(adj[u]), u))
        nb = sorted(adj[v])
        clique = frozenset(nb) | {v}
        if not any(clique <= cliques[k] for k in member[v]):
            for u in clique:
                member[u].append(len(cliques))
            cliques.append(clique)
        for i, a in enumerate(nb):
            adj[a].discard(v)
            for b in nb[i + 1:]:
                adj[a].add(b)
                adj[b].add(a)
        alive.discard(v)
    return [tuple(sorted(c)) for c in cliques]


def _soc_rows(blocks: list[sp.csr_matrix], offsets: list[np.ndarray] | None, nz: int) -> tuple[sp.csr_matrix, np.ndarray]:
    """Stack K cones of dimension d = len(blocks): row j of block i is component i of cone j.
    Returns (A, b) with s = b - A z, i.e. component i of cone j is offsets[i][j] + blocks[i][j] z."""
    d, count = len(blocks), blocks[0].shape[0]
    rows, cols, vals = [], [], []
    for i, blk in enumerate(blocks):
        coo = blk.tocoo()
        rows.append(d * coo.row + i)
        cols.append(coo.col)
        vals.append(-coo.data)
    a = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(d * count, nz))
    b = np.zeros(d * count)
    if offsets is not None:
        for i, off in enumerate(offsets):
            b[i::d] = off
    return a, b


class Relaxation:
    """A relaxation of the hosting-capacity problem for one case, assembled once and solved for
    any distribution of the added load."""

    def __init__(self, case: Case, kind: str = "sdp", threads: int = 0):
        if kind not in ("socp", "sdp"):
            raise ValueError(kind)
        self.case, self.kind, self.threads = case, kind, threads
        base = Lifted(case)
        branch_pairs = [tuple(p) for p in base.pairs]
        if kind == "sdp":
            self.cliques = chordal_cliques(case.n, branch_pairs)
            fill = [(c[a], c[b]) for c in self.cliques for a in range(len(c)) for b in range(a + 1, len(c))]
            self.lifted = Lifted(case, extra_pairs=fill)
        else:
            self.cliques = [tuple(p) for p in branch_pairs]
            self.lifted = base
        lf = self.lifted
        nz = lf.nz

        blocks, rhs, cones = [], [], []
        # linear limits
        blocks.append(lf.Aineq)
        rhs.append(lf.bineq)
        cones.append(clarabel.NonnegativeConeT(lf.Aineq.shape[0]))
        # thermal limits: (rate, P, Q) in the second-order cone, at both ends
        if len(lf.rated):
            zero = sp.csr_matrix((len(lf.rated), nz))
            for ap, aq in ((lf.Apf, lf.Aqf), (lf.Apt, lf.Aqt)):
                a, b = _soc_rows([zero, ap[lf.rated], aq[lf.rated]], [lf.rate, 0 * lf.rate, 0 * lf.rate], nz)
                blocks.append(a)
                rhs.append(b)
                cones += [clarabel.SecondOrderConeT(3)] * len(lf.rated)
        # pairs that form a clique of size two: (c_i + c_j, c_i - c_j, 2 wr, 2 wi) in the cone
        two = [lf.pair_index[c] for c in self.cliques if len(c) == 2]
        if two:
            k = np.array(two)
            i, j = lf.pairs[k, 0], lf.pairs[k, 1]
            r = np.arange(len(k))
            pick = lambda cols, vals: sp.csr_matrix((vals, (np.tile(r, len(cols) // len(r)), cols)), shape=(len(k), nz))
            ones = np.ones(len(k))
            a, b = _soc_rows([
                pick(np.concatenate([lf.i_c[i], lf.i_c[j]]), np.concatenate([ones, ones])),
                pick(np.concatenate([lf.i_c[i], lf.i_c[j]]), np.concatenate([ones, -ones])),
                pick(lf.i_wr[k], 2 * ones), pick(lf.i_wi[k], 2 * ones)], None, nz)
            blocks.append(a)
            rhs.append(b)
            cones += [clarabel.SecondOrderConeT(4)] * len(k)
        # larger cliques: the real embedding of the Hermitian clique matrix is positive semidefinite
        for c in self.cliques:
            if len(c) >= 3:
                a = self._psd_rows(c)
                blocks.append(a)
                rhs.append(np.zeros(a.shape[0]))
                cones.append(clarabel.PSDTriangleConeT(2 * len(c)))
        self._rest = sp.vstack([lf.Afix] + blocks).tocsc() if lf.Afix.shape[0] else sp.vstack(blocks).tocsc()
        self._rhs = np.concatenate([lf.beq, lf.bfix] + rhs)
        self._cones = [clarabel.ZeroConeT(2 * case.n + lf.Afix.shape[0])] + cones
        self._q = np.zeros(nz)
        self._q[lf.i_lam] = -1.0
        self._p = sp.csc_matrix((nz, nz))

    def _psd_rows(self, clique: tuple[int, ...]) -> sp.csr_matrix:
        """Rows that map z to minus the scaled upper triangle of M = [[R, -I], [I, R]], where
        R + jI is the Hermitian clique matrix: R_aa = c, and for a < b, R_ab = wr, I_ab = wi."""
        lf, k = self.lifted, len(clique)
        d = 2 * k
        tri = lambda i, j: j * (j + 1) // 2 + i   # (i <= j, column-major)
        rows, cols, vals = [], [], []

        def put(i: int, j: int, col: int, coef: float) -> None:
            rows.append(tri(i, j))
            cols.append(col)
            vals.append(-coef * (1.0 if i == j else SQRT2))

        for a in range(k):
            ca = int(lf.i_c[clique[a]])
            put(a, a, ca, 1.0)
            put(k + a, k + a, ca, 1.0)
            for b in range(a + 1, k):
                p = lf.pair_index[(clique[a], clique[b])]
                wr, wi = int(lf.i_wr[p]), int(lf.i_wi[p])
                put(a, b, wr, 1.0)                               # R_ab
                put(k + a, k + b, wr, 1.0)
                put(a, k + b, wi, -1.0)                          # -I_ab
                put(b, k + a, wi, 1.0)                           # -I_ba = +I_ab
        return sp.csr_matrix((vals, (rows, cols)), shape=(d * (d + 1) // 2, lf.nz))

    def solve(self, w: np.ndarray, tan_phi: float, verbose: bool = False) -> Relaxed:
        lf = self.lifted
        a = sp.vstack([lf.balances(w, tan_phi), self._rest]).tocsc()
        settings = clarabel.DefaultSettings()
        settings.verbose = verbose
        settings.static_regularization_constant = REGULARIZATION
        if self.threads:
            settings.max_threads = self.threads
        t0 = time.perf_counter()
        sol = clarabel.DefaultSolver(self._p, self._q, a, self._rhs, self._cones, settings).solve()
        seconds = time.perf_counter() - t0
        status = str(sol.status)
        if status not in OK:
            return Relaxed(self.kind, status, None, seconds)
        z = np.array(sol.x)
        ratio, volts, err = self._rank_and_voltages(z)
        # the dual objective bounds the optimum from the safe side; take the larger of the two values
        bound = max(-float(sol.obj_val), -float(sol.obj_val_dual))
        return Relaxed(self.kind, status, bound, seconds, z, ratio, volts, err,
                       abs(float(sol.obj_val) - float(sol.obj_val_dual)))

    def _rank_and_voltages(self, z: np.ndarray) -> tuple[float, np.ndarray, float]:
        lf, case = self.lifted, self.case
        c, wr, wi = z[lf.i_c], z[lf.i_wr], z[lf.i_wi]
        ratio = 0.0
        for cl in self.cliques:
            k = len(cl)
            x = np.zeros((k, k), dtype=complex)
            for a in range(k):
                x[a, a] = c[cl[a]]
                for b in range(a + 1, k):
                    p = lf.pair_index[(cl[a], cl[b])]
                    x[a, b] = wr[p] + 1j * wi[p]
                    x[b, a] = wr[p] - 1j * wi[p]
            ev = np.linalg.eigvalsh(x)
            if ev[-1] > 0:
                ratio = max(ratio, max(float(ev[-2]), 0.0) / float(ev[-1]))
        # angles along a spanning tree of the network: theta_i - theta_j = arg W_ij for i < j
        nb = [[] for _ in range(case.n)]
        for p in range(lf.n_branch_pairs):
            i, j = lf.pairs[p]
            ang = math.atan2(wi[p], wr[p])
            nb[i].append((j, -ang, p))
            nb[j].append((i, ang, p))
        theta = np.full(case.n, np.nan)
        theta[case.ref] = 0.0
        used, stack = set(), [case.ref]
        while stack:
            i = stack.pop()
            for j, step, p in nb[i]:
                if np.isnan(theta[j]):
                    theta[j] = theta[i] + step
                    used.add(p)
                    stack.append(j)
        err = 0.0
        for p in range(lf.n_branch_pairs):
            if p not in used:
                i, j = lf.pairs[p]
                d = math.atan2(wi[p], wr[p]) - (theta[i] - theta[j])
                err = max(err, abs(math.atan2(math.sin(d), math.cos(d))))
        volts = np.sqrt(np.maximum(c, 0.0)) * np.exp(1j * np.nan_to_num(theta))
        return ratio, volts, err


def dc_screening(case: Case, w: np.ndarray) -> tuple[float | None, str]:
    """The DC screening value (per unit): the largest lambda in the lossless linear power-flow
    model with branch limits on active power, generator limits and angle limits."""
    n, ng, m = case.n, case.ng, case.m
    b = 1.0 / (case.x * np.abs(case.tap))
    shift = np.angle(case.tap)
    rows = np.arange(m)
    d = sp.csr_matrix((np.concatenate([np.ones(m), -np.ones(m)]), (np.concatenate([rows, rows]),
                                                                    np.concatenate([case.f, case.t]))), shape=(m, n))
    bd = sp.diags(b) @ d                                          # P = bd theta - b shift
    nv = 1 + ng + n
    gen = sp.csr_matrix((np.ones(ng), (case.gen_bus, np.arange(ng))), shape=(n, ng))
    a_eq = sp.hstack([sp.csr_matrix(-w.reshape(-1, 1)), gen, -(d.T @ bd)]).tocsr()
    b_eq = case.pd + case.gs - d.T @ (b * shift)
    ref = sp.csr_matrix(([1.0], ([0], [1 + ng + case.ref])), shape=(1, nv))
    a_ub, b_ub = [], []
    rated = np.flatnonzero(np.isfinite(case.rate))
    if len(rated):
        flow = sp.hstack([sp.csr_matrix((len(rated), 1 + ng)), bd[rated]]).tocsr()
        a_ub += [flow, -flow]
        b_ub += [case.rate[rated] + (b * shift)[rated], case.rate[rated] - (b * shift)[rated]]
    for lim, sign in ((case.angmax, 1.0), (case.angmin, -1.0)):
        idx = np.flatnonzero(np.isfinite(lim))
        if len(idx):
            a_ub.append(sp.hstack([sp.csr_matrix((len(idx), 1 + ng)), sign * d[idx]]).tocsr())
            b_ub.append(sign * lim[idx])
    bounds = [(0, None)] + list(zip(case.pmin, case.pmax)) + [(None, None)] * n
    cost = np.zeros(nv)
    cost[0] = -1.0
    res = linprog(cost, A_ub=sp.vstack(a_ub) if a_ub else None, b_ub=np.concatenate(b_ub) if b_ub else None,
                  A_eq=sp.vstack([a_eq, ref]), b_eq=np.concatenate([b_eq, [0.0]]), bounds=bounds, method="highs")
    if res.status != 0:
        return None, res.message
    return float(res.x[0]), "Optimal"
