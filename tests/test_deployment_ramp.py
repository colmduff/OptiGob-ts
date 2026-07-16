"""Deployment-ramp coverage.

A selected cattle abatement/productivity ramps in linearly from the baseline
row over a fixed 2020->`deployment_year` clock, deliberately independent of
`target_year` and of the waypoints. The dairy:beef ratio ramps the same way,
from the baseline year's own observed ratio.

This reproduces the original OptiGob's year-indexed scaler tables
(`animal_emission_scalers`, `animal_protein_scalers`), which have exactly three
properties -- an identical baseline-year value across every scenario, a linear
ramp, and a fixed 2020-2050 horizon. Each is asserted below.

Regression context: before this, `run_cattle_systems` applied the *first
waypoint's* row from `baseline_year + 1` at full strength, which snapped beef
down 14.1% in 2021 on the shipped defaults and cattle CO2e down 32.2% on the
Frontier preset. See claude-docs/abatement-deployment-ramp.md and
claude-docs/NOTES.md.
"""

import copy
import os

import pytest

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")


def _config(scaler=1.0, abatement="Frontier", productivity="Strong increase",
            waypoint_years=(2030, 2050), target_year=2050, **extra):
    """A cattle scenario with an aggressive abatement/productivity selection --
    the combination that made the year-1 discontinuity largest.
    """
    config = {
        "baseline_year": 2020,
        "target_year": target_year,
        "non_cattle_agriculture": [
            {"name": "Pigs", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": []},
        ],
        "cattle_systems": {
            "abatement": "2020 BL", "productivity": "2020 Prod",
            "ratio_type": "dairy_per_beef", "ratio_value": 2.0,
            "waypoints": [
                {"year": year, "abatement": abatement, "scaler": scaler,
                 "scale_parameter": "co2e", "scale_absolute_or_percentage": False,
                 "dairy_productivity": productivity, "beef_productivity": productivity}
                for year in waypoint_years
            ],
        },
    }
    config.update(extra)
    return config


def _run(config):
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()
    return optigob


def _cattle_co2e(optigob, year):
    cattle = optigob.get_field(CATTLE_AGRICULTURE)
    idx = year - optigob.baseline_year
    return (cattle.get_system(CATTLE_AGRICULTURE_DAIRY).time_series[CO2E][idx]
            + cattle.get_system(CATTLE_AGRICULTURE_BEEF).time_series[CO2E][idx])


def _intensity(optigob, year):
    """kt CO2e per head -- isolates how much abatement/productivity has been
    deployed from how large the envelope let the herd be.
    """
    cattle = optigob.get_field(CATTLE_AGRICULTURE)
    idx = year - optigob.baseline_year
    heads = (cattle.get_system(CATTLE_AGRICULTURE_DAIRY).time_series[TOTAL_CATTLE_NUMBERS][idx]
             + cattle.get_system(CATTLE_AGRICULTURE_BEEF).time_series[TOTAL_CATTLE_NUMBERS][idx])
    return _cattle_co2e(optigob, year) / heads


def test_no_step_change_in_first_year():
    """Property 1: every scenario shares the baseline year's value, so the
    baseline_year -> baseline_year+1 move must be an ordinary annual step, not
    a cliff -- no matter how aggressive the selected abatement/productivity is.

    Asserted as smoothness rather than flatness: with an aggressive selection
    ramping in, emissions *should* trend down from 2021. What must not happen
    is the whole ramp landing at once. Before the fix this first step was
    -32.2% against ~0% for every later year.
    """
    optigob = _run(_config(scaler=1.0, abatement="Frontier", productivity="Strong increase"))
    steps = [_cattle_co2e(optigob, year + 1) - _cattle_co2e(optigob, year) for year in range(2020, 2030)]
    # Compared against the *adjacent* step, not the mean: the series trends
    # (each step is slightly larger than the last), so a mean would be a
    # moving target. What a cliff looks like is one step dwarfing its
    # neighbour -- pre-fix, step one was ~-6600 kt and step two ~0.
    assert steps[0] == pytest.approx(steps[1], rel=0.1), (
        f"first-year step {steps[0]:.1f} is an outlier against the next "
        f"({steps[1]:.1f}) -- the ramp is landing in year 1"
    )


def test_row_interpolation_is_linear_and_anchored():
    """Property 2: the effective reference row starts exactly at the baseline
    row, moves linearly, and reaches the waypoint row exactly at
    deployment_year.

    Tested on the row itself rather than on emissions intensity: intensity is
    co2e-per-row over heads-per-row, and since productivity changes the head
    count per reference unit, that ratio is rational in the ramp fraction, not
    linear. The row is the thing the ramp is defined on.
    """
    from optigob_ts.systems.cattle_agriculture import CattleAgriculture

    base = {"co2e": 100.0, "area_beef": 10.0, "co2e_unit": "kt"}
    waypoint = {"co2e": 40.0, "area_beef": 20.0, "co2e_unit": "kt"}

    assert CattleAgriculture._deploy_frac(2020, 2020, 2050) == 0.0
    assert CattleAgriculture._deploy_frac(2035, 2020, 2050) == pytest.approx(0.5)
    assert CattleAgriculture._deploy_frac(2050, 2020, 2050) == 1.0
    assert CattleAgriculture._deploy_frac(2100, 2020, 2050) == 1.0, "must hold, not overshoot"

    at_start = CattleAgriculture._interpolate_row(base, waypoint, 0.0)
    assert at_start["co2e"] == 100.0 and at_start["area_beef"] == 10.0
    at_mid = CattleAgriculture._interpolate_row(base, waypoint, 0.5)
    assert at_mid["co2e"] == pytest.approx(70.0) and at_mid["area_beef"] == pytest.approx(15.0)
    at_end = CattleAgriculture._interpolate_row(base, waypoint, 1.0)
    assert at_end["co2e"] == 40.0 and at_end["area_beef"] == 20.0
    assert at_mid["co2e_unit"] == "kt", "non-numeric fields pass through unblended"


def test_deployment_is_independent_of_checkpoint_placement():
    """Property 3, the one that motivates the fixed clock: "Frontier" must mean
    the same deployment rate regardless of where the user puts checkpoints.
    Compared on intensity, since the envelope legitimately differs.
    """
    dense = _run(_config(waypoint_years=(2030, 2040, 2050)))
    sparse = _run(_config(waypoint_years=(2050,)))
    assert _intensity(dense, 2030) == pytest.approx(_intensity(sparse, 2030), rel=1e-9)


def test_deployment_is_independent_of_target_year():
    """A shorter run must not deploy faster -- deployment_year is its own clock."""
    to_2050 = _run(_config(target_year=2050))
    to_2100 = _run(_config(target_year=2100, waypoint_years=(2030, 2050)))
    assert _intensity(to_2050, 2030) == pytest.approx(_intensity(to_2100, 2030), rel=1e-9)


def test_ramp_completes_at_deployment_year():
    """At deployment_year the effective row IS the waypoint row, so an earlier
    deployment_year must reach the same intensity sooner -- and both must agree
    once each has completed.
    """
    default = _run(_config(waypoint_years=(2030, 2050)))
    early = _run(_config(waypoint_years=(2030, 2050), deployment_year=2030))
    assert _intensity(early, 2030) != pytest.approx(_intensity(default, 2030), rel=1e-6)
    assert _intensity(early, 2050) == pytest.approx(_intensity(default, 2050), rel=1e-9)


def test_ratio_defaults_to_baseline_ratio_and_ramps():
    """An omitted ratio_value reproduces the baseline composition exactly; a
    configured one is reached at deployment_year, not in year 1.
    """
    config = _config(scaler=1.0, abatement="2020 BL", productivity="2020 Prod")
    del config["cattle_systems"]["ratio_value"]
    optigob = _run(config)

    cattle = optigob.get_field(CATTLE_AGRICULTURE)
    dairy = cattle.get_system(CATTLE_AGRICULTURE_DAIRY).time_series[TOTAL_CATTLE_NUMBERS]
    beef = cattle.get_system(CATTLE_AGRICULTURE_BEEF).time_series[TOTAL_CATTLE_NUMBERS]
    for idx in range(len(dairy)):
        assert dairy[idx] / beef[idx] == pytest.approx(dairy[0] / beef[0], rel=1e-6)


def test_configured_ratio_is_reached_at_deployment_year_not_year_one():
    config = _config(scaler=1.0, abatement="2020 BL", productivity="2020 Prod")
    optigob = _run(config)

    cattle = optigob.get_field(CATTLE_AGRICULTURE)
    dairy = cattle.get_system(CATTLE_AGRICULTURE_DAIRY)
    beef = cattle.get_system(CATTLE_AGRICULTURE_BEEF)
    # The LP's decision variables are multipliers on the reference row, and
    # ratio_value is expressed in that same space -- so recover them rather
    # than comparing head counts (head-per-reference-unit differs by system).
    dairy_row = cattle._baseline_row(dairy, optigob.db_manager, optigob.gwp)
    beef_row = cattle._baseline_row(beef, optigob.db_manager, optigob.gwp)

    def scaler_ratio(idx):
        return ((dairy.time_series[TOTAL_CATTLE_NUMBERS][idx] / dairy_row[TOTAL_CATTLE_NUMBERS])
                / (beef.time_series[TOTAL_CATTLE_NUMBERS][idx] / beef_row[TOTAL_CATTLE_NUMBERS]))

    baseline_ratio = scaler_ratio(0)
    assert baseline_ratio == pytest.approx(151.19 / 95.30, rel=1e-3)
    # Year 1 stays at baseline (bar one year's worth of ramp), not at 2.0.
    assert scaler_ratio(1) == pytest.approx(baseline_ratio + (2.0 - baseline_ratio) / 30, rel=1e-3)
    # deployment_year reaches the configured value.
    assert scaler_ratio(2050 - 2020) == pytest.approx(2.0, rel=1e-3)


def test_deployment_year_before_baseline_year_raises():
    with pytest.raises(ValueError, match="deployment_year"):
        Optigob(json_config=_config(deployment_year=2010), db_file_path=db_file_path)


def test_per_sector_ch4_reconciles_with_net_zero_total():
    """Results.ch4's per-sector columns must sum to exactly what
    check_net_zero_status's split-gas target is graded against -- otherwise the
    CH4 attribution shown to users would not explain the pass/fail they see.
    """
    config = _config(scaler=1.0)
    optigob = _run(config)

    ch4 = optigob.get_results().ch4
    sectors = [c for c in ch4.columns if not str(c).startswith("total_")]
    _, _, total_ch4 = optigob.get_net_zero_calculations()

    for offset, expected in enumerate(total_ch4):
        year = optigob.baseline_year + offset
        assert ch4[sectors].sum(axis=1)[year] == pytest.approx(expected, rel=1e-9)
