import os

from optigob_ts.optigob import Optigob

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")


def make_config(**overrides):
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
                 "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod",
                 "beef_productivity": "2020 Prod"}
            ]
        }
    }
    config.update(overrides)
    return config


def make_split_gas_config(ch4_scaler=0.8, **overrides):
    """Like make_config(), but with a single cattle waypoint at target_year
    (2030) carrying its own ch4_scaler -- the per-waypoint CH4 envelope
    (mirroring the co2e envelope exactly) needs ch4_scaler on every waypoint
    under split_gas=True."""
    config = make_config(**overrides)
    config["cattle_systems"] = {
        "abatement": "2020 BL",
        "productivity": "2020 Prod",
        "ratio_type": "dairy_per_beef",
        "ratio_value": 2.0,
        "waypoints": [
            {"year": 2030, "abatement": "2020 BL", "scaler": 0.8, "scale_parameter": "co2e",
             "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod",
             "beef_productivity": "2020 Prod",
             "ch4_scaler": ch4_scaler, "ch4_scale_absolute_or_percentage": False}
        ]
    }
    return config


def test_split_gas_omitted_is_regression_safe():
    """Not setting split_gas at all must behave identically to the existing
    (pre-split-gas) cattle optimiser path."""
    config = make_config()
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    idx = 2025 - 2020

    assert round(dairy.time_series["co2e"][idx], 2) == round(11149.265587902906, 2)
    assert round(beef.time_series["co2e"][idx], 2) == round(5216.449612097095, 2)


def test_split_gas_false_matches_omitted():
    """Explicit split_gas=False must produce byte-identical output to omitting
    it entirely -- new params must default to a true no-op."""
    config_omitted = make_config()
    config_explicit = make_config(split_gas=False)

    optigob_omitted = Optigob(json_config=config_omitted, db_file_path=db_file_path)
    optigob_omitted.run()
    optigob_explicit = Optigob(json_config=config_explicit, db_file_path=db_file_path)
    optigob_explicit.run()

    dairy_omitted = optigob_omitted.get_field("cattle_systems").get_system("Dairy")
    dairy_explicit = optigob_explicit.get_field("cattle_systems").get_system("Dairy")
    beef_omitted = optigob_omitted.get_field("cattle_systems").get_system("Beef")
    beef_explicit = optigob_explicit.get_field("cattle_systems").get_system("Beef")

    assert dairy_omitted.time_series["co2e"] == dairy_explicit.time_series["co2e"]
    assert beef_omitted.time_series["co2e"] == beef_explicit.time_series["co2e"]


def test_check_net_zero_status_no_split_gas_frac_configured():
    """With no split_gas_frac anywhere in config, split_gas_ch4 has nothing to
    check against and must be None, while net_zero is still a real bool
    (net_zero_frac defaults to 0 -- must reach net zero exactly)."""
    config = make_config()
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    status = optigob.check_net_zero_status()
    assert status == {"net_zero": False, "split_gas_ch4": None}
    assert isinstance(status["net_zero"], bool)


def test_net_zero_frac_configurable():
    """net_zero_frac generalizes the strict 'must reach zero' check into a
    configurable residual-fraction-of-baseline target ('how much remains',
    matching scaler's own convention). This scenario's co2e scaler is
    exactly 0.8, so final co2e is exactly 80% of baseline -- must fail at
    the default net_zero_frac=0 (strict net zero) and pass at 0.8."""
    config = make_config()
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()
    co2e, _, _ = optigob.get_net_zero_calculations()
    assert round(co2e[-1] / co2e[0], 6) == 0.8

    assert optigob.check_net_zero_status()["net_zero"] is False

    config_loose = make_config(net_zero_frac=0.8)
    optigob_loose = Optigob(json_config=config_loose, db_file_path=db_file_path)
    optigob_loose.run()
    assert optigob_loose.check_net_zero_status()["net_zero"] is True


def test_split_gas_ch4_respects_multiple_waypoint_checkpoints():
    """The CH4 envelope must support multiple independent checkpoints, the
    same way the co2e envelope already does via multiple waypoints -- this
    is the capability gap (a single global glide path couldn't do this) that
    prompted redesigning the CH4 mechanism to mirror co2e's per-waypoint
    structure exactly. Two waypoints (2025, 2030) with distinctly different
    ch4_scaler values must produce two distinctly different per-year slopes,
    not one smooth curve to a single global endpoint."""
    config = make_config(split_gas=True, split_gas_frac=0.5)
    config["cattle_systems"] = {
        "abatement": "2020 BL",
        "productivity": "2020 Prod",
        "ratio_type": "dairy_per_beef",
        "ratio_value": 2.0,
        "waypoints": [
            {"year": 2025, "abatement": "2020 BL", "scaler": 0.9, "scale_parameter": "co2e",
             "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod",
             "beef_productivity": "2020 Prod",
             "ch4_scaler": 0.85, "ch4_scale_absolute_or_percentage": False},
            {"year": 2030, "abatement": "2020 BL", "scaler": 0.7, "scale_parameter": "co2e",
             "scale_absolute_or_percentage": False, "dairy_productivity": "2020 Prod",
             "beef_productivity": "2020 Prod",
             "ch4_scaler": 0.6, "ch4_scale_absolute_or_percentage": False},
        ]
    }
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")

    def cattle_ch4(year):
        idx = year - 2020
        return dairy.time_series["ch4"][idx] + beef.time_series["ch4"][idx]

    assert round(cattle_ch4(2020), 2) == round(498.569, 2)
    assert round(cattle_ch4(2025), 2) == round(421.5336, 2)
    assert round(cattle_ch4(2030), 2) == round(293.1414, 2)

    slope_segment_1 = (cattle_ch4(2020) - cattle_ch4(2025)) / 5  # ch4_scaler=0.85
    slope_segment_2 = (cattle_ch4(2025) - cattle_ch4(2030)) / 5  # ch4_scaler=0.6, steeper
    assert slope_segment_2 > slope_segment_1 + 5  # genuinely different, not noise


