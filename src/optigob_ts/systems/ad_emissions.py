from dataclasses import dataclass

from .abstract_factory import Field, System
from ..common.keys import *
from ..common.utils import add_two_lists, get_total
from ..common.gwp import DEFAULT_GWP, transform_to_c02e


@dataclass
class ADSystem(System):
    implementation_year: int
    ccs: bool
    additional_biomethane_year: int
    additional_grass_biomethane: float
    willow_year: int
    cdr_bioenergy: float

    def load_data(self, db_manager, gwp=DEFAULT_GWP):
        # gwp is unused: AD's DB tables never store a precomputed co2e (only raw
        # co2/ch4/n2o) -- get_co2e() already recomputes it from those at evaluation
        # time, so there's nothing to fix up here. Accepted only to match
        # System.load_data's signature.
        kwargs = db_manager.get_ad_emissions(self.implementation_year,
                                             self.ccs,
                                             self.additional_biomethane_year,
                                             self.additional_grass_biomethane,
                                             self.willow_year,
                                             self.cdr_bioenergy)
        self.init_timeseries(kwargs)

    def get_net_zero(self, time_span):
        co2 = self.time_series[CO2][:time_span]
        n2o = self.time_series[N2O][:time_span]
        ch4 = self.time_series[CH4][:time_span]

        co2 = add_two_lists(co2, self.time_series["additional_" + CO2][:time_span])
        n2o = add_two_lists(n2o, self.time_series["additional_" + N2O][:time_span])
        ch4 = add_two_lists(ch4, self.time_series["additional_" + CH4][:time_span])
        return co2, n2o, ch4

class AnaerobicDigestion(Field):

    def __init__(self, data):
        self.name = AD_EMISSIONS
        self.systems = []

        data[NAME] = AD_EMISSIONS
        data["time_series"] = {}
        self.systems.append(ADSystem(**data))

    def get_co2e(self, time_span, gwp=DEFAULT_GWP):
        system = self.systems[0]
        co2e = []
        for i in range(time_span):
            co2 = system.time_series[CO2][i] + system.time_series["additional_" + CO2][i]
            ch4 = system.time_series[CH4][i] + system.time_series["additional_" + CH4][i]
            n2o = system.time_series[N2O][i] + system.time_series["additional_" + N2O][i]
            co2e.append(transform_to_c02e(co2=co2, ch4=ch4, n2o=n2o, gwp=gwp))

        output_list = [("ad_emissions", co2e)]
        return output_list

    def get_area(self, time_span):
        output_list = []
        for system in self.systems:
            output_list.append(("ad_area", system.time_series["area"]))
            output_list.append(("ad_additional_area", system.time_series["additional_area"]))
            output_list.append(("ad_willow_area", system.time_series["willow_area"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_ad", total))

        return output_list

    def get_bio_energy(self, time_span):
        output_list = []
        for system in self.systems:
            output_list.append(("ad_biomethane_energy", system.time_series["biomethane_energy"]))
            output_list.append(("ad_additional_biomethane_energy", system.time_series["additional_biomethane_energy"]))
            output_list.append(("ad_willow", system.time_series["willow_willow"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_ad", total))

        return output_list

    def get_substitution(self, time_span):
        output_list = []
        for system in self.systems:
            output_list.append(("ad_co2_substitution_credit", system.time_series["co2_substitution_credit"]))
            output_list.append(("ad_ch2_substitution_credit", system.time_series["ch4_substitution_credit"]))
            output_list.append(("ad_n2o_substitution_credit", system.time_series["n2o_substitution_credit"]))
            output_list.append(("ad_additional_co2_emission_credit", system.time_series["additional_co2_emission_credit"]))
            output_list.append(("ad_willow_lulucf_emission_credit", system.time_series["willow_lulucf_co2_emissions_credit"]))
            output_list.append(("willow_substitution_credit", system.time_series["willow_co2_substitution_credit"]))

        return output_list

    def get_biodiversity(self, time_span):
        output_list = []
        for system in self.systems:
            output_list.append(("ad_hnv_area", system.time_series["hnv_area"]))
            output_list.append(("ad_additional_hnv_area", system.time_series["additional_hnv_area"]))
            output_list.append(("ad_willow_hnv_area", system.time_series["willow_hnv_area"]))

        total = get_total(output_list, time_span)
        output_list.append(("total_ad", total))

        return output_list
