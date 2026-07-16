import math

from .common.keys import *
from .common.logger import get_logger

logger = get_logger("balancing")

# Tolerance for "is this balance actually negative, or just floating-point
# noise from accumulating many small ramped values over up to 81 years."
# Land areas here are in hectares, routinely in the hundreds of thousands --
# 1e-6 ha is not a meaningful shortfall at that scale.
_LAND_BALANCE_TOLERANCE = 1e-6


def _get_field(fields, name):
    for f in fields:
        if f.name == name:
            return f
    return None


def validate_land_balance(fields, baseline_year, target_year):
    """Raise `ValueError` if this scenario's configuration would ever drive
    the organic-soil pool negative -- i.e. ask for more organic-soil-origin
    land than physically exists, at any single year from `baseline_year` to
    `target_year`.

    Only one pool is checked here. The *general* grassland pool (cattle/
    sheep's freed land vs. afforestation+AD's claims on it) no longer needs
    a separate check: `CattleAgriculture.run_cattle_systems` now requires
    `ratio_type`/`ratio_value` (the heuristic split was removed), and that
    ratio-constrained optimiser already enforces a hard per-year
    `area_commitment` constraint automatically, for every cattle scenario,
    with no exceptions -- so that pool can no longer go negative by
    construction, and a redundant pre-check here would just duplicate what
    the optimiser (and its own `result.feasible` check) already guarantees.

    The **organic-soil pool** has no such automatic enforcement, which is
    why it still needs this: `"Organic soil under grass"`'s baseline
    `Drained` area is a fixed pool shared by two claimants -- the soil
    system's own rewetting waypoints, and afforestation's organic-soil-
    origin sub-claim. Rewetting is served first (unconditionally -- it's
    just whatever its own waypoints, now range-checked to `[0, 1]`,
    produce); afforestation's claim is checked against whatever remains.
    AD is not part of this pool -- none of its DB tables carry an
    organic-soil attribution at all. Unlike cattle's dairy/beef scalers,
    `afforestation_rate` is one value fixed for the whole run, not a
    per-year decision variable a solver adjusts -- there's no optimiser
    here to make this self-enforcing the way the grassland pool now is.

    This function must run *before* `balance_areas` in `Optigob.run()` --
    it validates the same numbers `balance_areas` is about to apply as
    bookkeeping, so validating first means that bookkeeping can never
    silently go negative.

    On violation, this reports not just which year and by how much, but
    the maximum feasible `afforestation_rate` that would have kept every
    year non-negative, computed directly (no solver needed, since
    afforestation's area scales *linearly* in `afforestation_rate`): for
    each year where afforestation has a nonzero claim, the rate at which
    that year's claim would exactly exhaust what's available is
    `configured_rate * available / claim_at_configured_rate`; the true max
    feasible rate is the minimum of that over every year.
    """
    logger.info("validate_land_balance: checking %s -> %s", baseline_year, target_year)
    organic_soils_field = _get_field(fields, ORGANIC_SOILS)
    forestry_field = _get_field(fields, FORESTRY)
    has_grass = organic_soils_field is not None and organic_soils_field.get_system(ORGANIC_SOILS_ORGANIC_SOIL_UNDER_GRASS) is not None
    has_afforestation = forestry_field is not None and forestry_field.get_system(FORESTRY_AFFORESTATION) is not None

    if has_grass and has_afforestation:
        logger.info("validate_land_balance: 'Organic soil under grass' + afforestation both present -> checking organic-soil pool")
        _validate_organic_soil_pool(fields, baseline_year, target_year)
        logger.info("validate_land_balance: organic-soil pool OK, never goes negative")
    else:
        logger.info(
            "validate_land_balance: organic-soil pool check skipped (organic_soils_under_grass=%s, afforestation=%s)",
            has_grass, has_afforestation,
        )
    logger.info(
        "validate_land_balance: grassland pool (cattle/sheep vs afforestation+AD) not checked here -- "
        "self-enforcing via the ratio-LP's area_commitment constraint, if cattle_systems is present"
    )


