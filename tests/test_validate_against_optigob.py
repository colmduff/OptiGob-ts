"""
Cross-validate OptiGob-ts's baseline-year area/GHG figures against `optigob`
(OptiGob/), an independent, mature, pip-installable package computing the
same real-world Irish AFOLU baseline via a different model (single-target-
year SIP rather than waypoints) and a different bundled database. This is a
national-plausibility sanity check, not an equivalence test -- the two
packages decompose sectors differently (OptiGob combines Pigs+Poultry and
combines Industrial+Domestic peat into one "wetland" bucket; OptiGob-ts
splits every one of those out, plus adds a synthetic `No-Crops` sibling
system with no OptiGob equivalent) and calibrate cattle baselines via
different mechanisms (OptiGob-ts bakes in a DB `scalers`-table multiplier;
OptiGob scales DB per-head reference rates by a SIP-supplied population).
Comparisons are therefore made at sector-total granularity with a generous
tolerance, loose enough to only catch gross errors (unit bugs, double
counting, wrong scaling).

Layout (self-contained data folder, mirroring tests/data/full_example/):
    tests/data/validation/
        input/optigob_sip.json          -- the OptiGob reference SIP
        input/optigob_ts_config.json    -- the OptiGob-ts scenario config (copy of full_example)
        output/comparison.csv           -- per-sector TS-vs-OptiGob table (written by the artifact test)
        output/comparison.xlsx          -- same, plus a per-category sheet
        output/figures/area_comparison.png
        output/figures/ghg_comparison.png

Both sides' inputs live in input/ so the comparison is fully reproducible from
this one folder. The OptiGob-ts config is a copy of the shared full-example
scenario; only its baseline year is read. See
claude-docs/baseline-validation-report.md for a written analysis of where the
residual differences come from.

Requires the `optigob` dev dependency (added to pyproject.toml); skipped if
not installed.

Run:  poetry run pytest tests/test_validate_against_optigob.py -v -s
"""
import json
from pathlib import Path

import pytest

from optigob_ts.optigob import Optigob

pytest.importorskip("optigob")
from optigob.resource_manager.optigob_data_manager import OptiGobDataManager
from optigob.livestock.baseline_livestock import BaselineLivestock
from optigob.static_ag.baseline_static_ag import BaselineStaticAg
from optigob.forest.baseline_forest import BaselineForest
from optigob.other_land.baseline_other_land import BaselineOtherLand

TESTS_DIR = Path(__file__).resolve().parent

VALIDATION_DIR = TESTS_DIR / "data" / "validation"
OPTIGOB_SIP_PATH = VALIDATION_DIR / "input" / "optigob_sip.json"
OPTIGOB_TS_CONFIG_PATH = VALIDATION_DIR / "input" / "optigob_ts_config.json"
OUTPUT_DIR = VALIDATION_DIR / "output"
FIGURES_DIR = OUTPUT_DIR / "figures"

# OptiGob's BaselineForest hardcodes harvest_rate="low" (no SIP field changes
# it). The full_example config's existing_forest entry uses "high", which
# alone would give a ~7x GHG mismatch -- a scenario-assumption difference, not
# a data bug. A dedicated low-harvest, forestry-only OptiGob-ts run gives a
# fair apples-to-apples forestry comparison. OptiGob's static-forest table has
# no `ccs` dimension; `ccs=True` here just matches the full_example config.
FORESTRY_ONLY_CONFIG = {
    "baseline_year": 2020,
    "target_year": 2021,
    "forestry": [{"name": "existing_forest", "harvest": "low", "ccs": True}],
}

ORGANIC_SOILS_GHG_LABELS = [
    "Drained_Organic soil under grass", "Rewetted_Organic soil under grass",
    "Drained_Industrial peat", "Rewetted_Industrial peat",
    "Drained_Domestic peat", "Rewetted_Domestic peat",
    "Natural_Near natural wetlands",
]

# The generous band used by every sector comparison: loose enough to pass
# through the known benign differences (herd calibration, per-animal emission
# factors, GWP-basis of pre-aggregated columns), tight enough to catch a
# genuine gross error (a units bug is typically a factor of 1000).
REL_TOL = 0.5


