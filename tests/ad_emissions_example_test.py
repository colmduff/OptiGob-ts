"""
Anaerobic digestion (AD) / bioenergy walkthrough, using
tests/data/ad_emissions/input/ad_emissions_example.json (a copy of
examples/ad_emissions_example.json).

Plain runnable script (no assertions) -- read it top to bottom alongside its
printed output and the saved chart. Input config, and output figures/excel/
logfiles, all live under tests/data/ad_emissions/. Run with:

    poetry run python tests/ad_emissions_example_test.py

--------------------------------------------------------------------------
THE SCENARIO (tests/data/ad_emissions/input/ad_emissions_example.json)
--------------------------------------------------------------------------
baseline_year=2020, target_year=2050. A single AD system with four
independent "switch on" years, each ramping in its own effect on top of
whatever came before -- this is the clearest example in the whole package
of "can I set an intermediate target on the way to 2050", because here it's
literally what the config is for:
  - implementation_year=2030: the CORE biomethane/AD strategy switches on
    (grass silage -> biomethane). It ramps in over a short, fixed-length
    window baked into the database (here: 2024-2030, ~6 years) that ENDS at
    implementation_year -- not a ramp starting from baseline_year (see
    claude-docs/code-walkthrough-and-optimisation-entry-point.md section on
    "willow" for the exact offset-shifting mechanism).
  - ccs=true: carbon capture applied to the AD system from implementation
    onward (BECCS -- bioenergy with carbon capture and storage).
  - additional_biomethane_year=2035, additional_grass_biomethane=2000.0:
    a SECOND, independent ramp -- extra biomethane capacity (2000 units,
    whatever unit additional_grass_biomethane is expressed in) phased in
    between implementation_year and this year.
  - willow_year=2040, cdr_bioenergy=1500.0: a THIRD independent ramp --
    willow (a dedicated energy crop) planted for bioenergy, contributing
    1500 units of carbon-dioxide-removal bioenergy (BECCS) by this year.

--------------------------------------------------------------------------
WHY THIS ANSWERS "CAN I SET AN INTERMEDIATE TARGET ON THE WAY TO 2050?"
--------------------------------------------------------------------------
Yes, directly -- each of these three ramps (core AD, additional biomethane,
willow) has its OWN target year, entirely independent of the others and of
target_year=2050 itself. Nothing forces them to line up: you could switch
on core AD in 2030, additional biomethane in 2026 (before core AD is even
fully ramped in), and willow as late as 2049. This is a config with NO
per-waypoint scaler/ratio choices at all (unlike cattle/non-cattle/organic
soils) -- you're choosing WHEN three fixed-size effects phase in, not HOW
BIG they eventually get relative to some baseline.

--------------------------------------------------------------------------
WHAT TO WATCH FOR IN THE OUTPUT / CHART
--------------------------------------------------------------------------
1. "ad_biomethane_energy" (the core ramp) is flat at 0 until ~2024, ramps up
   through implementation_year=2030, then flat at its full value (5700)
   for the rest of the run.
2. "ad_additional_biomethane_energy" is flat at 0 until implementation_year
   (2030), THEN ramps over the 2030-2035 window up to
   additional_grass_biomethane=2000, then flat.
3. "willow_willow" / "willow_BECCS" are flat at 0 the longest, only ramping
   over the short 2035-2040 window up to cdr_bioenergy=1500, then flat --
   so at 2032 you'd see core AD already flat, additional biomethane partway
   up, and willow still at zero: three short ramps staggered one after
   another, each ending at its own named year, none starting at
   baseline_year.
"""

import json
import logging
from pathlib import Path

import pandas as pd

from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import AD_EMISSIONS
from optigob_ts.common.logger import configure_logging

DATA_DIR = Path(__file__).resolve().parent / "data" / "ad_emissions"
CONFIG_PATH = DATA_DIR / "input" / "ad_emissions_example.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "ad_emissions.log"
PLOT_PATH = DATA_DIR / "output" / "figures" / "ad_emissions.png"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "ad_emissions.xlsx"


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=logging.INFO, log_to_file=str(LOG_PATH))

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()

    ad = optigob.get_field(AD_EMISSIONS).get_system(AD_EMISSIONS)
    years = list(range(optigob.baseline_year, optigob.target_year + 1))
    time_span = len(years)

    # Note: the underlying DB table backing this system is precomputed out to
    # a fixed horizon (longer than most target_years), so every raw
    # time_series entry must be sliced down to time_span before use here --
    # unlike cattle/non-cattle/organic soils, whose arrays are always built
    # out to exactly target_year by their own waypoint/run() logic.
    df = pd.DataFrame(
        {
            "ad_biomethane_energy": ad.time_series["biomethane_energy"][:time_span],
            "ad_additional_biomethane_energy": ad.time_series["additional_biomethane_energy"][:time_span],
            "willow_willow": ad.time_series["willow_willow"][:time_span],
            "willow_BECCS": ad.time_series["willow_BECCS"][:time_span],
        },
        index=years,
    )

    print("=" * 70)
    print("AD EMISSIONS / BIOENERGY WALKTHROUGH: 2020 -> 2050")
    print("=" * 70)
    print("(implementation_year=2030, additional_biomethane_year=2035, willow_year=2040)\n")
    print(df.loc[[2020, 2025, 2030, 2035, 2040, 2050]].round(1))

    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 5))
        for col in df.columns:
            ax.plot(years, df[col], label=col)
        for year, label in [(2030, "implementation_year"), (2035, "additional_biomethane_year"), (2040, "willow_year")]:
            ax.axvline(year, linestyle=":", color="gray", alpha=0.6)
            ax.text(year, ax.get_ylim()[1] * 0.95, label, rotation=90, fontsize=7, va="top")
        ax.set_title("AD / bioenergy: three independently staggered ramps")
        ax.set_xlabel("Year")
        ax.legend(fontsize=8)

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
