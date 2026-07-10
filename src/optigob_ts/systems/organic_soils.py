from dataclasses import dataclass

from .abstract_factory import Field, WayPointSystem, WayPoint
from ..common.keys import *
from ..common.gwp import recompute_co2e, DEFAULT_GWP

@dataclass()
class SoilType:
    area: float
    drainage_status: str
    parameters: dict

    def get(self, key):
        if key in self.parameters:
            return self.parameters[key]
        else:
            return []

@dataclass
class OrganicSoilWayPoint(WayPoint):
    rewetting_ratio: float

@dataclass
class OrganicSoilSystem(WayPointSystem):
    drainage_status: list[str]
    soil_types: list[SoilType]

    def init_timeseries(self, parameters):
        for st in self.soil_types:
            parameters[st.drainage_status + "_" + AREA] = [st.area]
            for key, value in st.parameters.items():
                if isinstance(value, int) or isinstance(value, float):
                    parameters[st.drainage_status + "_" + key] = [value * st.area]
                    if key in parameters:
                        parameters[key][0] += value * st.area
                    else:
                        parameters[key] = [value * st.area]
                else:
                    parameters[st.drainage_status + "_" + key] = [value]
        super().init_timeseries(parameters)

    def load_data(self, db_manager, gwp=DEFAULT_GWP):
        soil_types = []
        for drainage_status in self.drainage_status:
            kwargs = db_manager.get_organic_soils(self.name, drainage_status)
            recompute_co2e(kwargs, gwp)
            area = kwargs[AREA]
            del kwargs[AREA]
            soil_types.append(SoilType(drainage_status=drainage_status,
                                       area=area,
                                       parameters=kwargs))
            self.soil_types = soil_types
        self.init_timeseries({})

    def update_soil(self, rewetting_ratio=0.1, baseline_year=2020, target_year=2050):
        if not 0 <= rewetting_ratio <= 1:
            raise ValueError(
                f"rewetting_ratio must be between 0 and 1 (it's a fraction of "
                f"the baseline drained area to rewet), got {rewetting_ratio!r} "
                f"for {self.name!r} at target_year={target_year}"
            )

        baseline_drained_area = 0
        for st in self.soil_types:
            if st.drainage_status == DRAINED:
                baseline_drained_area = st.area

        new_parameters = {}
        for st in self.soil_types:
            new_area = st.area
            if st.drainage_status == DRAINED:
                new_area = (1 - rewetting_ratio) * baseline_drained_area
            if st.drainage_status == REWETTED:
                new_area = st.area + rewetting_ratio * baseline_drained_area
            new_parameters[st.drainage_status + "_" + AREA] = new_area
            for key, value in st.parameters.items():
                if isinstance(value, int) or isinstance(value, float):
                    new_parameters[st.drainage_status + "_" + key] = value * new_area
                    if key in new_parameters:
                        new_parameters[key] += value * new_area
                    else:
                        new_parameters[key] = value * new_area
                else:
                    new_parameters[st.drainage_status + "_" + key] = value

        self.update_time_series(new_config=new_parameters, baseline_year=baseline_year, target_year=target_year)

    def area_balance(self, idx, area, drainage_status):
        st = self.get_soil_type(drainage_status)
        assert st is not None
        self.time_series[drainage_status + "_" + AREA][idx] = area
        for key, value in st.parameters.items():
            if isinstance(value, int) or isinstance(value, float):
                self.time_series[drainage_status + "_" + key][idx] = value * area

    def get_soil_type(self, name):
        for st in self.soil_types:
            if st.drainage_status == name:
                return st
        return None

    def get(self, key):
        if key in self.time_series.keys():
            return super().get(key)

        results = []
        for ds in self.drainage_status:
            label = self.name + "_" + ds
            parameter = self.time_series[ds + "_" + key]
            results.append((label, parameter))
        return results

    def run(self, baseline_year, target_year, db_manager, gwp=DEFAULT_GWP):
        # gwp is unused here: the raw ch4/n2o/co2 -> co2e recompute for this system
        # already happened once in load_data(), and update_soil() only ever
        # re-scales already-loaded (and thus already GWP-consistent) parameters by
        # area -- accepted only to match Field.run's uniform call signature.
        for waypoint in self.waypoints:
            assert isinstance(waypoint, OrganicSoilWayPoint)
            self.update_soil(rewetting_ratio=waypoint.rewetting_ratio,
                             baseline_year=baseline_year,
                             target_year=waypoint.year)

        super().run(baseline_year, target_year, db_manager, gwp)

class OrganicSoils(Field):
    def __init__(self, data):
        self.name = ORGANIC_SOILS
        self.systems = []

        for s in data:
            way_points = []
            if WAY_POINTS in s:
                for way_point in s[WAY_POINTS]:
                    way_points.append(OrganicSoilWayPoint(**way_point))
            self.systems.append(OrganicSoilSystem(name=s[NAME],
                                                  drainage_status=s[ORGANIC_SOILS_DRAINAGE_STATUS],
                                                  waypoints=way_points,
                                                  time_series={},
                                                  soil_types=[]))

    def get_co2e(self, time_span, gwp=None):
        # gwp is unused here: co2e was already recomputed from ch4/n2o/co2 using the
        # run's AR/GWP selection back in OrganicSoilSystem.load_data(), so the values
        # in time_series are already correct -- accepted only to match
        # Field.get_co2e's signature.
        output_list = []

        for system in self.systems:
            assert isinstance(system, OrganicSoilSystem)
            for ds in system.drainage_status:
                output_list.append((ds + "_" + system.name, system.time_series[ds + "_" + CO2E]))

        return output_list

    def get_area(self, time_span):
        output_list = []

        for system in self.systems:
            assert isinstance(system, OrganicSoilSystem)
            for ds in system.drainage_status:
                output_list.append((ds + "_" + system.name, system.time_series[ds + "_" + AREA]))

        return output_list

    def get_biodiversity(self, time_span):
        output_list = []

        for system in self.systems:
            assert isinstance(system, OrganicSoilSystem)
            for ds in system.drainage_status:
                output_list.append((ds + "_" + system.name, system.time_series[ds + "_" + HNV_AREA + "_ratio"]))

        return output_list
