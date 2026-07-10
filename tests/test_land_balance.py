"""
Land-balance constraint coverage.

Two independent things are tested here (see claude-docs/land-balance.md and
balancing.py's module docstring for the full design rationale):

1. `cattle_systems` now requires `ratio_type`/`ratio_value` -- the heuristic
   split was removed since it had no land-balance awareness at all. Once
   ratio is mandatory, the ratio-optimiser's own per-year `area_commitment`
   constraint makes the general grassland pool (cattle/sheep vs.
   afforestation/AD) self-enforcing -- confirmed by reproducing
   land-balance.md's own worked example (afforestation_rate=5,
   target_year=2100, cattle frozen until 2030 via scaler=1) and showing it's
   infeasible under the old heuristic but feasible once ratio is added, with
   no other numbers changed.
2. The organic-soil pool ("Organic soil under grass"'s baseline Drained
   area, shared between rewetting and afforestation's organic-soil
   sub-claim) has no such optimiser covering it, so `validate_land_balance`
   is still the only enforcement -- tested directly here.
"""

import os

import pytest

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")


def _organic_soil_config(afforestation_rate, rewetting_ratio, target_year=2050):
    return {
        "baseline_year": 2020,
        "target_year": target_year,
        "forestry": [
            {"name": "existing_forest", "harvest": "high", "ccs": True},
            {"name": "afforestation", "afforestation_rate": afforestation_rate, "broadleaf_frac": 0.5, "organic_soil": 0.15, "harvest": "high", "ccs": True},
        ],
        "organic_soils": [
            {"name": "Organic soil under grass", "drainage_status": ["Drained", "Rewetted"], "waypoints": [{"year": 2030, "rewetting_ratio": rewetting_ratio}]},
        ],
    }


def test_cattle_systems_without_ratio_raises():
    # non_cattle_agriculture is required alongside cattle_systems even in
    # isolation -- run_cattle_systems()'s budget math always subtracts
    # non-cattle's contribution, cattle waypoints can't resolve without it
    # (same pattern used by tests/cattle_example_test.py).
    config = {
        "baseline_year": 2020,
        "target_year": 2050,
        "non_cattle_agriculture": [
            {"name": "Pigs", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": []},
        ],
        "cattle_systems": {
            "abatement": "2020 BL", "productivity": "2020 Prod",
            "waypoints": [{"year": 2030, "abatement": "2020 BL", "scaler": 0.8, "scale_parameter": "co2e", "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod", "beef_productivity": "2020 Prod"}],
        },
    }
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    with pytest.raises(ValueError, match="ratio_type"):
        optigob.run()


def test_grassland_pool_self_enforcing_once_ratio_is_set():
    """Reproduces land-balance.md's own worked example: cattle frozen until
    2030 (scaler=1), afforestation_rate=5 and AD both already claiming land
    by then. Infeasible under the old heuristic (confirmed by history in
    claude-docs/land-balance.md); feasible once ratio_type/ratio_value are
    added, with every other number identical -- the LP forces cattle to
    cede land immediately rather than waiting for its first waypoint.
    """
    config = {
        "baseline_year": 2020, "target_year": 2100,
        "forestry": [
            {"name": "existing_forest", "harvest": "high", "ccs": True},
            {"name": "afforestation", "afforestation_rate": 5, "broadleaf_frac": 0.5, "organic_soil": 0.15, "harvest": "high", "ccs": True},
        ],
        "organic_soils": [
            {"name": "Organic soil under grass", "drainage_status": ["Drained", "Rewetted"], "waypoints": [{"year": 2030, "rewetting_ratio": 0}, {"year": 2040, "rewetting_ratio": 0.2}]},
        ],
        "non_cattle_agriculture": [
            {"name": "Sheep", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": [{"year": 2030, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 1, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}, {"year": 2045, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 0.8, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}]},
        ],
        "cattle_systems": {
            "abatement": "2020 BL", "productivity": "2020 Prod",
            "waypoints": [
                {"year": 2030, "abatement": "2020 BL", "scaler": 1, "scale_parameter": "co2e", "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod", "beef_productivity": "2020 Prod"},
                {"year": 2050, "abatement": "MACC", "scaler": 0.5, "scale_parameter": "co2e", "scale_absolute_or_percentage": False, "dairy_productivity": "Strong increase", "beef_productivity": "Strong increase"},
            ],
        },
        "ad_emissions": {"implementation_year": 2035, "ccs": True, "additional_biomethane_year": 2040, "additional_grass_biomethane": 2000, "willow_year": 2045, "cdr_bioenergy": 5},
    }

    # No ratio_type/ratio_value -> can't even run (mandatory now).
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    with pytest.raises(ValueError, match="ratio_type"):
        optigob.run()

    # Same config, ratio added -> feasible, no other numbers touched.
    import copy
    with_ratio = copy.deepcopy(config)
    for wp in with_ratio["cattle_systems"]["waypoints"]:
        wp["ratio_type"] = "dairy_per_beef"
        wp["ratio_value"] = 2.0
    optigob = Optigob(json_config=with_ratio, db_file_path=db_file_path)
    optigob.run()  # must not raise


def test_organic_soil_pool_violation_raises_with_max_feasible_rate():
    config = _organic_soil_config(afforestation_rate=50, rewetting_ratio=0.5)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    with pytest.raises(ValueError, match="organic-soil pool") as excinfo:
        optigob.run()

    message = str(excinfo.value)
    assert "Max feasible afforestation_rate given current config:" in message


def test_organic_soil_pool_feasible_scenario_runs_clean():
    config = _organic_soil_config(afforestation_rate=1, rewetting_ratio=0.5)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()  # must not raise


def test_organic_soil_pool_reported_max_rate_is_actually_feasible():
    import re

    config = _organic_soil_config(afforestation_rate=50, rewetting_ratio=0.5)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    with pytest.raises(ValueError) as excinfo:
        optigob.run()

    max_rate = float(re.search(r"current config: ([0-9.]+)", str(excinfo.value)).group(1))

    feasible_config = _organic_soil_config(afforestation_rate=max_rate, rewetting_ratio=0.5)
    optigob = Optigob(json_config=feasible_config, db_file_path=db_file_path)
    optigob.run()  # must not raise -- the reported number must actually work if plugged back in
