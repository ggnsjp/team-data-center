"""The disk cache of solved Warm Ishikari plans (dcopt.heat.v1.cached_design), on a synthetic
instance: no map data and no solver needed. By default no solve is given a start. With the optional
warm start switched on, the inputs decide which solve gets a start and from which plan, and the
plans made that way are kept apart."""
import math
import pickle
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from synthetic import tiny

from dcopt.heat import v1
from dcopt.heat.v1 import Assumptions, Design, Site, cached_design, plan_key

ROOT = Path(__file__).resolve().parents[1]
DC = Site("dc", "DC", "DC", "dc", 141.3, 43.2, 0.0, "test", node=0)
SITES = [replace(s, node=i + 1) for i, s in enumerate(tiny().users)]
KINDS = {"greenhouse", "aquaculture", "school"}


def fake_design(calls):
    """Stands in for the MILP: records each call and returns a small, deterministic plan."""
    def run(dc, sites, A, k=4, kinds=None, links=None, time_limit=30.0, start=None):
        calls.append((A, k, frozenset(kinds or ()), time_limit, start))
        users = [s for s in sites if kinds is None or s.kind in kinds]
        served = np.array([[s.annual_mwh / 12] * 12 for s in users])
        d = Design(users, [(0, 1, 850.0)], {(0, 1): float(served.sum())}, served,
                   served.sum(axis=0) * (1 - 1 / A.cop), A.waste_heat_mwh(), A, "Optimal", 1.25)
        d.gap = 0.004
        d.warm_start = start is not None
        return d
    return run


OLD_STATUS = "Optimization terminated successfully. (HiGHS Status 7: Optimal)"


def old_plan(A):
    """A plan as the code before the warm start pickled it: scipy's message as the status and no
    warm_start field."""
    d = fake_design([])(DC, SITES, A, kinds=KINDS)
    d.status, d.seconds = OLD_STATUS, 12.5
    del d.__dict__["warm_start"]
    return d


def test_plan_key_is_stable_and_tracks_every_input(monkeypatch):
    A = Assumptions()
    key = plan_key(DC, SITES, A, 3, KINDS, 60)
    assert key == plan_key(DC, list(SITES), Assumptions(), 3, {"school", "aquaculture", "greenhouse"}, 60.0)
    assert key != plan_key(DC, SITES, replace(A, kerosene_yen_l=120.0), 3, KINDS, 60)
    assert key != plan_key(DC, SITES, replace(A, carbon_yen_t=500.0), 3, KINDS, 60)
    assert key != plan_key(DC, SITES, A, 4, KINDS, 60)
    assert key != plan_key(DC, SITES, A, 3, KINDS | {"snow"}, 60)
    assert key != plan_key(DC, SITES, A, 3, None, 60)
    assert key != plan_key(DC, SITES, A, 3, KINDS, 30)
    assert key != plan_key(DC, SITES[:-1], A, 3, KINDS, 60)
    assert key != plan_key(DC, [replace(SITES[0], annual_mwh=1.0)] + SITES[1:], A, 3, KINDS, 60)
    monkeypatch.setattr(v1, "code_version", lambda: "another-version")
    assert key != plan_key(DC, SITES, A, 3, KINDS, 60)


