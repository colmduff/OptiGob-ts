import os
from optigob_ts.optigob import Optigob
from optigob_ts.common.keys import *
import pytest

db_file_path = os.path.join(os.path.dirname(__file__), "data", "database.db")

config1 = {"baseline_year":2020,"target_year":2100,"forestry":[{"name":"existing_forest","harvest":"high","ccs":True},{"name":"afforestation","afforestation_rate":5,"broadleaf_frac":0.5,"organic_soil":0.15,"harvest":"high","ccs":True}],"organic_soils":[{"name":"Organic soil under grass","drainage_status":["Drained","Rewetted"],"waypoints":[{"year":2030,"rewetting_ratio":0},{"year":2040,"rewetting_ratio":0.2}]},{"name":"Near natural wetlands","drainage_status":["Natural"]},{"name":"Industrial peat","drainage_status":["Drained","Rewetted"],"waypoints":[{"year":2030,"rewetting_ratio":0},{"year":2040,"rewetting_ratio":0.15}]},{"name":"Domestic peat","drainage_status":["Drained","Rewetted"],"waypoints":[{"year":2030,"rewetting_ratio":0},{"year":2040,"rewetting_ratio":0.15}]}],"non_cattle_agriculture":[{"name":"Pigs","abatement":"2020 BL","productivity":"2020 Prod","waypoints":[{"year":2030,"abatement":"2020 BL","productivity":"2020 Prod","scaler":1,"scale_parameter":"co2e","scale_absolute_or_percentage":False},{"year":2040,"abatement":"MACC","productivity":"2020 Prod","scaler":0.9,"scale_parameter":"co2e","scale_absolute_or_percentage":False}]},{"name":"Poultry","abatement":"2020 BL","productivity":"2020 Prod","waypoints":[{"year":2030,"abatement":"2020 BL","productivity":"2020 Prod","scaler":1,"scale_parameter":"co2e","scale_absolute_or_percentage":False},{"year":2040,"abatement":"MACC","productivity":"2020 Prod","scaler":0.9,"scale_parameter":"co2e","scale_absolute_or_percentage":False}]},{"name":"Sheep","abatement":"2020 BL","productivity":"2020 Prod","waypoints":[{"year":2030,"abatement":"2020 BL","productivity":"2020 Prod","scaler":1,"scale_parameter":"co2e","scale_absolute_or_percentage":False},{"year":2045,"abatement":"2020 BL","productivity":"2020 Prod","scaler":0.8,"scale_parameter":"co2e","scale_absolute_or_percentage":False}]},{"name":"Crops","abatement":"2020 BL","productivity":"2020 Prod","waypoints":[{"year":2030,"abatement":"2020 BL","productivity":"2020 Prod","scaler":1,"scale_parameter":"co2e","scale_absolute_or_percentage":False},{"year":2040,"abatement":"2020 BL","productivity":"2020 Prod","scaler":0.9,"scale_parameter":"co2e","scale_absolute_or_percentage":False}]}],"cattle_systems":{"abatement":"2020 BL","productivity":"2020 Prod","ratio_type":"dairy_per_beef","ratio_value":2.0,"waypoints":[{"year":2030,"abatement":"2020 BL","scaler":1,"scale_parameter":"co2e","scale_absolute_or_percentage":False,"dairy_productivity":"2020 Prod","beef_productivity":"2020 Prod"},{"year":2040,"abatement":"2020 BL","scaler":0.8,"scale_parameter":"co2e","scale_absolute_or_percentage":False,"dairy_productivity":"Medium increase","beef_productivity":"Medium increase"},{"year":2050,"abatement":"MACC","scaler":0.5,"scale_parameter":"co2e","scale_absolute_or_percentage":False,"dairy_productivity":"Strong increase","beef_productivity":"Strong increase"}]},"ad_emissions":{"implementation_year":2035,"ccs":True,"additional_biomethane_year":2040,"additional_grass_biomethane":2000,"willow_year":2045,"cdr_bioenergy":5}}

