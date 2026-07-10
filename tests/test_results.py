import os
from io import BytesIO

import pytest

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")

# Same shape as test_area_balancing.py's config1, but target_year=2050 (not
# 2020-2100) so that ad_emissions's fixed 81-year (2020-2100) raw time_series
# arrays are deliberately shorter than time_span=31 -- exercising the
# truncation defense in Results._build_tidy, which config1's own 81-year span
# would coincidentally hide.
config = {
    "baseline_year": 2020,
    "target_year": 2050,
    "forestry": [
        {"name": "existing_forest", "harvest": "high", "ccs": True},
        {"name": "afforestation", "afforestation_rate": 5, "broadleaf_frac": 0.5, "organic_soil": 0.15, "harvest": "high", "ccs": True},
    ],
    "organic_soils": [
        {"name": "Organic soil under grass", "drainage_status": ["Drained", "Rewetted"], "waypoints": [{"year": 2030, "rewetting_ratio": 0}, {"year": 2040, "rewetting_ratio": 0.2}]},
        {"name": "Near natural wetlands", "drainage_status": ["Natural"]},
        {"name": "Industrial peat", "drainage_status": ["Drained", "Rewetted"], "waypoints": [{"year": 2030, "rewetting_ratio": 0}, {"year": 2040, "rewetting_ratio": 0.15}]},
        {"name": "Domestic peat", "drainage_status": ["Drained", "Rewetted"], "waypoints": [{"year": 2030, "rewetting_ratio": 0}, {"year": 2040, "rewetting_ratio": 0.15}]},
    ],
    "non_cattle_agriculture": [
        {"name": "Pigs", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": [{"year": 2030, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 1, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}, {"year": 2040, "abatement": "MACC", "productivity": "2020 Prod", "scaler": 0.9, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}]},
        {"name": "Poultry", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": [{"year": 2030, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 1, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}, {"year": 2040, "abatement": "MACC", "productivity": "2020 Prod", "scaler": 0.9, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}]},
        {"name": "Sheep", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": [{"year": 2030, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 1, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}, {"year": 2045, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 0.8, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}]},
        {"name": "Crops", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": [{"year": 2030, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 1, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}, {"year": 2040, "abatement": "2020 BL", "productivity": "2020 Prod", "scaler": 0.9, "scale_parameter": "co2e", "scale_absolute_or_percentage": False}]},
    ],
    "cattle_systems": {
        "abatement": "2020 BL", "productivity": "2020 Prod",
        "ratio_type": "dairy_per_beef", "ratio_value": 2.0,
        "waypoints": [
            {"year": 2030, "abatement": "2020 BL", "scaler": 1, "scale_parameter": "co2e", "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod", "beef_productivity": "2020 Prod"},
            {"year": 2040, "abatement": "2020 BL", "scaler": 0.8, "scale_parameter": "co2e", "scale_absolute_or_percentage": False, "dairy_productivity": "Medium increase", "beef_productivity": "Medium increase"},
            {"year": 2050, "abatement": "MACC", "scaler": 0.5, "scale_parameter": "co2e", "scale_absolute_or_percentage": False, "dairy_productivity": "Strong increase", "beef_productivity": "Strong increase"},
        ],
    },
    "ad_emissions": {
        "implementation_year": 2035, "ccs": True,
        "additional_biomethane_year": 2040, "additional_grass_biomethane": 2000,
        "willow_year": 2045, "cdr_bioenergy": 5,
    },
}


@pytest.fixture(scope="module")
def results():
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()
    return optigob.get_results()


@pytest.fixture(scope="module")
def optigob_run():
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()
    return optigob


def test_time_span():
    time_span = 2050 - 2020 + 1
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()
    r = optigob.get_results()

    counts = r.tidy.groupby(["field", "parameter", "label"], dropna=False)["year"].count()
    assert (counts == time_span).all()


def test_ad_area_not_silently_truncated_to_wrong_length(results):
    ad_rows = results.tidy[(results.tidy["field"] == AD_EMISSIONS) & (results.tidy["parameter"] == AREA)]
    assert not ad_rows.empty
    assert set(ad_rows["year"]) == set(range(2020, 2051))


def test_organic_soils_has_no_total_row(results):
    for parameter in (CO2E, AREA, BIODIVERSITY):
        rows = results.tidy[(results.tidy["field"] == ORGANIC_SOILS) & (results.tidy["parameter"] == parameter)]
        assert not rows.empty
        assert not rows["is_total"].any()


def test_ad_total_area_row_detected_despite_nonstandard_label(results):
    rows = results.tidy[(results.tidy["field"] == AD_EMISSIONS) & (results.tidy["parameter"] == AREA)]
    total_rows = rows[rows["label"] == "total_ad"]
    assert not total_rows.empty
    assert total_rows["is_total"].all()


def test_net_zero_rows_match_get_net_zero_calculations(results, optigob_run):
    co2e, co2e_split_gas, total_ch4 = optigob_run.get_net_zero_calculations()

    scenario_rows = results.tidy[(results.tidy["parameter"] == CO2E) & (results.tidy["field"].isna())]
    assert set(scenario_rows["label"]) == {"net_zero_co2e", "net_zero_split_gas_co2/n2o", "net_zero_split_gas_ch4"}
    assert (scenario_rows["is_total"]).all()

    def series_for(label):
        return list(scenario_rows[scenario_rows["label"] == label].sort_values("year")["value"])

    assert series_for("net_zero_co2e") == pytest.approx(co2e)
    assert series_for("net_zero_split_gas_co2/n2o") == pytest.approx(co2e_split_gas)
    assert series_for("net_zero_split_gas_ch4") == pytest.approx(total_ch4)


def test_livestock_population_rows_and_category(results):
    rows = results.tidy[results.tidy["parameter"] == "livestock_population"]
    assert set(rows["label"]) == {
        "Dairy_total_cattle_numbers",
        "Beef_total_cattle_numbers",
        "Spared Cattle/Sheep area_total_cattle_numbers",
        "total_cattle_systems",
    }
    assert (rows["unit"] == "head").all()

    total_rows = rows[rows["label"] == "total_cattle_systems"]
    assert total_rows["is_total"].all()

    # the category property is a report-style view (totals included)
    df = results.livestock_population
    assert "total_cattle_systems" in df.columns
    assert "Dairy_total_cattle_numbers" in df.columns
    assert list(df.index) == list(range(2020, 2051))


@pytest.mark.parametrize("category", [
    "area", "ghg", "protein", "biodiversity", "energy", "hwp", "substitution", "livestock_population",
])
def test_category_properties_return_dataframes(results, category):
    df = getattr(results, category)
    assert list(df.index) == list(range(2020, 2051))
    assert len(df.columns) > 0


@pytest.mark.parametrize("category", [
    "area", "ghg", "protein", "biodiversity", "energy", "hwp", "substitution", "livestock_population", "net_zero",
])
def test_plot_does_not_raise(results, category):
    import matplotlib
    matplotlib.use("Agg")
    ax = results.plot(category)
    assert ax is not None


def test_plot_rejects_unknown_category(results):
    with pytest.raises(ValueError):
        results.plot("not_a_real_category")


def test_wide_round_trips_against_tidy(results):
    wide = results.wide(AREA, field=FORESTRY)
    tidy_forestry_area = results.tidy[
        (results.tidy["field"] == FORESTRY) & (results.tidy["parameter"] == AREA) & (~results.tidy["is_total"])
    ]
    assert wide.sum().sum() == pytest.approx(tidy_forestry_area["value"].sum())


def test_to_csv_and_to_excel_do_not_raise(results, tmp_path):
    csv_path = tmp_path / "results.csv"
    results.to_csv(csv_path)
    assert csv_path.exists()

    excel_path = tmp_path / "results.xlsx"
    results.to_excel(excel_path)
    assert excel_path.exists()

    buffer = results.to_excel()
    assert isinstance(buffer, BytesIO)
