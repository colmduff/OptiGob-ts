from abc import ABC, abstractmethod
from dataclasses import dataclass
from ..common.keys import *
from ..common.utils import add_two_lists, get_total
from ..common.gwp import DEFAULT_GWP, transform_to_co2e_time_series


@dataclass
class System(ABC):
    name: str
    time_series: dict

    def init_timeseries(self, parameters):
        self.time_series = parameters

    @abstractmethod
    def load_data(self, db_manager, gwp=DEFAULT_GWP): pass

    def get(self, key):
        if key == CO2E:
            return self.get_co2e()
        if key in self.time_series.keys():
            return [(self.name, self.time_series[key])]

        return []

    def get_co2e(self, gwp=DEFAULT_GWP):
        co2e = transform_to_co2e_time_series(self.time_series[CO2], self.time_series[N2O], self.time_series[CH4], gwp)
        return self.name, co2e

    def get_current_year(self, baseline_year):
        current_year = None
        for key, value in self.time_series.items():
            if current_year is None:
                current_year = len(value)
            elif current_year != len(value):
                current_year = max(current_year, len(value))
                print("Warning! Inconsistent time series length in " + self.name)

        current_year += baseline_year - 1
        return current_year

    def get_parameters_by_index(self, index):
        parameters = {}
        for key, value in self.time_series.items():
            parameters[key] = value[index]
        return parameters

    def update_time_series_entry(self, index, parameters: dict):
        for key, value in parameters.items():
            self.time_series[key][index] = value

    def update_time_series(self, new_config: dict, baseline_year, target_year):
        if target_year <= self.get_current_year(baseline_year):
            target_index = target_year - baseline_year
            self.update_time_series_entry(target_index, new_config)
        else:
            baseline_dict = {}
            for key, value in self.time_series.items():
                if type(value) == list:
                    baseline_dict[key] = value[-1]
                else:
                    baseline_dict[key] = value

            timeframe = target_year - self.get_current_year(baseline_year)
            for i in range(timeframe):
                for key, value in new_config.items():
                    if type(value) == str:
                        self.time_series[key].append(value)
                    else:
                        new_value = (value - baseline_dict[key]) * ((i+1) / timeframe) + baseline_dict[key]
                        self.time_series[key].append(new_value)

    def run(self, baseline_year, target_year, db_manager, gwp=DEFAULT_GWP):
        if self.get_current_year(baseline_year) < target_year:
            parameters = self.get_parameters_by_index(-1)
            self.update_time_series(new_config=parameters,
                                    baseline_year=baseline_year,
                                    target_year=target_year)

    def get_net_zero(self, time_span):
        co2 = self.time_series[CO2][:time_span]
        n2o = self.time_series[N2O][:time_span]
        ch4 = self.time_series[CH4][:time_span]
        return co2, n2o, ch4

@dataclass
class WayPoint(ABC):
    year: int

@dataclass
class WayPointSystem(System, ABC):
    waypoints: list[WayPoint]

@dataclass
class Field(ABC):
    name: str
    systems: list[System]

    # this method reads the data from the configuration file to initialise each system in the field
    @abstractmethod
    def __init__(self, data):
        pass

    # this method starts the time series for each system by loading initial data from the database
    def load_data(self, db_manager, gwp=DEFAULT_GWP):
        for system in self.systems:
            system.load_data(db_manager, gwp)

    # this method fills the time series for each system according to the database and the configuration
    def run(self, baseline_year, target_year, db_manager, gwp=DEFAULT_GWP):
        for system in self.systems:
            system.run(baseline_year, target_year, db_manager, gwp)

    def get_system_names(self):
        system_names = []
        for s in self.systems:
            system_names.append(s.name)
        return system_names

    def get(self, parameter):
        totals = []
        for s in self.systems:
            entries = s.get(parameter)
            if len(totals) == 0:
                for e in entries:
                    totals.append(e)
            else:
                totals = [x+y for x,y in zip(totals, entries)]
        return totals

    # evaluation methods for the user interface
    def get_co2e(self, time_span, gwp=DEFAULT_GWP):
        output_list = []
        for s in self.systems:
            output_list.append(s.get_co2e(gwp))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list

    def get_area(self, time_span):
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_" + AREA, s.time_series[AREA]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list

    def get_protein(self, time_span): pass
    def get_bio_energy(self, time_span): pass
    def get_hwp(self, time_span): pass
    def get_substitution(self, time_span): pass
    def get_biodiversity(self, time_span): pass

    def get_net_zero(self, time_span):
        co2, n2o, ch4 = [], [], []
        for s in self.systems:
            s_co2, s_n20, s_ch4 = s.get_net_zero(time_span)
            co2 = add_two_lists(co2, s_co2)
            n2o = add_two_lists(n2o, s_n20)
            ch4 = add_two_lists(ch4, s_ch4)

        return co2, n2o, ch4

    def get_system(self, name):
        for system in self.systems:
            if system.name == name:
                return system
        return None
