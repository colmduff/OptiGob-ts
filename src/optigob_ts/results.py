"""Category-based results layer for a completed Optigob run.

`Optigob.get_results()` returns a `Results` instance built from an already-
`.run()`-called `Optigob`. It builds one internal long/tidy `pandas.DataFrame`
(one row per field/label/parameter/year) by iterating `optigob.fields`
directly -- unlike the removed `get_evaluation`, field identity is preserved
and all-zero rows are kept, not silently dropped.

The tidy table is an implementation detail. The main entry points are the
**category properties** -- `area`, `ghg`, `protein`, `biodiversity`,
`energy`, `hwp`, `substitution`, `livestock_population`, `net_zero` -- each
returning a ready-to-use, year-indexed DataFrame for that one kind of
output, and `plot(category)` for a quick chart of the same. There is no
class hierarchy here: an earlier version of this module split results into
one subclass per internal `Field` type (`ForestryResults`,
`CattleAgricultureResults`, etc.), which mirrored the simulation's internal
sector classes rather than the kinds of output someone actually wants to
look at -- most of those subclasses ended up empty. Output category (area,
GHG, protein...) is the axis that matters to a caller, not which internal
`Field` subclass happened to produce a number.

Two defensive behaviours in `_rows_from_result` aren't optional cleanups,
they're load-bearing:

- Every series returned by a `Field.get_<parameter>` call is sliced to
  `[:time_span]` before use, regardless of its actual length. Most fields'
  arrays are already exactly `time_span` long by construction, but
  `AnaerobicDigestion.get_area/get_bio_energy/get_substitution/get_biodiversity`
  return raw `time_series` lists that are always 81 entries (2020-2100)
  irrespective of the run's `target_year` -- only `get_co2e` truncates
  correctly upstream. Slicing defensively here, uniformly, means no field
  needs special-case handling and any future field with the same class of
  bug is automatically covered.
- `is_total` is detected structurally (last element of a field-method's
  returned list, if its label starts with "total_"), not by matching
  `f"total_{field.name}"` -- `AnaerobicDigestion` hardcodes the literal
  `"total_ad"` instead of `"total_ad_emissions"`, and some of its methods
  (`get_co2e`, `get_substitution`) never append a total row at all. Also,
  `OrganicSoils.get_co2e/get_area/get_biodiversity` never append a total
  row at any grain, so `is_total` is simply always False for that field --
  callers must not assume every field has a total row.

There is deliberately no naive cross-field grand total (e.g. "total area
across the whole scenario") anywhere in this module. Summing `area` rows
across all fields double-counts organic-soil-origin forest area (see
`claude-docs/bugs.md` item 7 and `claude-docs/land-balance.md` section 6).
For `ghg`, the correct cross-field total already exists --
`emissions.compute_net_zero()` -- and is surfaced here via `net_zero()`
rather than reimplemented, and via `net_zero` as a plottable category.
"""

import pandas as pd

from .common.keys import CO2E, AREA, PROTEIN, BIO_ENERGY, HWP, SUBSTITUTION, BIODIVERSITY, CO2, CH4, N2O
from .emissions import compute_net_zero
from .systems.cattle_agriculture import CattleAgriculture

PARAMETERS = (CO2E, AREA, PROTEIN, BIO_ENERGY, HWP, SUBSTITUTION, BIODIVERSITY)

# Raw single-gas parameters, reported per sector in kt of the gas itself with
# no GWP factor applied -- NOT interchangeable with CO2E. Handled separately
# from PARAMETERS because they all route through the one `Field.get_gas(gas,
# time_span)` method rather than a `get_<parameter>` of their own.
GAS_PARAMETERS = (CO2, CH4, N2O)

# One fixed unit per parameter (documented convention, not a per-row DB
# lookup -- AD's DB queries never select any "<metric>_unit" column at all,
# and reversing each field's ad-hoc label strings back to a DB metric key
# to look up its unit would be fragile). Sourced from
# claude-docs/database-reference.md.
PARAMETER_UNITS = {
    CO2E: "kt CO2e",
    AREA: "ha",
    PROTEIN: "t",
    BIO_ENERGY: "kWh",
    HWP: "m3",
    SUBSTITUTION: "kt CO2e",
    BIODIVERSITY: "ha",
    "livestock_population": "head",
    CO2: "kt CO2",
    CH4: "kt CH4",
    N2O: "kt N2O",
}

