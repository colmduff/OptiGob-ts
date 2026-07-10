import os
import pytest

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")

def test_ad_emissions_not_implemented():
    config = {
        "baseline_year": 2020,
        "target_year": 2050,
        # No "ad_emissions" key
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    ad_emissions = optigob.get_field(AD_EMISSIONS)
    assert ad_emissions is None

@pytest.mark.parametrize(
    "test_year, ccs, test_metric, expected_result",
    [
        (2060, True, "BECCS", -671.732351667945),
        (2060, False, "BECCS", 0.0)
    ],
)

def test_ad_emissions_ccs(test_year, ccs, test_metric, expected_result):
    config = {
        "baseline_year": 2020,
        "target_year": 2100,
        "ad_emissions": {
            "implementation_year": 2030,
            "ccs": ccs,
            "additional_biomethane_year": 2035,
            "additional_grass_biomethane": 0,
            "willow_year": 2040,
            "cdr_bioenergy": 0
        }
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    ad_emissions = optigob.get_field(AD_EMISSIONS).get_system(AD_EMISSIONS)
    idx = test_year - optigob.baseline_year
    assert round(ad_emissions.time_series[test_metric][idx],5) == round(expected_result,5)

@pytest.mark.parametrize(
    "implementation_year, test_metric, expected_result",
    [
        (2025, "biomethane_energy", 5700),
        (2030, "biomethane_energy", 5700),
        (2035, "biomethane_energy", 5700)
    ],
)
def test_ad_emissions_biomethane_strategy_implementation_year(implementation_year, test_metric, expected_result):
    config = {
        "baseline_year": 2020,
        "target_year": 2050,
        "ad_emissions": {
            "implementation_year": implementation_year,
            "ccs": False,
            "additional_biomethane_year": 2035,
            "additional_grass_biomethane": 0,
            "willow_year": 2040,
            "cdr_bioenergy": 0
        }
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    ad_emissions = optigob.get_field(AD_EMISSIONS).get_system(AD_EMISSIONS)
    idx = implementation_year - optigob.baseline_year
    assert ad_emissions.time_series[test_metric][idx] == expected_result
    assert ad_emissions.time_series[test_metric][idx - 1] < expected_result

@pytest.mark.parametrize(
    "additional_biomethane_year, additional_grass_biomethane, test_metric, expected_result",
    [
        (2025, 2000.0, "additional_biomethane_energy", 2000.0),
        (2035, 500.0, "additional_biomethane_energy", 500.0),
        (2045, 1000.0, "additional_biomethane_energy", 1000.0)
    ],
)

def test_ad_emissions_additional_ad(additional_biomethane_year, additional_grass_biomethane, test_metric, expected_result):
    config = {
        "baseline_year": 2020,
        "target_year": 2050,
        "ad_emissions": {
            "implementation_year": 2030,
            "ccs": True,
            "additional_biomethane_year": additional_biomethane_year,
            "additional_grass_biomethane": additional_grass_biomethane,
            "willow_year": 2040,
            "cdr_bioenergy": 0
        }
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    ad_emissions = optigob.get_field(AD_EMISSIONS).get_system(AD_EMISSIONS)
    idx = additional_biomethane_year - optigob.baseline_year
    assert ad_emissions.time_series[test_metric][idx] == expected_result
    assert ad_emissions.time_series[test_metric][idx-1] < expected_result

@pytest.mark.parametrize(
    "willow_year, cdr_bioenergy, test_metric, expected_result",
    [
        (2030, 1000.0, "willow_BECCS", 1000.0),
        (2040, 2000.0, "willow_BECCS", 2000.0),
        (2060, 300.0, "willow_BECCS", 300.0)
    ],
)

def test_ad_emissions_willow(willow_year, cdr_bioenergy, test_metric, expected_result):
    config = {
        "baseline_year": 2020,
        "target_year": 2050,
        "ad_emissions": {
            "implementation_year": 2030,
            "ccs": True,
            "additional_biomethane_year": 2035,
            "additional_grass_biomethane": 2000.0,
            "willow_year": willow_year,
            "cdr_bioenergy": cdr_bioenergy
        }
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    ad_emissions = optigob.get_field(AD_EMISSIONS).get_system(AD_EMISSIONS)
    idx = willow_year - optigob.baseline_year
    assert ad_emissions.time_series[test_metric][idx] == expected_result
    assert ad_emissions.time_series[test_metric][idx-1] < expected_result
