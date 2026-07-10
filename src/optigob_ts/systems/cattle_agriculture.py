from dataclasses import dataclass

from ..common.keys import *
from .abstract_factory import Field, WayPointSystem
from .agriculture import AgricultureSystem, AgricultureWayPoint
from .livestock_optimisation import LivestockOptimisation
from ..common.utils import get_total
from ..common.gwp import recompute_co2e, DEFAULT_GWP
from ..common.logger import get_logger

logger = get_logger("cattle_agriculture")


@dataclass()
class CattleWayPoint(AgricultureWayPoint):
    dairy_productivity: str
    beef_productivity:str
    ratio_type: str = None
    ratio_value: float = None
    ch4_scaler: float = None
    ch4_scale_absolute_or_percentage: bool = None

    def get_data(self, db_manager, system_name, agriculture, gwp=DEFAULT_GWP):
        if system_name == CATTLE_AGRICULTURE_BEEF:
            productivity = self.beef_productivity
        else:
            productivity = self.dairy_productivity

        kwargs = db_manager.get_agriculture_data(abatement=self.abatement,
                                                 productivity=productivity,
                                                 system=system_name,
                                                 agriculture=agriculture)
        return recompute_co2e(kwargs, gwp)

@dataclass
class CattleSystem(AgricultureSystem):

    def load_data(self, db_manager, gwp=DEFAULT_GWP):
        kwargs = db_manager.get_agriculture_data(abatement=self.baseline_abatement,
                                                 productivity=self.baseline_productivity,
                                                 system=self.name,
                                                 agriculture=TABLE_CATTLE)
        recompute_co2e(kwargs, gwp)
        if self.name == CATTLE_AGRICULTURE_SPARED_AREA:
            kwargs[AREA] = [0.0]
        self.init_timeseries(kwargs)

    def run(self, baseline_year, target_year, db_manager, gwp=DEFAULT_GWP):
        pass