def _run_baseline(config):
    optigob = Optigob(json_config=config, db_file_path=None)
    optigob.run()
    results = optigob.get_results()
    return results.area.loc[optigob.baseline_year], results.ghg.loc[optigob.baseline_year]


def _build_comparisons():
    """Compute every (sector, metric) TS-vs-OptiGob pair once. Returns a list
    of dict rows, each with sector/category/ts/og/unit -- consumed by both the
    per-sector assertions and the artifact (CSV/xlsx/figure) generation, so
    the numbers behind the report and the numbers behind the assertions can't
    drift apart."""
    ts_area, ts_ghg = _run_baseline(json.loads(OPTIGOB_TS_CONFIG_PATH.read_text()))
    ts_forest_area, ts_forest_ghg = _run_baseline(FORESTRY_ONLY_CONFIG)

    dm = OptiGobDataManager(json.loads(OPTIGOB_SIP_PATH.read_text()))
    lv = BaselineLivestock(dm)
    sa = BaselineStaticAg(dm)
    fo = BaselineForest(dm)
    ol = BaselineOtherLand(dm)

    rows = [
        {"sector": "Cattle", "category": "area", "unit": "ha",
         "ts": ts_area["total_cattle_systems"],
         "og": lv.get_total_area()},
        {"sector": "Cattle", "category": "ghg", "unit": "kt CO2e",
         "ts": ts_ghg["total_cattle_systems"],
         "og": lv.get_total_co2e_emission()},
        # No-Crops is a synthetic OptiGob-ts sibling system with no OptiGob
        # equivalent -- excluded from both metrics.
        {"sector": "Non-cattle ag", "category": "area", "unit": "ha",
         "ts": ts_area["total_non_cattle_agriculture"] - ts_area["No-Crops_area"],
         "og": sa.get_total_static_ag_area()},
        {"sector": "Non-cattle ag", "category": "ghg", "unit": "kt CO2e",
         "ts": ts_ghg["total_non_cattle_agriculture"] - ts_ghg["No-Crops"],
         "og": sa.get_total_static_ag_co2e()},
        # existing_forest_area only -- total_forestry also adds
        # existing_forest_organic_soil_area, a subset of it (see bugs.md #7).
        {"sector": "Forestry", "category": "area", "unit": "ha",
         "ts": ts_forest_area["existing_forest_area"],
         "og": fo.get_managed_forest_area()},
        {"sector": "Forestry", "category": "ghg", "unit": "kt CO2e",
         "ts": ts_forest_ghg["existing_forest"],
         "og": fo.get_total_forest_offset()},
        {"sector": "Organic soil under grass", "category": "area", "unit": "ha",
         "ts": ts_area["Drained_Organic soil under grass"] + ts_area["Rewetted_Organic soil under grass"],
         "og": ol.get_drained_organic_soil_area() + ol.get_rewetted_organic_area()},
        {"sector": "Wetland (peat + natural)", "category": "area", "unit": "ha",
         "ts": (ts_area["Drained_Industrial peat"] + ts_area["Rewetted_Industrial peat"]
                + ts_area["Drained_Domestic peat"] + ts_area["Rewetted_Domestic peat"]
                + ts_area["Natural_Near natural wetlands"]),
         "og": (ol.get_drained_wetland_area() + ol.get_rewetted_wetland_area()
                + ol.get_near_natural_wetland_area())},
        {"sector": "Organic soil + wetland", "category": "ghg", "unit": "kt CO2e",
         "ts": sum(ts_ghg[label] for label in ORGANIC_SOILS_GHG_LABELS),
         "og": ol.get_wetland_restoration_emission_co2e()},
    ]
    for row in rows:
        row["rel_diff"] = abs(row["ts"] - row["og"]) / abs(row["og"]) if row["og"] else 0.0
    return rows, ts_area, ts_ghg


@pytest.fixture(scope="module")
def comparison_data():
    rows, ts_area, ts_ghg = _build_comparisons()
    return {"rows": rows, "ts_area": ts_area, "ts_ghg": ts_ghg}


