"""Bug #11: forestry anchors its whole series to the database's first year, so
a config `baseline_year` that disagrees with the DB would silently misalign
forestry against every other sector. `Optigob` now validates the two match.
"""
import os

import pytest

from optigob_ts.optigob import Optigob
from optigob_ts.resource_manager.database_manager import DatabaseManager

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")


def _config(baseline_year):
    return {
        "baseline_year": baseline_year,
        "target_year": 2050,
        "forestry": [
            {"name": "existing_forest", "harvest": "high", "ccs": True},
        ],
    }


def test_db_reports_its_first_year():
    assert DatabaseManager(db_file_path).get_baseline_year() == 2020


def test_baseline_year_matching_db_is_accepted():
    # The default, correct case: config baseline == DB first year. Unchanged
    # behaviour -- construction succeeds.
    optigob = Optigob(json_config=_config(2020), db_file_path=db_file_path)
    assert optigob.baseline_year == 2020


def test_baseline_year_mismatch_raises_clearly():
    with pytest.raises(ValueError, match="does not match the database's first year"):
        Optigob(json_config=_config(2025), db_file_path=db_file_path)
