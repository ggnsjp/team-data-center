"""Weather-year scenarios: the demand rules and the per-scenario model plumbing."""
from __future__ import annotations

import numpy as np
import pytest

from dcopt.heat.network import Instance, Params, Scenario, Source, evaluate, solve, user_data
from dcopt.heat.v1 import Site
from dcopt.heat.weather import SNOW_N, WeatherYear, weather_year_from_csv

# A cold, snowy year and a mild, snow-poor one, next to the normals year they are measured against.
# The fixtures are built from monthly values expanded flat across each month's days: the indices
# and shares of a flat series match the monthly ones (deep-winter months never cross the base).
def from_monthly(year: int, t_month, snow_month) -> WeatherYear:
    t_day, s_day = [], []
    for m in range(12):
        n = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m]
        t_day += [t_month[m]] * n
        s_day += [snow_month[m] / n] * n
    return WeatherYear.from_daily(year, t_day, s_day)


COLD = from_monthly(1985, (-6.0, -5.0, -1.0, 6.0, 12.0, 16.5, 20.5, 21.5, 18.0, 11.5, 4.5, -1.5),
                    (170.0, 190.0, 90.0, 5.0, 0, 0, 0, 0, 0, 2.0, 40.0, 150.0))
MILD = from_monthly(1990, (-1.5, -0.5, 3.0, 9.0, 14.0, 18.0, 22.0, 23.0, 19.5, 13.0, 7.0, 2.0),
                    (70.0, 55.0, 30.0, 2.0, 0, 0, 0, 0, 0, 0.0, 15.0, 60.0))


def scens(weather):
    return [Scenario("lo", "低", "low", 0.5, 115.0, "low", None, weather),
            Scenario("hi", "高", "high", 0.5, 156.8, "high", None, weather)]


def instance(kinds) -> Instance:
    users = [Site(f"u{i}", f"u{i}", f"u{i}", kind, 0.0, 0.0, annual, "test")
             for i, (kind, annual) in enumerate(kinds)]
    src = Source("d", "d", "d", 0.0, 0.0, {"low": 6.0, "high": 10.0}, "operating", ("", ""), "test")
    n = 1 + len(users)
    dist = np.ones((n, n))
    return Instance([src], users, dist, road=False)


def test_weather_scales_and_reshapes_demand():
    """A cold year asks for more heat and shifts it into the cold months; a mild one less."""
    inst = instance([("snow", 1000.0), ("hospital", 1000.0), ("aquaculture", 1000.0)])
    ud = user_data(inst, Params(), scens(COLD))
    normals = user_data(inst, Params(), [Scenario("n", "平", "normals", 1.0, 115.0)])
    snow_c, hosp_c = ud.demand[0, :, 0], ud.demand[1, :, 0]
    snow_n, hosp_n = normals.demand[0, :, 0], normals.demand[1, :, 0]
    assert ud.demand.shape == (3, 12, 2) and ud.cap.shape == (3, 12, 2)
    assert snow_c.sum() == pytest.approx(1000 * COLD.snow_index)
    assert hosp_c.sum() == pytest.approx(1000 * COLD.hdd18_index)
    assert np.argmax(snow_c) == 1 and np.argmax(snow_n) == 0      # February snowiest in the cold year
    assert snow_c[:3].sum() > snow_n[:3].sum()                    # more winter snow than the normals
    assert hosp_c[:3].sum() > hosp_n[:3].sum()                    # a colder winter asks for more
    assert hosp_c[7] == 0 and hosp_n[7] == 0                      # no heating in either August
    assert hosp_c[9] > hosp_n[9]                                  # and a colder October
    # the fish farm's demand never varies with the weather
    assert np.allclose(ud.demand[2, :, 0], ud.demand[2, :, 1])
    assert ud.demand[2, :, 0].sum() == pytest.approx(1000.0)
    # a mild year asks for less than the normals year
    ud_mild = user_data(inst, Params(), scens(MILD))
    assert ud_mild.demand[1, :, 0].sum() < normals.demand[1, :, 0].sum()
    assert ud_mild.demand[0, :, 0].sum() == pytest.approx(1000 * MILD.snow_index)


