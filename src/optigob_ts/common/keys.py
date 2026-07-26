NAME = "name"
BASELINE_YEAR = "baseline_year"
TARGET_YEAR = "target_year"
DEPLOYMENT_YEAR = "deployment_year"
WAY_POINTS = "waypoints"
AR = "AR"
SPLIT_GAS = "split_gas"
SPLIT_GAS_FRAC = "split_gas_frac"
NET_ZERO_FRAC = "net_zero_frac"

CO2E = "co2e"
CO2_N2O_CO2E = "co2_n2o_co2e"
AREA = "area"
PROTEIN = "protein"
BIO_ENERGY = "bio_energy"
HWP = "hwp"
SUBSTITUTION = "substitution"
BIODIVERSITY = "biodiversity"

HNV_AREA = "hnv_area"
CO2 = "co2"
N2O = "n2o"
CH4 = "ch4"

FORESTRY = "forestry"
FORESTRY_AFFORESTATION = "afforestation"
FORESTRY_EXISTING_FOREST = "existing_forest"
AFFORESTATION_ORGANIC_SOIL_AREA = "organic_soil_area"

ORGANIC_SOILS = "organic_soils"
ORGANIC_SOILS_DRAINAGE_STATUS = "drainage_status"
ORGANIC_SOILS_ORGANIC_SOIL_UNDER_GRASS = "Organic soil under grass"
ORGANIC_SOILS_NEAR_NATURAL_WETLANDS = "Near natural wetlands"
ORGANIC_SOILS_INDUSTRIAL_PEAT = "Industrial peat"
ORGANIC_SOILS_DOMESTIC_PEAT = "Domestic peat"
DRAINED = "Drained"
REWETTED = "Rewetted"

NON_CATTLE_AGRICULTURE = "non_cattle_agriculture"
NON_CATTLE_AGRICULTURE_PIGS = "Pigs"
NON_CATTLE_AGRICULTURE_POULTRY = "Poultry"
NON_CATTLE_AGRICULTURE_SHEEP = "Sheep"
NON_CATTLE_AGRICULTURE_CROPS = "Crops"
NON_CATTLE_AGRICULTURE_NO_CROPS = "No-Crops"

CATTLE_AGRICULTURE = "cattle_systems"
CATTLE_AGRICULTURE_BEEF = "Beef"
CATTLE_AGRICULTURE_DAIRY = "Dairy"
# Raw product mass as stored in the `cattle` table, both in kg -- NOT protein.
# `get_protein` converts them via the `protein_content` table.
CATTLE_AGRICULTURE_MILK_YIELD = "milk_yield"
CATTLE_AGRICULTURE_BEEF_YIELD = "beef_carcass_yield"
# Derived output labels, in tonnes of protein.
CATTLE_AGRICULTURE_MILK_PROTEIN = "milk_protein"
CATTLE_AGRICULTURE_BEEF_PROTEIN = "beef_protein"
# Keys into the `protein_content` table.
PROTEIN_CONTENT_MILK = "milk"
PROTEIN_CONTENT_BEEF = "beef"
CATTLE_AGRICULTURE_SPARED_AREA = "Spared Cattle/Sheep area"
DAIRY_AREA = "area_dairy"
BEEF_AREA = "area_beef"
TOTAL_CATTLE_NUMBERS = "total_cattle_numbers"

AGRICULTURE_BASELINE_ABATEMENT = "abatement"
AGRICULTURE_BASELINE_PRODUCTIVITY = "productivity"

CATTLE_AGRICULTURE_RATIO_TYPE = "ratio_type"
CATTLE_AGRICULTURE_RATIO_VALUE = "ratio_value"

CH4_SCALER = "ch4_scaler"
CH4_SCALE_ABSOLUTE_OR_PERCENTAGE = "ch4_scale_absolute_or_percentage"

TABLE_NON_CATTLE="non_cattle"
TABLE_CATTLE="cattle"

AD_EMISSIONS = "ad_emissions"
AD_ADDITIONAL_AREA = "additional_area"
AD_WILLOW_AREA = "willow_area"