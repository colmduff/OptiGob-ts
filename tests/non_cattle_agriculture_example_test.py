"""
Non-cattle agriculture walkthrough, using
tests/data/non_cattle_agriculture/input/non_cattle_agriculture_example.json
(a copy of examples/non_cattle_agriculture_example.json).

Plain runnable script (no assertions) -- read it top to bottom alongside its
printed output and the saved chart. Input config, and output figures/excel/
logfiles, all live under tests/data/non_cattle_agriculture/. Run with:

    poetry run python tests/non_cattle_agriculture_example_test.py

--------------------------------------------------------------------------
THE SCENARIO (tests/data/non_cattle_agriculture/input/non_cattle_agriculture_example.json)
--------------------------------------------------------------------------
baseline_year=2020, target_year=2050. Four independent systems, each with
its own waypoint list (this sector has no cross-system coupling like
cattle's dairy/beef, or organic soils' Drained/Rewetted split):
  - Pigs:    2030 flat (scaler=1.0), 2050 scaler=0.8 -> a real cut.
  - Poultry: 2030 scaler=1.1, 2050 scaler=1.3 -> a real GROWTH scenario
    (poultry emissions/output expanding, not shrinking).
  - Sheep:   2030 flat, 2050 scaler=0.6 -> a real cut.
  - Crops:   2030 flat, 2050 scaler=0.9 -> a mild cut.

Each system's waypoints work exactly like Pigs' did in the cattle-example
notes: scaler is a fraction OF THAT SYSTEM'S OWN 2020 BASELINE (percentage
mode, scale_absolute_or_percentage=false), applied to "co2e" -- see
claude-docs/optigob-ts-full-guide.md section 4 for the "bounce" pitfall this
implies if you don't keep every waypoint's scaler expressed relative to the
same original baseline.

--------------------------------------------------------------------------
THE "Crops" -> "No-Crops" AREA-BALANCING WRINKLE
--------------------------------------------------------------------------
NonCattleAgriculture silently creates a fifth system, "No-Crops", whenever
a "Crops" system is configured (see NonCattleAgriculture.__init__ and
.run() area-balancing code) -- there's no "No-Crops" entry in the JSON at
all. Its whole purpose is area bookkeeping: if Crops' area shrinks by X
hectares from baseline, "No-Crops" area grows by that same X, keeping
total land area conserved. It carries no emissions of its own -- watch for
it appearing in the printed table and chart even though nothing in the
config mentions it.

--------------------------------------------------------------------------
WHAT TO WATCH FOR IN THE OUTPUT / CHART
--------------------------------------------------------------------------
1. Poultry's co2e line should visibly RISE (this config deliberately picks
   a growth scenario) while Pigs/Sheep/Crops fall -- a reminder that
   "waypoint" doesn't imply "reduction", it just means "target value".
2. No-Crops' area should move in the OPPOSITE direction to Crops' area,
   and by the same magnitude, at every year -- that's the conservation
   check described above.
3. "total_non_cattle_agriculture" (summed protein/co2e) is a genuine mix
   of rising and falling components -- it won't look like a clean
   monotonic curve, because Poultry is pulling it up while the others
   pull it down.
"""

import json
import logging
from pathlib import Path

import pandas as pd

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import NON_CATTLE_AGRICULTURE
from optigob_ts.common.logger import configure_logging

DATA_DIR = Path(__file__).resolve().parent / "data" / "non_cattle_agriculture"
CONFIG_PATH = DATA_DIR / "input" / "non_cattle_agriculture_example.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "non_cattle_agriculture.log"
PLOT_PATH = DATA_DIR / "output" / "figures" / "non_cattle_agriculture.png"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "non_cattle_agriculture.xlsx"

SYSTEMS = ["Pigs", "Poultry", "Sheep", "Crops", "No-Crops"]


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=logging.INFO, log_to_file=str(LOG_PATH))

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()

    nca = optigob.get_field(NON_CATTLE_AGRICULTURE)
    years = list(range(optigob.baseline_year, optigob.target_year + 1))

    co2e_df = pd.DataFrame(
        {name: nca.get_system(name).time_series["co2e"] for name in SYSTEMS if name != "No-Crops"},
        index=years,
    )
    area_df = pd.DataFrame(
        {name: nca.get_system(name).time_series["area"] for name in SYSTEMS},
        index=years,
    )

    print("=" * 70)
    print("NON-CATTLE AGRICULTURE WALKTHROUGH: 2020 -> 2050")
    print("=" * 70)
    print("\nCO2e by system (kt), selected years:")
    print(co2e_df.loc[[2020, 2030, 2040, 2050]].round(1))

    print("\nArea by system (ha), selected years -- watch Crops vs No-Crops move oppositely:")
    print(area_df.loc[[2020, 2030, 2040, 2050]].round(1))

    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(11, 4))

        for name in co2e_df.columns:
            axes[0].plot(years, co2e_df[name], label=name)
        axes[0].set_title("CO2e by system (kt)")
        axes[0].set_xlabel("Year")
        axes[0].legend()

        for name in area_df.columns:
            axes[1].plot(years, area_df[name], label=name)
        axes[1].set_title("Area by system (ha) -- Crops/No-Crops mirror each other")
        axes[1].set_xlabel("Year")
        axes[1].legend()

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
