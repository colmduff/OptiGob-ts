def apply_scalers(fields, db_manager, baseline_year):
    """Apply near-term (2020-2025) calibration factors from the bundled
    `scalers` DB table to every system whose name has a matching column.

    Known bug, mostly inert: multiplying a Python float by the first row's
    numpy.float64 scaler produces a numpy.float64, which then fails
    `AgricultureSystem.update_by_scaler`'s strict `type(x) is float` check on
    every subsequent row (see claude-docs/cattle-optimisation.md section 2).

    "Mostly", not "entirely" -- the earlier claim that this "does nothing for
    any sector" is wrong in two ways worth knowing:

    - The **baseline-year row does apply**, and is load-bearing. It is why 2020
      Dairy is ~4.15M head rather than the reference row's 27,439 (x151.19).
      Every baseline figure in the model depends on it.
    - It still calls `update_time_series`, so it **extends each matching
      system's series to 2025 with flat values** -- shifting the effective
      waypoint-interpolation anchor from 2020 to 2025 for Pigs/Poultry/Sheep/
      Crops/Dairy/Beef (but not No-Crops, which has no column).

    What is lost is rows 2021-2025: real observed history (beef -20.5% over
    those years) that the model discards and replaces with a modelled
    trajectory. See claude-docs/NOTES.md.

    NOTE (investigated, do not "fix" naively): simply switching that check
    to `isinstance(x, float)` activates the loop but exposes a deeper bug --
    `update_by_scaler` re-reads the already-scaled `value[0]` each year, so
    the scaler is applied on top of the prior year's scaled value (Dairy
    co2e reaches ~2,000,000 kt/yr). The near-flat final outputs are an
    accident of the cattle optimiser recomputing cattle from scratch and the
    other sectors' scalers being ~1.0. A correct fix must first define the
    intended calibration semantics and rework `update_by_scaler` so it scales
    a pristine per-unit baseline, not the running series value.
    """
    scalers = db_manager.get_scalers()
    for fi in fields:
        for system in fi.systems:
            if system.name in scalers.keys():
                for i in range(len(scalers["Year"])):
                    system.update_by_scaler(scaler=scalers[system.name][i],
                                            baseline_year=baseline_year,
                                            target_year=scalers["Year"][i])