TIDY_COLUMNS = ["field", "parameter", "label", "is_total", "year", "value", "unit"]


def _split_by_magnitude(df):
    """Partition `df`'s columns into (large, small) groups for a twin-axis
    plot, by finding the biggest log-scale gap between consecutive columns'
    max-abs-values, sorted descending. All-zero columns are always grouped
    with "small". Returns (large_columns, small_columns) as lists; small_columns
    is empty if there's no group of columns clearly dwarfed by the rest.
    """
    import numpy as np

    maxvals = df.abs().max()
    nonzero = maxvals[maxvals > 0].sort_values(ascending=False)
    if len(nonzero) < 2:
        return list(df.columns), []

    log_gaps = np.log(nonzero.values[:-1]) - np.log(nonzero.values[1:])
    split_at = log_gaps.argmax() + 1
    large_columns = list(nonzero.index[:split_at])
    small_columns = [c for c in df.columns if c not in large_columns]
    return large_columns, small_columns

# Public category name -> underlying tidy "parameter" value. Drives both the
# category properties below and plot(category).
CATEGORY_PARAMETERS = {
    "area": AREA,
    "ghg": CO2E,
    "protein": PROTEIN,
    "energy": BIO_ENERGY,
    "hwp": HWP,
    "substitution": SUBSTITUTION,
    "biodiversity": BIODIVERSITY,
    "livestock_population": "livestock_population",
    "co2": CO2,
    "ch4": CH4,
    "n2o": N2O,
}


