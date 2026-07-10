import os
from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *
import pytest

# Expected co2e/protein values below reflect AR5-recomputed co2e (co2 + ch4*28 + n2o*265),
# not the DB's precomputed co2e column -- see gwp.py/recompute_co2e. Because scale_parameter
# "co2e" drives every waypoint's dairy/beef scaler, this recompute also shifts every other
# scaled metric (protein, cattle numbers, etc.), not just the printed co2e figure.
#
# Also reflects the mandatory ratio-constrained optimiser (ratio_type=dairy_per_beef,
# ratio_value=2.0 here) -- the heuristic (no-ratio) split was removed since it had no
# land-balance awareness at all (see claude-docs/consistency-and-moo.md section 2/2a,
# claude-docs/land-balance.md). Only the baseline (2020) row is unaffected by that change.
db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")

config1 = {
    "baseline_year":2020,
    "target_year":2100,
    "non_cattle_agriculture":[
        {
            "name":"Pigs",
            "abatement":"2020 BL",
            "productivity":"2020 Prod",
            "waypoints":[
                {
                    "year":2030,
                    "abatement":"2020 BL",
                    "productivity":"2020 Prod",
                    "scaler":376.2,
                    "scale_parameter":"co2e",
                    "scale_absolute_or_percentage":True
                },
                {
                    "year":2040,
                    "abatement":"2020 BL",
                    "productivity":"2020 Prod",
                    "scaler":276.2,
                    "scale_parameter":"co2e",
                    "scale_absolute_or_percentage":True
                }
            ]
        }],
    "cattle_systems":
        {
            "abatement":"2020 BL",
            "productivity":"2020 Prod",
            "ratio_type":"dairy_per_beef",
            "ratio_value":2.0,
            "waypoints":[
                {
                    "year":2030,
                    "abatement":"2020 BL",
                    "scaler":1,
                    "scale_parameter":"co2e",
                    "scale_absolute_or_percentage":False,
                    "dairy_productivity":"2020 Prod",
                    "beef_productivity":"Medium increase"
                },
                {
                    "year":2040,
                    "abatement":"2020 BL",
                    "scaler":0.7,
                    "scale_parameter":"co2e",
                    "scale_absolute_or_percentage":False,
                    "dairy_productivity":"Medium increase",
                    "beef_productivity":"Medium increase"
                },
                {
                    "year":2050,
                    "abatement":"MACC",
                    "scaler":0.7,
                    "scale_parameter":"co2e",
                    "scale_absolute_or_percentage":False,
                    "dairy_productivity":"Strong increase",
                    "beef_productivity":"Strong increase"
                }
            ]
        }
}

@pytest.mark.parametrize(
    "test_years, config, test_metric, expected_results",
    [
        ([2020, 2030, 2040, 2050], config1, ["co2e", "human_consumed_protein"], [[(12941.864, 7633.53), (8560998737.33, 286692610.1)],
                                                                                 [(14564.822964841866, 5889.735361308424), (9634580537.351204, 255932269.4341366)],
                                                                                 [(9949.704374363824, 4507.971425636175), (8416403749.203429, 195889167.63333154)],
                                                                                 [(8857.649925909629, 3702.357627134163), (12713813291.807669, 263306510.3968644)]])
    ],
)

def test_non_cattle_agriculture(test_years, config, test_metric, expected_results):
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    dairy = optigob.get_field(CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_DAIRY)
    beef = optigob.get_field(CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_BEEF)

    for i in range(len(test_years)):
        idx = test_years[i] - optigob.baseline_year
        for j in range(len(test_metric)):
            expected_result = expected_results[i][j][0]
            actual_result = dairy.time_series[test_metric[j]][idx]
            assert round(actual_result,2) == round(expected_result,2)
            expected_result = expected_results[i][j][1]
            actual_result = beef.time_series[test_metric[j]][idx]
            assert round(actual_result,2) == round(expected_result,2)
