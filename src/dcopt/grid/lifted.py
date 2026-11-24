"""The lifted linear model that the relaxations and the AC problem share.

With W = V V^H, every power-flow quantity is linear in the entries of W that sit on the network:
c_i = W_ii = |V_i|^2 for each bus and W_ij = wr + j wi for each connected pair i < j. The model has

    y = [lambda, Pg (ng), Qg (ng)]          the added load and the generator outputs
    u = [c (n), wr (P), wi (P)]             the lifted voltage products, P pairs

and z = [y, u]. This module builds the linear maps in z:

    balances   Aeq z = beq                  active and reactive power at every bus
    fixed      Afix z = bfix                variables whose two bounds coincide
    limits     Aineq z <= bineq             generator, voltage and angle limits, lambda >= 0
    flows      Pf, Qf, Pt, Qt = A* z        branch flows at both ends (for the thermal limits)

The relaxations add convex cone constraints on u; the AC problem replaces u by its exact quadratic
expression in the rectangular voltages. The added load sits in the lambda column of the balances:
lambda * w_i of active power at bus i and lambda * w_i * tan(phi) of reactive power.
"""
from __future__ import annotations

import math

import numpy as np
import scipy.sparse as sp

from dcopt.grid.cases import Case

FIXED_TOL = 1e-9                       # bounds closer than this make an equality


