from .common.utils import add_two_lists
from .common.gwp import transform_to_c02e


def compute_net_zero(fields, gwp, time_span):
    """Sum CO2/N2O/CH4 across every field and return three related, but
    NOT interchangeable, whole-scenario series -- this does not just
    return "CO2e":

    - `co2e`: CO2 + N2O + CH4, all three converted to CO2e via GWP
      (kt CO2e). This is the "everything as CO2e" total.
    - `co2e_split_gas`: CO2 + N2O converted to CO2e (kt CO2e), with CH4
      forced to zero in that conversion -- i.e. CH4's contribution is
      fully excluded here, not merely left unconverted. This is the
      "long-lived gases only" figure used by split-gas accounting
      approaches that track CH4 separately rather than folding it into
      a CO2e stock target (see the sibling `OptiGob` package's
      `split_gas` flag for the same concept).
    - `total_ch4`: raw, UNCONVERTED CH4 in kt CH4 -- no GWP factor is
      ever applied to this series. Use this one directly if you need a
      CH4-specific target (e.g. "kt CH4 must fall X% by year Y"); do not
      treat it as CO2e-equivalent methane.

      Per-field note: every field except forestry sources this from its
      systems' raw `time_series["ch4"]` (agriculture, organic soils) or
      `time_series["ch4"] + time_series["additional_ch4"]` (AD) -- both
      already in kt CH4, untouched. Forestry contributes exactly 0 here
      (`ForestrySystem.get_net_zero` in `systems/forestry.py`), because
      this package's bundled DB has no separate CH4 estimate for forest
      sinks/sources at all -- forestry's whole climate effect is instead
      folded into `co2e`/`co2e_split_gas` as an already-precomputed CO2e
      figure (which is safe to sum alongside raw CO2 only because CO2's
      own GWP is exactly 1 in every AR version this package supports --
      see `common/gwp.py`).

    Returns `(co2e, co2e_split_gas, total_ch4)`, each a `list[float]`
    with one value per year from `baseline_year` to `target_year`.
    Callers need to pick which of the three answers their question --
    nothing here decides that for you.
    """
    total_co2, total_n2o, total_ch4 = [], [], []
    for f in fields:
        (co2, n2o, ch4) = f.get_net_zero(time_span=time_span)
        total_co2 = add_two_lists(total_co2, co2)
        total_n2o = add_two_lists(total_n2o, n2o)
        total_ch4 = add_two_lists(total_ch4, ch4)

    co2e = []
    co2e_split_gas = []
    for i in range(time_span):
        co2e.append(transform_to_c02e(co2=total_co2[i], n2o=total_n2o[i], ch4=total_ch4[i], gwp=gwp))
        co2e_split_gas.append(transform_to_c02e(co2=total_co2[i], n2o=total_n2o[i], ch4=0, gwp=gwp))

    return co2e, co2e_split_gas, total_ch4