def _max_feasible_afforestation_rate(configured_rate, per_year_claims, per_year_available):
    """Given the afforestation claim and the land available to it at every
    year (both already computed at `configured_rate`), return `(max_rate,
    infeasible_regardless)`. `infeasible_regardless=True` means at least one
    year has negative `available` even before afforestation's own claim --
    no afforestation_rate, including 0, fixes that; the other claimant(s)
    on that pool already exceed it alone.
    """
    if any(available < -_LAND_BALANCE_TOLERANCE for available in per_year_available):
        return None, True

    candidates = [
        configured_rate * available / claim
        for claim, available in zip(per_year_claims, per_year_available)
        if claim > 0
    ]
    if not candidates:
        return None, False
    return min(candidates), False


def _raise_land_balance_error(pool_name, year, claim, available, configured_rate, max_rate, infeasible_regardless):
    shortfall = claim - available
    if infeasible_regardless:
        raise ValueError(
            f"Land balance violated in the {pool_name} at year {year}: "
            f"claim={claim:,.1f} ha, available={available:,.1f} ha, "
            f"shortfall={shortfall:,.1f} ha. This pool is already "
            f"exceeded by other land uses alone -- no afforestation_rate "
            f"(including 0) resolves it; reduce AD/rewetting demand on "
            f"this pool instead."
        )
    # Floor (not round-to-nearest) so the displayed value is always itself
    # feasible if plugged back in as afforestation_rate -- round-to-nearest
    # can round *up* past the true max by enough to still violate the pool.
    max_rate_floor = math.floor(max_rate * 10000) / 10000
    raise ValueError(
        f"afforestation_rate={configured_rate} exceeds available land at "
        f"year {year} ({pool_name}): claim={claim:,.1f} ha, "
        f"available={available:,.1f} ha, shortfall={shortfall:,.1f} ha. "
        f"Max feasible afforestation_rate given current config: {max_rate_floor:,.4f}"
    )


def _validate_organic_soil_pool(fields, baseline_year, target_year):
    afforestation = _get_field(fields, FORESTRY).get_system(FORESTRY_AFFORESTATION)
    organic_soils_under_grass = _get_field(fields, ORGANIC_SOILS).get_system(ORGANIC_SOILS_ORGANIC_SOIL_UNDER_GRASS)

    organic_soil_pool = organic_soils_under_grass.time_series[DRAINED + "_" + AREA][0]
    logger.info(
        "_validate_organic_soil_pool: pool = 'Organic soil under grass' baseline Drained_area = %.1f ha",
        organic_soil_pool,
    )

    rewetting_claims, affor_claims = [], []
    for i in range(target_year - baseline_year + 1):
        rewetting_claims.append(organic_soil_pool - organic_soils_under_grass.time_series[DRAINED + "_" + AREA][i])
        affor_claims.append(afforestation.time_series[AFFORESTATION_ORGANIC_SOIL_AREA][i] - afforestation.time_series[AFFORESTATION_ORGANIC_SOIL_AREA][0])

    balances = [organic_soil_pool - r - a for r, a in zip(rewetting_claims, affor_claims)]
    for i, (r, a, b) in enumerate(zip(rewetting_claims, affor_claims, balances)):
        logger.debug(
            "_validate_organic_soil_pool: year=%s rewetting_claim=%.1f afforestation_claim=%.1f balance=%.1f",
            baseline_year + i, r, a, b,
        )

    worst_i = min(range(len(balances)), key=lambda i: balances[i])
    logger.info(
        "_validate_organic_soil_pool: tightest year=%s balance=%.1f (rewetting_claim=%.1f, afforestation_claim=%.1f)",
        baseline_year + worst_i, balances[worst_i], rewetting_claims[worst_i], affor_claims[worst_i],
    )
    if balances[worst_i] >= -_LAND_BALANCE_TOLERANCE:
        logger.info("_validate_organic_soil_pool: OK, never negative")
        return

    logger.info("_validate_organic_soil_pool: VIOLATED at year=%s -- computing max feasible afforestation_rate", baseline_year + worst_i)
    available_for_afforestation = [organic_soil_pool - r for r in rewetting_claims]
    max_rate, infeasible_regardless = _max_feasible_afforestation_rate(
        afforestation.afforestation_rate, affor_claims, available_for_afforestation
    )
    _raise_land_balance_error(
        "organic-soil pool", baseline_year + worst_i,
        claim=rewetting_claims[worst_i] + affor_claims[worst_i], available=organic_soil_pool,
        configured_rate=afforestation.afforestation_rate, max_rate=max_rate,
        infeasible_regardless=infeasible_regardless,
    )


