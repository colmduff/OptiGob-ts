"""
Step-by-step walkthrough confirming the ratio-constrained cattle optimiser
actually enforces the dairy:beef ratio it's configured with -- the same
"watch it actually run" companion pattern as `land_balance_example_test.py`,
applied to `systems/livestock_optimisation.py` / `cattle_agriculture.py`
instead of `balancing.py`.

Uses `tests/data/cattle_ratio/input/cattle_example.json` (a copy of
`examples/cattle_example.json`): dairy_per_beef 5:1 at 2030, then the
ratio FLIPS to beef_per_dairy 5:1 at 2050 (see `tests/cattle_example_test.py`
for the full narrative of this scenario). A flipping ratio is a strong
confirmation case -- if the LP's ratio constraint weren't actually binding,
flipping ratio_type wouldn't visibly change anything.

Two kinds of confirmation here, deliberately kept separate:

1. **Internal, via logging**: `LivestockOptimisation.optimise()` and
   `CattleAgriculture.run_cattle_systems()` now log their own inputs/outputs
   (added specifically so these modules are inspectable without external
   instrumentation -- same as `balancing.py`). INFO shows, every year, the
   solved dairy_scaler/beef_scaler, the *achieved* ratio computed from them,
   and how much of the area/emissions constraints were actually used.
2. **External, independent reconstruction**: this script separately
   re-fetches the same DB reference rows `CattleWayPoint.get_data()` used,
   and independently recomputes dairy_scaler/beef_scaler from the *output*
   time_series (`dairy_scaler = dairy.time_series["co2e"][idx] /
   dairy_reference_row["co2e"]`, exact because `update_time_series` applies
   the scaler to every numeric field identically, every year, in this
   per-year-solve branch). This doesn't just trust the log line -- it proves
   the same number two different ways.

It also explicitly shows what does *not* match `ratio_value` exactly:
`total_cattle_numbers` (a derived, composition-dependent field) is close to
but not exactly 5:1, because the LP's ratio constraint is on the *scalers*,
not on any one derived output -- see `claude-docs/consistency-and-moo.md`
§1 for the proof of this distinction ("realized dairy:beef ratio... close
but not exact, expected, not a bug").

Input config, and output figures/excel/logfiles, all live under
`tests/data/cattle_ratio/` (`input/cattle_example.json`,
`output/{figures,excel,logs}/`).

Run with:
    poetry run python tests/cattle_ratio_example_test.py
"""

import json
import logging
from pathlib import Path

from optigob_ts.optigob import Optigob
from optigob_ts.common.logger import configure_logging, get_logger
from optigob_ts.common.gwp import recompute_co2e

logger = get_logger("cattle_ratio_example")

# Bump to logging.DEBUG for the full per-year context alongside the
# per-year ratio confirmation (year_budget/area_commitment feeding each solve).
LOG_LEVEL = logging.INFO

DATA_DIR = Path(__file__).resolve().parent / "data" / "cattle_ratio"
CONFIG_PATH = DATA_DIR / "input" / "cattle_example.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "cattle_ratio.log"
FIGURE_PATH = DATA_DIR / "output" / "figures" / "cattle_ratio.png"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "cattle_ratio.xlsx"


def reconstruct_scalers(optigob, year):
    """Independently re-derives dairy_scaler/beef_scaler at `year` by
    re-fetching the same DB reference rows CattleWayPoint.get_data() used
    (both of cattle_example.json's waypoints share the same abatement/
    productivity settings, so one fetch covers the whole run) and dividing
    the actual output co2e by that reference row's co2e -- independent of,
    and a cross-check against, the LivestockOptimisation.optimise() log
    line for the same year.
    """
    dairy_ref = optigob.db_manager.get_agriculture_data(
        abatement="2020 BL", productivity="2020 Prod", system="Dairy", agriculture="cattle")
    beef_ref = optigob.db_manager.get_agriculture_data(
        abatement="2020 BL", productivity="2020 Prod", system="Beef", agriculture="cattle")
    recompute_co2e(dairy_ref, optigob.gwp)
    recompute_co2e(beef_ref, optigob.gwp)

    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    idx = year - optigob.baseline_year

    dairy_scaler = dairy.time_series["co2e"][idx] / dairy_ref["co2e"]
    beef_scaler = beef.time_series["co2e"][idx] / beef_ref["co2e"]
    return dairy_scaler, beef_scaler


