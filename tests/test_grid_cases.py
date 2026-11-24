"""Theme 2 data layer: the case model, the MATPOWER reader, the PGLib download guard and the
chordal extension. No network access and no downloaded files are needed."""
import math
import urllib.request

import networkx as nx
import numpy as np
import pytest

from dcopt.grid import cases
from dcopt.grid.lifted import Lifted, weights
from dcopt.grid.relax import chordal_cliques

CASE_TEXT = """
function mpc = tiny
mpc.version = '2';
mpc.baseMVA = 50;   % a comment
%% bus data
mpc.bus = [
    10  3  0    0   0  0  1  1.0  0  66  1  1.05  0.95;
    20  1  20  10   0  5  1  1.0  0  66  1  1.05  0.95;
    30  1  10   5   0  0  1  1.0  0  66  1  1.10  0.90;
    40  4   0   0   0  0  1  1.0  0  66  1  1.10  0.90;
];
mpc.gen = [
    10  0  0  30  -30  1  100  1  80  10;
    20  0  0  10  -10  1  100  0  40   0;
];
mpc.branch = [
    10  20  0.01  0.10  0.02  60  0  0  0     0  1  -30   30;
    20  30  0.02  0.20  0.00   0  0  0  0.98  5  1  -360  360;
    10  30  0.03  0.30  0.00  25  0  0  0     0  0  -30   30;
    30  40  0.03  0.30  0.00  25  0  0  0     0  1  -30   30;
];
"""


def test_matpower_reader_units_and_filters():
    c = cases.read_matpower(CASE_TEXT, "tiny")
    assert (c.n, c.ng, c.m) == (3, 1, 2)                   # isolated bus, idle generator, open branch dropped
    assert list(c.bus_id) == [10, 20, 30] and c.ref == 0 and c.base_mva == 50
    assert c.pd == pytest.approx([0, 0.4, 0.2]) and c.qd == pytest.approx([0, 0.2, 0.1])
    assert c.bs == pytest.approx([0, 0.1, 0]) and c.vmin == pytest.approx([0.95, 0.95, 0.90])
    assert c.pmax == pytest.approx([1.6]) and c.pmin == pytest.approx([0.2]) and c.qmax == pytest.approx([0.6])
    assert c.rate[0] == pytest.approx(1.2) and np.isinf(c.rate[1])           # 0 MVA means no limit
    assert c.angmax[0] == pytest.approx(math.radians(30)) and np.isinf(c.angmax[1]) and np.isinf(c.angmin[1])
    assert c.tap[0] == pytest.approx(1.0) and abs(c.tap[1]) == pytest.approx(0.98)
    assert np.angle(c.tap[1]) == pytest.approx(math.radians(5))
    assert c.label(1) == "20" and c.connected()


def test_admittances_match_the_bus_admittance_matrix():
    c = cases.read_matpower(CASE_TEXT, "tiny")
    yff, yft, ytf, ytt = c.admittances()
    ys = 1 / (c.r + 1j * c.x)
    assert ytt == pytest.approx(ys + 0.5j * c.b)
    assert yff[1] == pytest.approx(ytt[1] / 0.98 ** 2) and yft[1] == pytest.approx(-ys[1] / np.conj(c.tap[1]))
    y = c.ybus()
    assert y[0, 1] == pytest.approx(yft[0]) and y[1, 0] == pytest.approx(ytf[0])
    assert y[1, 1] == pytest.approx(ytt[0] + yff[1] + 1j * c.bs[1])


@pytest.mark.parametrize("name", list(cases.BUILTIN))
def test_builtin_systems_load_and_are_connected(name):
    c = cases.load(name)
    assert c.connected() and c.n >= 2 and c.ng >= 1
    assert np.all(c.vmin <= c.vmax) and np.all(c.pmin <= c.pmax) and np.all(c.x > 0)
    assert name in cases.available()


def test_outage_and_load_scaling_leave_the_original_untouched():
    c = cases.ring5()
    out = c.without_branch(2)
    assert out.m == c.m - 1 and c.m == 6 and out.connected()
    assert not cases.feeder8().without_branch(0).connected()   # a radial feeder splits
    half = c.scaled_loads(0.5)
    assert half.pd.sum() == pytest.approx(0.5 * c.pd.sum()) and c.pd.sum() == pytest.approx(2.5)


