import os
import pytest

from optigob_ts.systems.livestock_optimisation import LivestockOptimisation
from optigob_ts.optigob import Optigob

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")


# --- Unit tests directly against the LP, isolated from the DB and the rest
# --- of the model -- these pin down the actual invariant the optimiser is
# --- supposed to guarantee (the *scaler* ratio, not any one derived output
# --- field -- see claude-docs/consistency-and-moo.md for why the ratio
# --- constrains the scalers, and derived fields like population only end up
# --- close to, not exactly at, ratio_value when the two reference rows
# --- differ in composition).

def test_optimise_emissions_binding():
    dairy_waypoint_data = {"co2e": 10.0, "area_dairy": 5.0, "area_beef": 2.0}
    beef_waypoint_data = {"co2e": 5.0, "area_dairy": 0.0, "area_beef": 8.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2e",
        ratio_type="dairy_per_beef",
        ratio_value=3.0,
        emissions_budget=100.0,
        area_commitment=10000.0,  # generous -- emissions constraint binds instead
    )

    assert result.feasible
    assert round(result["dairy_scaler"] / result["beef_scaler"], 6) == 3.0
    assert round(result["beef_scaler"], 6) == round(100.0 / 35.0, 6)
    assert round(result["dairy_scaler"], 6) == round(300.0 / 35.0, 6)


def test_optimise_area_binding():
    dairy_waypoint_data = {"co2e": 1.0, "area_dairy": 5.0, "area_beef": 2.0}
    beef_waypoint_data = {"co2e": 1.0, "area_dairy": 0.0, "area_beef": 8.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2e",
        ratio_type="dairy_per_beef",
        ratio_value=2.0,
        emissions_budget=10000.0,  # generous -- area constraint binds instead
        area_commitment=50.0,
    )

    assert result.feasible
    assert round(result["dairy_scaler"] / result["beef_scaler"], 6) == 2.0
    assert round(result["beef_scaler"], 6) == round(50.0 / 22.0, 6)
    assert round(result["dairy_scaler"], 6) == round(100.0 / 22.0, 6)


def test_optimise_beef_per_dairy_ratio_type():
    dairy_waypoint_data = {"co2e": 1.0, "area_dairy": 1.0, "area_beef": 1.0}
    beef_waypoint_data = {"co2e": 1.0, "area_dairy": 0.0, "area_beef": 1.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2e",
        ratio_type="beef_per_dairy",
        ratio_value=4.0,
        emissions_budget=100.0,
        area_commitment=10000.0,
    )

    assert result.feasible
    assert round(result["beef_scaler"] / result["dairy_scaler"], 6) == 4.0


def test_optimise_invalid_ratio_type_raises():
    with pytest.raises(ValueError):
        LivestockOptimisation().optimise(
            dairy_waypoint_data={"co2e": 1.0, "area_dairy": 1.0, "area_beef": 1.0},
            beef_waypoint_data={"co2e": 1.0, "area_dairy": 0.0, "area_beef": 1.0},
            scale_parameter="co2e",
            ratio_type="not_a_real_ratio_type",
            ratio_value=1.0,
            emissions_budget=100.0,
            area_commitment=100.0,
        )


def test_optimise_ch4_budget_binding():
    """When ch4_budget is passed, it must be enforced as a real constraint --
    not just a number reported after the fact. Generous co2_n2o_co2e/area
    budgets, tight ch4_budget: the ratio must still hold, and CH4 usage must
    saturate the budget (proving the constraint actually binds)."""
    dairy_waypoint_data = {"co2_n2o_co2e": 1.0, "ch4": 2.0, "area_dairy": 1.0, "area_beef": 1.0}
    beef_waypoint_data = {"co2_n2o_co2e": 1.0, "ch4": 1.0, "area_dairy": 0.0, "area_beef": 1.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2_n2o_co2e",
        ratio_type="dairy_per_beef",
        ratio_value=2.0,
        emissions_budget=10000.0,
        area_commitment=10000.0,
        ch4_budget=10.0,
    )

    assert result.feasible
    assert round(result["dairy_scaler"] / result["beef_scaler"], 6) == 2.0
    ch4_used = result["beef_scaler"] * 1.0 + result["dairy_scaler"] * 2.0
    assert round(ch4_used, 6) == 10.0


