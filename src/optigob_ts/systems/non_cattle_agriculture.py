from dataclasses import dataclass

from .abstract_factory import Field
from ..common.keys import *
from .agriculture import AgricultureWayPoint, AgricultureSystem
from ..common.utils import get_total
from ..common.gwp import recompute_co2e, DEFAULT_GWP


@dataclass
class NonCattleWayPoint(AgricultureWayPoint):
    productivity: str

    def get_data(self, db_manager, system_name, agriculture, gwp=DEFAULT_GWP):
        kwargs = db_manager.get_agriculture_data(abatement=self.abatement,
                                                 productivity=self.productivity,
                                                 system=system_name,
                                                 agriculture=agriculture)
        return recompute_co2e(kwargs, gwp)

@dataclass
class NonCattleSystem(AgricultureSystem):

    def load_data(self, db_manager, gwp=DEFAULT_GWP):
        kwargs = db_manager.get_agriculture_data(abatement=self.baseline_abatement,
                                                 productivity=self.baseline_productivity,
                                                 system=self.name,
                                                 agriculture=TABLE_NON_CATTLE)
        recompute_co2e(kwargs, gwp)
        self.init_timeseries(kwargs)


    def run(self, baseline_year, target_year, db_manager, gwp=DEFAULT_GWP):
        for waypoint in self.waypoints:
            assert isinstance(waypoint, NonCattleWayPoint)
            waypoint_data = waypoint.get_data(db_manager=db_manager, system_name=self.name, agriculture=TABLE_NON_CATTLE, gwp=gwp)

            if waypoint.scale_absolute_or_percentage:
                scaler = waypoint.scaler / waypoint_data[waypoint.scale_parameter]
            else:
                scaler = self.time_series[waypoint.scale_parameter][0] / waypoint_data[waypoint.scale_parameter] * waypoint.scaler

            for key, value in waypoint_data.items():
                if isinstance(value, int) or isinstance(value, float):
                    waypoint_data[key] = scaler * value

            self.update_time_series(new_config=waypoint_data,
                                    baseline_year=baseline_year,
                                    target_year=waypoint.year)

        super().run(baseline_year, target_year, db_manager, gwp)

class NonCattleAgriculture(Field):
    def __init__(self, data):
        self.name = NON_CATTLE_AGRICULTURE
        self.systems = []

        for system in data:
            way_points = []
            for way_point in system[WAY_POINTS]:
                way_points.append(NonCattleWayPoint(**way_point))
            self.systems.append(NonCattleSystem(name=system[NAME],
                                                baseline_abatement=system[AGRICULTURE_BASELINE_ABATEMENT],
                                                baseline_productivity=system[AGRICULTURE_BASELINE_PRODUCTIVITY],
                                                waypoints=way_points,
                                                time_series={}))
            if system[NAME] == NON_CATTLE_AGRICULTURE_CROPS:
                self.systems.append(NonCattleSystem(name=NON_CATTLE_AGRICULTURE_NO_CROPS,
                                                    baseline_abatement=system[AGRICULTURE_BASELINE_ABATEMENT],
                                                    baseline_productivity=system[AGRICULTURE_BASELINE_PRODUCTIVITY],
                                                    waypoints=[],
                                                    time_series={}))

    def run(self, baseline_year, target_year, db_manager, gwp=DEFAULT_GWP):
        super().run(baseline_year, target_year, db_manager, gwp)

        #area balancing crops
        c = self.get_system(NON_CATTLE_AGRICULTURE_CROPS)
        if c is not None:
            nc = self.get_system(NON_CATTLE_AGRICULTURE_NO_CROPS)
            baseline_area = c.time_series[AREA][0]
            no_crop = []
            for i in range(len(c.time_series[AREA])):
                diff = c.time_series[AREA][i] - baseline_area
                no_crop.append(nc.time_series[AREA][i] - diff)
            self.get_system(NON_CATTLE_AGRICULTURE_NO_CROPS).time_series[AREA] = no_crop

    def get_protein(self, time_span):
        """Protein output in tonnes.

        Unlike cattle, the `non_cattle` table's `protein` metric is ALREADY
        protein in tonnes, not raw product mass, so no `protein_content`
        factor applies here -- applying one would understate these sectors
        four-fold. (Crops carries a separate `human_consumed_protein` that
        differs from `protein`, 176,358.5 t vs 271,320.8 t; that split only
        makes sense for a protein figure.) See
        `cattle_agriculture.py::get_protein` for the sectors that do need
        converting.
        """
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_protein", s.time_series["protein"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + NON_CATTLE_AGRICULTURE, total))

        return output_list

    def get_biodiversity(self, time_span):
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_hnv_area", s.time_series["hnv_area"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + NON_CATTLE_AGRICULTURE, total))

        return output_list
