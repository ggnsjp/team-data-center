"""A lower bound on the hostable load: an AC-feasible operating point, found by a local
interior-point method and then checked independently.

Problem   maximize lambda over x = [y, e, f]: y = [lambda, Pg, Qg] and the bus voltages in
          rectangular coordinates V = e + jf. The lifted products of the shared model are exact
          quadratics here,  c_i = e_i^2 + f_i^2,  wr = e_i e_j + f_i f_j,  wi = f_i e_j - e_i f_j,
          so every linear row of the lifted model becomes a quadratic constraint and a thermal
          limit becomes P(x)^2 + Q(x)^2 <= rate^2. Jacobians and the Hessian of the Lagrangian are
          exact and sparse (each lifted product has a constant Hessian).
Method    A primal-dual interior-point method in the style of MIPS (Wang, Murillo-Sanchez,
          Zimmerman and Thomas 2007): Newton steps on the perturbed optimality conditions with a
          fraction-to-boundary rule. It finds a local optimum; nothing here proves global
          optimality. The certificate comes from the relaxations in relax.py.
Check     `check_point` recomputes the complex power balance and every limit from the voltages
          alone. Only a point that passes it (largest violation below `FEAS_TOL` per unit) counts
          as a lower bound.
Optional  `global_gurobi` hands the same problem to Gurobi's nonconvex solver for cross-checks
          on small systems. Nothing else in the package needs Gurobi.
"""
from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from dcopt.grid.cases import Case
from dcopt.grid.lifted import Lifted

FEAS_TOL = 1e-6                        # largest violation (per unit) of an accepted AC point
ACTIVE_TOL = 1e-6                      # a multiplier above this marks a binding limit
Z_FLOOR = 1e-2                         # smallest initial slack of the interior-point method
PROX, PROX_MIN, PROX_MAX, PROX_SHRINK = 0.05, 1e-7, 10.0, 0.2   # the proximal weight in `maximize`


@dataclass
class ACPoint:
    """An operating point returned by the local solver. Powers are per unit."""
    value: float | None                # lambda at a verified point, None if no point was verified
    violation: float                   # largest violation found by `check_point`
    converged: bool
    iterations: int
    seconds: float
    start: str = ""
    lam: float = 0.0
    pg: np.ndarray | None = None
    qg: np.ndarray | None = None
    voltages: np.ndarray | None = None
    mu: np.ndarray | None = None       # multipliers of the labelled limits, then thermal from/to
    detail: dict = field(default_factory=dict)


def check_point(case: Case, w: np.ndarray, tan_phi: float, lam: float, pg: np.ndarray, qg: np.ndarray,
                v: np.ndarray) -> dict:
    """Every constraint of the AC problem, evaluated from the complex voltages. Returns the
    violations by kind (per unit, radians for angles) and the largest of them under "max"."""
    yff, yft, ytf, ytt = case.admittances()
    vf, vt = v[case.f], v[case.t]
    sf = vf * np.conj(yff * vf + yft * vt)
    st = vt * np.conj(ytf * vf + ytt * vt)
    sbus = np.conj(case.gs + 1j * case.bs) * np.abs(v) ** 2
    np.add.at(sbus, case.f, sf)
    np.add.at(sbus, case.t, st)
    sgen = np.zeros(case.n, dtype=complex)
    np.add.at(sgen, case.gen_bus, pg + 1j * qg)
    mismatch = sgen - (case.pd + 1j * case.qd) - lam * w * (1 + 1j * tan_phi) - sbus
    vm = np.abs(v)
    ang = np.angle(vf * np.conj(vt))
    pos = lambda a: float(np.max(a, initial=0.0))
    out = {
        "balance_p": float(np.max(np.abs(mismatch.real), initial=0.0)),
        "balance_q": float(np.max(np.abs(mismatch.imag), initial=0.0)),
        "voltage": max(pos(vm - case.vmax), pos(case.vmin - vm)),
        "thermal": max(pos(np.abs(sf) - case.rate), pos(np.abs(st) - case.rate)),
        "generation_p": max(pos(pg - case.pmax), pos(case.pmin - pg)),
        "generation_q": max(pos(qg - case.qmax), pos(case.qmin - qg)),
        "angle": max(pos(ang - case.angmax), pos(case.angmin - ang)),
        "lambda": max(-lam, 0.0),
    }
    out["max"] = max(out.values())
    out["sf"], out["st"] = sf, st
    return out


