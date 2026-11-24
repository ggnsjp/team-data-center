"""Power-system test cases: the data model, a MATPOWER-format reader, PGLib-OPF downloads and
three small built-in systems.

Units    Everything is per unit on `base_mva` once a case is loaded: loads, shunts, generator
         limits, branch ratings. Angles are in radians. A rating of `inf` means "no limit".
Indices  Buses are renumbered 0..n-1 in file order; `bus_id` keeps the original numbers.
         Out-of-service branches and generators, and isolated buses, are dropped on load.
PGLib    The benchmark library of the IEEE PES Task Force on Benchmarks for Validation of
         Emerging Power System Algorithms (Babaeinejadsarookolaee et al. 2019, arXiv:1908.02788),
         https://github.com/power-grid-lib/pglib-opf, licensed CC BY 4.0. The files are downloaded
         into data/cache/pglib/ on first use and are not part of this repository.
Built-in The systems in `BUILTIN` are our own illustrative data (made-up values in a realistic
         per-unit range). They need no download, and the tests run on them.
"""
from __future__ import annotations

import math
import re
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PGLIB_DIR = ROOT / "data" / "cache" / "pglib"
PGLIB_URL = "https://raw.githubusercontent.com/power-grid-lib/pglib-opf/master/pglib_opf_{name}.m"
PGLIB_CASES = ("case14_ieee", "case30_ieee", "case39_epri", "case57_ieee", "case118_ieee", "case300_ieee")
TIMEOUT_S = 20.0
ANGLE_FREE = math.radians(89.0)        # an angle limit at or beyond this is treated as "no limit"


