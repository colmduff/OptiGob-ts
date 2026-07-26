"""Protein is tonnes of protein -- for cattle AND non-cattle.

These tests exist because it once wasn't. The `cattle` table stores raw product
mass in kg (`milk_yield`, `beef_carcass_yield`); `get_protein` used to pass
those straight through as though they were tonnes of protein, so milk was
reported ~28,600x too large and beef ~5,000x, on the same axis as the
non-cattle sectors, which really are tonnes of protein.

The conversion mirrors OptiGob (`livestock/livestock_budget.py`): raw mass x
the `protein_content` factor (milk 0.035, beef 0.23), then kg -> t.
"""
import json
import os

import pytest

from optigob_ts.optigob import Optigob
from optigob_ts.resource_manager.database_manager import DatabaseManager

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")
config_path = os.path.join(os.path.dirname(__file__), "data", "full_example",
                           "input", "config.json")

BASELINE_YEAR = 2020

# Ireland 2020, CSO: 8,293 million litres milk intake; 633,000 t beef and veal
# carcass weight. The raw yields anchor to these, which is how we know they are
# product mass and not protein.
CSO_2020_MILK_LITRES = 8.293e9
CSO_2020_BEEF_CARCASS_T = 633_000


@pytest.fixture(scope="module")
def results():
    with open(config_path) as f:
        config = json.load(f)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()
    return optigob.get_results()


@pytest.fixture(scope="module")
def baseline(results):
    return results.protein.loc[BASELINE_YEAR]


def test_protein_content_factors_match_optigob():
    """The six factors are OptiGob's `protein_content` table, verbatim."""
    db = DatabaseManager(db_file_path)
    assert db.get_protein_content_scaler("milk") == 0.035
    assert db.get_protein_content_scaler("beef") == 0.23
    assert db.get_protein_content_scaler("sheep") == 0.25
    assert db.get_protein_content_scaler("pig") == 0.25
    assert db.get_protein_content_scaler("poultry") == 0.27
    assert db.get_protein_content_scaler("crops") == 0.25


def test_unknown_protein_content_type_raises():
    db = DatabaseManager(db_file_path)
    with pytest.raises(ValueError, match="protein content scaler"):
        db.get_protein_content_scaler("unobtainium")


@pytest.mark.parametrize("column, expected", [
    # 8,194,875,975 kg milk x 0.035 / 1000
    ("Dairy_milk_protein", 286_820.7),
    #   366,122,762 kg dairy-origin beef carcass x 0.23 / 1000
    ("Dairy_beef_protein", 84_208.2),
    #   286,692,610 kg suckler beef carcass x 0.23 / 1000
    ("Beef_beef_protein", 65_939.3),
])
def test_cattle_protein_baseline_values(baseline, column, expected):
    assert baseline[column] == pytest.approx(expected, rel=1e-4)


def test_dairy_produces_both_milk_and_beef(baseline):
    """Dairy-origin beef is a real, separate product from suckler beef.

    Collapsing the two is the reporting mistake that motivated splitting these
    into distinctly-named series, so assert they are both present and distinct.
    """
    assert baseline["Dairy_milk_protein"] > 0
    assert baseline["Dairy_beef_protein"] > 0
    assert baseline["Beef_beef_protein"] > 0
    assert baseline["Dairy_beef_protein"] != baseline["Beef_beef_protein"]
    # A beef system produces no milk.
    assert baseline["Beef_milk_protein"] == 0


def test_raw_yields_are_product_mass_in_kg(results):
    """Anchor the DB inputs against CSO 2020, so a future unit slip in
    `tools/data_sources/dynamic_systems.xlsx` fails here rather than silently
    rescaling every protein figure."""
    from optigob_ts.common.keys import (CATTLE_AGRICULTURE, CATTLE_AGRICULTURE_DAIRY,
                                        CATTLE_AGRICULTURE_BEEF,
                                        CATTLE_AGRICULTURE_MILK_YIELD,
                                        CATTLE_AGRICULTURE_BEEF_YIELD)
    with open(config_path) as f:
        config = json.load(f)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()
    cattle = optigob.get_field(CATTLE_AGRICULTURE)
    dairy = cattle.get_system(CATTLE_AGRICULTURE_DAIRY)
    beef = cattle.get_system(CATTLE_AGRICULTURE_BEEF)

    milk_kg = dairy.time_series[CATTLE_AGRICULTURE_MILK_YIELD][0]
    assert milk_kg == pytest.approx(CSO_2020_MILK_LITRES, rel=0.05)

    beef_kg = (dairy.time_series[CATTLE_AGRICULTURE_BEEF_YIELD][0]
               + beef.time_series[CATTLE_AGRICULTURE_BEEF_YIELD][0])
    assert beef_kg / 1000.0 == pytest.approx(CSO_2020_BEEF_CARCASS_T, rel=0.05)


def test_cattle_and_non_cattle_totals_are_same_order_of_magnitude(baseline):
    """The regression guard that would have caught the original bug.

    Before the conversion existed these differed by ~4 orders of magnitude
    (8.85e9 vs 3.64e5) while both were labelled "t", which made the stacked
    protein chart unreadable and the two totals not summable.
    """
    cattle = baseline["total_cattle_systems"]
    non_cattle = baseline["total_non_cattle_agriculture"]
    assert cattle == pytest.approx(436_968.2, rel=1e-4)
    assert non_cattle == pytest.approx(364_294.0, rel=1e-4)
    assert 0.1 < cattle / non_cattle < 10


def test_cattle_total_is_the_sum_of_its_products(baseline):
    products = [c for c in baseline.index
                if c.endswith("_milk_protein") or c.endswith("_beef_protein")]
    assert baseline["total_cattle_systems"] == pytest.approx(
        sum(baseline[c] for c in products), rel=1e-9)


def test_no_column_reports_raw_yield(results):
    """No protein column may be in the billions -- that only happens if a raw
    kg yield has leaked through unconverted."""
    df = results.protein
    assert df.abs().max().max() < 1e7, (
        "a protein column is implausibly large; a raw kg yield is likely "
        f"unconverted:\n{df.abs().max().sort_values(ascending=False).head()}")