class Lifted:
    def __init__(self, case: Case, extra_pairs: list[tuple[int, int]] | None = None):
        self.case = case
        n, ng, m = case.n, case.ng, case.m
        lo, hi = np.minimum(case.f, case.t), np.maximum(case.f, case.t)
        keys, inv = np.unique(lo * n + hi, return_inverse=True)
        pairs = [(int(k // n), int(k % n)) for k in keys]
        self.n_branch_pairs = len(pairs)
        if extra_pairs:
            have = set(pairs)
            pairs += sorted({(min(a, b), max(a, b)) for a, b in extra_pairs} - have)
        self.pairs = np.array(pairs, dtype=int).reshape(-1, 2)
        self.pair_index = {p: k for k, p in enumerate(pairs)}
        self.pair_of_branch = inv                              # (m,) pair of each branch
        self.sign = np.where(case.f < case.t, 1.0, -1.0)       # W_ft = wr + j * sign * wi
        npair = len(pairs)

        self.i_lam = 0
        self.i_pg = 1 + np.arange(ng)
        self.i_qg = 1 + ng + np.arange(ng)
        self.ny = 1 + 2 * ng
        self.i_c = self.ny + np.arange(n)
        self.i_wr = self.ny + n + np.arange(npair)
        self.i_wi = self.ny + n + npair + np.arange(npair)
        self.nu = n + 2 * npair
        self.nz = self.ny + self.nu

        # ---- branch flows, linear in z --------------------------------------------------------
        yff, yft, ytf, ytt = case.admittances()
        k, s, rows = inv, self.sign, np.arange(m)

        def flow(*terms: tuple[np.ndarray, np.ndarray]) -> sp.csr_matrix:
            r = np.concatenate([rows] * len(terms))
            c = np.concatenate([t[0] for t in terms])
            v = np.concatenate([t[1] for t in terms])
            return sp.csr_matrix((v, (r, c)), shape=(m, self.nz))

        self.Apf = flow((self.i_c[case.f], yff.real), (self.i_wr[k], yft.real), (self.i_wi[k], yft.imag * s))
        self.Aqf = flow((self.i_c[case.f], -yff.imag), (self.i_wr[k], -yft.imag), (self.i_wi[k], yft.real * s))
        self.Apt = flow((self.i_c[case.t], ytt.real), (self.i_wr[k], ytf.real), (self.i_wi[k], -ytf.imag * s))
        self.Aqt = flow((self.i_c[case.t], -ytt.imag), (self.i_wr[k], -ytf.imag), (self.i_wi[k], -ytf.real * s))
        self.rated = np.flatnonzero(np.isfinite(case.rate))
        self.rate = case.rate[self.rated]

        # ---- bus balances (the lambda column is added by `balances`) ---------------------------
        cf = sp.csr_matrix((np.ones(m), (rows, case.f)), shape=(m, n))
        ct = sp.csr_matrix((np.ones(m), (rows, case.t)), shape=(m, n))
        bus = np.arange(n)
        gen_p = sp.csr_matrix((np.ones(ng), (case.gen_bus, self.i_pg)), shape=(n, self.nz))
        gen_q = sp.csr_matrix((np.ones(ng), (case.gen_bus, self.i_qg)), shape=(n, self.nz))
        shunt_g = sp.csr_matrix((case.gs, (bus, self.i_c)), shape=(n, self.nz))
        shunt_b = sp.csr_matrix((case.bs, (bus, self.i_c)), shape=(n, self.nz))
        ep = gen_p - shunt_g - (cf.T @ self.Apf + ct.T @ self.Apt)
        eq = gen_q + shunt_b - (cf.T @ self.Aqf + ct.T @ self.Aqt)
        self.Aeq0 = sp.vstack([ep, eq]).tocsr()
        self.beq = np.concatenate([case.pd, case.qd])

        # ---- limits ------------------------------------------------------------------------
        fix_rows: list[tuple[int, float]] = []                  # (column, value)
        ineq: list[tuple[list[int], list[float], float]] = []    # (columns, coefficients, rhs)
        labels: list[tuple[str, int]] = []                       # (kind, element index)

        def bounds(cols: np.ndarray, lower: np.ndarray, upper: np.ndarray, kind_lo: str, kind_hi: str) -> None:
            for e, (col, a, b) in enumerate(zip(cols, lower, upper)):
                if np.isfinite(a) and np.isfinite(b) and b - a < FIXED_TOL:
                    fix_rows.append((int(col), 0.5 * (a + b)))
                    continue
                if np.isfinite(b):
                    ineq.append(([int(col)], [1.0], float(b)))
                    labels.append((kind_hi, e))
                if np.isfinite(a):
                    ineq.append(([int(col)], [-1.0], float(-a)))
                    labels.append((kind_lo, e))

        ineq.append(([self.i_lam], [-1.0], 0.0))
        labels.append(("lambda", 0))
        bounds(self.i_pg, case.pmin, case.pmax, "pmin", "pmax")
        bounds(self.i_qg, case.qmin, case.qmax, "qmin", "qmax")
        bounds(self.i_c, case.vmin ** 2, case.vmax ** 2, "vmin", "vmax")
        for l in range(m):                                       # tan(angmin) wr <= s wi <= tan(angmax) wr
            wr, wi, sg = int(self.i_wr[k[l]]), int(self.i_wi[k[l]]), float(s[l])
            if np.isfinite(case.angmin[l]):
                ineq.append(([wr, wi], [math.tan(case.angmin[l]), -sg], 0.0))
                labels.append(("angmin", l))
            if np.isfinite(case.angmax[l]):
                ineq.append(([wr, wi], [-math.tan(case.angmax[l]), sg], 0.0))
                labels.append(("angmax", l))

        r = np.concatenate([[i] * len(c) for i, (c, _, _) in enumerate(ineq)]).astype(int)
        c = np.concatenate([c for c, _, _ in ineq]).astype(int)
        v = np.concatenate([v for _, v, _ in ineq])
        self.Aineq = sp.csr_matrix((v, (r, c)), shape=(len(ineq), self.nz))
        self.bineq = np.array([h for _, _, h in ineq])
        self.labels = labels
        self.Afix = sp.csr_matrix((np.ones(len(fix_rows)), (np.arange(len(fix_rows)), [c for c, _ in fix_rows])),
                                  shape=(len(fix_rows), self.nz))
        self.bfix = np.array([val for _, val in fix_rows])

    def balances(self, w: np.ndarray, tan_phi: float) -> sp.csr_matrix:
        """The balance rows with the added load in the lambda column: lambda * w of active power
        and lambda * w * tan(phi) of reactive power drawn at each bus."""
        n = self.case.n
        col = sp.csr_matrix((np.concatenate([-w, -w * tan_phi]), (np.arange(2 * n), np.zeros(2 * n, dtype=int))),
                            shape=(2 * n, self.nz))
        return (self.Aeq0 + col).tocsr()


def weights(case: Case, bus) -> np.ndarray:
    """The distribution of the added load: one bus index, or a mapping {bus index: weight}."""
    w = np.zeros(case.n)
    if isinstance(bus, dict):
        for i, share in bus.items():
            w[int(i)] = float(share)
        total = w.sum()
        if total <= 0:
            raise ValueError("the weights must be positive")
        return w / total
    w[int(bus)] = 1.0
    return w
