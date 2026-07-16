"""
A runnable, non-pytest example script showing the full OptiGob-ts workflow
end to end, using the full example scenario in
tests/data/full_example/input/config.json (a copy of examples/config.json;
forestry, organic soils, non-cattle agriculture, cattle agriculture, and
anaerobic digestion all present in one run).

Demonstrates the category-based results layer (`Optigob.get_results()` /
`optigob_ts.results.Results`): one DataFrame per kind of output (area, GHG,
protein, biodiversity, energy, hwp, substitution, livestock population,
net-zero), plus quick plots of the same. Input config, and output figures/
excel/logfiles, all live under tests/data/full_example/.

Run from the OptiGob-ts/ directory with:
    poetry run python tests/example.py
"""

import json
import logging
from pathlib import Path

from optigob_ts.optigob import Optigob
from optigob_ts.common.logger import configure_logging, get_logger

DATA_DIR = Path(__file__).resolve().parent / "data" / "full_example"
CONFIG_PATH_NZ = DATA_DIR / "input" / "config.json"
CONFIG_PATH_SPLIT_GAS = DATA_DIR / "input" / "config_split_gas.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "full_example.log"
FIGURES_DIR = DATA_DIR / "output" / "figures"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "full_example.xlsx"

# Categories exposed as both a Results property and a results.plot(...) argument.
CATEGORIES = (
    "area", "ghg", "protein", "biodiversity", "energy", "hwp", "substitution",
    "livestock_population",
)

# The area chart's full column set (forestry, AD, every non-cattle system,
# every organic-soil drainage status...) is too busy to read at a glance --
# restrict it to the two things worth watching in a land-use scenario like
# this one: the cattle (livestock) area itself, and the drained/rewetted
# organic-soil area (excludes "Natural_..." -- Near natural wetlands is
# neither drained nor rewetted, so it's not part of that story).
AREA_COLUMN_PREFIXES = ("Dairy_", "Beef_", "Spared Cattle/Sheep area_", "Drained_", "Rewetted_")


def _area_columns_of_interest(df):
    return [c for c in df.columns if c.startswith(AREA_COLUMN_PREFIXES)]


