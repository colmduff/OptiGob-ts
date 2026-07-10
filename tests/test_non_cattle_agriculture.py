import os
from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *
import pytest

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")

# Expected co2e/protein values below reflect AR5-recomputed co2e (co2 + ch4*28 +
# n2o*265), not the DB's precomputed co2e column -- see gwp.py/recompute_co2e.
@pytest.mark.parametrize(
    "test_years, system_name, way_points, test_metric, expected_results",
    [
        ([2020, 2030, 2040], "Pigs", [(2030, "2020 BL", 0.9, "co2e", False), (2040, "MACC", 300.0, "co2e", True)], ("co2e", "protein"), [(473.0, 55453.70), (425.7, 49908.33), (300.0, 43391.001564945225)]),
    ],
)

def test_non_cattle_agriculture(test_years, system_name, way_points, test_metric, expected_results):
    waypoints = []
    for (year, abatement, scaler, metric, absolute_value) in way_points:
        waypoints.append({"year":year, "abatement":abatement, "productivity": "2020 Prod", "scaler":scaler, "scale_parameter":metric, "scale_absolute_or_percentage":absolute_value})

    config = {
        "baseline_year": 2020,
        "target_year": 2100,
        NON_CATTLE_AGRICULTURE: [
            {
                "name": system_name,
                "abatement": "2020 BL",
                "productivity":"2020 Prod",
                "waypoints": waypoints
            }
        ],
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    system = optigob.get_field(NON_CATTLE_AGRICULTURE).get_system(system_name)
    for i in range(len(test_years)):
        idx = test_years[i] - optigob.baseline_year
        for j in range(len(test_metric)):
            expected_value = expected_results[i][j]
            actual_value = system.time_series[test_metric[j]][idx]
            assert round(actual_value, 2) == round(expected_value, 2)