class Results:
    """Wraps one completed `Optigob` run's output as category DataFrames.

    `optigob` must already have had `.run()` called on it.
    """

    def __init__(self, optigob):
        self.optigob = optigob
        self.baseline_year = optigob.baseline_year
        self.target_year = optigob.target_year
        self.time_span = optigob.target_year - optigob.baseline_year + 1
        self._tidy = self._build_tidy()

    def _rows_from_result(self, field_name, parameter, result):
        rows = []
        if result is None:
            return rows

        last_index = len(result) - 1
        for index, (label, values) in enumerate(result):
            is_total = index == last_index and label.startswith("total_")
            sliced = values[: self.time_span]
            for year_offset, value in enumerate(sliced):
                rows.append({
                    "field": field_name,
                    "parameter": parameter,
                    "label": label,
                    "is_total": is_total,
                    "year": self.baseline_year + year_offset,
                    "value": value,
                    "unit": PARAMETER_UNITS[parameter],
                })
        return rows

    def _build_tidy(self):
        rows = []

        for field in self.optigob.fields:
            for parameter in PARAMETERS:
                method = getattr(field, "get_" + parameter)
                if parameter == CO2E:
                    result = method(self.time_span, self.optigob.gwp)
                else:
                    result = method(self.time_span)
                rows.extend(self._rows_from_result(field.name, parameter, result))

            for gas in GAS_PARAMETERS:
                result = field.get_gas(gas, self.time_span)
                rows.extend(self._rows_from_result(field.name, gas, result))

            # Livestock headcount isn't one of the 7 standard parameters --
            # cattle is the only field that tracks a headcount at all.
            if isinstance(field, CattleAgriculture):
                result = field.get_livestock_population(self.time_span)
                rows.extend(self._rows_from_result(field.name, "livestock_population", result))

        co2e, co2e_split_gas, total_ch4 = compute_net_zero(self.optigob.fields, self.optigob.gwp, self.time_span)
        net_zero_series = [
            ("net_zero_co2e", co2e),
            ("net_zero_split_gas_co2/n2o", co2e_split_gas),
            ("net_zero_split_gas_ch4", total_ch4),
        ]
        for label, values in net_zero_series:
            sliced = values[: self.time_span]
            for year_offset, value in enumerate(sliced):
                rows.append({
                    "field": None,
                    "parameter": CO2E,
                    "label": label,
                    "is_total": True,
                    "year": self.baseline_year + year_offset,
                    "value": value,
                    "unit": PARAMETER_UNITS[CO2E],
                })

        if not rows:
            return pd.DataFrame(columns=TIDY_COLUMNS)
        return pd.DataFrame(rows, columns=TIDY_COLUMNS)

    @property
    def tidy(self):
        return self._tidy

    def wide(self, parameter, field=None, include_totals=False):
        """Pivot `tidy` for one parameter into year-indexed, label-columned form.

        If `field` is omitted, rows from every field (and, for "co2e", the
        scenario-level net-zero rows) are included together -- labels are
        distinct across fields in practice, so this is a convenient
        "everything for this parameter" overview, not just a per-field view.
        """
        df = self._tidy[self._tidy["parameter"] == parameter]
        if field is not None:
            df = df[df["field"] == field]
        if not include_totals:
            df = df[~df["is_total"]]
        return df.pivot(index="year", columns="label", values="value")

    def net_zero(self):
        df = self._tidy[(self._tidy["parameter"] == CO2E) & (self._tidy["field"].isna())]
        return df.pivot(index="year", columns="label", values="value")

    @property
    def area(self):
        return self.wide(CATEGORY_PARAMETERS["area"], include_totals=True)

    @property
    def ghg(self):
        return self.wide(CATEGORY_PARAMETERS["ghg"], include_totals=True)

    @property
    def protein(self):
        return self.wide(CATEGORY_PARAMETERS["protein"], include_totals=True)

    @property
    def energy(self):
        return self.wide(CATEGORY_PARAMETERS["energy"], include_totals=True)

    @property
    def hwp(self):
        return self.wide(CATEGORY_PARAMETERS["hwp"], include_totals=True)

    @property
    def substitution(self):
        return self.wide(CATEGORY_PARAMETERS["substitution"], include_totals=True)

    @property
    def biodiversity(self):
        return self.wide(CATEGORY_PARAMETERS["biodiversity"], include_totals=True)

    @property
    def livestock_population(self):
        return self.wide(CATEGORY_PARAMETERS["livestock_population"], include_totals=True)

    @property
    def co2(self):
        """Per-sector CO2 in kt CO2 -- raw, no GWP applied. Forestry's column
        carries its precomputed CO2e figure (that field has no gas-level
        breakdown at all; see `systems/forestry.py`), so this is not a pure
        CO2 series for that one sector.
        """
        return self.wide(CATEGORY_PARAMETERS["co2"], include_totals=True)

    @property
    def ch4(self):
        """Per-sector CH4 in kt CH4 -- raw, UNCONVERTED. Not CO2e: do not sum
        alongside `ghg`. Sums (over non-total columns) to `compute_net_zero`'s
        `total_ch4`, which is what `check_net_zero_status`'s split-gas target
        grades.
        """
        return self.wide(CATEGORY_PARAMETERS["ch4"], include_totals=True)

    @property
    def n2o(self):
        """Per-sector N2O in kt N2O -- raw, no GWP applied."""
        return self.wide(CATEGORY_PARAMETERS["n2o"], include_totals=True)

    def plot(self, category, ax=None, include_totals=False, dynamic_only=False, split_by_magnitude=False,
             columns=None):
        """Quick line chart (years on the x-axis, one line per column) of
        one category's DataFrame (`"net_zero"` is also a valid category
        here, mapping to `net_zero()`). Requires the optional `viz` extra
        (matplotlib) -- lazily imported so the base install doesn't need
        it. Returns the `Axes` so the caller can further customize or save
        the figure.

        Defaults to `include_totals=False` -- unlike the matching category
        *property*, which defaults to a report-style view with totals
        included. A chart with every individual system's line plus every
        field's total line is visually noisy (and, for `wide()`'s own
        reasons, arithmetically misleading to eyeball); pass
        `include_totals=True` if you specifically want the total lines
        drawn too.

        `dynamic_only=True` drops columns whose value never changes across
        the run (e.g. a baseline area that has no waypoint scaling it) --
        useful when eyeballing a chart for validation, since a flat line
        carries no information and just adds clutter/legend noise.

        `split_by_magnitude=True` moves columns dwarfed by the rest into a
        second, stacked subplot with its own y-axis (see
        `_split_by_magnitude`) -- unlike the `"net_zero"` split below, both
        panels share the same unit here; this just stops a handful of small
        systems (e.g. Poultry, or Pigs next to Dairy/Beef) from being
        flattened to an unreadable line near zero by one or two much larger
        ones. No-op if there's no clear large/small grouping. Ignored for
        `"net_zero"`, which always splits out CH4 regardless of this flag.
        Two separate panels (not a shared-pixel twin axis) are used
        deliberately: a twin axis draws both groups' lines in the same
        pixel space with only a second y-axis label to tell them apart, which
        is easy to misread (a small-magnitude line sitting near the top of
        the shared plot area can look like it belongs to the large axis). If
        you pass your own `ax`, this still falls back to a twin axis, since
        adding a sibling panel to an `Axes` that already belongs to someone
        else's figure isn't possible -- the two-panel layout only applies
        when `plot()` creates its own figure (the default, `ax=None`).

        `columns`, if given, restricts the chart to that subset of column
        names (any not present in the category's DataFrame are silently
        dropped) -- applied before `dynamic_only`/`split_by_magnitude`, so
        those still operate only within the restricted set.
        """
        from matplotlib import pyplot as plt

        if category == "net_zero":
            df = self.net_zero()
            unit = PARAMETER_UNITS[CO2E]
        elif category in CATEGORY_PARAMETERS:
            parameter = CATEGORY_PARAMETERS[category]
            df = self.wide(parameter, include_totals=include_totals)
            unit = PARAMETER_UNITS[parameter]
        else:
            valid = sorted(CATEGORY_PARAMETERS) + ["net_zero"]
            raise ValueError(f"Unknown category {category!r}. Valid categories: {valid}")

        if columns is not None:
            df = df[[c for c in columns if c in df.columns]]

        if dynamic_only:
            df = df.loc[:, df.nunique() > 1]

        ch4_label = "net_zero_split_gas_ch4"
        if category == "net_zero" and ch4_label in df.columns:
            # net_zero_split_gas_ch4 is raw kt CH4 -- no GWP applied -- while
            # the other two net_zero series are kt CO2e. Sharing one axis
            # squashes CH4's real movement into a sliver near zero, since its
            # absolute scale is an order of magnitude smaller; give it its
            # own panel instead.
            large_columns = [c for c in df.columns if c != ch4_label]
            small_columns = [ch4_label]
            small_unit = "kt CH4"
        elif split_by_magnitude:
            large_columns, small_columns = _split_by_magnitude(df)
            small_unit = unit
        else:
            large_columns, small_columns = list(df.columns), []
            small_unit = unit

        stacked = small_columns and ax is None
        if stacked:
            _, (ax, ax_small) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
        elif small_columns:
            # Caller supplied their own Axes -- we can't add a sibling panel
            # to a figure we don't own, so fall back to a twin axis here.
            ax_small = ax.twinx()
        else:
            ax_small = None
            if ax is None:
                _, ax = plt.subplots(figsize=(9, 5))

        if ax_small is not None:
            df[large_columns].plot(ax=ax)
            ax.set_ylabel(unit)
            ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize="small")

            df[small_columns].plot(ax=ax_small, linestyle="--")
            ax_small.set_ylabel(small_unit)
            ax_small.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize="small")
            if stacked:
                # Two independent panels -- the bottom one carries the x-axis label.
                ax_small.set_xlabel("Year")
            else:
                # Twin-axis fallback: ax_small shares ax's actual x-axis.
                ax.set_xlabel("Year")
        else:
            df.plot(ax=ax)
            ax.set_ylabel(unit)
            ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize="small")
            ax.set_xlabel("Year")

        ax.set_title(category)
        ax.figure.tight_layout()
        return ax

    def to_csv(self, path, **kwargs):
        self._tidy.to_csv(path, index=False, **kwargs)

    def to_excel(self, path=None):
        from io import BytesIO
        import openpyxl  # noqa: F401 -- lazy import, optional dependency check

        target = path if path is not None else BytesIO()

        sheet_names = list(dict.fromkeys(
            "scenario" if field is None else field for field in self._tidy["field"]
        ))

        with pd.ExcelWriter(target, engine="openpyxl") as writer:
            for name in sheet_names:
                mask = self._tidy["field"].isna() if name == "scenario" else self._tidy["field"] == name
                sheet_df = self._tidy[mask].copy()
                sheet_df["column"] = sheet_df["parameter"] + ":" + sheet_df["label"]
                table = sheet_df.pivot(index="year", columns="column", values="value")
                table.to_excel(writer, sheet_name=name[:31])

        if path is None:
            target.seek(0)
            return target
