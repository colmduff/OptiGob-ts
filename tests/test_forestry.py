import os
from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *
import pytest

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")

@pytest.mark.parametrize(
    "test_year, test_metric, harvest, ccs, expected",
    [
        (2060, "hwp_material_substitution_credit", "low",  False, -2939.8346225622618),
        (2060, "hwp_material_substitution_credit", "high", False, -4259.176198816194),
        (2060, "hwp_material_substitution_credit", "low",  True,  -646.7636169636975),
        (2060, "hwp_material_substitution_credit", "high", True,  -937.0187637395626),
    ],
)

def test_existing_forest(test_year, test_metric, harvest, ccs, expected):
    config = {
        "baseline_year": 2020,
        "target_year": 2100,
        "forestry": [
            {
                "name": "existing_forest",
                "harvest": harvest,
                "ccs": ccs,
            },
            {
                "name": "afforestation",
                "afforestation_rate": 1,
                "broadleaf_frac": 0.5,
                "organic_soil": 0.15,
                "harvest": "low",
                "ccs": False,
            },
        ],
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    existing_forest = optigob.get_field(FORESTRY).get_system(FORESTRY_EXISTING_FOREST)
    idx = test_year - optigob.baseline_year
    result = existing_forest.time_series[test_metric][idx]

    assert round(result, 5) == round(expected, 5)

@pytest.mark.parametrize(
    "test_year, test_metric, afforestation_rate, broadleaf_frac, organic_soil, harvest, ccs, expected",
    [
        (2060, "ghg_fluxes", 2, 0.5, 0.15, "high", True, 2*-247.578614393099),
        (2060, "ghg_fluxes", 0.5, 0.3, 0.15, "high", True, 0.5*-216.026131213205),
        (2060, "ghg_fluxes", 5, 0.5, 0, "high", True, 5*-272.36374622488),
        (2060, "ghg_fluxes", 1, 0.5, 0.15, "low", True, -293.275104947476),
        (2060, "ghg_fluxes", 0, 0.5, 0.15, "high", True, 0),
        (2050, "beccs", 3, 0.5, 0.15, "high", True, 3*-3.72515260505617),
        (2050, "beccs", 1, 0.5, 0.15, "high", False, 0.0),
    ],
)
def test_afforestation(test_year, test_metric, afforestation_rate, broadleaf_frac, organic_soil, harvest, ccs, expected):
    config = {
        "baseline_year": 2020,
        "target_year": 2100,
        "forestry": [
            {
                "name": "existing_forest",
                "harvest": "high",
                "ccs": True,
            },
            {
                "name": "afforestation",
                "afforestation_rate": afforestation_rate,
                "broadleaf_frac": broadleaf_frac,
                "organic_soil": organic_soil,
                "harvest": harvest,
                "ccs": ccs,
            },
        ],
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    afforestation = optigob.get_field(FORESTRY).get_system(FORESTRY_AFFORESTATION)
    idx = test_year - optigob.baseline_year
    result = afforestation.time_series[test_metric][idx]

    assert round(result, 5) == round(expected, 5)