def _annotate_target_achieved(ax, optigob):
    """Stamp every figure with the one-line answer to "did this scenario hit
    its target" (Optigob.target_achieved()) -- so a chart is self-describing
    without needing to cross-reference the printed console output."""
    ax.text(
        0.02, 0.02, f"Target achieved: {optigob.target_achieved()}",
        transform=ax.transAxes, fontsize="small",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=logging.INFO, log_to_file=str(LOG_PATH))
    logger = get_logger("example")

    with open(CONFIG_PATH_NZ) as f:
        config = json.load(f)

    logger.info("Loaded example nz config: baseline_year=%s target_year=%s",
                config["baseline_year"], config["target_year"])

    # db_file_path=None -> use the bundled default database
    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()

    results = optigob.get_results()
    sample_years = sorted({
        optigob.baseline_year,
        (optigob.baseline_year + optigob.target_year) // 2,
        optigob.target_year,
    })

    for category in CATEGORIES:
        df = getattr(results, category)
        print("#" * 60)
        print(f"{category} -- {df.shape[1]} columns, {len(df)} years (showing {sample_years})")
        print(df.loc[sample_years])

    print("#" * 60)
    print("net_zero -- whole-scenario CO2e (this is the correct cross-field total,")
    print("not a naive sum of the ghg DataFrame's columns -- see results.py's docstring)")
    print(results.net_zero().loc[sample_years])

    print("#" * 60)
    print(f"split_gas={optigob.split_gas} -> check_net_zero_status()={optigob.check_net_zero_status()}")
    print(f"Target achieved: {optigob.target_achieved()}")

    # The cattle dairy/beef split is the part of the model most worth
    # inspecting directly -- see claude-docs/consistency-and-moo.md and
    # claude-docs/cattle-optimisation.md. cattle_systems requires
    # ratio_type/ratio_value now (the heuristic split was removed), so this
    # is always the ratio-constrained LP solve, never a heuristic.
    if optigob.get_field("cattle_systems") is not None:
        print("#" * 60)
        print(f"Cattle dairy/beef split detail (ratio_type={config['cattle_systems']['ratio_type']}, "
              f"ratio_value={config['cattle_systems']['ratio_value']})")
        print(results.livestock_population.loc[sample_years])

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for category in CATEGORIES + ("net_zero",):
        # area carries a handful of baseline columns that never move (e.g.
        # existing forest, non-cattle systems with no area-scaling waypoint)
        # -- dropping them keeps the validation chart to the lines that
        # actually respond to the scenario. ghg's per-system lines span
        # several orders of magnitude (Dairy/Beef vs Poultry/Pigs), so give
        # the small ones their own axis rather than flattening them near zero.
        # area is further restricted to livestock + drained/rewetted soil
        # area (see _area_columns_of_interest) -- the rest is clutter for
        # this scenario's purposes.
        ax = results.plot(
            category,
            dynamic_only=(category == "area"),
            split_by_magnitude=(category in ("ghg", "area")),
            columns=_area_columns_of_interest(results.area) if category == "area" else None,
        )
        _annotate_target_achieved(ax, optigob)
        out_path = FIGURES_DIR / f"{category}.png"
        ax.figure.savefig(out_path)
        print(f"Wrote {out_path}")

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    results.to_excel(EXCEL_PATH)
    print(f"Wrote {EXCEL_PATH}")

    run_ratio_demo(config, logger)

    ## Now re-run with split_gas=True, to show how the same config but with
    ## split_gas=True produces a different set of results (see
    ## claude-docs/consistency-and-moo.md for discussion of the split_gas_frac parameter and its effect on the model).
    with open(CONFIG_PATH_SPLIT_GAS) as f:
        config_split_gas = json.load(f) 

    logger.info("Loaded example split_gas config: baseline_year=%s target_year=%s",
                config_split_gas["baseline_year"], config_split_gas["target_year"])
    
    # db_file_path=None -> use the bundled default database
    optigob = Optigob(json_config=config_split_gas, db_file_path=None)
    optigob.run()

    results = optigob.get_results()

    sample_years = sorted({
        optigob.baseline_year,
        (optigob.baseline_year + optigob.target_year) // 2,
        optigob.target_year,
    })

    print(f"SAMPLE YEARS: {sample_years}")

    for category in CATEGORIES:
        df = getattr(results, category)
        print("#" * 60)
        print(f"{category} -- {df.shape[1]} columns, {len(df)} years (showing {sample_years})")
        print(df.loc[sample_years])

    print("#" * 60)
    print("net_zero -- whole-scenario CO2e (this is the correct cross-field total,")
    print("not a naive sum of the ghg DataFrame's columns -- see results.py's docstring)")
    print(results.net_zero().loc[sample_years])

    print("#" * 60)
    print(f"split_gas={optigob.split_gas} -> check_net_zero_status()={optigob.check_net_zero_status()}")
    print(f"Target achieved: {optigob.target_achieved()}")

    # The cattle dairy/beef split is the part of the model most worth
    # inspecting directly -- see claude-docs/consistency-and-moo.md and
    # claude-docs/cattle-optimisation.md. cattle_systems requires
    # ratio_type/ratio_value now (the heuristic split was removed), so this
    # is always the ratio-constrained LP solve, never a heuristic.
    if optigob.get_field("cattle_systems") is not None:
        print("#" * 60)
        print(f"Cattle dairy/beef split detail (ratio_type={config_split_gas['cattle_systems']['ratio_type']}, "
              f"ratio_value={config_split_gas['cattle_systems']['ratio_value']})")
        print(results.livestock_population.loc[sample_years])

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for category in CATEGORIES + ("net_zero",):
        # area carries a handful of baseline columns that never move (e.g.
        # existing forest, non-cattle systems with no area-scaling waypoint)
        # -- dropping them keeps the validation chart to the lines that
        # actually respond to the scenario. ghg's per-system lines span
        # several orders of magnitude (Dairy/Beef vs Poultry/Pigs), so give
        # the small ones their own axis rather than flattening them near zero.
        # area is further restricted to livestock + drained/rewetted soil
        # area (see _area_columns_of_interest) -- the rest is clutter for
        # this scenario's purposes.
        ax = results.plot(
            category,
            dynamic_only=(category == "area"),
            split_by_magnitude=(category in ("ghg", "area")),
            columns=_area_columns_of_interest(results.area) if category == "area" else None,
        )
        _annotate_target_achieved(ax, optigob)
        out_path = FIGURES_DIR / f"{category}-split-gas.png"
        ax.figure.savefig(out_path)
        print(f"Wrote {out_path}")

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    results.to_excel(EXCEL_PATH)
    print(f"Wrote {EXCEL_PATH}")

    run_ratio_demo(config_split_gas, logger)

        


def run_ratio_demo(base_config, logger):
    """
    Same scenario as main(), but with a different ratio_value (5.0 instead
    of config.json's 2.0) on cattle_systems, to show how changing that one
    number reshapes the whole dairy/beef split -- see
    claude-docs/cattle-optimisation.md and claude-docs/consistency-and-moo.md.
    """
    import copy
    config = copy.deepcopy(base_config)
    config["cattle_systems"]["ratio_type"] = "dairy_per_beef"
    config["cattle_systems"]["ratio_value"] = 5.0

    logger.info("Re-running with ratio_type=dairy_per_beef, ratio_value=5.0 on cattle_systems")

    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()
    results = optigob.get_results()
    sample_years = sorted({optigob.baseline_year, (optigob.baseline_year + optigob.target_year) // 2, optigob.target_year})

    print("#" * 60)
    print("Cattle dairy/beef split detail WITH ratio_type=dairy_per_beef, ratio_value=5.0")
    print("(compare against the ratio_value=2.0 table above)")
    print(results.livestock_population.loc[sample_years])


if __name__ == "__main__":
    main()
