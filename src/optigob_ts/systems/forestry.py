from dataclasses import dataclass

from .abstract_factory import Field, System
from ..common.keys import *
from ..common.utils import add_two_lists, get_total


@dataclass
class ForestrySystem(System):
    ccs: bool
    harvest: str
    nz_metrics: list[str]

    def load_data(self, db_manager, gwp=None):
        # gwp is unused: forest data has no ch4/n2o/co2 breakdown to recompute co2e
        # from -- accepted only to match System.load_data's signature.
        self.init_nz_metrics(db_manager)

    def init_nz_metrics(self, db_manager):
        self.nz_metrics = db_manager.get_nz_metrics(self.name, self.ccs)

    def get_co2e(self, gwp=None):
        # gwp is unused: forest CO2e is a precomputed DB column with no CH4/N2O/CO2
        # breakdown to recompute from -- accepted here only to match System.get_co2e's
        # signature so Field.get_co2e can call it uniformly across system types.
        # include net zero calculation table
        co2e_emissions = []
        for metric in self.nz_metrics:
            co2e_emissions = add_two_lists(co2e_emissions, self.time_series[metric])

        return self.name, co2e_emissions

    def get_net_zero(self, time_span):
        co2 = self.time_series[CO2E][:time_span]
        n2o = [0] * time_span
        ch4 = [0] * time_span
        return co2, n2o, ch4

    def get_gas(self, gas, time_span):
        # Forestry has no gas-level breakdown in this package's DB at all: its
        # whole climate effect is a single precomputed CO2e figure. Mirrors
        # get_net_zero above, which reports that figure as CO2 and zero for the
        # other two -- so CO2 is the CO2e series and CH4/N2O are structurally
        # zero, not merely unknown.
        if gas == CO2:
            return self.name, self.time_series[CO2E][:time_span]
        return self.name, [0] * time_span

@dataclass
class ExistingForest(ForestrySystem):
    def load_data(self, db_manager, gwp=None):
        super().load_data(db_manager, gwp)
        kwargs = db_manager.get_existing_forest_data(harvest=self.harvest,
                                                     ccs=self.ccs)
        self.init_timeseries(kwargs)

@dataclass
class Afforestation(ForestrySystem):
    afforestation_rate: float
    broadleaf_frac: float
    organic_soil: float

    def load_data(self, db_manager, gwp=None):
        super().load_data(db_manager, gwp)
        kwargs = db_manager.get_afforestation_data(affor_rate=self.afforestation_rate,
                                                   broadleaf_frac=self.broadleaf_frac,
                                                   organic_soil_frac=self.organic_soil,
                                                   harvest=self.harvest,
                                                   ccs=self.ccs)
        self.init_timeseries(kwargs)

class Forestry(Field):
    def __init__(self, data):
        self.name = FORESTRY
        self.systems = []

        for s in data:
            s["time_series"] = {}
            s["nz_metrics"] = []
            if s[NAME] == FORESTRY_AFFORESTATION:
                self.systems.append(Afforestation(**s))
            if s[NAME] == FORESTRY_EXISTING_FOREST:
                self.systems.append(ExistingForest(**s))

    def run(self, baseline_year, target_year, db_manager, gwp=None):
        super().run(baseline_year, target_year, db_manager, gwp)
        for system in self.systems:
            (_, co2e_emissions) = system.get_co2e()
            system.time_series[CO2E] = co2e_emissions


    def get_area(self, time_span):
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_" + AREA, s.time_series[AREA]))
            output_list.append((s.name + "_" + AFFORESTATION_ORGANIC_SOIL_AREA, s.time_series[AFFORESTATION_ORGANIC_SOIL_AREA]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list

    def get_hwp(self, time_span):
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_harvest_volume", s.time_series["harvest_volume"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list

    def get_substitution(self, time_span):
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_hwp_material_substitution_credit", s.time_series["hwp_material_substitution_credit"]))
            output_list.append((s.name + "_hwp_energy_substitution_credit", s.time_series["hwp_energy_substitution_credit"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list

    def get_biodiversity(self, time_span):
        output_list = []
        for s in self.systems:
            output_list.append((s.name + "_" + HNV_AREA, s.time_series[HNV_AREA]))

        total = get_total(output_list, time_span)
        output_list.append(("total_" + self.name, total))

        return output_list
