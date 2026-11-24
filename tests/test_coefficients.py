"""Every worked number on docs/formulations/heat-model.md, checked against the code."""
import numpy as np
import pytest

from dcopt.heat.network import (KEROSENE_KG_CO2_PER_L, KEROSENE_KWH_PER_L, PIPE_SIZES, Instance, Params, Scenario,
                                Source, default_scenarios, duration_energy, pair_calculator, pipe_cost_yen_m,
                                user_data, waste_heat)
from dcopt.heat.v1 import PROFILES, Site

AMB, CEN = Params(mode="ambient"), Params(mode="central")


# ---------------------------------------------------------------------------------------------- COP
@pytest.mark.parametrize("kind, cop", [("greenhouse", 7.95), ("school", 7.95), ("public", 7.95),
                                       ("pool", 8.0), ("onsen", 4.76), ("hospital", 4.76), ("hotel", 4.76)])
def test_cop_ambient_by_supply_temperature(kind, cop):
    assert AMB.cop(kind) == pytest.approx(cop, abs=0.005)


@pytest.mark.parametrize("kind", ["aquaculture", "snow"])
def test_direct_use_below_27_degrees(kind):
    assert AMB.cop(kind) is None
    k = AMB.per_kind(kind)
    assert k["elec"] == 0.0 and k["share"] == 1.0 and k["r"] == pytest.approx(1 + AMB.loss)


def test_cop_central_is_the_same_for_everyone():
    assert {round(CEN.cop(k), 6) for k in CEN.supply_c} == {round(0.5 * 333.15 / 35, 6)}
    assert CEN.cop("greenhouse") == pytest.approx(4.76, abs=0.005)


def test_cop_is_capped_at_8():
    assert AMB.carnot_cop(40.0, 25.0) == 8.0
    assert AMB.carnot_cop(26.0, 25.0) == 8.0            # tiny lifts would otherwise explode


# --------------------------------------------------------------------------------- value of a MWh
def test_replaced_kerosene_per_mwh():
    assert 1000 / (KEROSENE_KWH_PER_L * AMB.boiler_eff) == pytest.approx(121.3, abs=0.05)


@pytest.mark.parametrize("price, fuel, with_cop8", [(115.0, 13_948, 10_823), (156.8, 19_018, 15_893)])
def test_value_per_mwh(price, fuel, with_cop8):
    assert AMB.fuel_yen_per_mwh(price) == pytest.approx(fuel, abs=1.0)
    assert AMB.fuel_yen_per_mwh(price) - AMB.power_yen_kwh * 1000 / 8 == pytest.approx(with_cop8, abs=1.0)


def test_capital_recovery_factors():
    assert AMB.crf == pytest.approx(0.0510, abs=5e-5)
    assert AMB.crf_hp == pytest.approx(0.0672, abs=5e-5)


def test_co2_per_mwh_of_kerosene_heat():
    assert KEROSENE_KG_CO2_PER_L / (KEROSENE_KWH_PER_L * AMB.boiler_eff) == pytest.approx(0.303, abs=5e-4)


# -------------------------------------------------------------------------------------------- pipes
CAP_10K = {50: 0.09, 80: 0.25, 100: 0.54, 150: 1.41, 200: 2.72, 250: 4.62}
CAP_30K = {50: 0.27, 80: 0.76, 100: 1.62, 150: 4.23, 200: 8.17, 250: 13.86}
COST = {50: 84_233, 80: 121_473, 100: 146_300, 150: 208_367, 200: 270_433, 250: 332_500}


@pytest.mark.parametrize("dT, table", [(10.0, CAP_10K), (30.0, CAP_30K)])
def test_pipe_capacities(dT, table):
    assert {s.dn: round(s.capacity_mw(dT), 2) for s in PIPE_SIZES} == pytest.approx(table, abs=0.006)


def test_pipe_costs_per_metre():
    assert {s.dn: s.yen_m for s in PIPE_SIZES} == pytest.approx(COST, abs=1.0)
    assert pipe_cost_yen_m(25) == pytest.approx(40_000 * 1.33)
    assert pipe_cost_yen_m(250) == pytest.approx(250_000 * 1.33)


def test_large_pipes_are_about_seven_times_cheaper_per_mw():
    dn80, dn250 = PIPE_SIZES[1], PIPE_SIZES[5]
    per_mw = lambda s: s.yen_m / s.capacity_mw(10.0)
    assert per_mw(dn80) / per_mw(dn250) == pytest.approx(7.0, abs=0.5)      # "about 7 times" on the page


# ------------------------------------------------------------------------------- what a connection delivers
def test_duration_energy_regimes():
    mu, h, f = 0.2, 744, 1.4                         # load spread evenly over [0.12, 0.28] MW
    assert duration_energy(mu, h, f, 0.30) == pytest.approx(mu * h)          # connection covers the top
    assert duration_energy(mu, h, f, 0.10) == pytest.approx(0.10 * h)        # below the bottom: always full
    c, lo, hi = 0.2, 0.12, 0.28
    assert duration_energy(mu, h, f, c) == pytest.approx(((c ** 2 - lo ** 2) / 2 + c * (hi - c)) / (hi - lo) * h)
    assert duration_energy(0.0, h, f, 0.5) == 0.0