class ACProblem:
    """The AC hosting-capacity problem of one case, assembled once and solved for any distribution
    of the added load and any starting point."""

    def __init__(self, case: Case):
        self.case = case
        lf = self.lifted = Lifted(case)
        n, npair = case.n, len(lf.pairs)
        i, j = lf.pairs[:, 0], lf.pairs[:, 1]
        bus, k, one = np.arange(n), np.arange(npair), np.ones(npair)
        # d u / d v as (row, col, source, coefficient): entry = coefficient * v[source], v = [e, f]
        self._rows = np.concatenate([bus, bus, n + k, n + k, n + k, n + k,
                                     n + npair + k, n + npair + k, n + npair + k, n + npair + k])
        self._cols = np.concatenate([bus, n + bus, i, j, n + i, n + j, i, j, n + i, n + j])
        self._src = np.concatenate([bus, n + bus, j, i, n + j, n + i, n + j, n + i, j, i])
        self._coef = np.concatenate([2 * np.ones(n), 2 * np.ones(n), one, one, one, one, -one, one, one, -one])
        self.ny, self.nx = lf.ny, lf.ny + 2 * n
        r = lf.rated
        self._flows = [lf.Apf[r], lf.Aqf[r], lf.Apt[r], lf.Aqt[r]]
        self._rate2 = lf.rate ** 2
        self._ref = sp.csr_matrix(([1.0], ([0], [self.ny + n + case.ref])), shape=(1, self.nx))
        self._df = np.zeros(self.nx)
        self._df[0] = -1.0
        self.n_labelled = lf.Aineq.shape[0]

    # ---- evaluation ----------------------------------------------------------------------------
    def _lift(self, x: np.ndarray) -> tuple[np.ndarray, sp.csr_matrix]:
        lf, n = self.lifted, self.case.n
        v = x[self.ny:]
        u_v = sp.csr_matrix((self._coef * v[self._src], (self._rows, self._cols)), shape=(lf.nu, 2 * n))
        z = np.concatenate([x[:self.ny], 0.5 * (u_v @ v)])
        return z, sp.block_diag([sp.identity(self.ny, format="csr"), u_v], format="csr")

    def _hessian(self, aeq: sp.csr_matrix, lam: np.ndarray, mu: np.ndarray, flows, jac) -> sp.csr_matrix:
        lf, n = self.lifted, self.case.n
        ne, nf, nl, nr = aeq.shape[0], lf.Afix.shape[0], self.n_labelled, len(lf.rated)
        mu_f, mu_t = mu[nl:nl + nr], mu[nl + nr:nl + 2 * nr]
        nu = aeq.T @ lam[:ne] + lf.Afix.T @ lam[ne:ne + nf] + lf.Aineq.T @ mu[:nl]
        for a, fl, m in zip(self._flows, flows, (mu_f, mu_f, mu_t, mu_t)):
            nu = nu + a.T @ (2 * m * fl)
        nu = nu[self.ny:]
        hvv = sp.csr_matrix((nu[self._rows] * self._coef, (self._cols, self._src)), shape=(2 * n, 2 * n))
        lxx = sp.block_diag([sp.csr_matrix((self.ny, self.ny)), hvv], format="csr")
        for j, m in zip(jac, (mu_f, mu_f, mu_t, mu_t)):
            lxx = lxx + j.T @ sp.diags(2 * m) @ j
        return lxx

    def start(self, voltages: np.ndarray | None = None, y: np.ndarray | None = None) -> np.ndarray:
        """A starting point: the given voltages and y, or a flat start with mid-range generators."""
        case, lf = self.case, self.lifted
        mid = lambda lo, hi: np.where(np.isfinite(lo) & np.isfinite(hi), 0.5 * (lo + hi), 0.0)
        x = np.zeros(self.nx)
        if y is None:
            x[lf.i_pg], x[lf.i_qg] = mid(case.pmin, case.pmax), mid(case.qmin, case.qmax)
        else:
            x[:self.ny] = y
            x[0] = max(x[0], 0.0)
        if voltages is None:
            voltages = 0.5 * (case.vmin + case.vmax) + 0j
        voltages = voltages * np.exp(-1j * np.angle(voltages[case.ref]))
        x[self.ny:self.ny + case.n], x[self.ny + case.n:] = voltages.real, voltages.imag
        return x

    # ---- the interior-point method ---------------------------------------------------------------
    def solve(self, w: np.ndarray, tan_phi: float, x0: np.ndarray | None = None, start: str = "flat",
              cost: np.ndarray | None = None, extra_load: float = 0.0, prox: float = 0.0,
              max_it: int = 250, tol: float = 1e-8, step_control: bool = False) -> ACPoint:
        """One interior-point run from x0. By default the objective is to maximize lambda; `cost`
        (a vector over y = [lambda, Pg, Qg]) replaces it, and `extra_load` adds a fixed load of
        that size with the distribution w. With prox > 0 the objective gets the proximal term
        prox * |x - x0|^2, which keeps the Newton systems well conditioned (see `maximize`)."""
        case, lf = self.case, self.lifted
        aeq = lf.balances(w, tan_phi)
        beq = lf.beq + extra_load * np.concatenate([w, w * tan_phi])
        df = np.zeros(self.nx)
        if cost is None:
            df[0] = -1.0
        else:
            df[:self.ny] = cost
        x = self.start() if x0 is None else x0.copy()
        center = x.copy()
        prox_h = sp.identity(self.nx, format="csr") * (2.0 * prox)
        t0 = time.perf_counter()
        inf = lambda a: float(np.max(np.abs(a), initial=0.0))
        cost_of = lambda xv: float(df @ xv) + prox * float((xv - center) @ (xv - center))
        grad_of = lambda xv: df + 2.0 * prox * (xv - center)

        def evaluate(xv: np.ndarray):
            z_, t_ = self._lift(xv)
            g_ = np.concatenate([aeq @ z_ - beq, lf.Afix @ z_ - lf.bfix, self._ref @ xv])
            flows_ = [a @ z_ for a in self._flows]
            h_ = np.concatenate([lf.Aineq @ z_ - lf.bineq, flows_[0] ** 2 + flows_[1] ** 2 - self._rate2,
                                 flows_[2] ** 2 + flows_[3] ** 2 - self._rate2])
            return z_, t_, g_, h_, flows_

        def jacobians(t_: sp.csr_matrix, flows_):
            jac_ = [a @ t_ for a in self._flows]
            dg_ = sp.vstack([aeq @ t_, lf.Afix @ t_, self._ref]).tocsr()
            dh_ = sp.vstack([lf.Aineq @ t_] + [2 * (sp.diags(flows_[p]) @ jac_[p] + sp.diags(flows_[q]) @ jac_[q])
                                               for p, q in ((0, 1), (2, 3))]).tocsr()
            return dg_, dh_, jac_

        _, t, g, h, flows = evaluate(x)
        dg, dh, jac = jacobians(t, flows)
        nx, neq, niq = self.nx, len(g), len(h)
        xi, sigma = 0.99995, 0.1
        gamma = 1.0
        lam = np.zeros(neq)
        z = np.maximum(-h, Z_FLOOR)
        mu = gamma / z
        f = cost_of(x)
        lx = grad_of(x) + dg.T @ lam + dh.T @ mu
        converged, it, conds = False, 0, (np.inf,) * 4
        feas = max(inf(g), float(np.max(h, initial=0.0)))
        grad = inf(lx) / (1 + max(inf(lam), inf(mu)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", MatrixRankWarning)
            while it < max_it:
                it += 1
                lxx = self._hessian(aeq, lam, mu, flows, jac) + prox_h
                zinv = 1.0 / z
                dh_zinv = dh.T @ sp.diags(zinv)
                m = lxx + dh_zinv @ sp.diags(mu) @ dh
                n_vec = lx + dh_zinv @ (mu * h + gamma)
                rhs = np.concatenate([-n_vec, -g])
                kkt = sp.bmat([[m, dg.T], [dg, None]], format="csc")
                step = spsolve(kkt, rhs)
                if not np.all(np.isfinite(step)):                 # singular system: regularize once
                    reg = sp.diags(np.concatenate([np.full(nx, 1e-8), np.full(neq, -1e-8)]))
                    step = spsolve((kkt + reg).tocsc(), rhs)
                    if not np.all(np.isfinite(step)):
                        break
                dx, dlam = step[:nx], step[nx:]
                dz = -h - z - dh @ dx
                dmu = -mu + zinv * (gamma - mu * dz)
                neg = dz < 0
                alpha_p = min(xi * np.min(z[neg] / -dz[neg]), 1.0) if neg.any() else 1.0
                neg = dmu < 0
                alpha_d = min(xi * np.min(mu[neg] / -dmu[neg]), 1.0) if neg.any() else 1.0
                if step_control:                                   # shorten a step the model predicts badly
                    _, t1, g1, h1, fl1 = evaluate(x + alpha_p * dx)
                    dg1, dh1, _ = jacobians(t1, fl1)
                    feas1 = max(inf(g1), float(np.max(h1, initial=0.0)))
                    grad1 = inf(grad_of(x + alpha_p * dx) + dg1.T @ lam + dh1.T @ mu) / (1 + max(inf(lam), inf(mu)))
                    if feas1 > feas and grad1 > grad:
                        lag = f + lam @ g + mu @ (h + z) - gamma * np.sum(np.log(z))
                        alpha = alpha_p
                        for _ in range(20):
                            dx1 = alpha * dx
                            _, _, g1, h1, _ = evaluate(x + dx1)
                            lag1 = cost_of(x + dx1) + lam @ g1 + mu @ (h1 + z) - gamma * np.sum(np.log(z))
                            pred = lx @ dx1 + 0.5 * dx1 @ (lxx @ dx1)
                            rho = (lag1 - lag) / pred if pred != 0 else 1.0
                            if 0.95 < rho < 1.05:
                                break
                            alpha /= 2
                        scale = alpha / alpha_p
                        dx, dz, dlam, dmu = scale * dx, scale * dz, scale * dlam, scale * dmu
                x = x + alpha_p * dx
                z = z + alpha_p * dz
                lam = lam + alpha_d * dlam
                mu = mu + alpha_d * dmu
                gamma = sigma * float(z @ mu) / niq
                f_old, f = f, cost_of(x)
                _, t, g, h, flows = evaluate(x)
                dg, dh, jac = jacobians(t, flows)
                lx = grad_of(x) + dg.T @ lam + dh.T @ mu
                feas = max(inf(g), float(np.max(h, initial=0.0)))
                grad = inf(lx) / (1 + max(inf(lam), inf(mu)))
                conds = (feas, grad, float(z @ mu) / (1 + inf(x)), abs(f - f_old) / (1 + abs(f_old)))
                if max(conds) < tol:
                    converged = True
                    break
                if not np.all(np.isfinite(x)) or alpha_p < 1e-12 or alpha_d < 1e-12 or gamma > 1e16:
                    break
        seconds = time.perf_counter() - t0
        n = case.n
        if not np.all(np.isfinite(x)):
            return ACPoint(None, np.inf, False, it, seconds, start)
        v = x[self.ny:self.ny + n] + 1j * x[self.ny + n:]
        pg, qg = x[lf.i_pg], x[lf.i_qg]
        lam_load = float(x[0]) + extra_load
        chk = check_point(case, w, tan_phi, lam_load, pg, qg, v)
        ok = chk["max"] < FEAS_TOL
        return ACPoint(lam_load if ok else None, chk["max"], converged, it, seconds, start, lam_load, pg, qg, v,
                       mu if cost is None else None,
                       {"conditions": conds, "x": x, "check": {k: v for k, v in chk.items() if k not in ("sf", "st")}})

    def maximize(self, w: np.ndarray, tan_phi: float, x0: np.ndarray, start: str = "base", rho: float = PROX,
                 rounds: int = 40, tol: float = 1e-8) -> ACPoint | None:
        """Maximize lambda from a given point by the proximal-point method: each round solves
        max lambda - rho |x - x_k|^2 from the last verified point x_k. The proximal term keeps the
        Newton systems well conditioned where the plain problem stalls; rho shrinks after every
        successful round and grows again after a failed one. The added load never decreases from
        one verified point to the next. A round with a negligible proximal term that no longer
        moves has the optimality conditions of the original problem, so its multipliers identify
        the binding limits."""
        t0 = time.perf_counter()
        best, x, total_it = None, x0, 0
        for _ in range(rounds):
            trial = self.solve(w, tan_phi, x0=x, start=start, prox=rho)
            total_it += trial.iterations
            if trial.value is None or not trial.converged or (best is not None and trial.value < best.value - 1e-9):
                if rho >= PROX_MAX:
                    break
                rho = min(rho * 10.0, PROX_MAX)
                continue
            gain = trial.value - (best.value if best is not None else -np.inf)
            best, x = trial, trial.detail["x"]
            if gain < tol * max(1.0, abs(best.value)) and rho <= PROX_MIN * 10.0:
                break
            rho = max(rho * PROX_SHRINK, PROX_MIN)
        if best is not None:
            best.iterations, best.seconds = total_it, time.perf_counter() - t0
            best.detail["prox"] = rho
        return best

    def base_point(self, relaxed_voltages: np.ndarray | None = None) -> ACPoint:
        """A feasible operating point of the case as it is (no added load). Tried in this order, and
        the first point that passes the check is returned:
          1. the flat start itself, with every generator at the output nearest to zero (a network
             without load is feasible there, and the interior-point method is ill-conditioned on it);
          2. the least-generation dispatch from the flat start;
          3. the same from a start whose total generation matches the load;
          4. the same with a proximal term, and from the given voltage estimate."""
        case, lf = self.case, self.lifted
        w = np.zeros(case.n)
        x = self.start()
        x[lf.i_pg], x[lf.i_qg] = np.clip(0.0, case.pmin, case.pmax), np.clip(0.0, case.qmin, case.qmax)
        v = x[self.ny:self.ny + case.n] + 1j * x[self.ny + case.n:]
        chk = check_point(case, w, 0.0, 0.0, x[lf.i_pg], x[lf.i_qg], v)
        if chk["max"] < FEAS_TOL:
            return ACPoint(0.0, chk["max"], True, 0, 0.0, "base (flat start is feasible)", 0.0, x[lf.i_pg], x[lf.i_qg], v,
                           None, {"x": x, "check": {k: val for k, val in chk.items() if k not in ("sf", "st")}})
        cost = np.zeros(self.ny)
        cost[lf.i_lam] = 1.0
        cost[lf.i_pg] = 1.0
        point = self.solve(w, 0.0, start="base (flat)", cost=cost)
        if point.value is not None:
            return point
        matched = self.start()
        span = case.pmax - case.pmin
        share = float(np.clip((1.02 * case.pd.sum() - case.pmin.sum()) / max(float(span.sum()), 1e-9), 0.02, 0.98))
        matched[lf.i_pg] = case.pmin + share * span
        attempts = [("base (matched dispatch)", matched, 0.0), ("base (proximal)", self.start(), 1e-2),
                    ("base (matched, proximal)", matched, 1e-2)]
        if relaxed_voltages is not None:
            attempts.append(("base (relaxation)", self.start(relaxed_voltages), 0.0))
        for name, x0, prox in attempts:
            trial = self.solve(w, 0.0, x0=x0, start=name, cost=cost, prox=prox)
            if trial.value is not None:
                return trial
        return point

    def climb(self, w: np.ndarray, tan_phi: float, base: ACPoint, upper: float, steps: int = 14) -> ACPoint | None:
        """A fallback when the direct runs fail: bisection on a fixed added load between 0 and an
        upper bound, each feasibility run warm-started from the last feasible point."""
        if base.value is None:
            return None
        cost = np.zeros(self.ny)
        cost[self.lifted.i_lam] = 1.0
        cost[self.lifted.i_pg] = 1.0
        lo, hi, best, x_best = 0.0, float(upper), None, base.detail["x"]
        for _ in range(steps):
            mid = 0.5 * (lo + hi)
            trial = self.solve(w, tan_phi, x0=x_best, start="bisection", cost=cost, extra_load=mid)
            if trial.value is not None:
                lo, best, x_best = mid, trial, trial.detail["x"]
            else:
                hi = mid
        return best

    def binding(self, point: ACPoint) -> list[dict]:
        """The binding limits of a solved point, each with the extra hostable load (per unit) that a
        1 % relaxation of that limit would give, from its multiplier."""
        case, lf = self.case, self.lifted
        if point.mu is None:
            return []
        out = []
        nl, nr = self.n_labelled, len(lf.rated)
        for row, (kind, e) in enumerate(lf.labels):
            mu = float(point.mu[row])
            if kind == "lambda" or mu < ACTIVE_TOL:
                continue
            if kind in ("pmax", "pmin"):
                lim = abs(float(getattr(case, kind)[e]))
                out.append({"kind": "generation (P)", "element": f"generator at bus {case.label(case.gen_bus[e])}",
                            "limit": kind, "gain": mu * 0.01 * lim})
            elif kind in ("qmax", "qmin"):
                lim = abs(float(getattr(case, kind)[e]))
                out.append({"kind": "reactive (Q)", "element": f"generator at bus {case.label(case.gen_bus[e])}",
                            "limit": kind, "gain": mu * 0.01 * lim})
            elif kind in ("vmin", "vmax"):
                lim = float(getattr(case, kind)[e])
                out.append({"kind": "voltage", "element": f"bus {case.label(e)}", "limit": kind,
                            "gain": mu * 0.02 * lim ** 2})
            else:                                                   # angmin, angmax
                a = float(getattr(case, kind)[e])
                wr = float(abs(point.voltages[case.f[e]] * np.conj(point.voltages[case.t[e]])).real)
                out.append({"kind": "angle", "element": f"branch {case.label(case.f[e])}-{case.label(case.t[e])}",
                            "limit": kind, "gain": mu * 0.01 * abs(a) * (1 + np.tan(a) ** 2) * wr})
        for end, offset in (("from", nl), ("to", nl + nr)):
            for pos, l in enumerate(lf.rated):
                mu = float(point.mu[offset + pos])
                if mu >= ACTIVE_TOL:
                    out.append({"kind": "thermal",
                                "element": f"branch {case.label(case.f[l])}-{case.label(case.t[l])}",
                                "limit": f"rating ({end} end)", "gain": mu * 0.02 * float(case.rate[l]) ** 2})
        return sorted(out, key=lambda b: -b["gain"])


def global_gurobi(case: Case, w: np.ndarray, tan_phi: float, time_limit: float = 60.0,
                  gap: float = 1e-4) -> tuple[float | None, float | None, str]:
    """The same AC problem as a nonconvex quadratically constrained program for Gurobi (optional).
    Returns (best feasible lambda, proven upper bound, status), per unit."""
    import gurobipy as gp
    from gurobipy import GRB

    lf = Lifted(case)
    n = case.n
    with gp.Env(empty=True) as env:
        env.setParam("OutputFlag", 0)
        env.start()
        with gp.Model(env=env) as m:
            z = m.addMVar(lf.nz, lb=-GRB.INFINITY, name="z")
            vmax = float(case.vmax.max())
            e = m.addMVar(n, lb=-vmax, ub=vmax, name="e")
            f = m.addMVar(n, lb=-vmax, ub=vmax, name="f")
            m.addConstr(lf.balances(w, tan_phi) @ z == lf.beq)
            if lf.Afix.shape[0]:
                m.addConstr(lf.Afix @ z == lf.bfix)
            m.addConstr(lf.Aineq @ z <= lf.bineq)
            r = lf.rated
            if len(r):
                for ap, aq in ((lf.Apf[r], lf.Aqf[r]), (lf.Apt[r], lf.Aqt[r])):
                    p = m.addMVar(len(r), lb=-GRB.INFINITY)
                    q = m.addMVar(len(r), lb=-GRB.INFINITY)
                    m.addConstr(p == ap @ z)
                    m.addConstr(q == aq @ z)
                    for a in range(len(r)):
                        m.addConstr(p[a] * p[a] + q[a] * q[a] <= float(lf.rate[a]) ** 2)
            for i in range(n):
                m.addConstr(z[int(lf.i_c[i])] == e[i] * e[i] + f[i] * f[i])
            for k, (i, j) in enumerate(lf.pairs):
                m.addConstr(z[int(lf.i_wr[k])] == e[int(i)] * e[int(j)] + f[int(i)] * f[int(j)])
                m.addConstr(z[int(lf.i_wi[k])] == f[int(i)] * e[int(j)] - e[int(i)] * f[int(j)])
            m.addConstr(f[case.ref] == 0)
            m.addConstr(e[case.ref] >= 0)
            m.setObjective(z[lf.i_lam], GRB.MAXIMIZE)
            m.Params.NonConvex = 2
            m.Params.TimeLimit = time_limit
            m.Params.MIPGap = gap
            m.optimize()
            best = float(m.ObjVal) if m.SolCount else None
            bound = float(m.ObjBound) if m.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL) else None
            return best, bound, {GRB.OPTIMAL: "optimal", GRB.TIME_LIMIT: "time limit",
                                 GRB.INFEASIBLE: "infeasible"}.get(m.Status, str(m.Status))