@pytest.mark.parametrize("sector,category", [
    ("Cattle", "area"), ("Cattle", "ghg"),
    ("Non-cattle ag", "area"), ("Non-cattle ag", "ghg"),
    ("Forestry", "area"), ("Forestry", "ghg"),
    ("Organic soil under grass", "area"),
    ("Wetland (peat + natural)", "area"),
    ("Organic soil + wetland", "ghg"),
])
def test_sector_within_tolerance(comparison_data, sector, category):
    row = next(r for r in comparison_data["rows"] if r["sector"] == sector and r["category"] == category)
    print(f"{sector} {category}: optigob-ts={row['ts']:,.1f}  optigob={row['og']:,.1f}  "
          f"rel_diff={row['rel_diff']:.1%}")
    assert row["rel_diff"] <= REL_TOL, (
        f"{sector} {category}: optigob-ts={row['ts']:,.1f} vs optigob={row['og']:,.1f} "
        f"differ by {row['rel_diff']:.1%}, exceeding {REL_TOL:.0%} tolerance"
    )


def test_ad_area_and_ghg_are_zero_at_baseline(comparison_data):
    # OptiGob has no baseline AD/bioenergy module at all -- always 0. This
    # example config's AD implementation_year/etc. are all after baseline_year
    # too, so both sides agree exactly.
    area, ghg = comparison_data["ts_area"], comparison_data["ts_ghg"]
    assert area["total_ad"] == 0
    assert ghg["ad_emissions"] == 0


def test_total_agricultural_area_matches_national_scale(comparison_data):
    """Independent sanity anchor: OptiGob-ts's own baseline cattle +
    non-cattle agriculture area should be in the right ballpark for Ireland's
    actual national agricultural area (~4.5M ha), regardless of the OptiGob
    comparison -- catches the class of gross error (units, double counting)
    that originally prompted this validation."""
    area = comparison_data["ts_area"]
    total = area["total_cattle_systems"] + area["total_non_cattle_agriculture"]
    assert 3_000_000 < total < 6_000_000, (
        f"Total agricultural area {total:,.0f} ha is implausible for Ireland's national scale"
    )


def test_generate_validation_artifacts(comparison_data):
    """Write the comparison table (CSV + xlsx) and the two comparison bar
    charts into tests/data/validation/output/. This is the source of the
    figures referenced by claude-docs/baseline-validation-report.md; running
    the test suite regenerates them."""
    import pandas as pd

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(comparison_data["rows"])[["sector", "category", "unit", "ts", "og", "rel_diff"]]
    df = df.rename(columns={"ts": "optigob_ts", "og": "optigob"})
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    try:
        with pd.ExcelWriter(OUTPUT_DIR / "comparison.xlsx", engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="all", index=False)
            for cat in ("area", "ghg"):
                df[df["category"] == cat].to_excel(writer, sheet_name=cat, index=False)
    except ModuleNotFoundError:
        pass  # openpyxl is an optional extra; CSV + figures still written

    _plot_category(df, "area", "Baseline land area: OptiGob-ts vs OptiGob (ha)",
                   FIGURES_DIR / "area_comparison.png")
    _plot_category(df, "ghg", "Baseline GHG: OptiGob-ts vs OptiGob (kt CO2e)",
                   FIGURES_DIR / "ghg_comparison.png")

    assert (OUTPUT_DIR / "comparison.csv").exists()
    assert (FIGURES_DIR / "area_comparison.png").exists()
    assert (FIGURES_DIR / "ghg_comparison.png").exists()


def _plot_category(df, category, title, out_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
    except ModuleNotFoundError:
        return  # matplotlib is an optional extra

    import numpy as np

    sub = df[df["category"] == category].reset_index(drop=True)
    x = np.arange(len(sub))
    width = 0.38

    fig, ax = plt.subplots(figsize=(10, 6))
    bars_ts = ax.bar(x - width / 2, sub["optigob_ts"], width, label="OptiGob-ts")
    bars_og = ax.bar(x + width / 2, sub["optigob"], width, label="OptiGob")

    ax.set_ylabel(sub["unit"].iloc[0])
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(sub["sector"], rotation=20, ha="right", fontsize="small")
    ax.legend()

    # Annotate each pair with its relative difference so the chart is
    # self-describing without cross-referencing the CSV.
    for i, rel in enumerate(sub["rel_diff"]):
        top = max(sub["optigob_ts"].iloc[i], sub["optigob"].iloc[i])
        ax.annotate(f"{rel:.1%}", (i, top), textcoords="offset points",
                    xytext=(0, 4), ha="center", fontsize="small")

    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
