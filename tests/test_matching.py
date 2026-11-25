"""Theme 4: the area records, the three ways of counting, storage, shifting, the replay and the LP."""
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest
from synthetic_records import FLOOR, month_csv, write_year

from dcopt.matching import records, score, system
from dcopt.matching.portfolio import Costs, best_delivery, cheapest


@pytest.fixture()
def year(tmp_path, monkeypatch) -> pd.DataFrame:
    monkeypatch.setattr(records, "DIR", tmp_path)
    write_year(tmp_path, 2024)
    return records.load_fiscal_year(2024, download=False)


@pytest.fixture(scope="module")
def fortnight() -> pd.DataFrame:
    return records.read_month(month_csv(2025, 5, seed=3)).iloc[: 14 * 48]


# ------------------------------------------------------------------ records
@pytest.mark.parametrize("new_layout", [False, True])
def test_a_month_reads_in_both_layouts(new_layout):
    df = records.read_month(month_csv(2026, 4, new_layout=new_layout))
    assert list(df.columns) == records.COLUMNS and len(df) == 30 * 48
    assert df.index[0] == pd.Timestamp("2026-04-01 00:00") and df.index[-1] == pd.Timestamp("2026-04-30 23:30")
    c = records.check(df)
    assert c["irregular_steps"] == 0 and c["missing_values"] == 0 and c["max_imbalance_mw"] == 0
    assert (df["biomass_curtailed"] == 0).all()               # a column the old layout lacks reads as zero


def test_other_text_is_not_read():
    with pytest.raises(ValueError):
        records.read_month("month,day,t_mean_c\n1,1,-3.2\n")


def test_a_new_column_stops_the_reader():
    text = month_csv(2025, 6).decode("cp932").replace("その他,合計", "その他,水素,合計", 1)
    with pytest.raises(ValueError, match="unknown columns"):
        records.read_month(text)


def test_fiscal_year_runs_from_april_to_march():
    months = records.fiscal_year(2025)
    assert months[0] == (2025, 4) and months[-1] == (2026, 3) and len(months) == 12