def test_duration_energy_is_monotone_and_concave_in_size():
    sizes = np.linspace(0.0, 0.4, 41)
    e = np.array([duration_energy(0.2, 744, 1.4, c) for c in sizes])
    assert np.all(np.diff(e) >= -1e-9)
    assert np.all(np.diff(e, 2) <= 1e-6)


def test_pool_example_on_the_math_page():
    d_jan = 800 * PROFILES["pool"][0]
    assert d_jan == pytest.approx(111, abs=0.6)
    mu = d_jan / 744
    peak = 1.4 * mu                                  # January is the pool's heaviest month
    assert duration_energy(mu, 744, 1.4, peak) == pytest.approx(d_jan)
    assert duration_energy(mu, 744, 1.4, 0.7 * peak) == pytest.approx(98.6, abs=0.6)


# -------------------------------------------------------------------- per-MWh coefficients table
def test_coefficients_ambient_with_heat_pump():
    cop = AMB.cop("greenhouse")
    k = AMB.per_kind("greenhouse")
    assert k["elec"] == pytest.approx(1 / cop)
    assert k["share"] == pytest.approx(1 - 1 / cop)
    assert k["r"] == pytest.approx((1 - 1 / cop) * (1 + AMB.loss))
    assert k["hp_user"] is True


def test_coefficients_central():
    cop = CEN.cop("greenhouse")
    k = CEN.per_kind("greenhouse")
    assert k["elec"] == pytest.approx((1 + CEN.loss) / cop)
    assert k["share"] == 1.0
    assert k["r"] == pytest.approx((1 + CEN.loss) * (1 - 1 / cop))
    assert k["hp_user"] is False


def test_losses_and_temperature_differences_by_mode():
    assert (AMB.loss, AMB.dT) == (0.02, 10.0)
    assert (CEN.loss, CEN.dT) == (0.08, 30.0)


# ------------------------------------------------------------------------------------- waste heat
def test_waste_heat_10_mw_in_january():
    src = Source("x", "x", "x", 0.0, 0.0, {"low": 6.0, "high": 10.0}, "operating", ("", ""), "test")
    inst = Instance([src], [], np.zeros((1, 1)), road=False)
    w = waste_heat(inst, AMB, [Scenario("hi", "高", "high", 1.0, 115.0, "high")])
    assert w[0, 0, 0] == pytest.approx(4_464)
    assert w[0, 1, 0] == pytest.approx(10 * 672 * 0.6)                       # February, 28 days


# --------------------------------------------------------- the worked pair: No. 1 and the fish farm
def test_worked_pair_no1_and_fish_farm():
    src = Source("isrd1", "No.1", "No.1", 0.0, 0.0, {"low": 6.0, "high": 10.0}, "operating", ("", ""), "test")
    fish = Site("fish", "fish", "fish", "aquaculture", 0.0, 0.0, 5000.0, "test")
    inst = Instance([src], [fish], np.array([[0.0, 2483.0], [2483.0, 0.0]]), road=False)
    rows = {r["key"]: r for r in pair_calculator(inst, AMB, default_scenarios(), 0, 0)}
    assert rows["size"]["value"] == "DN150"
    assert rows["peak"]["value"] == pytest.approx(0.68, abs=0.01)
    assert rows["capex"]["value"] == pytest.approx(517.4e6, rel=1e-3)
    assert rows["hp"]["value"] == 0
    assert rows["heat"]["value"] == pytest.approx(5000, abs=1)
    assert rows["saving_low-115"]["value"] == pytest.approx(69.7e6, rel=2e-3)
    assert rows["saving_low-156.8"]["value"] == pytest.approx(95.1e6, rel=2e-3)
    assert rows["saving"]["value"] == pytest.approx(82.4e6, rel=2e-3)
    assert rows["co2"]["value"] == pytest.approx(1516, abs=2)
    assert rows["payback"]["value"] == pytest.approx(6.3, abs=0.05)


def test_user_data_matches_the_page_for_a_direct_user():
    fish = Site("fish", "fish", "fish", "aquaculture", 0.0, 0.0, 5000.0, "test")
    src = Source("d", "d", "d", 0.0, 0.0, {"low": 6.0, "high": 10.0}, "operating", ("", ""), "test")
    inst = Instance([src], [fish], np.array([[0.0, 1.0], [1.0, 0.0]]), road=False)
    ud = user_data(inst, AMB, default_scenarios())
    assert ud.q[0] == pytest.approx(ud.peak[0] * 1.0 * (1 + AMB.loss))      # sigma = 1 for direct use
    assert ud.co2[0] == pytest.approx(0.303, abs=5e-4)                       # no electricity, no grid term
    assert ud.hp[0] == 0.0
    assert ud.cap[0].sum(axis=0) == pytest.approx(5000, abs=1e-6)             # alpha = 1 covers the flat demand
