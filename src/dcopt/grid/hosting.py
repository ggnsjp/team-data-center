"""Hosting capacity of a bus: how much added load the network can serve there.

Definition  For a bus b (or a weighted set of buses) and a power factor cos(phi), the hosting
            capacity is the largest added load lambda (MW), with reactive power lambda tan(phi),
            for which the AC network still has an operating point within every limit: bus
            voltages, branch ratings at both ends, angle differences and generator P and Q.
            Existing loads stay fixed and all generators may redispatch (the best case).
Bracket     upper bounds   SOCP and SDP relaxations (relax.py): no AC point can exceed them.
            lower bound    a verified AC-feasible point (ac.py): this much load is hostable.
            gap            (upper - lower) / upper. Zero means the AC value is known exactly.
Screening   The DC value is the usual linear screening estimate. It is not a bound.

Example     >>> from dcopt.grid import cases, hosting
            >>> h = hosting.hosting_capacity(cases.load("ring5"), bus=2)
            >>> round(h.ac, 1), round(h.upper, 1), h.limit
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from dcopt.grid.ac import ACPoint, ACProblem
from dcopt.grid.cases import Case
from dcopt.grid.lifted import weights
from dcopt.grid.relax import Relaxation, dc_screening

METHODS = ("dc", "socp", "sdp", "ac")
GAP_CLOSED = 1e-4                      # a gap below this counts as closed; no further AC runs
DIRECT_ITERATIONS = 80                 # cap of the direct run (a run that converges needs far fewer)
SETTLED_PROX = 1e-5                    # a climb that ends with a proximal weight below this has settled
KINDS = ("thermal", "voltage", "generation (P)", "reactive (Q)", "angle")


@dataclass
class Hosting:
    """The bracket for one bus. Powers are in MW; `None` marks a value that was not computed or
    could not be found."""
    case: str
    bus: str
    pf: float
    dc: float | None = None            # DC screening estimate (not a bound)
    socp: float | None = None          # upper bound, second-order cone relaxation
    sdp: float | None = None           # upper bound, semidefinite relaxation
    ac: float | None = None            # lower bound, verified AC-feasible point
    upper: float | None = None         # the tighter of the two upper bounds
    gap: float | None = None           # (upper - ac) / upper
    rank_ratio: float | None = None    # second/first eigenvalue of the SDP solution, worst clique
    violation: float | None = None     # largest violation of the AC point (per unit)
    limit: str = ""                    # the kind of limit that binds most, "" if unknown
    binding: list[dict] = field(default_factory=list)   # binding limits, most sensitive first
    start: str = ""                    # the starting point that gave the AC value
    times: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)
    voltages: np.ndarray | None = None  # the AC point's complex bus voltages

    def row(self) -> dict:
        """A flat record for tables and CSV files."""
        top = self.binding[0] if self.binding else {}
        return {"case": self.case, "bus": self.bus, "pf": self.pf, "dc": self.dc, "socp": self.socp,
                "sdp": self.sdp, "ac": self.ac, "upper": self.upper, "gap": self.gap, "rank_ratio": self.rank_ratio,
                "violation": self.violation, "limit": self.limit, "top_element": top.get("element", ""),
                "top_gain_mw": top.get("gain"), "start": self.start,
                **{f"t_{k}": v for k, v in self.times.items()}, **{f"status_{k}": v for k, v in self.status.items()}}


class HostingModel:
    """The models of one case, built on first use and reused for every bus."""

    def __init__(self, case: Case, threads: int = 0):
        self.case, self.threads = case, threads
        self._relax: dict[str, Relaxation] = {}
        self._ac: ACProblem | None = None
        self._base: ACPoint | None = None

    def relaxation(self, kind: str) -> Relaxation:
        if kind not in self._relax:
            self._relax[kind] = Relaxation(self.case, kind, threads=self.threads)
        return self._relax[kind]

    @property
    def ac(self) -> ACProblem:
        if self._ac is None:
            self._ac = ACProblem(self.case)
        return self._ac

    def base(self) -> ACPoint:
        """A feasible operating point without added load (the same for every bus)."""
        if self._base is None:
            self._base = self.ac.base_point()
        return self._base

    def evaluate(self, bus, pf: float = 0.95, methods: tuple[str, ...] = METHODS) -> Hosting:
        case, mva = self.case, self.case.base_mva
        w = weights(case, bus)
        tan_phi = math.tan(math.acos(pf))
        out = Hosting(case.name, case.label(int(bus)) if not isinstance(bus, dict) else "weighted", pf)
        if "dc" in methods:
            t0 = time.perf_counter()
            value, status = dc_screening(case, w)
            out.dc = None if value is None else value * mva
            out.times["dc"], out.status["dc"] = time.perf_counter() - t0, status
        relaxed = {}
        for kind in ("socp", "sdp"):
            if kind in methods:
                r = relaxed[kind] = self.relaxation(kind).solve(w, tan_phi)
                setattr(out, kind, None if r.value is None else r.value * mva)
                out.times[kind], out.status[kind] = r.seconds, r.status
        uppers = [v for v in (out.sdp, out.socp) if v is not None]
        out.upper = min(uppers) if uppers else None
        if "sdp" in relaxed and relaxed["sdp"].solved:
            out.rank_ratio = relaxed["sdp"].rank_ratio
        if "ac" in methods:
            t0 = time.perf_counter()
            point = self._ac_point(w, tan_phi, relaxed, None if out.upper is None else out.upper / mva)
            out.times["ac"] = time.perf_counter() - t0
            if point is not None and point.value is not None:
                out.ac, out.violation, out.start, out.voltages = point.value * mva, point.violation, point.start, point.voltages
                out.binding = [{**b, "gain": b["gain"] * mva} for b in self.ac.binding(point)]
                gains = {k: sum(b["gain"] for b in out.binding if b["kind"] == k) for k in KINDS}
                if out.binding:
                    out.limit = max(gains, key=gains.get)
                out.status["ac"] = "verified"
            else:
                out.status["ac"] = "no verified point"
        if out.ac is not None and out.upper is not None and out.upper > 0:
            out.gap = max(out.upper - out.ac, 0.0) / out.upper
        return out

    def _ac_point(self, w: np.ndarray, tan_phi: float, relaxed: dict, upper: float | None) -> ACPoint | None:
        """The best verified AC point: a direct run from the base point, then the proximal-point
        climb from the best point so far, and, if that climb did not settle, a second climb from
        the voltages recovered from the tightest relaxation."""
        ac, best = self.ac, None

        def closed() -> bool:
            return upper is not None and best is not None and upper - best.value <= GAP_CLOSED * max(upper, 1e-9)

        def keep(p: ACPoint | None) -> None:
            nonlocal best
            if p is not None and p.value is not None and (best is None or p.value > best.value):
                best = p

        base = self.base()
        if base.value is None:
            return None
        direct = ac.solve(w, tan_phi, x0=base.detail["x"], start="base point", max_it=DIRECT_ITERATIONS)
        if direct.converged:
            keep(direct)
        if closed():
            return best
        climb = ac.maximize(w, tan_phi, best.detail["x"] if best is not None else base.detail["x"],
                            start="proximal climb")
        keep(climb)
        settled = climb is not None and climb.detail.get("prox", 1.0) <= SETTLED_PROX
        if not closed() and not settled:
            r = next((relaxed[k] for k in ("sdp", "socp") if k in relaxed and relaxed[k].solved), None)
            if r is not None:
                keep(ac.maximize(w, tan_phi, ac.start(r.voltages, r.z[:ac.ny].copy()),
                                 start=f"proximal climb from the {r.kind} solution"))
        return best


def hosting_capacity(case: Case, bus, pf: float = 0.95, methods: tuple[str, ...] = METHODS,
                     model: HostingModel | None = None) -> Hosting:
    """The hosting-capacity bracket of one bus (an index into the case, or {index: weight})."""
    return (model or HostingModel(case)).evaluate(bus, pf, methods)


_WORKER: dict = {}


def _init_worker(case: Case) -> None:
    _WORKER["model"] = HostingModel(case, threads=1)


def _work(args: tuple) -> Hosting:
    bus, pf, methods = args
    return _WORKER["model"].evaluate(bus, pf, methods)


def hosting_map(case: Case, buses=None, pf: float = 0.95, methods: tuple[str, ...] = METHODS,
                workers: int = 1) -> list[Hosting]:
    """The bracket for every bus in `buses` (default: all), in bus order. With workers > 1 the
    buses are spread over processes, each with a single-threaded solver."""
    buses = list(range(case.n)) if buses is None else [int(b) for b in buses]
    if workers <= 1:
        model = HostingModel(case)
        return [model.evaluate(b, pf, methods) for b in buses]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(case,)) as pool:
        return list(pool.map(_work, [(b, pf, methods) for b in buses]))


def hosting_curve(case: Case, bus: int, levels, pf: float = 0.95,
                  methods: tuple[str, ...] = ("socp", "sdp", "ac")) -> list[tuple[float, Hosting]]:
    """The bracket at several load levels: every existing load multiplied by each level."""
    return [(float(a), HostingModel(case.scaled_loads(float(a))).evaluate(bus, pf, methods)) for a in levels]


def _n1_work(args: tuple) -> tuple[int, Hosting]:
    case, branch, bus, pf, methods = args
    return branch, HostingModel(case.without_branch(branch), threads=1).evaluate(bus, pf, methods)


def hosting_n1(case: Case, bus: int, pf: float = 0.95, methods: tuple[str, ...] = ("socp", "ac"),
               workers: int = 1) -> dict:
    """Hosting capacity after each single-branch outage that keeps the network connected, and the
    worst of them. Each outage is solved on its own, so generators redispatch after the outage.
    An outage whose relaxation is infeasible cannot even serve the existing load: it counts as
    zero hostable load and is reported under "infeasible"."""
    outages = [l for l in range(case.m) if case.without_branch(l).connected()]
    tasks = [(case, l, bus, pf, methods) for l in outages]
    if workers <= 1:
        results = [_n1_work(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_n1_work, tasks))
    proven = ("PrimalInfeasible", "AlmostPrimalInfeasible")
    infeasible = [l for l, h in results if any(h.status.get(k) in proven for k in ("socp", "sdp"))]
    lower = [(h.ac, l) for l, h in results if h.ac is not None] + [(0.0, l) for l in infeasible]
    upper = [(h.upper, l) for l, h in results if h.upper is not None] + [(0.0, l) for l in infeasible]

    def name(l: int) -> str:
        return f"{case.label(case.f[l])}-{case.label(case.t[l])}"

    worst_lo, worst_up = (min(lower) if lower else (None, None)), (min(upper) if upper else (None, None))
    return {"outages": len(outages), "skipped": case.m - len(outages), "infeasible": len(infeasible),
            "ac": worst_lo[0], "ac_branch": name(worst_lo[1]) if lower else "",
            "upper": worst_up[0], "upper_branch": name(worst_up[1]) if upper else "",
            "missing_ac": len(outages) - len(lower), "results": results}


def summarize(rows: list[Hosting]) -> dict:
    """Counts and shares over the buses of one case, for the experiment tables."""
    n = len(rows)
    with_ac = [h for h in rows if h.ac is not None]
    gaps = np.array([h.gap for h in with_ac if h.gap is not None])
    socp_gap = np.array([max(h.socp - h.ac, 0.0) / h.socp for h in with_ac if h.socp])
    sdp_gap = np.array([max(h.sdp - h.ac, 0.0) / h.sdp for h in with_ac if h.sdp])
    med = lambda a: float(np.median(a)) if len(a) else None
    top = lambda a: float(np.max(a)) if len(a) else None
    limits = {k: sum(h.limit == k for h in with_ac) for k in KINDS}
    return {
        "buses": n, "ac_found": len(with_ac),
        "gap_below_0.1%": int(np.sum(gaps < 1e-3)), "gap_below_1%": int(np.sum(gaps < 1e-2)),
        "socp_gap_median": med(socp_gap), "socp_gap_max": top(socp_gap),
        "sdp_gap_median": med(sdp_gap), "sdp_gap_max": top(sdp_gap),
        "dc_above_upper": sum(1 for h in rows if h.dc is not None and h.upper is not None and h.dc > h.upper * (1 + 1e-6)),
        "dc_above_ac": sum(1 for h in with_ac if h.dc is not None and h.dc > h.ac * (1 + 1e-6)),
        "dc_below_ac": sum(1 for h in with_ac if h.dc is not None and h.dc < h.ac * (1 - 1e-6)),
        "limits": limits,
        "time_median": {k: med(np.array([h.times[k] for h in rows if k in h.times])) for k in METHODS},
    }
