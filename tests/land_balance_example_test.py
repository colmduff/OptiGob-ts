"""
Step-by-step walkthrough of `balancing.py` -- the module that reconciles
land area *between* fields (cattle/sheep/afforestation/AD/organic soils)
after each field has already independently computed its own trajectory.
See `claude-docs/land-balance.md` for the full design writeup; this script
is the "watch it actually run" companion to that doc.

`balancing.py` has two top-level entry points, always called in this order
from `Optigob.run()`:

    1. validate_land_balance(fields, baseline_year, target_year)
       -- read-only. Raises ValueError if the organic-soil pool
       ("Organic soil under grass"'s baseline Drained area, shared between
       rewetting and afforestation's organic-soil sub-claim) would ever go
       negative. The *other* land pool (cattle/sheep vs afforestation+AD)
       needs no check here -- it's self-enforcing because ratio_type/
       ratio_value are mandatory on cattle_systems now, and the ratio-LP's
       own area_commitment constraint already guarantees it every year.
    2. balance_areas(fields, baseline_year, target_year)
       -- mutates. Credits freed-up land to "Spared Cattle/Sheep area",
       and subtracts afforestation's organic-soil claim from "Organic soil
       under grass"'s Drained area. Guaranteed not to go negative *because*
       step 1 already checked it would not.

This script replicates `Optigob.run()`'s exact sequence by hand (field.run()
per field, then run_cattle_systems(), then those two balancing calls) so
each step is a visible, separately-printed line -- rather than calling
`optigob.run()` as one opaque block. `common.logger` is configured at INFO
by default, which prints one summary line per pool/function (pool size,
tightest year, pass/fail) -- `balancing.py`'s own internal logging, added
specifically so this module is inspectable without instrumenting it
externally. Bump LOG_LEVEL below to logging.DEBUG for the full per-year
arithmetic (every year's claim/balance, not just the tightest one) -- verbose
(~250 lines for this scenario's 31 years x 2 balancing functions), but
exactly what "step through it year by year" means literally.

Input config, and output figures/excel/logfiles, all live under
`tests/data/land_balance/` (`input/feasible_config.json`,
`output/{figures,excel,logs}/`).

Run with:
    poetry run python tests/land_balance_example_test.py
"""

import json
import logging
from pathlib import Path

from optigob_ts.optigob import Optigob
from optigob_ts.common.logger import configure_logging, get_logger
from optigob_ts import balancing
from optigob_ts.systems.non_cattle_agriculture import NonCattleAgriculture
from optigob_ts.systems.forestry import Forestry
from optigob_ts.systems.ad_emissions import AnaerobicDigestion
from optigob_ts.systems.cattle_agriculture import CattleAgriculture

logger = get_logger("land_balance_example")

# Bump to logging.DEBUG for the full per-year trace (see module docstring).
LOG_LEVEL = logging.INFO

DATA_DIR = Path(__file__).resolve().parent / "data" / "land_balance"
CONFIG_PATH = DATA_DIR / "input" / "feasible_config.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "land_balance.log"
FIGURE_PATH = DATA_DIR / "output" / "figures" / "land_balance.png"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "land_balance.xlsx"

with open(CONFIG_PATH) as f:
    FEASIBLE_CONFIG = json.load(f)


def run_up_to_balancing(config):
    """Replicates Optigob.__init__ + the field.run()/run_cattle_systems()
    portion of Optigob.run() -- everything *before* balancing.py gets
    involved -- so the two balancing calls below are isolated, explicit
    steps rather than buried inside optigob.run().
    """
    optigob = Optigob(json_config=config, db_file_path=None)

    nca = forestry = ad_emissions = None
    for fi in optigob.fields:
        fi.run(optigob.baseline_year, optigob.target_year, optigob.db_manager, optigob.gwp)
        if isinstance(fi, NonCattleAgriculture):
            nca = fi
        elif isinstance(fi, Forestry):
            forestry = fi
        elif isinstance(fi, AnaerobicDigestion):
            ad_emissions = fi

    for fi in optigob.fields:
        if isinstance(fi, CattleAgriculture):
            fi.run_cattle_systems(optigob.baseline_year, optigob.target_year, optigob.db_manager, nca,
                                  forestry=forestry, ad_emissions=ad_emissions, gwp=optigob.gwp)

    return optigob