def test_split_gas_ch4_scaler_missing_on_waypoint_raises():
    """ch4_scaler is mandatory on every cattle waypoint under split_gas=True
    -- mirrors ratio_type/ratio_value's mandatoriness -- since without it the
    LP has no CH4 target to actually respect at that checkpoint."""
    config = make_config(split_gas=True, split_gas_frac=0.8)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    try:
        optigob.run()
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_split_gas_true_feasible_engages_constraint():
    """A comfortably feasible ch4_scaler must (a) make check_net_zero_status()
    report split_gas_ch4=True when split_gas_frac is at least as loose, and
    (b) actually change the LP's solution vs. split_gas=False -- proving the
    CH4 constraint is enforced, not just reported after the fact."""
    config_split_gas = make_split_gas_config(ch4_scaler=0.8, split_gas=True, split_gas_frac=0.8)
    optigob_split_gas = Optigob(json_config=config_split_gas, db_file_path=db_file_path)
    optigob_split_gas.run()

    status = optigob_split_gas.check_net_zero_status()
    assert status["split_gas_ch4"] is True

    _, _, ch4_split_gas = optigob_split_gas.get_net_zero_calculations()
    assert round(ch4_split_gas[-1], 4) == round(410.8552, 4)
    assert round(ch4_split_gas[0] * 0.8, 4) == round(410.8552, 4)

    config_baseline = make_split_gas_config()  # split_gas=False -> no CH4 constraint at all
    optigob_baseline = Optigob(json_config=config_baseline, db_file_path=db_file_path)
    optigob_baseline.run()
    _, _, ch4_baseline = optigob_baseline.get_net_zero_calculations()

    # The split-gas run's ch4_scaler must have actually constrained CH4 down
    # further than the unconstrained baseline run -- not just coincidentally
    # passing the post-hoc check.
    assert ch4_split_gas[-1] < ch4_baseline[-1]


def test_split_gas_true_too_tight_reports_false():
    """An aggressive split_gas_frac, where non-livestock CH4 (Pigs) alone
    already exceeds the whole-AFOLU target, must report split_gas_ch4=False
    even though cattle's own (equally aggressive) ch4_scaler is fully
    satisfied -- proving the post-hoc split_gas_frac check is independent of,
    and can be stricter than, whatever the waypoint-level ch4_scaler asked
    the LP to hit."""
    config = make_split_gas_config(ch4_scaler=0.01, split_gas=True, split_gas_frac=0.01)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    status = optigob.check_net_zero_status()
    assert status["split_gas_ch4"] is False

    idx = 2030 - 2020
    dairy = optigob.get_field("cattle_systems").get_system("Dairy")
    beef = optigob.get_field("cattle_systems").get_system("Beef")
    assert abs(dairy.time_series["ch4"][idx]) < 1e-6
    assert abs(beef.time_series["ch4"][idx]) < 1e-6

    _, _, total_ch4 = optigob.get_net_zero_calculations()
    # Cattle contributes ~0 (its own ch4_scaler target is met exactly); the
    # final total is just non-livestock (Pigs) CH4, which alone busts the
    # (very tight) whole-AFOLU target.
    assert round(total_ch4[-1], 4) == 15.0
    assert total_ch4[-1] > total_ch4[0] * 0.01


def test_target_achieved_resolves_to_net_zero_when_split_gas_off():
    config = make_config()  # split_gas omitted -> net_zero mode
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    status = optigob.check_net_zero_status()
    assert status["net_zero"] is False  # this scenario doesn't hit strict net zero
    assert optigob.target_achieved() is status["net_zero"]


def test_target_achieved_resolves_to_split_gas_ch4_when_split_gas_on():
    config = make_split_gas_config(ch4_scaler=0.8, split_gas=True, split_gas_frac=0.8)
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    status = optigob.check_net_zero_status()
    assert status["split_gas_ch4"] is True
    # net_zero is False for this scenario -- target_achieved() must report
    # the split-gas result, not silently fall back to net_zero.
    assert status["net_zero"] is False
    assert optigob.target_achieved() is True


def test_split_gas_true_without_frac_raises():
    config = make_config(split_gas=True)
    try:
        Optigob(json_config=config, db_file_path=db_file_path)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_split_gas_frac_out_of_range_raises():
    config = make_config(split_gas=True, split_gas_frac=1.5)
    try:
        Optigob(json_config=config, db_file_path=db_file_path)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_net_zero_frac_out_of_range_raises():
    config = make_config(net_zero_frac=-0.1)
    try:
        Optigob(json_config=config, db_file_path=db_file_path)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_split_gas_true_non_co2e_waypoint_scale_parameter_raises():
    config = make_config(split_gas=True, split_gas_frac=0.8)
    config["cattle_systems"]["waypoints"][0]["scale_parameter"] = "area"
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    try:
        optigob.run()
        assert False, "expected ValueError"
    except ValueError:
        pass
