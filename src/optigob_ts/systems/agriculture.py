from abc import abstractmethod
from dataclasses import dataclass

from .abstract_factory import WayPoint, WayPointSystem


@dataclass
class AgricultureWayPoint(WayPoint):
    abatement: str
    scaler: float
    scale_parameter: str                # tells us whether we scale by productivity, emissions, area, etc.
    scale_absolute_or_percentage: bool  # True for absolute value, False for percentage of baseline

@dataclass
class AgricultureSystem(WayPointSystem):
    baseline_abatement: str
    baseline_productivity: str

    def init_timeseries(self, parameters):
        super().init_timeseries(parameters)

        for key, value in self.time_series.items():
            if not type(self.time_series[key]) is list:
                self.time_series[key] = [self.time_series[key]]

    @abstractmethod
    def load_data(self, db_manager): pass

    def update_by_scaler(self, scaler, baseline_year, target_year):
        new_config = {}
        for key, value in self.time_series.items():
            baseline_value = value[0]
            if type(baseline_value) is float:
                new_config[key] = baseline_value * scaler
            else:
                new_config[key] = baseline_value

        self.update_time_series(new_config, baseline_year, target_year)
