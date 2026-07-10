"""
Cattle production walkthrough, start to finish, using the opt-in ratio-based
livestock optimiser (see src/optigob_ts/systems/livestock_optimisation.py).

This is a plain runnable script, not a pytest test file (no assertions) --
it's meant to be read top to bottom alongside its printed output to see how
a cattle scenario actually plays out year by year. Run it with:

    poetry run python tests/cattle_example_test.py

--------------------------------------------------------------------------
THE SCENARIO (tests/data/cattle/input/cattle_example.json, a copy of
examples/cattle_example.json)
--------------------------------------------------------------------------
baseline_year=2020, target_year=2050. One trivial non_cattle_agriculture
system (Pigs, held flat) is included only because run_cattle_systems()'s
budget math always subtracts non-cattle's contribution from the combined
emissions budget -- cattle waypoints cannot be run in total isolation (see
claude-docs/optigob-ts-full-guide.md, cattle_agriculture.py section).

Two cattle waypoints:
  - 2030: scaler=0.8 -> combined (dairy+beef+pigs) co2e must be <= 80% of
    the 2020 baseline. ratio_type="dairy_per_beef", ratio_value=5.0
    -> dairy must be ~5x beef within that budget.
  - 2050: scaler=0.6 -> combined co2e must be <= 60% of baseline. The ratio
    FLIPS: ratio_type="beef_per_dairy", ratio_value=5.0 -> beef must now
    be ~5x dairy. This demonstrates that ratio_type/ratio_value are
    per-waypoint overrides, not a single fixed setting for the whole run --
    each waypoint independently re-solves the LP with its own ratio.

Both scalers are percentages OF THE SAME ORIGINAL 2020 BASELINE, not of
each other (see claude-docs/optigob-ts-full-guide.md section 4) -- 0.8 then
0.6 is a genuinely deepening reduction (80% of baseline, then 60% of
baseline), which is why this scenario is safe from the "bounce" problem
covered in that doc.

--------------------------------------------------------------------------
WHAT TO WATCH FOR IN THE OUTPUT
--------------------------------------------------------------------------
1. At 2030, the realized dairy:beef ratio (by cattle numbers) will be CLOSE
   to but not exactly 5.0. This is expected, not a bug: the ratio_value
   constrains the optimiser's internal dairy_scaler/beef_scaler exactly --
   any one derived field (like cattle numbers) only matches that ratio as
   closely as the Dairy and Beef reference DB rows happen to agree in
   composition. See claude-docs/consistency-and-moo.md for the full proof.
2. At 2040 (a year with NO waypoint of its own), the result is NOT a
   straight-line interpolation between 2030 and 2050 -- the ratio branch
   re-solves the LP independently for every year, not just at waypoints
   (see claude-docs/cattle-example-walkthrough.md's land-balance addendum).
   Every year in the 2030->2050 segment uses 2050's own ratio
   (beef_per_dairy, 5.0) applied to that year's own interpolated emissions
   limit and REAL (non-interpolated) area_commitment -- so 2040 is already
   close to 2050's beef-heavy composition, not halfway back through parity.
   The only thing that's still linearly interpolated between waypoints is
   the *emissions limit* itself (baseline*scaler has no other defined value
   between two named waypoints); area_commitment and the ratio are both
   resolved fresh, every year.
3. The combined co2e (dairy+beef+pigs) hits *exactly* 80% / 60% of baseline
   at 2030/2050 -- the optimiser always satisfies the emissions constraint
   with equality when maximising herd size, since more budget always means
   more animals under this objective. This is also true at every
   intermediate year now, relative to that year's own interpolated limit
   (whenever area isn't the tighter constraint that year).
"""

import json
from pathlib import Path

from optigob_ts.optigob import Optigob
from optigob_ts.common.logger import configure_logging, get_logger
import logging

