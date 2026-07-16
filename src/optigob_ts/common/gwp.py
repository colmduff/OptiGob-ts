from dataclasses import dataclass


@dataclass(frozen=True)
class GWPValues:
    co2: float
    ch4: float
    n2o: float


AR4 = GWPValues(co2=1, ch4=25, n2o=298)
AR5 = GWPValues(co2=1, ch4=28, n2o=265)
AR6 = GWPValues(co2=1, ch4=27, n2o=273)

GWP_VERSIONS = {"AR4": AR4, "AR5": AR5, "AR6": AR6}
DEFAULT_GWP = AR5


def get_gwp_values(version: str) -> GWPValues:
    try:
        return GWP_VERSIONS[version]
    except KeyError:
        raise ValueError(f"Unknown GWP/AR version {version!r}. Available: {sorted(GWP_VERSIONS)}")


def transform_to_c02e(co2, n2o, ch4, gwp: GWPValues = DEFAULT_GWP):
    return co2 * gwp.co2 + gwp.n2o * n2o + gwp.ch4 * ch4


def transform_to_co2e_time_series(co2, n2o, ch4, gwp: GWPValues = DEFAULT_GWP):
    assert len(co2) == len(n2o) and len(co2) == len(ch4)
    co2e = []
    for i in range(len(co2)):
        co2e.append(transform_to_c02e(co2[i], n2o[i], ch4[i], gwp))
    return co2e


def recompute_co2e(kwargs: dict, gwp: GWPValues, co2_key="co2", ch4_key="ch4", n2o_key="n2o", co2e_key="co2e",
                    co2_n2o_co2e_key="co2_n2o_co2e") -> dict:
    """Set kwargs[co2e_key] to the GWP-recomputed value from its raw gas
    components, in place.

    NOTE: despite the name, this does not overwrite anything for the tables it is
    actually called on -- neither `cattle` nor `non_cattle` has a `co2e` metric at
    all, so `co2e` and `co2_n2o_co2e` are *created* here, not corrected. They are
    therefore valid `scale_parameter` values without being DB columns (see
    claude-docs/scalers-and-waypoints.md). Forestry is the sector with a
    precomputed CO2e of unknown GWP basis, and it does not route through here --
    it has no gas-level breakdown to recompute from.

    Also sets kwargs[co2_n2o_co2e_key] to the same figure with CH4 excluded
    (CO2 + N2O only, named explicitly so it can't be mistaken for the full
    co2e figure) -- the "long-lived gases only" budget used by split-gas
    accounting. Computed unconditionally, alongside co2e, so it rides through
    every existing waypoint/scaler mechanism the same way co2e already does."""
    kwargs[co2e_key] = transform_to_c02e(co2=kwargs[co2_key], n2o=kwargs[n2o_key], ch4=kwargs[ch4_key], gwp=gwp)
    kwargs[co2_n2o_co2e_key] = transform_to_c02e(co2=kwargs[co2_key], n2o=kwargs[n2o_key], ch4=0, gwp=gwp)
    return kwargs
