import os

import pytest

from optigob_ts.common.gwp import AR4, AR5, AR6, GWPValues, get_gwp_values
from optigob_ts.common.keys import *
from optigob_ts.optigob import Optigob

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")

config1 = {
    "baseline_year": 2020,
    "target_year": 2050,
    "non_cattle_agriculture": [
        {
            "name": "Pigs",
            "abatement": "2020 BL",
            "productivity": "2020 Prod",
            "waypoints": [
                {
                    "year": 2030,
                    "abatement": "2020 BL",
                    "productivity": "2020 Prod",
                    "scaler": 1.0,
                    "scale_parameter": "co2e",
                    "scale_absolute_or_percentage": False,
                }
            ],
        }
    ],
    "cattle_systems": {
        "abatement": "2020 BL",
        "productivity": "2020 Prod",
        "ratio_type": "dairy_per_beef",
        "ratio_value": 2.0,
        "waypoints": [
            {
                "year": 2030,
                "abatement": "2020 BL",
                "scaler": 1,
                "scale_parameter": "co2e",
                "scale_absolute_or_percentage": False,
                "dairy_productivity": "2020 Prod",
                "beef_productivity": "2020 Prod",
            }
        ],
    },
}


def test_get_gwp_values_known_versions():
    assert get_gwp_values("AR4") == AR4
    assert get_gwp_values("AR5") == AR5
    assert get_gwp_values("AR6") == AR6


def test_get_gwp_values_unknown_version_raises():
    with pytest.raises(ValueError):
        get_gwp_values("bogus")


def test_optigob_defaults_to_ar5():
    optigob = Optigob(json_config=config1, db_file_path=db_file_path)
    assert optigob.gwp == AR5


def test_optigob_ar_selection_changes_cattle_co2e():
    config_ar5 = dict(config1)
    config_ar6 = dict(config1, **{AR: "AR6"})

    optigob_ar5 = Optigob(json_config=config_ar5, db_file_path=db_file_path)
    optigob_ar5.run()
    optigob_ar6 = Optigob(json_config=config_ar6, db_file_path=db_file_path)
    optigob_ar6.run()

    dairy_ar5 = optigob_ar5.get_field(CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_DAIRY)
    dairy_ar6 = optigob_ar6.get_field(CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_DAIRY)

    co2e_ar5 = dairy_ar5.get_co2e(optigob_ar5.gwp)[1]
    co2e_ar6 = dairy_ar6.get_co2e(optigob_ar6.gwp)[1]

    assert co2e_ar5 != co2e_ar6
