def apply_scalers(fields, db_manager, baseline_year):
    """Apply near-term (2020-2025) calibration factors from the bundled
    `scalers` DB table to every system whose name has a matching column.

    Known, currently-inert bug: the first row's scaler (1.0, meant to be
    a no-op) is a numpy.float64; multiplying a Python float by it
    produces a numpy.float64, which then fails
    `AgricultureSystem.update_by_scaler`'s strict `type(x) is float`
    check on every subsequent row -- so this mechanism currently does
    nothing for any sector (see claude-docs/livestock-optimisation-gap.md
    section 2).

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