def balance_areas(fields, baseline_year, target_year):
    """Reconcile land area moving *between* fields after each field has
    independently run its own time series.

    Only handles cross-field balancing; within-field balancing (organic
    soil rewetting, cropland/no-cropland split) happens inside
    `OrganicSoilSystem.run()` / `NonCattleAgriculture.run()` respectively.

    Two balances are performed here, both conditional on the relevant
    fields being present in this scenario:

        beef.area_beef    =>                          => afforestation.area
        dairy.area_dairy  => spared_sheep_cattle.area => ad.area
        dairy.area_beef   =>                          => additional_ad.area
        sheep.area        =>                          => willow_ad.area

    i.e. land freed up by cattle/sheep shrinking is first absorbed as
    "spared" cattle/sheep area, then afforestation and AD feedstock area
    draw down from that same pool; and organic soil freed by rewetting
    feeds into afforestation's organic-soil area.
    """
    logger.info("balance_areas: %s -> %s", baseline_year, target_year)
    if _get_field(fields, CATTLE_AGRICULTURE) is not None:
        logger.info("balance_areas: cattle_systems present -> running _balance_spared_sheep_cattle_area")
        _balance_spared_sheep_cattle_area(fields, baseline_year, target_year)
    else:
        logger.info("balance_areas: no cattle_systems -> skipping _balance_spared_sheep_cattle_area")

    # organic_soil_under_grass.drained_area => afforestation.organic_soil_area
    if (_get_field(fields, ORGANIC_SOILS) is not None
            and _get_field(fields, ORGANIC_SOILS).get_system(ORGANIC_SOILS_ORGANIC_SOIL_UNDER_GRASS) is not None
            and _get_field(fields, FORESTRY) is not None
            and _get_field(fields, FORESTRY).get_system(FORESTRY_AFFORESTATION) is not None):
        logger.info("balance_areas: 'Organic soil under grass' + afforestation both present -> running _balance_afforestation_organic_soils")
        _balance_afforestation_organic_soils(fields, baseline_year, target_year)
    else:
        logger.info("balance_areas: skipping _balance_afforestation_organic_soils (missing organic_soils-under-grass and/or afforestation)")