def snapshot(optigob, years, verbose=True):
    """Returns (and, if verbose, prints) the exact time_series values
    balancing.py reads and writes, at a handful of years, so you can see
    cause (per-year logging) and effect (the actual numbers) side by side.
    """
    spared = optigob.get_field("cattle_systems").get_system("Spared Cattle/Sheep area")
    grass = optigob.get_field("organic_soils").get_system("Organic soil under grass")
    rows = []
    for y in years:
        i = y - optigob.baseline_year
        spared_area = spared.time_series["area"][i]
        grass_drained_area = grass.time_series["Drained_area"][i]
        if verbose:
            print(f"  {y}: spared_area={spared_area:>14,.1f} ha   "
                  f"grass_Drained_area={grass_drained_area:>12,.1f} ha")
        rows.append({"year": y, "spared_area_ha": spared_area, "grass_drained_area_ha": grass_drained_area})
    return rows


def save_outputs(rows):
    """Saves the AFTER-balancing snapshot (full year range) as a figure
    and an excel file under tests/data/land_balance/output/.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    df = pd.DataFrame(rows)

    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df["year"], df["spared_area_ha"], label="Spared Cattle/Sheep area")
    ax.plot(df["year"], df["grass_drained_area_ha"], label="Organic soil under grass -- Drained area")
    ax.set_xlabel("year")
    ax.set_ylabel("ha")
    ax.set_title("balance_areas() output over time")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_PATH, dpi=120)
    plt.close(fig)
    print(f"\nFigure saved to {FIGURE_PATH}")

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(EXCEL_PATH, index=False)
    print(f"Excel saved to {EXCEL_PATH}")


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=LOG_LEVEL, log_to_file=str(LOG_PATH))

    print("#" * 70)
    print("STEP 0: build Optigob, run every field, run cattle (all BEFORE")
    print("        balancing.py touches anything)")
    print("#" * 70)
    optigob = run_up_to_balancing(FEASIBLE_CONFIG)
    print("\nBEFORE balancing:")
    snapshot(optigob, [2020, 2030, 2040, 2050])

    print("\n" + "#" * 70)
    print("STEP 1: balancing.validate_land_balance(...)  -- read-only,")
    print("        checks the organic-soil pool never goes negative")
    print("#" * 70)
    balancing.validate_land_balance(optigob.fields, optigob.baseline_year, optigob.target_year)
    print("-> did not raise: organic-soil pool is feasible for every year")

    print("\n" + "#" * 70)
    print("STEP 2: balancing.balance_areas(...)  -- mutates spared_area and")
    print("        grass's Drained_area")
    print("#" * 70)
    balancing.balance_areas(optigob.fields, optigob.baseline_year, optigob.target_year)
    print("\nAFTER balancing:")
    snapshot(optigob, [2020, 2030, 2040, 2050])

    all_years = list(range(optigob.baseline_year, optigob.target_year + 1))
    after_rows = snapshot(optigob, all_years, verbose=False)
    save_outputs(after_rows)

    print("\n" + "#" * 70)
    print("FAILURE DEMO 1: cattle_systems without ratio_type/ratio_value")
    print("#" * 70)
    import copy
    no_ratio_config = copy.deepcopy(FEASIBLE_CONFIG)
    for wp in no_ratio_config["cattle_systems"]["waypoints"]:
        del wp["ratio_type"]
        del wp["ratio_value"]
    try:
        run_up_to_balancing(no_ratio_config)
        print("-> did NOT raise (unexpected)")
    except ValueError as e:
        print(f"-> raised, as expected, before balancing.py even runs:\n   {e}")

    print("\n" + "#" * 70)
    print("FAILURE DEMO 2: afforestation_rate too high for the organic-soil pool")
    print("#" * 70)
    violating_config = copy.deepcopy(FEASIBLE_CONFIG)
    violating_config["forestry"][1]["afforestation_rate"] = 50
    violating_config["organic_soils"][0]["waypoints"] = [{"year": 2030, "rewetting_ratio": 0.5}]
    optigob2 = run_up_to_balancing(violating_config)
    try:
        balancing.validate_land_balance(optigob2.fields, optigob2.baseline_year, optigob2.target_year)
        print("-> did NOT raise (unexpected)")
    except ValueError as e:
        print(f"-> raised, as expected (set LOG_LEVEL = logging.DEBUG at the top of\n"
              f"   this file to see every year's rewetting_claim/afforestation_claim/\n"
              f"   balance leading up to the violating year, not just the summary):\n   {e}")


if __name__ == "__main__":
    main()