def test_pipes_sized_for_the_worst_weather_year():
    """The design peak and pipe load come from the worst scenario; each year's deliveries adapt."""
    inst = instance([("snow", 1000.0)])
    ud = user_data(inst, Params(), scens(COLD))
    normals = user_data(inst, Params(), [Scenario("n", "平", "normals", 1.0, 115.0)])
    assert ud.peak[0] == pytest.approx(ud.peak_w[0].max())
    assert ud.peak[0] > normals.peak[0]                           # a snowy year has a higher peak
    assert ud.q[0] == pytest.approx(Params().alpha * ud.peak[0] * (1 + Params().loss))
    # with weather-free scenarios the numbers are exactly the normals ones
    ud_plain = user_data(inst, Params(), [Scenario("lo", "低", "low", 1.0, 115.0, "low")])
    assert ud_plain.peak[0] == pytest.approx(normals.peak[0])
    assert np.allclose(ud_plain.cap[:, :, 0], normals.cap[:, :, 0])


def test_weather_scenarios_solve_and_respect_their_caps():
    """The MILP with weather scenarios: deliveries never exceed the year's own deliverable energy."""
    inst = instance([("snow", 1500.0), ("hospital", 1500.0)])
    P = Params(mode="ambient")
    plan = solve(inst, P, scens(COLD))
    assert len(plan.connected) == 2
    for w in range(len(plan.scens)):
        assert plan.net[w] == pytest.approx(plan.value[w] - plan.annual_cost)
        for u in range(inst.U):
            assert np.all(plan.s[u, :, :, w] <= plan.ud.cap[u, :, w] + 1e-6)   # the year's own caps
        assert plan.delivered[w] >= 0


def test_evaluation_keeps_the_built_pipes():
    """The second stage keeps the plan's own design peak: on its own scenarios it reproduces the
    plan exactly, and evaluating on colder years stays feasible (never an infeasible LP) with the
    pipes' sizing unchanged — deliveries saturate at what was built, the demand never re-sizes it."""
    inst = instance([("hospital", 1200.0)])
    P = Params(mode="ambient")
    mild = solve(inst, P, scens(MILD))
    assert len(mild.connected) == 1
    assert evaluate(mild).expected_net == pytest.approx(mild.expected_net, abs=1e-6)
    cold = evaluate(mild, scens(COLD))
    assert np.allclose(cold.ud.peak, mild.ud.peak)            # the pipes keep their sizing
    assert cold.delivered.sum() > 0                            # and they still deliver in a cold year


def test_load_years_aggregates_daily_csv(tmp_path):
    """A daily CSV becomes monthly means / monthly totals; regression for the last-day-only bug."""
    rows = ["month,day,t_mean_c,snow_cm"]
    n_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for m in range(1, 13):
        for d in range(1, n_days[m - 1] + 1):
            t = -5.0 if m == 1 else (25.0 if m == 7 else 10.0)
            s = 10.0 if (m == 1 and d <= 10) else ""
            rows.append(f"{m},{d},{t},{s}")
    path = tmp_path / "year.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    wy = weather_year_from_csv(2001, path)
    assert wy.t_month[0] == pytest.approx(-5.0) and wy.t_month[6] == pytest.approx(25.0)
    assert wy.snow_month[0] == pytest.approx(100.0) and wy.snow_month[6] == pytest.approx(0.0)
    assert wy.snow_index == pytest.approx(100.0 / SNOW_N)
    assert wy.n_missing_t == 0


def test_missing_temperature_day_is_imputed_and_counted(tmp_path):
    """One blank day must not sink a whole year: it is imputed from its month's other days and
    counted in n_missing_t; a month with no observation at all fails loudly."""
    n_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    def csv(tmp, blank_days=(), blank_months=()):
        rows = ["month,day,t_mean_c,snow_cm"]
        for m in range(1, 13):
            for d in range(1, n_days[m - 1] + 1):
                t = "" if (m in blank_months or (m, d) in blank_days) else (
                    0.1 * d if m == 1 else (25.0 if m == 7 else 10.0))
                rows.append(f"{m},{d},{t},")
        p = tmp / "year.csv"
        p.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return p

    wy = weather_year_from_csv(2001, csv(tmp_path, blank_days={(1, 15)}))
    assert wy.n_missing_t == 1
    # with the day dropped, the month's mean becomes the imputed value
    assert wy.t_month[0] == pytest.approx(0.1 * (496 - 15) / 30)
    assert wy.t_month[6] == pytest.approx(25.0)

    with pytest.raises(ValueError, match="no mean-temperature observation"):
        weather_year_from_csv(2001, csv(tmp_path, blank_months={2}))