def _balance_spared_sheep_cattle_area(fields, baseline_year, target_year):
    """Grow/shrink `CattleAgriculture`'s "Spared Cattle/Sheep area" system
    to absorb whatever area dairy, beef, sheep, afforestation and AD
    collectively free up (or consume) relative to baseline, each year.

    `diff` is the sum of (baseline area - this year's area) across every
    included field/system -- positive when land has been freed, negative
    when a field has grown into more land than at baseline -- and is
    added directly onto the spared-area system's own area for that year.
    """
    assert _get_field(fields, CATTLE_AGRICULTURE) is not None
    sheep_included = _get_field(fields, NON_CATTLE_AGRICULTURE) is not None and _get_field(fields, NON_CATTLE_AGRICULTURE).get_system(NON_CATTLE_AGRICULTURE_SHEEP) is not None
    afforestation_included = _get_field(fields, FORESTRY) is not None and _get_field(fields, FORESTRY).get_system(FORESTRY_AFFORESTATION) is not None
    ad_included = _get_field(fields, AD_EMISSIONS) is not None

    dairy = _get_field(fields, CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_DAIRY)
    beef = _get_field(fields, CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_BEEF)
    sheep, afforestation, ad_emissions = None, None, None

    if sheep_included:
        sheep = _get_field(fields, NON_CATTLE_AGRICULTURE).get_system(NON_CATTLE_AGRICULTURE_SHEEP)
    if afforestation_included:
        afforestation = _get_field(fields, FORESTRY).get_system(FORESTRY_AFFORESTATION)
    if ad_included:
        ad_emissions = _get_field(fields, AD_EMISSIONS).get_system(AD_EMISSIONS)

    logger.info(
        "_balance_spared_sheep_cattle_area: sheep_included=%s afforestation_included=%s ad_included=%s",
        sheep_included, afforestation_included, ad_included,
    )

    spared_area_system = _get_field(fields, CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_SPARED_AREA)
    for i in range(target_year - baseline_year + 1):
        diff = (dairy.time_series[DAIRY_AREA][0] - dairy.time_series[DAIRY_AREA][i]
                 + dairy.time_series[BEEF_AREA][0] - dairy.time_series[BEEF_AREA][i]
                 + beef.time_series[BEEF_AREA][0] - beef.time_series[BEEF_AREA][i])
        if sheep_included:
            diff += sheep.time_series[AREA][0] - sheep.time_series[AREA][i]
        if afforestation_included:
            diff += afforestation.time_series[AREA][0] - afforestation.time_series[AREA][i]
        if ad_included:
            diff += (ad_emissions.time_series[AREA][0] - ad_emissions.time_series[AREA][i]
                     + ad_emissions.time_series[AD_ADDITIONAL_AREA][0] - ad_emissions.time_series[AD_ADDITIONAL_AREA][i]
                     + ad_emissions.time_series[AD_WILLOW_AREA][0] - ad_emissions.time_series[AD_WILLOW_AREA][i])

        before = spared_area_system.time_series[AREA][i]
        spared_area_system.time_series[AREA][i] += diff
        after = spared_area_system.time_series[AREA][i]
        logger.debug(
            "_balance_spared_sheep_cattle_area: year=%s diff=%.1f spared_area %.1f -> %.1f",
            baseline_year + i, diff, before, after,
        )
        if after < -_LAND_BALANCE_TOLERANCE:
            logger.warning(
                "_balance_spared_sheep_cattle_area: year=%s spared_area went NEGATIVE (%.1f) -- "
                "should be unreachable now that cattle_systems requires ratio_type/ratio_value",
                baseline_year + i, after,
            )


def _balance_afforestation_organic_soils(fields, baseline_year, target_year):
    """Feed organic soil freed by afforestation's own accounting back
    into `OrganicSoils`' "Organic soil under grass" drained-area system,
    keeping the two fields' organic-soil area consistent with each other
    year over year (only called when both fields, and both specific
    systems, are present in the scenario -- see `balance_areas`).
    """
    afforestation = _get_field(fields, FORESTRY).get_system(FORESTRY_AFFORESTATION)
    organic_soils_under_grass = _get_field(fields, ORGANIC_SOILS).get_system(ORGANIC_SOILS_ORGANIC_SOIL_UNDER_GRASS)

    for i in range(target_year - baseline_year + 1):
        before = organic_soils_under_grass.time_series[DRAINED + "_" + AREA][i]
        diff = afforestation.time_series[AFFORESTATION_ORGANIC_SOIL_AREA][0] - afforestation.time_series[AFFORESTATION_ORGANIC_SOIL_AREA][i]
        new_area = before + diff
        organic_soils_under_grass.area_balance(i, new_area, DRAINED)
        logger.debug(
            "_balance_afforestation_organic_soils: year=%s afforestation_organic_soil_claim=%.1f Drained_area %.1f -> %.1f",
            baseline_year + i, -diff, before, new_area,
        )
        if new_area < -_LAND_BALANCE_TOLERANCE:
            logger.warning(
                "_balance_afforestation_organic_soils: year=%s Drained_area went NEGATIVE (%.1f) -- "
                "should be unreachable, validate_land_balance() runs before this",
                baseline_year + i, new_area,
            )