DATA_DIR = Path(__file__).resolve().parent / "data" / "cattle"
CONFIG_PATH = DATA_DIR / "input" / "cattle_example.json"
LOG_PATH = DATA_DIR / "output" / "logs" / "cattle.log"
FIGURE_PATH = DATA_DIR / "output" / "figures" / "cattle.png"
EXCEL_PATH = DATA_DIR / "output" / "excel" / "cattle.xlsx"


def main():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("")  # truncate -- fresh log per run, not an ever-growing append
    configure_logging(level=logging.WARNING, log_to_file=str(LOG_PATH))  # keep console output focused on the walkthrough
    logger = get_logger("cattle_example")

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()

    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    pigs = optigob.get_field("non_cattle_agriculture").get_system("Pigs")
    spared = optigob.get_field("cattle_systems").get_system("Spared Cattle/Sheep area")

    years = [2020, 2030, 2040, 2050]

    print("=" * 70)
    print("CATTLE PRODUCTION WALKTHROUGH: 2020 (baseline) -> 2050 (target)")
    print("=" * 70)

    print("""
2020: BASELINE
------------------------------------------------------------------
No waypoint has fired yet -- these are the raw baseline numbers the
whole scenario is measured against.
""")
    i = 0
    baseline_combined_co2e = dairy.time_series["co2e"][i] + beef.time_series["co2e"][i] + pigs.time_series["co2e"][i]
    print(f"  Dairy CO2e:            {dairy.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Beef CO2e:             {beef.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Pigs CO2e:             {pigs.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Combined CO2e:         {baseline_combined_co2e:>14,.1f} kt")
    print(f"  Dairy cattle numbers:  {dairy.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  Beef cattle numbers:   {beef.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  Baseline dairy:beef ratio (by numbers): {dairy.time_series['total_cattle_numbers'][i] / beef.time_series['total_cattle_numbers'][i]:.2f} : 1")
    print(f"  Dairy protein (milk):  {dairy.time_series['protein_milk'][i]:>18,.0f}")
    print(f"  Beef protein (beef):   {beef.time_series['protein_beef'][i]:>18,.0f}")

    print("""
2030: FIRST WAYPOINT -- scaler=0.8, ratio_type=dairy_per_beef, ratio_value=5.0
------------------------------------------------------------------
Target: combined (dairy+beef+pigs) co2e <= 80% of the 2020 baseline.
Within that budget, the optimiser must find dairy/beef scalers such that
dairy_scaler = 5.0 x beef_scaler exactly (that ratio is exact -- it's the
LP's actual constraint). Expect dairy to grow in relative share and beef
to shrink sharply to make room for that 5:1 skew.
""")
    i = 2030 - 2020
    combined = dairy.time_series["co2e"][i] + beef.time_series["co2e"][i] + pigs.time_series["co2e"][i]
    print(f"  Dairy CO2e:            {dairy.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Beef CO2e:             {beef.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Combined CO2e:         {combined:>14,.1f} kt   (target was {0.8 * baseline_combined_co2e:,.1f} kt = 80% of baseline)")
    print(f"  Dairy cattle numbers:  {dairy.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  Beef cattle numbers:   {beef.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  Realized dairy:beef ratio (by numbers): {dairy.time_series['total_cattle_numbers'][i] / beef.time_series['total_cattle_numbers'][i]:.2f} : 1   (target was 5.00 : 1 -- close but not exact, see note 1 above)")
    print(f"  Dairy protein (milk):  {dairy.time_series['protein_milk'][i]:>18,.0f}")
    print(f"  Beef protein (beef):   {beef.time_series['protein_beef'][i]:>18,.0f}")
    print(f"  Spared area so far:    {spared.time_series['area'][i]:>14,.1f} ha")

    print("""
2040: MID-TRANSITION (no waypoint here -- but still independently re-solved)
------------------------------------------------------------------
There is no waypoint at 2040, but the ratio branch solves every year fresh
(see note 2 above) -- 2040 already uses 2050's beef_per_dairy ratio against
its own interpolated budget, so it's already beef-heavy here, not halfway
back through parity like a naive interpolation would suggest.
""")
    i = 2040 - 2020
    print(f"  Dairy CO2e:            {dairy.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Beef CO2e:             {beef.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Dairy cattle numbers:  {dairy.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  Beef cattle numbers:   {beef.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  dairy:beef ratio (by numbers): {dairy.time_series['total_cattle_numbers'][i] / beef.time_series['total_cattle_numbers'][i]:.2f} : 1   (independently solved, not interpolated -- see note 2 above)")
    print(f"  Dairy protein (milk):  {dairy.time_series['protein_milk'][i]:>18,.0f}")
    print(f"  Beef protein (beef):   {beef.time_series['protein_beef'][i]:>18,.0f}")

    print("""
2050: SECOND WAYPOINT -- scaler=0.6, ratio_type=beef_per_dairy, ratio_value=5.0
------------------------------------------------------------------
Target: combined co2e <= 60% of the 2020 baseline (a deeper cut than 2030 --
0.6 < 0.8, so this is a genuine further reduction, not a rebound). The
ratio has flipped: beef must now be 5.0 x dairy exactly.
""")
    i = 2050 - 2020
    combined = dairy.time_series["co2e"][i] + beef.time_series["co2e"][i] + pigs.time_series["co2e"][i]
    print(f"  Dairy CO2e:            {dairy.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Beef CO2e:             {beef.time_series['co2e'][i]:>14,.1f} kt")
    print(f"  Combined CO2e:         {combined:>14,.1f} kt   (target was {0.6 * baseline_combined_co2e:,.1f} kt = 60% of baseline)")
    print(f"  Dairy cattle numbers:  {dairy.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  Beef cattle numbers:   {beef.time_series['total_cattle_numbers'][i]:>14,.0f} head")
    print(f"  Realized beef:dairy ratio (by numbers): {beef.time_series['total_cattle_numbers'][i] / dairy.time_series['total_cattle_numbers'][i]:.2f} : 1   (target was 5.00 : 1)")
    print(f"  Dairy protein (milk):  {dairy.time_series['protein_milk'][i]:>18,.0f}")
    print(f"  Beef protein (beef):   {beef.time_series['protein_beef'][i]:>18,.0f}")
    print(f"  Spared area so far:    {spared.time_series['area'][i]:>14,.1f} ha")

    print("""
------------------------------------------------------------------
SUMMARY: 2020 -> 2030 -> 2050
------------------------------------------------------------------
Total herd (dairy + beef) at each point, and how the composition inverted:
""")
    rows = []
    for y in years:
        i = y - 2020
        dn = dairy.time_series["total_cattle_numbers"][i]
        bn = beef.time_series["total_cattle_numbers"][i]
        print(f"  {y}: total herd = {dn + bn:>12,.0f} head   (dairy {dn:>12,.0f} / beef {bn:>12,.0f}, ratio {dn / bn:.2f}:1)")
        rows.append({"year": y, "dairy_total_cattle_numbers": dn, "beef_total_cattle_numbers": bn,
                     "total_herd": dn + bn, "dairy_over_beef": dn / bn})

    save_outputs(rows)


def save_outputs(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    df = pd.DataFrame(rows)

    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df["year"], df["dairy_total_cattle_numbers"], marker="o", label="Dairy")
    ax.plot(df["year"], df["beef_total_cattle_numbers"], marker="o", label="Beef")
    ax.set_xlabel("year")
    ax.set_ylabel("total_cattle_numbers")
    ax.set_title("Cattle numbers: composition inverts as the ratio flips")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_PATH, dpi=120)
    plt.close(fig)
    print(f"\nFigure saved to {FIGURE_PATH}")

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(EXCEL_PATH, index=False)
    print(f"Excel saved to {EXCEL_PATH}")


if __name__ == "__main__":
    main()