def check_ratio(optigob, year, ratio_type, ratio_value):
    dairy_scaler, beef_scaler = reconstruct_scalers(optigob, year)
    if ratio_type == "dairy_per_beef":
        achieved = dairy_scaler / beef_scaler
    else:
        achieved = beef_scaler / dairy_scaler

    ok = abs(achieved - ratio_value) < 1e-6
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] year={year} {ratio_type}: dairy_scaler={dairy_scaler:.6f} "
          f"beef_scaler={beef_scaler:.6f} achieved={achieved:.6f} vs configured={ratio_value}")
    row = {"year": year, "ratio_type": ratio_type, "dairy_scaler": dairy_scaler,
           "beef_scaler": beef_scaler, "achieved_ratio": achieved, "configured_ratio_value": ratio_value,
           "status": status}
    return ok, row


def herd_numbers(optigob, years):
    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    print("  (contrast: total_cattle_numbers is NOT forced to exactly 5:1 -- it's a")
    print("   derived field, only as close to the ratio as the reference rows agree)")
    rows = []
    for y in years:
        idx = y - optigob.baseline_year
        dn = dairy.time_series["total_cattle_numbers"][idx]
        bn = beef.time_series["total_cattle_numbers"][idx]
        print(f"    {y}: dairy={dn:>14,.0f}  beef={bn:>14,.0f}  dairy/beef={dn / bn:.3f}")
        rows.append({"year": y, "dairy_total_cattle_numbers": dn, "beef_total_cattle_numbers": bn,
                     "dairy_over_beef": dn / bn})
    return rows


def save_outputs(ratio_rows, herd_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    ratio_df = pd.DataFrame(ratio_rows)
    herd_df = pd.DataFrame(herd_rows)

    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(ratio_df["year"], ratio_df["achieved_ratio"], marker="o", label="achieved (scaler-based)")
    ax1.axhline(ratio_rows[0]["configured_ratio_value"], color="grey", linestyle="--", label="configured ratio_value")
    ax1.set_title("Scaler ratio: exact")
    ax1.set_xlabel("year")
    ax1.legend()
    ax2.plot(herd_df["year"], herd_df["dairy_over_beef"], marker="o", color="tab:orange")
    ax2.set_title("total_cattle_numbers ratio: close, not exact")
    ax2.set_xlabel("year")
    fig.tight_layout()
    fig.savefig(FIGURE_PATH, dpi=120)
    plt.close(fig)
    print(f"\nFigure saved to {FIGURE_PATH}")

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(EXCEL_PATH) as writer:
        ratio_df.to_excel(writer, sheet_name="scaler_ratio_check", index=False)
        herd_df.to_excel(writer, sheet_name="herd_numbers", index=False)
    print(f"Excel saved to {EXCEL_PATH}")


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=LOG_LEVEL, log_to_file=str(LOG_PATH))

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    print("#" * 70)
    print("Running cattle_example.json (dairy_per_beef 5:1 @ 2030,")
    print("beef_per_dairy 5:1 @ 2050) -- watch the INFO log lines below: every")
    print("year, LivestockOptimisation.optimise() reports the achieved ratio")
    print("it just solved for, compared against the configured ratio_value.")
    print("#" * 70)
    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()

    print("\n" + "#" * 70)
    print("INDEPENDENT CHECK: re-fetch the DB reference rows ourselves and")
    print("recompute dairy_scaler/beef_scaler from the output time_series,")
    print("without relying on the log line above")
    print("#" * 70)
    all_ok = True
    ratio_rows = []
    # Within the 2030 segment (2021-2030), ratio_type=dairy_per_beef.
    for year in [2021, 2025, 2030]:
        ok, row = check_ratio(optigob, year, "dairy_per_beef", 5.0)
        all_ok &= ok
        ratio_rows.append(row)
    # Within the 2050 segment (2031-2050), ratio_type flips to beef_per_dairy.
    for year in [2031, 2040, 2050]:
        ok, row = check_ratio(optigob, year, "beef_per_dairy", 5.0)
        all_ok &= ok
        ratio_rows.append(row)

    print(f"\n-> {'ALL YEARS MATCHED configured ratio_value exactly' if all_ok else 'MISMATCH FOUND -- see above'}")

    print("\n" + "#" * 70)
    print("Herd numbers over the same years -- qualitatively flips, but not")
    print("forced to exactly 5:1 (see module docstring)")
    print("#" * 70)
    herd_rows = herd_numbers(optigob, [2020, 2030, 2040, 2050])

    save_outputs(ratio_rows, herd_rows)


if __name__ == "__main__":
    main()
