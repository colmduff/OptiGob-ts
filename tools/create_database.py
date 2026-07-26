import itertools
import sqlite3
from itertools import combinations

import pandas as pd
from pandas.core.interchange.dataframe_protocol import DataFrame


def create_table(data):
    indices = {}
    for i in range(10):
        indices.update({data[i][0].lower() : i})
        if data[i][0] == "year":
            break
    parameter_name_list = list(indices.keys())
    if 'year' in parameter_name_list:
        parameter_name_list.remove('year')

    variable_title_list = [data[indices['year']][1]]
    while variable_title_list[0] != data[indices['year']][1 + len(variable_title_list)]:
        variable_title_list.append(data[indices['year']][1 + len(variable_title_list)])

    years = []
    variable_list = [[] for _ in range(len(variable_title_list))]
    parameter_list = [[] for _ in range(len(parameter_name_list))]

    j = 1
    while j < len(data[0]):
        for i in range(indices['year'] + 1, len(data)):
            years.append(int(data[i][0]))
            for p in range(len(parameter_name_list)):
                param_value = data[indices[parameter_name_list[p]]][j]
                if param_value != '':
                    parameter_list[p].append(param_value)
                else:
                    for k in range(len(variable_title_list)):
                        param_value = data[indices[parameter_name_list[p]]][j+k]
                        if param_value != '':
                            parameter_list[p].append(param_value)
                            break
            for k in range(len(variable_title_list)):
                variable_list[k].append(data[i][j+k])
        j += len(variable_title_list)

    d = {'year': years}
    for p in range(len(parameter_name_list)):
        d.update({parameter_name_list[p]: parameter_list[p]})
    for v in range(len(variable_title_list)):
        d.update({variable_title_list[v]: variable_list[v]})
    df = pd.DataFrame(data=d)
    return df

def create_scenario_table(param_dict):
    keys = param_dict.keys()
    values = param_dict.values()
    combinations = list(itertools.product(*values))
    return pd.DataFrame(combinations, columns=keys)

def match_scenario(scenario, data, indices, data_idx):
    for key, value in scenario.items():
        entry = data[indices[key]][data_idx]
        if (not (entry == "" or entry == "any")) and not entry == value:
            return False
    return True

def create_forestry_table(data):

    indices = {}
    for i in range(10):
        indices.update({data[i][0].lower() : i})
        if data[i][0] == "year":
            break

    headers = list(indices.keys())
    parameter_name_list = []
    for h in headers:
        if not h in ["year", "metric", "unit"]:
            parameter_name_list.append(h)

    param_dict = {}
    for p in parameter_name_list:
        values = []
        for v in data[indices[p]]:
            if v != p and v != "any" and v != "" and not v in values:
                values.append(v)
        param_dict[p] = values

    scenarios = create_scenario_table(param_dict)

    table_data = {"year": []}
    for p in parameter_name_list:
        table_data[p] = []
    for m in range(1, len(data[0])):
        table_data[data[0][m]] = []
        table_data[data[0][m] + "_unit"] = []

    for row in scenarios.itertuples(index=False):
        params = row._asdict()
        for i in range(indices["year"] + 1, len(data)):
            table_data["year"].append(int(data[i][0]))
            for key, value in params.items():
                table_data[key].append(value)
        for j in range(1, len(data[0])):
            if match_scenario(params, data, indices, j):
                for i in range(indices["year"] + 1, len(data)):
                    table_data[data[indices["metric"]][j]].append(data[i][j])
                    table_data[data[indices["metric"]][j] + "_unit"].append(data[indices["unit"]][j])

    df = pd.DataFrame(data=table_data)
    return df


def read_forestry(excel_path, sqlite_db_path):
    conn = sqlite3.connect(sqlite_db_path)

    xls_sheets = pd.ExcelFile(excel_path).sheet_names
    for sheet in xls_sheets:
        if sheet == "nz_calc_included":
            data = pd.read_excel(excel_path, sheet_name=sheet)
            df = pd.DataFrame(data=data)
            df.to_sql(sheet, conn, if_exists='replace', index=False)
        else:
            data = pd.read_excel(excel_path, sheet_name=sheet, header=None).values.tolist()
            df = create_forestry_table(data)
            df.to_sql(sheet, conn, if_exists='replace', index=False)

    conn.commit()
    conn.close()

def create_animals_table(data):
    parameter_name_list = []
    i = 0
    while type(data[i][0]) is str:
        parameter_name_list.append(data[i][0])
        i += 1
    parameter_name_list.append("metric")
    parameter_name_list.append("unit")
    parameter_name_list.append("value")

    pivot_i = i
    pivot_j = 1

    parameter_list = []
    for _ in parameter_name_list:
        parameter_list.append([])

    for j in range(pivot_j + 1, len(data[0])):
        for i in range(pivot_i + 1, len(data)):
            parameter_list[parameter_name_list.index("value")].append(data[i][j])
            parameter_list[parameter_name_list.index("metric")].append(data[i][0])
            parameter_list[parameter_name_list.index("unit")].append(data[i][1])
            for k in range(pivot_i):
                parameter_list[parameter_name_list.index(data[k][0])].append(data[k][j])

    d = {}
    for i in range(len(parameter_name_list)):
        d.update({parameter_name_list[i] : parameter_list[i]})
    df = pd.DataFrame(data=d)
    return df

def read_animals(excel_path, sqlite_db_path):
    conn = sqlite3.connect(sqlite_db_path)

    xls_sheets = pd.ExcelFile(excel_path).sheet_names
    for sheet in xls_sheets:
        # These sheets are already tabular (one header row, one row per record),
        # so they go straight to SQL. The rest are the wide metric-by-scenario
        # layout that `create_animals_table` has to unpivot.
        if sheet in ("scalers", "protein_content"):
            data = pd.read_excel(excel_path, sheet_name=sheet)
            df = pd.DataFrame(data=data)
            df.to_sql(sheet, conn, if_exists='replace', index=False)
        else:
            data = pd.read_excel(excel_path, sheet_name=sheet, header=None).values.tolist()
            df = create_animals_table(data)
            df.to_sql(sheet, conn, if_exists='replace', index=False)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    import argparse
    import os

    HERE = os.path.dirname(os.path.realpath(__file__))
    DEFAULT_STATIC_XLSX = os.path.join(HERE, "data_sources", "static_systems.xlsx")
    DEFAULT_DYNAMIC_XLSX = os.path.join(HERE, "data_sources", "dynamic_systems.xlsx")
    DEFAULT_DB = os.path.join(
        HERE, "..", "src", "optigob_ts", "database", "optigob_ts_default_0.1.1.db"
    )

    parser = argparse.ArgumentParser(description="Rebuild the optigob_ts bundled SQLite database from source spreadsheets.")
    parser.add_argument("--static-xlsx", default=DEFAULT_STATIC_XLSX)
    parser.add_argument("--dynamic-xlsx", default=DEFAULT_DYNAMIC_XLSX)
    parser.add_argument("--db-path", default=os.path.abspath(DEFAULT_DB))
    args = parser.parse_args()

    read_forestry(args.static_xlsx, args.db_path)
    read_animals(args.dynamic_xlsx, args.db_path)