def test_optimise_ch4_budget_none_matches_default():
    """Calling optimise() without ch4_budget at all must reproduce today's
    exact single-budget behavior -- explicit regression pin."""
    dairy_waypoint_data = {"co2e": 10.0, "ch4": 999.0, "area_dairy": 5.0, "area_beef": 2.0}
    beef_waypoint_data = {"co2e": 5.0, "ch4": 999.0, "area_dairy": 0.0, "area_beef": 8.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2e",
        ratio_type="dairy_per_beef",
        ratio_value=3.0,
        emissions_budget=100.0,
        area_commitment=10000.0,
    )

    assert result.feasible
    assert round(result["beef_scaler"], 6) == round(100.0 / 35.0, 6)
    assert round(result["dairy_scaler"], 6) == round(300.0 / 35.0, 6)


def test_optimise_ch4_budget_zero_forces_zero_animals():
    dairy_waypoint_data = {"co2_n2o_co2e": 1.0, "ch4": 1.0, "area_dairy": 1.0, "area_beef": 1.0}
    beef_waypoint_data = {"co2_n2o_co2e": 1.0, "ch4": 1.0, "area_dairy": 0.0, "area_beef": 1.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2_n2o_co2e",
        ratio_type="dairy_per_beef",
        ratio_value=2.0,
        emissions_budget=10000.0,
        area_commitment=10000.0,
        ch4_budget=0.0,
    )

    assert result.feasible
    assert result["dairy_scaler"] == 0.0
    assert result["beef_scaler"] == 0.0


def test_optimise_infeasible_when_ch4_budget_negative():
    dairy_waypoint_data = {"co2_n2o_co2e": 1.0, "ch4": 1.0, "area_dairy": 1.0, "area_beef": 1.0}
    beef_waypoint_data = {"co2_n2o_co2e": 1.0, "ch4": 1.0, "area_dairy": 0.0, "area_beef": 1.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2_n2o_co2e",
        ratio_type="dairy_per_beef",
        ratio_value=2.0,
        emissions_budget=10000.0,
        area_commitment=10000.0,
        ch4_budget=-10.0,
    )

    assert not result.feasible
    assert "message" in result


def test_optimise_infeasible_when_budget_negative():
    dairy_waypoint_data = {"co2e": 1.0, "area_dairy": 1.0, "area_beef": 1.0}
    beef_waypoint_data = {"co2e": 1.0, "area_dairy": 0.0, "area_beef": 1.0}

    result = LivestockOptimisation().optimise(
        dairy_waypoint_data=dairy_waypoint_data,
        beef_waypoint_data=beef_waypoint_data,
        scale_parameter="co2e",
        ratio_type="dairy_per_beef",
        ratio_value=2.0,
        emissions_budget=-10.0,  # negative -- not even zero animals fits
        area_commitment=10000.0,
    )

    assert not result.feasible
    assert "message" in result


# --- Integration test through the full Optigob pipeline, real bundled DB --
# --- confirms the opt-in wiring (waypoint fallback to block-level ratio,
# --- area_commitment computed from sibling sectors) end to end. Expected
# --- values below are the actual output of this exact config, hand-verified
# --- once and hard-coded (same convention as the other test_*.py files in
# --- this suite). Reflect AR5-recomputed co2e (see gwp.py/recompute_co2e),
# --- not the DB's precomputed co2e column.
# ---
# --- The dairy/beef figures moved when the ratio stopped snapping to
# --- ratio_value in baseline_year+1 and started ramping there from the
# --- baseline year's own observed ratio (see
# --- claude-docs/abatement-deployment-ramp.md). The 2025 split is now the
# --- ratio 5/30 of the way from 1.5865 to 2.0, not a flat 2.0. Verified as a
# --- pure redistribution: the dairy+beef total is unchanged at 16365.72
# --- (the emissions budget still binds identically), dairy -693.78 and beef
# --- +693.78.