@dataclass(frozen=True)
class Case:
    """A bus-branch network in per unit. See the module docstring for the conventions."""
    name: str
    base_mva: float
    bus_id: np.ndarray                 # (n,) original bus numbers
    pd: np.ndarray                     # (n,) active load
    qd: np.ndarray                     # (n,) reactive load
    gs: np.ndarray                     # (n,) shunt conductance (power drawn at V = 1)
    bs: np.ndarray                     # (n,) shunt susceptance (reactive power injected at V = 1)
    vmin: np.ndarray                   # (n,)
    vmax: np.ndarray                   # (n,)
    base_kv: np.ndarray                # (n,)
    ref: int                           # index of the reference bus
    gen_bus: np.ndarray                # (ng,) bus index of each generator
    pmin: np.ndarray
    pmax: np.ndarray
    qmin: np.ndarray
    qmax: np.ndarray
    f: np.ndarray                      # (m,) from-bus index
    t: np.ndarray                      # (m,) to-bus index
    r: np.ndarray
    x: np.ndarray
    b: np.ndarray                      # (m,) total line charging
    rate: np.ndarray                   # (m,) apparent-power rating, inf = none
    tap: np.ndarray                    # (m,) complex tap: ratio * exp(j * shift), at the from end
    angmin: np.ndarray                 # (m,) lower limit on theta_f - theta_t, -inf = none
    angmax: np.ndarray                 # (m,) upper limit, inf = none

    @property
    def n(self) -> int:
        return len(self.bus_id)

    @property
    def ng(self) -> int:
        return len(self.gen_bus)

    @property
    def m(self) -> int:
        return len(self.f)

    def admittances(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Branch admittances (yff, yft, ytf, ytt) of the standard pi model with an ideal
        transformer at the from end: I_f = yff V_f + yft V_t and I_t = ytf V_f + ytt V_t."""
        ys = 1.0 / (self.r + 1j * self.x)
        ytt = ys + 0.5j * self.b
        yff = ytt / (self.tap * np.conj(self.tap))
        yft = -ys / np.conj(self.tap)
        ytf = -ys / self.tap
        return yff, yft, ytf, ytt

    def ybus(self) -> np.ndarray:
        """Dense bus admittance matrix (for checks on small systems)."""
        yff, yft, ytf, ytt = self.admittances()
        y = np.zeros((self.n, self.n), dtype=complex)
        np.add.at(y, (self.f, self.f), yff)
        np.add.at(y, (self.f, self.t), yft)
        np.add.at(y, (self.t, self.f), ytf)
        np.add.at(y, (self.t, self.t), ytt)
        y[np.arange(self.n), np.arange(self.n)] += self.gs + 1j * self.bs
        return y

    def label(self, i: int) -> str:
        return str(int(self.bus_id[i]))

    def scaled_loads(self, alpha: float) -> "Case":
        """The same network with every load multiplied by alpha (a load-level snapshot)."""
        return replace(self, pd=self.pd * alpha, qd=self.qd * alpha)

    def without_branch(self, l: int) -> "Case":
        """The network after the outage of branch l (for N-1 screening)."""
        keep = np.arange(self.m) != l
        return replace(self, **{k: getattr(self, k)[keep]
                                for k in ("f", "t", "r", "x", "b", "rate", "tap", "angmin", "angmax")})

    def connected(self) -> bool:
        parent = list(range(self.n))

        def find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for a, b in zip(self.f, self.t):
            parent[find(int(a))] = find(int(b))
        return len({find(i) for i in range(self.n)}) == 1


def make_case(name: str, base_mva: float, buses: list[dict], gens: list[dict], branches: list[dict]) -> Case:
    """Build a case from plain dictionaries. Powers are given in MW/MVAr/MVA and converted to
    per unit here; voltages in per unit; angles in degrees."""
    ids = [b["id"] for b in buses]
    pos = {i: k for k, i in enumerate(ids)}
    arr = lambda rows, key, default=0.0: np.array([float(r.get(key, default)) for r in rows])  # noqa: E731
    ref = [k for k, b in enumerate(buses) if b.get("ref")]
    rate = arr(branches, "rate", 0.0)
    ratio = arr(branches, "ratio", 1.0)
    ratio[ratio == 0.0] = 1.0
    shift = np.radians(arr(branches, "shift", 0.0))
    amin, amax = np.radians(arr(branches, "angmin", -360.0)), np.radians(arr(branches, "angmax", 360.0))
    return Case(
        name=name, base_mva=float(base_mva), bus_id=np.array(ids),
        pd=arr(buses, "pd") / base_mva, qd=arr(buses, "qd") / base_mva,
        gs=arr(buses, "gs") / base_mva, bs=arr(buses, "bs") / base_mva,
        vmin=arr(buses, "vmin", 0.9), vmax=arr(buses, "vmax", 1.1), base_kv=arr(buses, "base_kv", 1.0),
        ref=ref[0] if ref else pos[gens[int(np.argmax([g.get("pmax", 0.0) for g in gens]))]["bus"]],
        gen_bus=np.array([pos[g["bus"]] for g in gens], dtype=int),
        pmin=arr(gens, "pmin") / base_mva, pmax=arr(gens, "pmax") / base_mva,
        qmin=arr(gens, "qmin") / base_mva, qmax=arr(gens, "qmax") / base_mva,
        f=np.array([pos[br["f"]] for br in branches], dtype=int),
        t=np.array([pos[br["t"]] for br in branches], dtype=int),
        r=arr(branches, "r"), x=arr(branches, "x"), b=arr(branches, "b"),
        rate=np.where(rate > 0, rate / base_mva, np.inf),
        tap=ratio * np.exp(1j * shift),
        angmin=np.where(amin <= -ANGLE_FREE, -np.inf, amin), angmax=np.where(amax >= ANGLE_FREE, np.inf, amax),
    )


# ---------------------------------------------------------------------------------------------
# MATPOWER format (the format of PGLib-OPF)
# ---------------------------------------------------------------------------------------------

def _matrix(text: str, key: str) -> np.ndarray:
    m = re.search(rf"mpc\.{key}\s*=\s*\[(.*?)\]\s*;", text, flags=re.S)
    if not m:
        raise ValueError(f"no mpc.{key} block in the case file")
    rows = [row.split() for row in re.split(r"[;\n]", m.group(1)) if row.strip()]
    width = max(len(r) for r in rows)
    return np.array([[float(v) for v in r] + [0.0] * (width - len(r)) for r in rows])


def read_matpower(text: str, name: str = "case") -> Case:
    """Parse a MATPOWER case (version 2). Only the fields the hosting-capacity models use are read:
    buses, generators and branches; costs are ignored."""
    text = "\n".join(line.split("%", 1)[0] for line in text.splitlines())
    base = float(re.search(r"mpc\.baseMVA\s*=\s*([-+0-9.eE]+)", text).group(1))
    bus, gen, branch = _matrix(text, "bus"), _matrix(text, "gen"), _matrix(text, "branch")
    bus = bus[bus[:, 1] != 4]                                   # type 4: isolated
    live = set(bus[:, 0].astype(int))
    gen = gen[(gen[:, 7] > 0) & np.isin(gen[:, 0].astype(int), list(live))]
    if branch.shape[1] > 10:
        branch = branch[branch[:, 10] != 0]
    branch = branch[np.isin(branch[:, 0].astype(int), list(live)) & np.isin(branch[:, 1].astype(int), list(live))]
    wide = branch.shape[1] > 12
    buses = [dict(id=int(b[0]), ref=(int(b[1]) == 3), pd=b[2], qd=b[3], gs=b[4], bs=b[5], base_kv=b[9],
                  vmax=b[11], vmin=b[12]) for b in bus]
    gens = [dict(bus=int(g[0]), qmax=g[3], qmin=g[4], pmax=g[8], pmin=g[9]) for g in gen]
    branches = [dict(f=int(br[0]), t=int(br[1]), r=br[2], x=br[3], b=br[4], rate=br[5], ratio=br[8],
                     shift=br[9], angmin=br[11] if wide else -360.0, angmax=br[12] if wide else 360.0)
                for br in branch]
    return make_case(name, base, buses, gens, branches)


def pglib_path(name: str) -> Path:
    return PGLIB_DIR / f"pglib_opf_{name}.m"


def ensure_pglib(name: str, timeout: float = TIMEOUT_S) -> Path | None:
    """The cached PGLib-OPF file for `name` (e.g. "case118_ieee"), downloaded on first use.
    Returns None when the file is not cached and cannot be downloaded; nothing is raised, so a
    caller can carry on with the built-in systems."""
    path = pglib_path(name)
    if path.exists() and path.stat().st_size > 0:
        return path
    if not re.fullmatch(r"case[0-9a-z_]+", name):
        return None
    try:
        req = urllib.request.Request(PGLIB_URL.format(name=name), headers={"User-Agent": "team-data-center"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
        read_matpower(text, name)                              # refuse to cache something unreadable
    except Exception:                                          # offline, timeout, a moved file
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def load(name: str, download: bool = True) -> Case:
    """A case by name: a built-in system, or a PGLib-OPF case (downloaded on first use)."""
    if name in BUILTIN:
        return BUILTIN[name]()
    path = ensure_pglib(name) if download else (pglib_path(name) if pglib_path(name).exists() else None)
    if path is None:
        raise FileNotFoundError(
            f"{name}: not a built-in system and not in {PGLIB_DIR} (download failed or disabled). "
            f"Built-in systems: {', '.join(BUILTIN)}.")
    return read_matpower(path.read_text(encoding="utf-8"), name)


def available(download: bool = False) -> list[str]:
    """Names that `load` can serve right now: the built-in systems, then the cached PGLib cases."""
    cached = [c for c in PGLIB_CASES if pglib_path(c).exists() or (download and ensure_pglib(c))]
    return list(BUILTIN) + cached


# ---------------------------------------------------------------------------------------------
# Built-in illustrative systems (our own data)
# ---------------------------------------------------------------------------------------------

def two_bus(x: float = 0.1, r: float = 0.0, vmin: float = 0.9) -> Case:
    """A stiff source and one load bus behind a line: the textbook loadability example. With
    r = 0 and a unity-power-factor load, the largest load is V1^2 sin(2 delta) / (2 x) at
    cos(delta) = vmin / V1 (the lower voltage limit binds before the nose of the PV curve)."""
    return make_case("two_bus", 100.0,
                     [dict(id=1, ref=True, vmin=1.0, vmax=1.0), dict(id=2, vmin=vmin, vmax=1.1)],
                     [dict(bus=1, pmin=0, pmax=5000, qmin=-5000, qmax=5000)],
                     [dict(f=1, t=2, r=r, x=x, b=0.0)])


def ring5() -> Case:
    """A five-bus meshed system: two generators, three loads, six lines with ratings."""
    buses = [dict(id=1, ref=True), dict(id=2, pd=90, qd=30), dict(id=3, pd=100, qd=35),
             dict(id=4), dict(id=5, pd=60, qd=20)]
    for b in buses:
        b.update(vmin=0.95, vmax=1.05, base_kv=187.0)
    gens = [dict(bus=1, pmin=0, pmax=300, qmin=-150, qmax=150), dict(bus=4, pmin=0, pmax=200, qmin=-100, qmax=100)]
    lines = [(1, 2, 0.012, 0.070, 0.030, 180), (1, 3, 0.020, 0.110, 0.045, 150), (2, 3, 0.015, 0.080, 0.030, 100),
             (2, 4, 0.018, 0.095, 0.040, 150), (3, 5, 0.014, 0.075, 0.030, 120), (4, 5, 0.010, 0.060, 0.025, 160)]
    return make_case("ring5", 100.0, buses, gens,
                     [dict(f=f, t=t, r=r, x=x, b=b, rate=s, angmin=-30, angmax=30) for f, t, r, x, b, s in lines])


def feeder8() -> Case:
    """A radial 66 kV-class feeder: a substation and seven load buses on a trunk with two laterals."""
    buses = [dict(id=1, ref=True, vmin=1.0, vmax=1.03)] + [
        dict(id=i, pd=p, qd=q, vmin=0.94, vmax=1.06) for i, p, q in
        [(2, 6, 2), (3, 8, 3), (4, 5, 1.5), (5, 7, 2.5), (6, 4, 1.5), (7, 6, 2), (8, 3, 1)]]
    for b in buses:
        b["base_kv"] = 66.0
    gens = [dict(bus=1, pmin=0, pmax=200, qmin=-100, qmax=100)]
    lines = [(1, 2, 0.020, 0.045, 60), (2, 3, 0.030, 0.060, 45), (3, 4, 0.035, 0.065, 30), (4, 5, 0.040, 0.070, 30),
             (2, 6, 0.045, 0.075, 30), (3, 7, 0.040, 0.070, 30), (7, 8, 0.050, 0.080, 20)]
    return make_case("feeder8", 100.0, buses, gens,
                     [dict(f=f, t=t, r=r, x=x, b=0.004, rate=s) for f, t, r, x, s in lines])


BUILTIN = {"ring5": ring5, "feeder8": feeder8, "two_bus": two_bus}