def test_a_failed_download_returns_none_and_load_explains(monkeypatch, tmp_path):
    monkeypatch.setattr(cases, "PGLIB_DIR", tmp_path)

    def offline(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    assert cases.ensure_pglib("case14_ieee") is None
    assert cases.ensure_pglib("../../etc/passwd") is None
    with pytest.raises(FileNotFoundError, match="Built-in systems"):
        cases.load("case14_ieee")
    assert cases.available() == list(cases.BUILTIN)


def test_a_downloaded_case_is_cached_only_if_it_parses(monkeypatch, tmp_path):
    monkeypatch.setattr(cases, "PGLIB_DIR", tmp_path)

    class Reply:
        def __init__(self, text):
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self.text.encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Reply("<html>not a case</html>"))
    assert cases.ensure_pglib("case5_pjm") is None and not list(tmp_path.iterdir())
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Reply(CASE_TEXT))
    path = cases.ensure_pglib("case5_pjm")
    assert path is not None and path.exists() and cases.load("case5_pjm").n == 3


def test_weights_normalize_and_reject_empty_sets():
    c = cases.ring5()
    assert weights(c, 3)[3] == 1.0 and weights(c, 3).sum() == 1.0
    assert weights(c, {1: 2.0, 2: 6.0}) == pytest.approx([0, 0.25, 0.75, 0, 0])
    with pytest.raises(ValueError):
        weights(c, {1: 0.0})


def test_lifted_model_reproduces_the_flows_of_a_voltage_profile():
    c = cases.read_matpower(CASE_TEXT, "tiny")
    lf = Lifted(c)
    rng = np.random.default_rng(1)
    v = (0.95 + 0.1 * rng.random(c.n)) * np.exp(1j * 0.2 * rng.standard_normal(c.n))
    z = np.zeros(lf.nz)
    z[lf.i_c] = np.abs(v) ** 2
    w = v[lf.pairs[:, 0]] * np.conj(v[lf.pairs[:, 1]])
    z[lf.i_wr], z[lf.i_wi] = w.real, w.imag
    yff, yft, ytf, ytt = c.admittances()
    sf = v[c.f] * np.conj(yff * v[c.f] + yft * v[c.t])
    st = v[c.t] * np.conj(ytf * v[c.f] + ytt * v[c.t])
    assert lf.Apf @ z == pytest.approx(sf.real) and lf.Aqf @ z == pytest.approx(sf.imag)
    assert lf.Apt @ z == pytest.approx(st.real) and lf.Aqt @ z == pytest.approx(st.imag)
    # the balance rows equal generation minus the injections S = V conj(Y V), with no generation set
    s_bus = v * np.conj(c.ybus() @ v)
    residual = lf.balances(np.zeros(c.n), 0.0) @ z
    assert residual == pytest.approx(np.concatenate([-s_bus.real, -s_bus.imag]))


@pytest.mark.parametrize("seed", range(4))
def test_chordal_cliques_cover_every_edge_and_form_a_chordal_graph(seed):
    g = nx.connected_watts_strogatz_graph(24, 4, 0.3, seed=seed)
    edges = [(min(a, b), max(a, b)) for a, b in g.edges]
    cliques = chordal_cliques(24, edges)
    cover = nx.Graph()
    cover.add_nodes_from(range(24))
    for c in cliques:
        assert list(c) == sorted(c)
        cover.add_edges_from((c[a], c[b]) for a in range(len(c)) for b in range(a + 1, len(c)))
    assert all(cover.has_edge(a, b) for a, b in edges)
    assert nx.is_chordal(cover)
    assert not any(set(a) < set(b) for a in cliques for b in cliques)        # only maximal cliques


def test_a_tree_needs_no_fill():
    c = cases.feeder8()
    pairs = [tuple(p) for p in Lifted(c).pairs]
    assert sorted(chordal_cliques(c.n, pairs)) == sorted(pairs)
