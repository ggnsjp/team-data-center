"""The pipe heat-loss rule: published coefficients, Sapporo's ground temperature, hand-checked numbers."""
import pytest

from dcopt.heat import loss


def test_one_kilometre_by_hand():
    # DN100, two single pipes of series 1, 60/30 C in ground at 10 C: 0.518 x (45 - 10) = 18.13 W/m
    assert loss.loss_w_per_m(100, 60, 30, 10.0, "pair", 1) == pytest.approx(18.13, abs=0.01)
    # kept warm all year that is 18.13 W/m x 1,000 m x 8,760 h = 158.8 MWh
    flat_ground = sum(loss.loss_w_per_m(100, 60, 30, 10.0, "pair", 1) * 1000 * d * 24 / 1e6 for d in loss.DAYS)
    assert flat_ground == pytest.approx(158.8, abs=0.1)
    assert loss.yearly_loss_mwh([(100, 1.0)], 60, 30, "pair", 1) == pytest.approx(flat_ground, rel=0.01)


def test_more_insulation_and_twin_pipes_lose_less():
    for dn in (50, 80, 100, 150, 200):
        assert loss.u_value(dn, "pair", 1) > loss.u_value(dn, "pair", 2) > loss.u_value(dn, "pair", 3)
        assert loss.u_value(dn, "twin", 2) < loss.u_value(dn, "pair", 2)
    assert loss.u_value(250, "twin", 2) == loss.u_value(250, "pair", 2)      # no twin pipe of that size in the table
    with pytest.raises(ValueError):
        loss.u_value(100, "trench")


def test_ground_temperature_follows_the_measured_wave():
    year = [loss.ground_c(m, 1.0) for m in range(12)]
    assert sum(d * t for d, t in zip(loss.DAYS, year)) / 365 == pytest.approx(10.0, abs=0.2)
    assert max(year) - min(year) == pytest.approx(13.5, abs=1.0)            # 16.8 - 3.3 C at 1.0 m
    assert year.index(min(year)) == 2 and year.index(max(year)) == 8        # March and September
    deep = [loss.ground_c(m, 3.0) for m in range(12)]
    assert max(deep) - min(deep) < max(year) - min(year)                    # the wave fades with depth
    assert deep.index(min(deep)) > year.index(min(year))                    # and arrives later


def test_a_warmer_network_and_a_longer_route_lose_more():
    pipes = [(80, 1.7), (150, 0.8), (250, 2.5)]
    ambient, central = loss.yearly_loss_mwh(pipes, 30, 20), loss.yearly_loss_mwh(pipes, 60, 30)
    assert 0 < ambient < central
    assert loss.yearly_loss_mwh([(dn, 2 * km) for dn, km in pipes], 30, 20) == pytest.approx(2 * ambient)
    winter, summer = loss.monthly_loss_mwh(pipes, 30, 20)[2], loss.monthly_loss_mwh(pipes, 30, 20)[8]
    assert winter > summer                                                  # the ground is coldest in March