@pytest.mark.parametrize(
    "config",
    [
        config1
    ],
)
def test_time_span(config):
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    timespan = optigob.target_year - optigob.baseline_year + 1

    for f in optigob.fields:
        for s in f.systems:
            for key, value in s.time_series.items():
                assert len(value) == timespan

@pytest.mark.parametrize(
    "config",
    [
        config1
    ],
)

def test_area_balancing_crops(config):
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    timespan = optigob.target_year - optigob.baseline_year + 1

    crops = optigob.get_field(NON_CATTLE_AGRICULTURE).get_system(NON_CATTLE_AGRICULTURE_CROPS)
    no_crops = optigob.get_field(NON_CATTLE_AGRICULTURE).get_system(NON_CATTLE_AGRICULTURE_NO_CROPS)

    baseline_area = crops.time_series[AREA][0] + no_crops.time_series[AREA][0]
    for i in range(timespan):
        total_area = crops.time_series[AREA][i] + no_crops.time_series[AREA][i]
        assert round(baseline_area, 2) == round(total_area, 2)


@pytest.mark.parametrize(
    "config",
    [
        config1
    ],
)
def test_area_balancing_afforestation(config):
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    timespan = optigob.target_year - optigob.baseline_year + 1

    afforestation = optigob.get_field(FORESTRY).get_system(FORESTRY_AFFORESTATION)
    organic_soil_under_grass = optigob.get_field(ORGANIC_SOILS).get_system(ORGANIC_SOILS_ORGANIC_SOIL_UNDER_GRASS)

    baseline_area = afforestation.time_series[AFFORESTATION_ORGANIC_SOIL_AREA][0] + organic_soil_under_grass.time_series["Drained_area"][0] + organic_soil_under_grass.time_series["Rewetted_area"][0]
    for i in range(timespan):
        total_area = afforestation.time_series[AFFORESTATION_ORGANIC_SOIL_AREA][i] + organic_soil_under_grass.time_series["Drained_area"][i] + organic_soil_under_grass.time_series["Rewetted_area"][i]
        assert round(baseline_area, 2) == round(total_area, 2)

@pytest.mark.parametrize(
    "config",
    [
        config1
    ],
)
def test_area_balancing_spared_cattle_sheep_area(config):
    optigob = Optigob(json_config=config, db_file_path=db_file_path)
    optigob.run()

    timespan = optigob.target_year - optigob.baseline_year + 1
    dairy = optigob.get_field(CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_DAIRY)
    beef = optigob.get_field(CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_BEEF)
    spared_area = optigob.get_field(CATTLE_AGRICULTURE).get_system(CATTLE_AGRICULTURE_SPARED_AREA)
    sheep = optigob.get_field(NON_CATTLE_AGRICULTURE).get_system(NON_CATTLE_AGRICULTURE_SHEEP)
    afforestation = optigob.get_field(FORESTRY).get_system(FORESTRY_AFFORESTATION)
    ad_emissions = optigob.get_field(AD_EMISSIONS).get_system(AD_EMISSIONS)

    baseline_area = dairy.time_series[DAIRY_AREA][0] + dairy.time_series[BEEF_AREA][0] + beef.time_series[BEEF_AREA][0] + spared_area.time_series[AREA][0] + sheep.time_series[AREA][0] + afforestation.time_series[AREA][0] + ad_emissions.time_series[AREA][0] + ad_emissions.time_series[AD_ADDITIONAL_AREA][0] + ad_emissions.time_series[AD_WILLOW_AREA][0]
    for i in range(timespan):
        total_area = dairy.time_series[DAIRY_AREA][i] + dairy.time_series[BEEF_AREA][i] + beef.time_series[BEEF_AREA][i] + spared_area.time_series[AREA][i] + sheep.time_series[AREA][i] + afforestation.time_series[AREA][i] + ad_emissions.time_series[AREA][i] + ad_emissions.time_series[AD_ADDITIONAL_AREA][i] + ad_emissions.time_series[AD_WILLOW_AREA][i]
        assert round(baseline_area, 2) == round(total_area, 2)


@pytest.mark.parametrize(
    "config",
    [
        config1
    ],
)
def test_organic_soils_balancing(config):
    pass