def test_missing_months_name_the_command(tmp_path, monkeypatch):
    monkeypatch.setattr(records, "DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="dcopt.matching.records 2024"):
        records.load_fiscal_year(2024, download=False)
    assert records.cached_fiscal_years() == []


def test_a_whole_year_loads(year):
    assert len(year) == 365 * 48 and records.cached_fiscal_years() == [2024]
    assert records.check(year)["slots"] == records.check(year)["expected_slots"]
    assert records.energy_gwh(year["demand"]) == pytest.approx(float(year["demand"].sum()) / 2000)


# ------------------------------------------------------------------ counting
def test_volume_is_matched_plus_surplus(year):
    load = score.flat_load(len(year), 100.0)
    for volume, solar in [(0.5, 0.0), (1.0, None), (2.5, 1.0)]:
        s = score.score(load, score.contracted(year, load, volume, solar))
        assert s.volume == pytest.approx(volume)
        assert s.matched + s.surplus == pytest.approx(s.volume)
        assert 0 <= s.matched <= min(1.0, s.volume) + 1e-12


def test_a_contract_shaped_like_the_load_matches_all_of_it():
    load = score.flat_load(7 * 48, 20.0)
    s = score.score(load, load.copy())
    assert s.matched == pytest.approx(1.0) and s.surplus == pytest.approx(0.0) and s.longest_gap_h == 0


def test_more_volume_never_lowers_the_match(year):
    load = score.flat_load(len(year), 100.0)
    shares = [score.score(load, score.contracted(year, load, x)).matched for x in (0.5, 1, 1.5, 2, 4, 8)]
    assert all(b >= a - 1e-12 for a, b in pairwise(shares)) and shares[0] < 0.5 < shares[-1] <= 1


def test_solar_alone_leaves_the_night(year):
    load = score.flat_load(len(year), 100.0)
    s = score.score(load, score.contracted(year, load, 10.0, 1.0))
    assert s.matched < 0.75 and s.longest_gap_h >= 8          # no volume of solar covers the night


def test_longest_run():
    assert score.longest_run(np.array([0, 1, 1, 0, 1, 1, 1, 0], dtype=bool)) == 3
    assert score.longest_run(np.zeros(5, dtype=bool)) == 0 and score.longest_run(np.ones(4, dtype=bool)) == 4


# ------------------------------------------------------------------ storage and shifting
@pytest.mark.parametrize("hours", [1.0, 4.0, 12.0])
@pytest.mark.parametrize("volume", [0.8, 1.5])
def test_the_battery_rule_delivers_what_the_linear_program_does(fortnight, hours, volume):
    load = score.flat_load(len(fortnight), 50.0)
    gen = score.contracted(fortnight, load, volume)
    rule = score.score(load, score.with_storage(load, gen, 50.0, 50.0 * hours, passes=8), gen).matched
    assert rule == pytest.approx(best_delivery(load, gen, 50.0, 50.0 * hours), abs=2e-4)


def test_a_larger_battery_never_delivers_less(year):
    load = score.flat_load(len(year), 100.0)
    gen = score.contracted(year, load, 1.2)
    shares = [score.score(load, score.with_storage(load, gen, 100.0, 100.0 * h), gen).matched for h in (0, 1, 4, 12, 48)]
    assert shares[0] == pytest.approx(score.score(load, gen).matched)
    assert all(b >= a - 1e-9 for a, b in pairwise(shares))
    assert shares[-1] <= 1.0 + 1e-9


def test_shifting_limits(year):
    load = score.flat_load(len(year), 100.0)
    gen = score.contracted(year, load, 1.0)
    plain = score.score(load, gen).matched
    assert score.shifted_share(load, gen, 0.0, 0.5) == pytest.approx(plain)
    assert score.shifted_share(load, gen, 0.3, 0.0) == pytest.approx(plain)       # nowhere to move the work to
    some, more = score.shifted_share(load, gen, 0.2, 0.25), score.shifted_share(load, gen, 0.5, 1.0)
    assert plain < some < more
    days = len(load) // 48                                    # with full freedom only the day's totals matter
    daily = np.minimum(gen.reshape(days, 48).sum(axis=1), load.reshape(days, 48).sum(axis=1)).sum() / load.sum()
    assert score.shifted_share(load, gen, 1.0, 1e6) == pytest.approx(daily)


# ------------------------------------------------------------------ the replay of the records
def test_replaying_nothing_gives_the_records_back(year):
    r = system.replay(year)
    assert r.thermal_gwh == pytest.approx(records.energy_gwh(records.thermal(year)))
    assert r.curtailed_gwh == pytest.approx(records.energy_gwh(records.curtailed_renewable(year)))
    assert r.base_curtailed_gwh > 0                           # the synthetic year has curtailed slots
    assert system.thermal_floor(year) == pytest.approx(FLOOR, abs=1)


def test_an_added_load_takes_curtailed_output_first(year):
    load = score.flat_load(len(year), 50.0)
    r = system.replay(year, load)
    absorbed = system.absorbed_gwh(year, load)
    assert 0 < absorbed < r.added_load_gwh
    assert r.thermal_change_gwh == pytest.approx(r.added_load_gwh - absorbed)
    assert r.curtailed_gwh == pytest.approx(r.base_curtailed_gwh - absorbed)
    assert 0.9 < r.thermal_per_added_load < 1.0


@pytest.mark.parametrize("mw, factor", [(0.0, 2.0), (100.0, 1.0), (100.0, 1.5), (400.0, 3.0)])
def test_the_replay_keeps_the_energy_balance(year, mw, factor):
    extra = system.scaled_fleet(year, factor, factor)
    r = system.replay(year, mw, extra)
    change = (r.thermal_gwh - r.curtailed_gwh) - (r.base_thermal_gwh - r.base_curtailed_gwh)
    assert change == pytest.approx(r.added_load_gwh - r.added_renewable_gwh)
    assert r.thermal_mw.min() >= min(r.floor_mw, records.thermal(year).min()) - 1e-9
    assert (r.curtailed_mw >= -1e-9).all()


def test_added_renewables_lower_thermal_and_a_higher_floor_wastes_more(year):
    extra = system.scaled_fleet(year, 2.0, 2.0)
    low, high = system.replay(year, 0.0, extra, floor_mw=300.0), system.replay(year, 0.0, extra, floor_mw=900.0)
    assert low.thermal_gwh < high.thermal_gwh < low.base_thermal_gwh
    assert low.curtailed_gwh < high.curtailed_gwh


def test_break_even_load(year):
    extra = system.scaled_fleet(year, 2.0, 2.0)
    mw = system.break_even_load(year, extra)
    base = system.replay(year).thermal_gwh
    assert 0 < mw < 5000
    assert system.replay(year, mw, extra).thermal_gwh == pytest.approx(base, rel=1e-6)
    assert system.replay(year, mw + 20, extra).thermal_gwh > base > system.replay(year, mw - 20, extra).thermal_gwh


# ------------------------------------------------------------------ the cheapest portfolio
def test_the_program_meets_the_target_and_no_grid_point_is_cheaper(fortnight):
    load = score.flat_load(len(fortnight), 10.0)
    s, w = score.shaped(fortnight["solar"], load), score.shaped(fortnight["wind"], load)
    costs = Costs(solar_yen_kwh=10.0, wind_yen_kwh=14.0)
    best = cheapest(load, s, w, 0.8, costs, battery=False)
    assert best.feasible and best.matched == pytest.approx(0.8, abs=1e-6)
    assert best.yen_per_kwh_used == pytest.approx(10.0 * best.solar + 14.0 * best.wind)
    for xs in np.linspace(0, 3, 13):
        for xw in np.linspace(0, 3, 13):
            if score.score(load, xs * s + xw * w).matched >= 0.8:
                assert 10.0 * xs + 14.0 * xw >= best.yen_per_kwh_used - 1e-6


def test_a_battery_never_makes_the_target_dearer_and_higher_targets_cost_more(fortnight):
    load = score.flat_load(len(fortnight), 10.0)
    s, w = score.shaped(fortnight["solar"], load), score.shaped(fortnight["wind"], load)
    plain = cheapest(load, s, w, 0.9, battery=False)
    with_battery = [cheapest(load, s, w, t) for t in (0.7, 0.9, 0.99)]
    assert all(p.feasible for p in with_battery)
    assert with_battery[1].yen_per_kwh_used <= plain.yen_per_kwh_used + 1e-6
    costs = [p.yen_per_kwh_used for p in with_battery]
    assert costs[0] < costs[1] < costs[2]
    p = with_battery[1]                                       # the sizes the program chose deliver the target
    assert p.battery_h >= Costs().battery_min_hours * p.battery_mw - 1e-6
    rule = score.with_storage(load, p.solar * s + p.wind * w, p.battery_mw * 10.0, p.battery_h * 10.0, passes=8)
    assert score.score(load, rule).matched == pytest.approx(0.9, abs=2e-3)


def test_a_target_out_of_reach_is_reported(fortnight):
    load = score.flat_load(len(fortnight), 10.0)
    s = score.shaped(fortnight["solar"], load)
    out = cheapest(load, s, np.zeros(len(load)), 0.95, battery=False)        # solar alone, no storage: the night
    assert not out.feasible
