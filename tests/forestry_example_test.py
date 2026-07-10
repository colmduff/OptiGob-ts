"""
Forestry walkthrough, using tests/data/forestry/input/forestry_example.json
(a copy of examples/forestry_example.json).

Plain runnable script (no assertions) -- read it top to bottom alongside its
printed output and the saved chart. Input config, and output figures/excel/
logfiles, all live under tests/data/forestry/. Run with:

    poetry run python tests/forestry_example_test.py

--------------------------------------------------------------------------
THE SCENARIO (tests/data/forestry/input/forestry_example.json)
--------------------------------------------------------------------------
baseline_year=2020, target_year=2100. Two forestry systems:
  - existing_forest: harvest="high", ccs=True. This is the pre-existing
    national forest estate -- there is nothing to configure about its
    *size* (it already exists), only how it's managed (harvest intensity,
    whether carbon capture is applied to any wood-energy use).
  - afforestation: afforestation_rate=5.0 (kha/year of NEW planting),
    broadleaf_frac=0.5 (share of new planting that's broadleaf vs conifer),
    organic_soil=0.15 (share of new planting on organic soil, which behaves
    very differently carbon-wise than mineral soil), harvest="high", ccs=True.

--------------------------------------------------------------------------
THE KEY DIFFERENCE FROM CATTLE / NON-CATTLE / ORGANIC SOILS
--------------------------------------------------------------------------
Forestry has NO waypoints at all -- there's no "waypoints" list in the
config, and ForestrySystem doesn't implement one. Every year's value is
already precomputed upstream (by the GOBLIN/FERS-CBM model that built the
bundled database) as a direct function of the handful of static parameters
above (rate, composition, harvest intensity, ccs on/off) -- OptiGob-ts just
reads out that whole precomputed trajectory. There is nothing to "ramp"
here: you aren't authoring a path, you're selecting *which already-computed
path* applies by choosing these parameters once. Contrast this with cattle
or organic soils, where a single system's fate is deliberately re-targeted
at multiple points in time.

--------------------------------------------------------------------------
WHAT TO WATCH FOR IN THE OUTPUT / CHART
--------------------------------------------------------------------------
1. existing_forest's co2e is a net SINK (negative -- it's actively removing
   carbon) that is roughly flat/slowly changing over time, since nothing
   about it is being altered mid-run.
2. afforestation's co2e starts near zero (new trees planted in 2020 haven't
   grown yet) and becomes an increasingly large sink as decades pass and
   the planted area matures -- this is the "carbon accumulates as trees
   grow" curve, not a policy ramp.
3. harvest_volume (an HWP-relevant output) is where you'd see any wood
   actually being taken out for harvested wood products -- compare
   existing_forest's (established, harvestable now) against afforestation's
   (near zero for decades, since newly planted trees aren't harvestable yet).
"""

import json
import logging
from pathlib import Path

import pandas as pd

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import FORESTRY, FORESTRY_EXISTING_FOREST, FORESTRY_AFFORESTATION
from optigob_ts.common.logger import configure_logging

DATA_DIR = Path(__file__).resolve().parent / "data" / "forestry"
CONFIG_PATH = DATA_DIR / "input" / "forestry_example.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "forestry.log"
PLOT_PATH = DATA_DIR / "output" / "figures" / "forestry.png"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "forestry.xlsx"


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=logging.INFO, log_to_file=str(LOG_PATH))

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()

    existing_forest = optigob.get_field(FORESTRY).get_system(FORESTRY_EXISTING_FOREST)
    afforestation = optigob.get_field(FORESTRY).get_system(FORESTRY_AFFORESTATION)

    years = list(range(optigob.baseline_year, optigob.target_year + 1))
    df = pd.DataFrame(
        {
            "existing_forest_co2e": existing_forest.time_series["co2e"],
            "afforestation_co2e": afforestation.time_series["co2e"],
            "existing_forest_harvest_volume": existing_forest.time_series["harvest_volume"],
            "afforestation_harvest_volume": afforestation.time_series["harvest_volume"],
        },
        index=years,
    )
    df["total_co2e"] = df["existing_forest_co2e"] + df["afforestation_co2e"]

    print("=" * 70)
    print("FORESTRY WALKTHROUGH: 2020 -> 2100 (no waypoints -- see notes above)")
    print("=" * 70)
    print(df.loc[[2020, 2030, 2050, 2075, 2100]].round(1))

    print("\nNote: co2e is negative throughout -- both systems are net carbon sinks.")
    print(f"Total forestry co2e sink by 2100: {df['total_co2e'].iloc[-1]:,.1f} kt")

    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(11, 4))

        axes[0].plot(df.index, df["existing_forest_co2e"], label="existing_forest")
        axes[0].plot(df.index, df["afforestation_co2e"], label="afforestation")
        axes[0].plot(df.index, df["total_co2e"], label="total", linestyle="--", color="black")
        axes[0].set_title("Forestry CO2e (kt) -- negative = net sink")
        axes[0].set_xlabel("Year")
        axes[0].legend()

        axes[1].plot(df.index, df["existing_forest_harvest_volume"], label="existing_forest")
        axes[1].plot(df.index, df["afforestation_harvest_volume"], label="afforestation")
        axes[1].set_title("Harvest volume")
        axes[1].set_xlabel("Year")
        axes[1].legend()

        fig.tight_layout()
        PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(PLOT_PATH, dpi=120)
        print(f"\nChart saved to {PLOT_PATH}")
    except ImportError:
        print("\nmatplotlib not installed (poetry install -E viz) -- skipping chart.")

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(EXCEL_PATH)
    print(f"Excel saved to {EXCEL_PATH}")


if __name__ == "__main__":
    main()
