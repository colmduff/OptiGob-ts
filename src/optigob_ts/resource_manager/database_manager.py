import os
import sqlite3
import pandas as pd

from ..database import get_local_dir

class DatabaseManager:
    def __init__(self, database_path=None):
        """
        Initializes the DatabaseManager class.

        Parameters:
            database_path (str, optional): Path to the SQLite database file.
                                           If None, uses the bundled default database.
        """
        if database_path is None:
            self.database_path = os.path.abspath(
                os.path.join(get_local_dir(), "optigob_ts_default_0.1.0.db")
            )
        else:
            self.database_path = os.path.abspath(database_path)

        self.conn = sqlite3.connect(self.database_path)

    def get_baseline_year(self):
        """Return the first (minimum) year in the forestry baseline table.

        Forestry reads its whole 2020-2100 trajectory in year order and treats
        row 0 as the baseline, while every other sector anchors to the config's
        `baseline_year`. If the two disagree, forestry would silently misalign
        against everything else (bug #11), so `Optigob` validates that the
        config's `baseline_year` equals this value. Returns None if the table
        is empty/absent (validation is then skipped).
        """
        try:
            row = self.conn.execute("SELECT MIN(year) FROM existing_forest").fetchone()
        except sqlite3.Error:
            return None
        return row[0] if row and row[0] is not None else None

    def get_existing_forest_data(self,
                                 harvest="high",
                                 ccs=True):
        query = """
            SELECT
                area,
                area_unit,
                hnv_area,
                hnv_area_unit,
                organic_soil_area,
                organic_soil_area_unit,
                ghg_fluxes,
                ghg_fluxes_unit,
                harvest_volume,
                harvest_volume_unit,
                hwp_c_storage,
                hwp_c_storage_unit,
                beccs,
                beccs_unit,
                hwp_material_substitution_credit,
                hwp_material_substitution_credit_unit,
                wood_energy,
                wood_energy_unit,
                hwp_energy_substitution_credit,
                hwp_energy_substitution_credit_unit
            FROM existing_forest
            WHERE harvest_rate = ?
                  AND ccs = ?
            ORDER BY year;
        """
        if ccs:
            ccs = "yes"
        else:
            ccs = "no"

        params = (harvest, ccs)
        df = pd.read_sql_query(query, self.conn, params=params)
        kwargs = df.to_dict(orient="list")
        return kwargs

    def get_afforestation_data(self,
                               affor_rate=2,
                               broadleaf_frac=0.5,
                               organic_soil_frac=0.15,
                               harvest="high",
                               ccs=True):

        if organic_soil_frac == 0:
            organic_soil_frac = "0"

        query = """
            SELECT
                area,
                area_unit,
                hnv_area,
                hnv_area_unit,
                organic_soil_area,
                organic_soil_area_unit,
                ghg_fluxes,
                ghg_fluxes_unit,
                harvest_volume,
                harvest_volume_unit,
                hwp_c_storage,
                hwp_c_storage_unit,
                beccs,
                beccs_unit,
                hwp_material_substitution_credit,
                hwp_material_substitution_credit_unit,
                wood_energy,
                wood_energy_unit,
                hwp_energy_substitution_credit,
                hwp_energy_substitution_credit_unit
            FROM afforestation
            WHERE harvest_rate = ?
                  AND ccs = ?
                  AND bl_c_ratio = ?
                  AND o_m_ratio = ?
            ORDER BY year;
        """
        if ccs:
            ccs = "yes"
        else:
            ccs = "no"

        params = (harvest, ccs, broadleaf_frac, organic_soil_frac)
        df = pd.read_sql_query(query, self.conn, params=params)

        kwargs = df.to_dict(orient="list")
        for key, value in kwargs.items():
            if isinstance(value[0], int) or isinstance(value[0], float):
                scaled_values = []
                for v in value:
                    scaled_values.append(affor_rate * v)
                kwargs[key] = scaled_values

        return kwargs

    def get_nz_metrics(self,
                       system_name,
                       ccs):
        col = "ccs" if ccs else "no_ccs"

        query = f"""
            SELECT DISTINCT
                metric
            FROM
                nz_calc_included
            WHERE
                system = ?
                AND {col} = 'yes';
        """

        df = pd.read_sql_query(query, self.conn, params=(system_name,))
        return df["metric"].tolist()

    def get_agriculture_data(self, abatement="2020 BL", productivity="2020 BL", agriculture="non_cattle", system="Pigs"):
        query = f"""
            SELECT
                metric,
                unit,
                value
            FROM {agriculture}
            WHERE Abatement = ?
                    AND Productivity = ?
                    AND System = ?
        """
        params = (abatement, productivity, system)
        df = pd.read_sql_query(query, self.conn, params=params)
        metric = df.get("metric").to_list()
        unit = df.get("unit").to_list()
        value = df.get("value").to_list()

        kwargs = {}
        for i in range(len(metric)):
            kwargs[metric[i].lower()] = value[i]
            kwargs[metric[i].lower() + "_unit"] = unit[i]

        return kwargs

    def get_scalers(self):
        query = "SELECT * FROM scalers"
        df = pd.read_sql_query(query, self.conn)
        return df

    def get_organic_soils(self, name="Organic soil under grass", drainage_status="Drained"):
        query = """
            SELECT
                metric,
                unit,
                value
            FROM organic_soils
            WHERE "Organic soil type" = ?
                    AND "Drainage status" = ?
        """
        params = (name, drainage_status)
        df = pd.read_sql_query(query, self.conn, params=params)
        metric = df.get("metric").to_list()
        unit = df.get("unit").to_list()
        value = df.get("value").to_list()

        kwargs = {}
        for i in range(len(metric)):
            kwargs[metric[i].lower()] = value[i]
            kwargs[metric[i].lower() + "_unit"] = unit[i]

        return kwargs

    def get_ad_emissions(self, implementation_year, ccs, additional_biomethane_year, additional_grass_biomethane, willow_year, cdr_bioenergy):
        implementation_offset = 2030 # year in the dataset when biomethane strategy is implemented
        additional_biomethane_offset = 2035
        additional_biomethane_scaler = 1000.0
        willow_offset = 2040
        willow_scaler = 1000.0

        query = """
            SELECT
                biomethane_energy,
                area,
                hnv_area,
                co2,
                ch4,
                n2o,
                co2_substitution_credit,
                ch4_substitution_credit,
                n2o_substitution_credit,
            	BECCS
            FROM ad_biomethane_strategy
            WHERE ccs = ?
        """
        ccs = "yes" if ccs else "no"
        params = (ccs,)
        df = pd.read_sql_query(query, self.conn, params=params)

        kwargs = df.to_dict(orient="list")
        offset = implementation_year - implementation_offset
        while offset < 0:
            for _, values in kwargs.items():
                del values[0]
                values.append(values[-1])
            offset += 1
        while offset > 0:
            for key, values in kwargs.items():
                kwargs[key] = [values[0]] + values
                del kwargs[key][-1]
            offset -= 1

        query = """
            SELECT
                biomethane_energy,
                grass_dry_matter,
                area,
                hnv_area,
                co2,
                ch4,
                n2o,
                nh3,
                n_to_water_emissions,
                p_to_water_emissions,
                co2_emission_credit,
                beccs
            FROM additional_ad
            WHERE ccs = ?
        """
        df = pd.read_sql_query(query, self.conn, params=params)

        additional_kwargs = df.to_dict(orient="list")
        offset = additional_biomethane_year - additional_biomethane_offset
        while offset < 0:
            for key, values in additional_kwargs.items():
                del values[0]
                values.append(values[-1])
            offset += 1
        while offset > 0:
            for key, values in additional_kwargs.items():
                additional_kwargs[key] = [values[0]] + values
                del additional_kwargs[key][-1]
            offset -= 1

        scaler = additional_grass_biomethane / additional_biomethane_scaler
        for key, values in additional_kwargs.items():
            if isinstance(values[0], int) or isinstance(values[0], float):
                for i in range(len(values)):
                    values[i] *= scaler
            kwargs["additional_" + key] = values

        query = """
            SELECT
                willow,
                willow_dry_matter,
                area,
                hnv_area,
                lulucf_co2_emissions_credit,
                co2_substitution_credit,
                BECCS
            FROM willow_beccs
            WHERE ccs = ?
        """
        df = pd.read_sql_query(query, self.conn, params=params)

        willow_kwargs = df.to_dict(orient="list")
        offset = willow_year - willow_offset
        while offset < 0:
            for _, values in willow_kwargs.items():
                del values[0]
                values.append(values[-1])
            offset += 1
        while offset > 0:
            for key, values in willow_kwargs.items():
                willow_kwargs[key] = [values[0]] + values
                del willow_kwargs[key][-1]
            offset -= 1

        scaler = cdr_bioenergy / willow_scaler
        for key, values in willow_kwargs.items():
            if isinstance(values[0], int) or isinstance(values[0], float):
                for i in range(len(values)):
                    values[i] *= scaler
            kwargs["willow_" + key] = values

        return kwargs