def test_cattle_optimiser_end_to_end():
    config = {
        "baseline_year": 2020,
        "target_year": 2030,
        "non_cattle_agriculture": [
            {"name": "Pigs", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": []}
        ],
        "cattle_systems": {
            "abatement": "2020 BL",
            "productivity": "2020 Prod",
            "ratio_type": "dairy_per_beef",
            "ratio_value": 2.0,
            "waypoints": [
                {"year": 2025, "abatement": "2020 BL", "scaler": 0.8, "scale_parameter": "co2e",
                 "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod", "beef_productivity": "2020 Prod"}
            ]
        }
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    idx = 2025 - 2020

    assert round(dairy.time_series["co2e"][idx], 2) == round(10455.492571082397, 2)
    assert round(beef.time_series["co2e"][idx], 2) == round(5910.222628917603, 2)

    # The budget is what binds, so the split moving must not move the total.
    assert round(dairy.time_series["co2e"][idx] + beef.time_series["co2e"][idx], 2) == round(16365.72, 2)

    # Held flat after the last waypoint, same as the heuristic path.
    assert round(dairy.time_series["co2e"][idx], 2) == round(dairy.time_series["co2e"][-1], 2)
    assert round(beef.time_series["co2e"][idx], 2) == round(beef.time_series["co2e"][-1], 2)


def test_cattle_optimiser_ratio_holds_when_budget_tight():
    """Unlike the heuristic (which zeroes out beef before touching dairy),
    the optimiser must hold the ratio even under a severe cut."""
    config = {
        "baseline_year": 2020,
        "target_year": 2030,
        "non_cattle_agriculture": [
            {"name": "Pigs", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": []}
        ],
        "cattle_systems": {
            "abatement": "2020 BL",
            "productivity": "2020 Prod",
            "ratio_type": "dairy_per_beef",
            "ratio_value": 2.0,
            "waypoints": [
                {"year": 2025, "abatement": "2020 BL", "scaler": 0.2, "scale_parameter": "co2e",
                 "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod", "beef_productivity": "2020 Prod"}
            ]
        }
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    idx = 2025 - 2020

    # Beef must NOT be zeroed out -- both shrink together under the ratio.
    assert beef.time_series["co2e"][idx] > 0
    assert dairy.time_series["co2e"][idx] > 0


def test_cattle_optimiser_area_constraint_binds_every_year():
    """
    Reproduces and closes the land-balance gap found this session (see
    claude-docs/database-reference.md's afforestation section and
    claude-docs/cattle-example-walkthrough.md's land-balance addendum):
    afforestation follows its own fixed, non-linear DB schedule that starts
    consuming land almost immediately after baseline_year, while cattle used
    to only move via linear interpolation between waypoints -- with no
    re-check against what afforestation was actually doing in between. That
    let land go negative in intermediate years even though both waypoint
    endpoints were individually feasible. The ratio branch now re-solves the
    LP independently for every year, using each year's REAL area as a hard
    constraint.

    This config uses a generous emissions target (scaler=0.99 -- emissions
    essentially never binds) combined with a large afforestation_rate, so
    area is left as the only real constraint -- proving it actually
    engages, not just coincidentally passing because area was never tight.
    """
    config = {
        "baseline_year": 2020,
        "target_year": 2050,
        "forestry": [
            {"name": "existing_forest", "harvest": "high", "ccs": True},
            {"name": "afforestation", "afforestation_rate": 60.0, "broadleaf_frac": 0.5,
             "organic_soil": 0.15, "harvest": "high", "ccs": True},
        ],
        "non_cattle_agriculture": [
            {"name": "Pigs", "abatement": "2020 BL", "productivity": "2020 Prod", "waypoints": []}
        ],
        "cattle_systems": {
            "abatement": "2020 BL",
            "productivity": "2020 Prod",
            "waypoints": [
                {"year": 2050, "abatement": "2020 BL", "scaler": 0.99, "scale_parameter": "co2e",
                 "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod",
                 "beef_productivity": "2020 Prod", "ratio_type": "dairy_per_beef", "ratio_value": 2.0},
            ],
        },
    }

    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    spared = optigob.get_field("cattle_systems").get_system("Spared Cattle/Sheep area")
    afforestation = optigob.get_field("forestry").get_system("afforestation")

    time_span = 2050 - 2020 + 1
    baseline_combined_area = (dairy.time_series["area_dairy"][0] + dairy.time_series["area_beef"][0]
                              + beef.time_series["area_beef"][0])

    # (a) land is never over-committed at any year.
    for i in range(time_span):
        assert spared.time_series["area"][i] >= -1e-6, \
            f"negative spared area at year {2020 + i}: {spared.time_series['area'][i]}"

    # (b) the area constraint actually saturates (binds with ~zero slack) at
    # several intermediate, non-waypoint years -- proving the per-year area
    # constraint genuinely engages rather than the LP just happening to use
    # less area than what was available.
    binding_years = []
    for i in range(time_span):
        year = 2020 + i
        if year in (2020, 2050):
            continue
        combined_area = (dairy.time_series["area_dairy"][i] + dairy.time_series["area_beef"][i]
                         + beef.time_series["area_beef"][i])
        area_commitment = baseline_combined_area - (afforestation.time_series["area"][i]
                                                     - afforestation.time_series["area"][0])
        if abs(area_commitment - combined_area) < 1.0:
            binding_years.append(year)

    assert len(binding_years) >= 3, f"expected area to bind at several intermediate years, got {binding_years}"
