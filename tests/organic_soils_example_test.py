"""
Organic soils walkthrough, using
tests/data/organic_soils/input/organic_soils_example.json (a copy of
examples/organic_soils_example.json).

Plain runnable script (no assertions) -- read it top to bottom alongside its
printed output and the saved chart. Input config, and output figures/excel/
logfiles, all live under tests/data/organic_soils/. Run with:

    poetry run python tests/organic_soils_example_test.py

--------------------------------------------------------------------------
THE SCENARIO (tests/data/organic_soils/input/organic_soils_example.json)
--------------------------------------------------------------------------
baseline_year=2020, target_year=2050. Four soil types:
  - Organic soil under grass: Drained/Rewetted, waypoints rewetting_ratio
    0.1 (2030) -> 0.4 (2050) -- an increasingly ambitious rewetting policy.
  - Near natural wetlands: drainage_status=["Natural"] only, NO waypoints
    -- there's nothing to rewet, it's already natural/undrained, so it's
    included purely so its (small, static) emissions are counted.
  - Industrial peat / Domestic peat: Drained/Rewetted, waypoints
    rewetting_ratio 0.0 (2030) -> 0.3 (2050).

--------------------------------------------------------------------------
THE CORE MECHANIC: rewetting_ratio MOVES AREA, NOT JUST EMISSIONS
--------------------------------------------------------------------------
Each soil type's BASELINE Drained area is fixed at 2020. A waypoint's
rewetting_ratio (e.g. 0.4) doesn't scale current emissions directly -- it
reallocates a FRACTION OF THE ORIGINAL 2020 DRAINED AREA into the Rewetted
category (see OrganicSoilSystem.update_soil() in organic_soils.py):
    new_drained_area  = (1 - rewetting_ratio) * baseline_drained_area
    new_rewetted_area = original_rewetted_area + rewetting_ratio * baseline_drained_area
Every per-hectare metric (co2e, hnv_area_ratio, etc.) is then recomputed as
that new area times the (fixed) per-hectare rate for that drainage status.
So rewetting_ratio=0.4 always means "40% of the ORIGINAL drained area is now
rewetted" -- never 40% of whatever the drained area happened to be at the
previous waypoint. This is the same "always relative to original baseline,
never the previous waypoint" rule documented for cattle/non-cattle scalers
in claude-docs/optigob-ts-full-guide.md section 4, just expressed as a
ratio over area instead of a scaler over an emissions value.

--------------------------------------------------------------------------
WHAT TO WATCH FOR IN THE OUTPUT / CHART
--------------------------------------------------------------------------
1. Drained co2e should FALL and Rewetted co2e should RISE at every waypoint
   for the three rewettable soil types -- area is moving from one bucket
   to the other, and Drained/Rewetted organic soil have very different
   (opposite-sign, in general) per-hectare emission rates.
2. Near natural wetlands has a flat, single-line "Natural" series across
   the whole run -- nothing ever changes it.
3. Industrial/Domestic peat start their rewetting later in relative terms
   (0.0 at 2030, i.e. no change yet) then jump to 0.3 by 2050, while
   Organic soil under grass is already partway rewetted by 2030 (0.1) --
   a visibly different pace between soil types in the same scenario.
"""

import json
import logging
from pathlib import Path

import pandas as pd

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import ORGANIC_SOILS
from optigob_ts.common.logger import configure_logging

DATA_DIR = Path(__file__).resolve().parent / "data" / "organic_soils"
CONFIG_PATH = DATA_DIR / "input" / "organic_soils_example.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "organic_soils.log"
PLOT_PATH = DATA_DIR / "output" / "figures" / "organic_soils.png"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "organic_soils.xlsx"

SOILS = ["Organic soil under grass", "Industrial peat", "Domestic peat"]


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=logging.INFO, log_to_file=str(LOG_PATH))

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()

    organic_soils = optigob.get_field(ORGANIC_SOILS)
    wetlands = organic_soils.get_system("Near natural wetlands")
    years = list(range(optigob.baseline_year, optigob.target_year + 1))

    print("=" * 70)
    print("ORGANIC SOILS WALKTHROUGH: 2020 -> 2050")
    print("=" * 70)

    co2e_cols = {}
    for name in SOILS:
        soil = organic_soils.get_system(name)
        co2e_cols[f"{name} (Drained)"] = soil.time_series["Drained_co2e"]
        co2e_cols[f"{name} (Rewetted)"] = soil.time_series["Rewetted_co2e"]
    co2e_cols["Near natural wetlands (Natural)"] = wetlands.time_series["Natural_co2e"]
    co2e_df = pd.DataFrame(co2e_cols, index=years)

    print("\nCO2e by soil type/drainage status (kt), selected years:")
    print(co2e_df.loc[[2020, 2030, 2040, 2050]].round(1).T)

    area_cols = {}
    for name in SOILS:
        soil = organic_soils.get_system(name)
        area_cols[f"{name} (Drained)"] = soil.time_series["Drained_area"]
        area_cols[f"{name} (Rewetted)"] = soil.time_series["Rewetted_area"]
    area_df = pd.DataFrame(area_cols, index=years)

    print("\nArea by soil type/drainage status (ha), selected years:")
    print(area_df.loc[[2020, 2030, 2040, 2050]].round(1).T)

    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        for col in co2e_df.columns:
            axes[0].plot(years, co2e_df[col], label=col)
        axes[0].set_title("CO2e by soil type / drainage status (kt)")
        axes[0].set_xlabel("Year")
        axes[0].legend(fontsize=7)

        for col in area_df.columns:
            axes[1].plot(years, area_df[col], label=col)
        axes[1].set_title("Area by soil type / drainage status (ha)")
        axes[1].set_xlabel("Year")
        axes[1].legend(fontsize=7)

        fig.tight_layout()
        PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(PLOT_PATH, dpi=120)
        print(f"\nChart saved to {PLOT_PATH}")
    except ImportError:
        print("\nmatplotlib not installed (poetry install -E viz) -- skipping chart.")

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(EXCEL_PATH) as writer:
        co2e_df.to_excel(writer, sheet_name="co2e")
        area_df.to_excel(writer, sheet_name="area")
    print(f"Excel saved to {EXCEL_PATH}")


if __name__ == "__main__":
    main()