def test_plan_key_is_the_same_in_a_fresh_interpreter():
    """No per-process hash randomization: a restarted app must find the plans it saved."""
    code = ("import sys; sys.path.insert(0, 'tests'); from test_plan_cache import DC, SITES, KINDS; "
            "from dcopt.heat.v1 import Assumptions, plan_key; "
            "print(plan_key(DC, SITES, Assumptions(), 3, KINDS, 60))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == plan_key(DC, SITES, Assumptions(), 3, KINDS, 60)


def test_cached_design_round_trips_through_disk(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(v1, "design", fake_design(calls))
    A = Assumptions()
    first, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert not hit and len(calls) == 1
    assert len(list(tmp_path.glob("*.pkl"))) == 1 and not list(tmp_path.glob("*.tmp"))

    again, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert hit and len(calls) == 1                                     # no second solve
    assert again.A == first.A and again.edges == first.edges and again.status == first.status
    assert [s.key for s in again.sites] == [s.key for s in first.sites]
    np.testing.assert_array_equal(again.served, first.served)
    assert again.annual_net == first.annual_net
    assert again.seconds == first.seconds and again.gap == first.gap

    _, hit = cached_design(DC, SITES, replace(A, power_yen_kwh=30.0), k=3, kinds=KINDS, time_limit=60,
                           cache_dir=tmp_path)
    assert not hit and len(calls) == 2                                 # new settings, new solve


def test_cached_design_uses_the_env_folder_and_survives_a_broken_file(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(v1, "design", fake_design(calls))
    monkeypatch.setenv(v1.PLAN_CACHE_ENV, str(tmp_path))
    A = Assumptions()
    (tmp_path / f"{plan_key(DC, SITES, A, 3, KINDS, 60)}.pkl").write_bytes(b"not a pickle")
    d, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60)
    assert not hit and len(calls) == 1 and d.gap == 0.004
    _, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60)
    assert hit and len(calls) == 1


def test_default_cache_folder_is_git_ignored(monkeypatch):
    monkeypatch.delenv(v1.PLAN_CACHE_ENV, raising=False)
    rel = v1.plan_cache_dir().relative_to(ROOT)
    assert rel.parts[:2] == ("data", "cache")
    out = subprocess.run(["git", "check-ignore", "-q", str(rel / "plan.pkl")], cwd=ROOT, check=False)
    assert out.returncode == 0


def test_the_inputs_decide_the_start():
    A = Assumptions()
    assert v1.start_assumptions(A) is None                                   # the published settings: cold
    moved = replace(A, kerosene_yen_l=140.0, it_load_mw=20.0)
    assert v1.start_assumptions(moved) is None                               # no policy: cold
    assert v1.start_assumptions(replace(moved, carbon_yen_t=8000.0, subsidy=0.5)) == moved
    assert v1.start_assumptions(replace(A, subsidy=0.33)) == A
    assert v1.no_policy(replace(moved, carbon_yen_t=500.0)) == moved and v1.no_policy(A) == A


def test_the_warm_start_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv(v1.WARM_START_ENV, raising=False)
    assert not v1.warm_start_on()
    for value, on in (("1", True), ("true", True), ("on", True), ("0", False), ("", False), ("no", False)):
        monkeypatch.setenv(v1.WARM_START_ENV, value)
        assert v1.warm_start_on() is on
    monkeypatch.delenv(v1.WARM_START_ENV)

    def as_before(dc, sites, A, k=4, kinds=None, links=None, time_limit=30.0):   # design() without `start`
        calls.append(A)
        return fake_design([])(dc, sites, A, k=k, kinds=kinds, time_limit=time_limit)

    calls = []
    monkeypatch.setattr(v1, "design", as_before)
    B = replace(Assumptions(), carbon_yen_t=8000.0, subsidy=0.5)
    d, hit = cached_design(DC, SITES, B, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert not hit and calls == [B] and not d.warm_start        # one solve, no start, no no-policy plan first
    assert [f.stem for f in tmp_path.glob("*.pkl")] == [plan_key(DC, SITES, B, 3, KINDS, 60)]


def test_plans_made_with_a_warm_start_are_kept_apart(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(v1, "design", fake_design(calls))
    monkeypatch.delenv(v1.WARM_START_ENV, raising=False)
    A = Assumptions()
    B = replace(A, subsidy=0.5)
    assert plan_key(DC, SITES, B, 3, KINDS, 60, warm=True) != plan_key(DC, SITES, B, 3, KINDS, 60)

    monkeypatch.setenv(v1.WARM_START_ENV, "1")                           # switched on: B from a start
    warm, hit = cached_design(DC, SITES, B, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert not hit and warm.warm_start and len(calls) == 2
    monkeypatch.delenv(v1.WARM_START_ENV)                                # switched off: that plan is not shown
    cold, hit = cached_design(DC, SITES, B, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert not hit and not cold.warm_start and len(calls) == 3 and calls[2][4] is None
    base, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert hit and not base.warm_start and len(calls) == 3              # the no-policy plan is the same either way
    assert len(list(tmp_path.glob("*.pkl"))) == 3

    for on in (True, False, True):                                       # both stay available, each under its switch
        d, hit = cached_design(DC, SITES, B, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path, warm_start=on)
        assert hit and d.warm_start is on
    assert len(calls) == 3

    wrong = tmp_path / f"{plan_key(DC, SITES, B, 3, KINDS, 60)}.pkl"     # a warm plan under the default key
    wrong.write_bytes((tmp_path / f"{plan_key(DC, SITES, B, 3, KINDS, 60, warm=True)}.pkl").read_bytes())
    d, hit = cached_design(DC, SITES, B, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert not hit and not d.warm_start and len(calls) == 4             # is not served: solved again


def test_a_policy_solve_starts_from_the_no_policy_plan_of_the_same_settings(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(v1, "design", fake_design(calls))
    A = replace(Assumptions(), kerosene_yen_l=140.0)
    B = replace(A, carbon_yen_t=8000.0)
    d, hit = cached_design(DC, SITES, B, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path, warm_start=True)
    assert not hit and d.warm_start and d.A == B
    assert [(c[0], c[4] is None) for c in calls] == [(A, True), (B, False)]   # the no-policy plan first, cold
    assert calls[1][4].A == A and not calls[1][4].warm_start                 # and that plan is the start
    assert len(list(tmp_path.glob("*.pkl"))) == 2                            # both are kept

    base, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path, warm_start=True)
    assert hit and len(calls) == 2 and not base.warm_start


def test_the_published_settings_get_no_start_even_with_the_warm_start_on(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(v1, "design", fake_design(calls))
    for before in (replace(Assumptions(), subsidy=0.5), replace(Assumptions(), kerosene_yen_l=90.0)):
        cached_design(DC, SITES, before, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path, warm_start=True)
    cold = [c[4] is None for c in calls if c[0] == Assumptions()]
    assert cold == [True]                              # solved once, as the start of the subsidy case, from nothing
    d, hit = cached_design(DC, SITES, Assumptions(), k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path,
                           warm_start=True)
    assert hit and not d.warm_start
    same, hit = cached_design(DC, SITES, Assumptions(), k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert hit and not same.warm_start                 # and it is the plan the switched-off page shows


def test_the_start_does_not_depend_on_what_was_solved_before(monkeypatch, tmp_path):
    A = Assumptions()
    B = replace(A, power_yen_kwh=30.0, subsidy=0.5)
    others = [replace(A, kerosene_yen_l=90.0), replace(A, carbon_yen_t=2000.0), replace(B, subsidy=0.25,
                                                                                         it_load_mw=5.0), A]
    seen = []
    for folder, before in ((tmp_path / "fresh", []), (tmp_path / "used", others)):
        calls = []
        monkeypatch.setattr(v1, "design", fake_design(calls))
        for other in before:
            cached_design(DC, SITES, other, k=3, kinds=KINDS, time_limit=60, cache_dir=folder, warm_start=True)
        del calls[:]
        cached_design(DC, SITES, B, k=3, kinds=KINDS, time_limit=60, cache_dir=folder, warm_start=True)
        seen.append([(c[0], None if c[4] is None else c[4].A) for c in calls])
    assert seen[0] == seen[1] == [(v1.no_policy(B), None), (B, v1.no_policy(B))]


def test_a_plan_saved_by_another_version_of_the_code_is_not_served(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(v1, "design", fake_design(calls))
    A = Assumptions()
    with monkeypatch.context() as earlier:
        earlier.setattr(v1, "code_version", lambda: "the-version-before")
        old_file = tmp_path / f"{plan_key(DC, SITES, A, 3, KINDS, 60)}.pkl"
    old_file.write_bytes(pickle.dumps(old_plan(A)))
    d, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert not hit and len(calls) == 1 and d.status == "Optimal"       # solved again, not the old wording
    assert old_file.exists() and len(list(tmp_path.glob("*.pkl"))) == 2


def test_a_plan_without_the_newer_fields_still_reads(monkeypatch, tmp_path):
    """The key keeps such a file from being served, but reading one must not break anything."""
    calls = []
    monkeypatch.setattr(v1, "design", fake_design(calls))
    A = Assumptions()
    (tmp_path / f"{plan_key(DC, SITES, A, 3, KINDS, 60)}.pkl").write_bytes(pickle.dumps(old_plan(A)))
    d, hit = cached_design(DC, SITES, A, k=3, kinds=KINDS, time_limit=60, cache_dir=tmp_path)
    assert hit and not calls and d.warm_start is False and math.isfinite(d.gap)
    assert d.status.split(".")[0] == "Optimization terminated successfully"   # what the page would show
    policy, hit = cached_design(DC, SITES, replace(A, subsidy=0.5), k=3, kinds=KINDS, time_limit=60,
                                cache_dir=tmp_path, warm_start=True)
    assert not hit and policy.warm_start and len(calls) == 1
    assert calls[0][4].status == OLD_STATUS and calls[0][4].A == A            # and it can be a start