class CattleAgriculture(Field):
    def __init__(self, data):
        self.name = CATTLE_AGRICULTURE
        self.ratio_type = data.get(CATTLE_AGRICULTURE_RATIO_TYPE)
        self.ratio_value = data.get(CATTLE_AGRICULTURE_RATIO_VALUE)

        way_points = []
        for way_point in data[WAY_POINTS]:
            way_points.append(CattleWayPoint(**way_point))

        dairy = CattleSystem(name=CATTLE_AGRICULTURE_DAIRY,
                                  baseline_abatement=data[AGRICULTURE_BASELINE_ABATEMENT],
                                  baseline_productivity=data[AGRICULTURE_BASELINE_PRODUCTIVITY],
                                  waypoints=way_points,
                                  time_series={})

        beef = CattleSystem(name=CATTLE_AGRICULTURE_BEEF,
                                  baseline_abatement=data[AGRICULTURE_BASELINE_ABATEMENT],
                                  baseline_productivity=data[AGRICULTURE_BASELINE_PRODUCTIVITY],
                                  waypoints=way_points,
                                  time_series={})

        # add spared cattle/sheep area
        spared_area = CattleSystem(name=CATTLE_AGRICULTURE_SPARED_AREA,
                                   baseline_abatement=data[AGRICULTURE_BASELINE_ABATEMENT],
                                   baseline_productivity=data[AGRICULTURE_BASELINE_PRODUCTIVITY],
                                   waypoints=[],
                                   time_series={AREA:[0.0]})

        self.systems = [dairy, beef, spared_area]

    def _sum_nca(self, nca, key):
        """Sum a given time_series key across every NCA system -- the same
        summation run_cattle_systems() already does inline for the co2e/
        co2_n2o_co2e envelope, factored out so the parallel CH4 envelope
        can reuse it instead of duplicating the loop."""
        values = []
        for system in nca.systems:
            if len(values) == 0:
                values = system.time_series[key]
            else:
                values = [x + y for (x, y) in zip(values, system.time_series[key])]
        return values

    def run_cattle_systems(self, baseline_year, target_year, db_manager, nca,
                           forestry=None, ad_emissions=None, gwp=DEFAULT_GWP, split_gas=False):
        # Tracks the (year, limit) anchor the *next* segment's per-year limit
        # interpolation starts from. Starts at the implicit baseline anchor
        # (scaler=1.0 at baseline_year); advances to each waypoint's own
        # limit after that waypoint is processed -- "limit" is always defined
        # relative to the original baseline (see
        # claude-docs/optigob-ts-full-guide.md section 4), never the
        # previous waypoint's achieved value. prev_anchor_ch4_limit tracks
        # the same thing for the parallel CH4 envelope (split_gas only).
        prev_anchor_year = baseline_year
        prev_anchor_limit = None
        prev_anchor_ch4_limit = None

        for waypoint in self.systems[0].waypoints:
            assert isinstance(waypoint, CattleWayPoint)
            dairy_waypoint_data = waypoint.get_data(db_manager=db_manager,
                                                    system_name=CATTLE_AGRICULTURE_DAIRY,
                                                    agriculture=TABLE_CATTLE,
                                                    gwp=gwp)
            beef_waypoint_data = waypoint.get_data(db_manager=db_manager,
                                                   system_name=CATTLE_AGRICULTURE_BEEF,
                                                   agriculture=TABLE_CATTLE,
                                                   gwp=gwp)

            effective_scale_parameter = waypoint.scale_parameter
            if split_gas:
                if waypoint.scale_parameter != CO2E:
                    raise ValueError(
                        f"split_gas=True currently requires every cattle waypoint's "
                        f"scale_parameter to be {CO2E!r}, got {waypoint.scale_parameter!r} "
                        f"at year={waypoint.year}."
                    )
                effective_scale_parameter = CO2_N2O_CO2E

            nca_values = self._sum_nca(nca, effective_scale_parameter)

            baseline = (nca_values[0]
                        + self.systems[0].time_series[effective_scale_parameter][0]
                        + self.systems[1].time_series[effective_scale_parameter][0])

            if waypoint.scale_absolute_or_percentage:
                limit = waypoint.scaler
            else:
                limit = baseline * waypoint.scaler

            # Parallel CH4 envelope, built exactly the same way as the co2e/
            # co2_n2o_co2e envelope above (own baseline, own limit, own
            # anchor tracking below) -- non-cattle-agriculture's own CH4 is
            # exogenous/fixed by the time cattle runs, so it's subtracted
            # out the same way nca_values is subtracted from year_budget.
            # Mandatory per waypoint under split_gas, mirroring ratio_type/
            # ratio_value's mandatoriness -- otherwise the LP has no CH4
            # target to actually respect at this checkpoint.
            ch4_limit = None
            if split_gas:
                if waypoint.ch4_scaler is None:
                    raise ValueError(
                        f"split_gas=True requires ch4_scaler on every cattle waypoint -- "
                        f"missing at year={waypoint.year}."
                    )
                nca_ch4_values = self._sum_nca(nca, CH4)
                ch4_baseline = (nca_ch4_values[0]
                                 + self.systems[0].time_series[CH4][0]
                                 + self.systems[1].time_series[CH4][0])
                if waypoint.ch4_scale_absolute_or_percentage:
                    ch4_limit = waypoint.ch4_scaler
                else:
                    ch4_limit = ch4_baseline * waypoint.ch4_scaler

            ratio_type = waypoint.ratio_type or self.ratio_type
            ratio_value = waypoint.ratio_value or self.ratio_value

            if ratio_type is None or ratio_value is None:
                raise ValueError(
                    f"cattle_systems requires ratio_type/ratio_value (set at "
                    f"the cattle_systems block level, or per-waypoint) -- "
                    f"missing at waypoint year={waypoint.year}. The "
                    f"heuristic (no-ratio) split has been removed: it had no "
                    f"land-balance awareness at all, unlike this ratio-"
                    f"constrained optimiser, which enforces a hard per-year "
                    f"area_commitment constraint automatically. See "
                    f"claude-docs/consistency-and-moo.md section 2/2a and "
                    f"claude-docs/land-balance.md for why."
                )

            # Ratio-constrained, budget-optimised split (mandatory -- see
            # claude-docs/livestock-optimisation-gap.md), solved
            # independently for EVERY year in this segment (not just at
            # the waypoint) so that area_commitment -- computed from the
            # real, already-fully-run per-year trajectories of sheep/
            # afforestation/AD -- is a hard constraint every year, not just
            # at waypoints. This closes the land-balance gap documented in
            # claude-docs/database-reference.md's afforestation section:
            # naively, dairy/beef could be only linearly interpolated
            # between waypoints, with no re-check against what
            # afforestation/sheep/AD were actually doing in between, which
            # could (and did) let land go negative in intermediate years
            # even though both waypoint endpoints were individually
            # feasible.
            sheep = nca.get_system(NON_CATTLE_AGRICULTURE_SHEEP)
            afforestation = forestry.get_system(FORESTRY_AFFORESTATION) if forestry is not None else None
            ad = ad_emissions.get_system(AD_EMISSIONS) if ad_emissions is not None else None

            anchor_limit = prev_anchor_limit if prev_anchor_limit is not None else baseline
            anchor_ch4_limit = None
            if split_gas:
                anchor_ch4_limit = prev_anchor_ch4_limit if prev_anchor_ch4_limit is not None else ch4_baseline
            segment_start = prev_anchor_year
            segment_end = waypoint.year

            logger.info(
                "run_cattle_systems: segment %s -> %s, ratio_type=%s ratio_value=%s "
                "limit=%.1f (baseline=%.1f, scaler=%s)",
                segment_start, segment_end, ratio_type, ratio_value, limit, baseline, waypoint.scaler,
            )

            for year in range(segment_start + 1, segment_end + 1):
                idx = year - baseline_year
                frac = (year - segment_start) / (segment_end - segment_start)
                year_limit = anchor_limit + (limit - anchor_limit) * frac

                year_budget = year_limit - nca_values[idx]
                if year_budget < 0:
                    year_budget = 0

                ch4_budget_this_year = None
                if split_gas:
                    ch4_year_limit = anchor_ch4_limit + (ch4_limit - anchor_ch4_limit) * frac
                    ch4_budget_this_year = ch4_year_limit - nca_ch4_values[idx]
                    if ch4_budget_this_year < 0:
                        ch4_budget_this_year = 0

                area_commitment = (self.systems[0].time_series[DAIRY_AREA][0]
                                    + self.systems[0].time_series[BEEF_AREA][0]
                                    + self.systems[1].time_series[BEEF_AREA][0])
                if sheep is not None:
                    area_commitment += sheep.time_series[AREA][0] - sheep.time_series[AREA][idx]
                if afforestation is not None:
                    area_commitment += afforestation.time_series[AREA][0] - afforestation.time_series[AREA][idx]
                if ad is not None:
                    area_commitment += (ad.time_series[AREA][0] - ad.time_series[AREA][idx]
                                         + ad.time_series[AD_ADDITIONAL_AREA][0] - ad.time_series[AD_ADDITIONAL_AREA][idx]
                                         + ad.time_series[AD_WILLOW_AREA][0] - ad.time_series[AD_WILLOW_AREA][idx])

                logger.debug(
                    "run_cattle_systems: year=%s year_budget=%.1f area_commitment=%.1f",
                    year, year_budget, area_commitment,
                )
                result = LivestockOptimisation().optimise(
                    dairy_waypoint_data=dairy_waypoint_data,
                    beef_waypoint_data=beef_waypoint_data,
                    scale_parameter=effective_scale_parameter,
                    ratio_type=ratio_type,
                    ratio_value=ratio_value,
                    emissions_budget=year_budget,
                    area_commitment=area_commitment,
                    ch4_budget=ch4_budget_this_year,
                )
                if not result.feasible:
                    raise ValueError(result["message"])
                dairy_scaler = result["dairy_scaler"]
                beef_scaler = result["beef_scaler"]

                scaled_dairy_waypoint = {}
                for key, value in dairy_waypoint_data.items():
                    if isinstance(value, int) or isinstance(value, float):
                        scaled_dairy_waypoint[key] = dairy_scaler * value
                    else:
                        scaled_dairy_waypoint[key] = value
                self.systems[0].update_time_series(new_config=scaled_dairy_waypoint,
                                                   baseline_year=baseline_year,
                                                   target_year=year)

                scaled_beef_waypoint = {}
                for key, value in beef_waypoint_data.items():
                    if isinstance(value, int) or isinstance(value, float):
                        scaled_beef_waypoint[key] = beef_scaler * value
                    else:
                        scaled_beef_waypoint[key] = value
                self.systems[1].update_time_series(new_config=scaled_beef_waypoint,
                                                   baseline_year=baseline_year,
                                                   target_year=year)

            prev_anchor_year = waypoint.year
            prev_anchor_limit = limit
            prev_anchor_ch4_limit = ch4_limit if split_gas else None

        for i in range(len(self.systems)):
            self.systems[i].update_time_series(new_config=self.systems[i].get_parameters_by_index(-1),
                                               baseline_year=baseline_year,
                                               target_year=target_year)

    def get_area(self, time_span):
        output_list = [(CATTLE_AGRICULTURE_DAIRY + "_" + DAIRY_AREA, self.systems[0].time_series[DAIRY_AREA]),
                       (CATTLE_AGRICULTURE_DAIRY + "_" + BEEF_AREA, self.systems[0].time_series[BEEF_AREA]),
                       (CATTLE_AGRICULTURE_BEEF + "_" + BEEF_AREA, self.systems[1].time_series[BEEF_AREA]),
                       (CATTLE_AGRICULTURE_SPARED_AREA + "_" + AREA, self.systems[2].time_series[AREA])]

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list

    def get_protein(self, time_span):
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_protein_milk", s.time_series["protein_milk"]))
            output_list.append((s.name + "_protein_beef", s.time_series["protein_beef"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list

    def get_livestock_population(self, time_span):
        """Head count by system (Dairy, Beef, Spared Cattle/Sheep area --
        the latter always 0, it holds no animals). Not one of the 7
        standard `Field.get_*` parameters (co2e/area/protein/bio_energy/
        hwp/substitution/biodiversity) -- cattle is the only field that
        tracks a headcount at all, so this is specific to `CattleAgriculture`
        rather than a base `Field` method.
        """
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_total_cattle_numbers", s.time_series["total_cattle_numbers"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list
