# optigob-ts

> ⚠️ **Work in progress — not yet validated.** This model is under active
> development and validation. Its outputs may still change and should **not** be
> used for decision-making or cited as results yet. See the "Known limitations"
> section below.

`optigob-ts` is a time-series land use change and environmental assessment tool for Ireland's agriculture, forestry, and other land use (AFOLU) sector. It simulates a full **year-by-year pathway** from a baseline year to a target year, driven by user-specified "waypoints" — target values at specific years that the engine linearly interpolates between and flat-holds after the last one.

---

## Relationship to other `optigob` projects

This package is an **extraction of the core simulation engine** from [`OptiGOBTimeSeries`](../OptiGOBTimeSeries), a Streamlit dashboard repository. Only the non-UI model code (`optigob/`, `resource_manager/`, `configuration/keys.py`, and their tests) was lifted out — the Streamlit app, its pages, and Docker/deployment files were deliberately left behind. The `moo/` multi-objective (NSGA-II) scenario discovery layer from that repository was also left out of this first extraction; it may be added as a follow-on phase.

**This is a different, incompatible model from the [`optigob`](../OptiGob) PyPI package.** Both happen to be called "optigob," but:

- `optigob` (the original pip package) computes a **single-target-year snapshot** — baseline vs. one scenario year — using a Pyomo optimisation to solve livestock populations under an emissions budget constraint.
- `optigob-ts` (this package) computes a **full year-by-year time series** from a baseline year to a target year, driven by waypoints. Livestock dairy/beef splitting defaults to a hand-rolled budget heuristic (beef absorbs cuts first, down to zero, before dairy is touched), but an **opt-in, ratio-constrained Pyomo optimiser** mirroring `optigob`'s own approach is also available per cattle waypoint — see "Livestock optimiser" below.

The import names are deliberately different (`optigob` vs. `optigob_ts`) so both can be installed in the same environment without collision.

---

## Installation

Not yet published to PyPI (planned once validation is complete). Install from source:

```bash
pip install "git+https://github.com/colmduff/optigob-ts.git"
```

The `Results` object's `.plot(category)` (matplotlib) and `.to_excel()` (Excel export)
convenience methods, and the ratio-constrained livestock optimiser (HiGHS solver), require
optional extras:

```bash
pip install "git+https://github.com/colmduff/optigob-ts.git#egg=optigob-ts[full]"      # matplotlib, openpyxl, and highspy
pip install "git+https://github.com/colmduff/optigob-ts.git#egg=optigob-ts[viz]"       # matplotlib only
pip install "git+https://github.com/colmduff/optigob-ts.git#egg=optigob-ts[export]"    # openpyxl only
pip install "git+https://github.com/colmduff/optigob-ts.git#egg=optigob-ts[optimise]"  # highspy only (solver)
```

The core simulation engine's hard dependencies are `pandas` and `pyomo` (small, pure-Python); a solver backend (`highspy`, an optional extra) is only needed if you use the ratio-constrained livestock optimiser described below.

## Usage

```python
import json
from optigob_ts.optigob import Optigob

with open("examples/config.json") as f:
    config = json.load(f)

optigob = Optigob(json_config=config, db_file_path=None)  # None uses the bundled database
optigob.run()

results = optigob.get_results()   # Results object, year-indexed DataFrames per output category
print(results.ghg)                # emissions; also .area, .protein, .energy, .hwp, .substitution,
                                  # .biodiversity, .livestock_population, and .net_zero()
print(optigob.target_achieved())  # did the scenario meet its net-zero / split-gas target?
```

`Results` also offers `.plot(category)` (matplotlib), `.to_csv(path)`, and `.to_excel(path)`.
See `examples/config.json` for a full example scenario exercising every field type (forestry, organic soils, non-cattle agriculture, cattle agriculture, anaerobic digestion).

## Architecture

The `Optigob` class (`src/optigob_ts/optigob.py`) is the central orchestrator. It builds a list of `Field` objects (one per sector present in the config: `Forestry`, `NonCattleAgriculture`, `CattleAgriculture`, `OrganicSoils`, `AnaerobicDigestion`, defined in `src/optigob_ts/systems/`), each of which owns a list of `System` objects.

- **Waypoints**: a `System`'s `run()` walks its waypoints in the order given, computing a target parameter dict for each waypoint year and calling the shared `update_time_series()` (in `systems/abstract_factory.py`), which linearly interpolates every numeric field from its last known value up to the new target, one year at a time. After the last waypoint, the series is flat-held out to the target year.
- **Data**: `resource_manager/database_manager.py` queries a bundled SQLite database (`src/optigob_ts/database/optigob_ts_default_0.1.1.db`) for baseline values and scenario scalers. Pass a custom `db_file_path` to `Optigob(...)` to use a different database with the same schema. Rebuild it from the source spreadsheets with `python tools/create_database.py`.
- **Cross-field area balancing**: after all fields run, `Optigob.area_balancing()` reconciles land freed up by shrinking livestock/afforestation/AD area back into a "spared area" bucket, and reconciles afforestation's organic soil area against the "organic soil under grass" system.

To rebuild the bundled database from its source spreadsheets (`tools/data_sources/*.xlsx`):

```bash
python tools/create_database.py
```

## Livestock optimiser (opt-in)

By default, `cattle_systems` uses a fixed heuristic to split each waypoint's emissions budget between dairy and beef (beef absorbs cuts first, down to zero; dairy absorbs any surplus first). Adding `ratio_type`/`ratio_value` to the `cattle_systems` block (or to an individual waypoint, to override the block-level default) activates a Pyomo-based optimiser instead — `src/optigob_ts/systems/livestock_optimisation.py`, modelled directly on `optigob`'s own `LivestockOptimisation` — which solves for the dairy/beef split that maximises herd size subject to the waypoint's emissions budget, an area budget (computed from land freed up by sheep/afforestation/AD relative to their own baselines), and a fixed ratio constraint:

```json
"cattle_systems": {
    "abatement": "2020 BL",
    "productivity": "2020 Prod",
    "ratio_type": "dairy_per_beef",
    "ratio_value": 2.0,
    "waypoints": [ ... ]
}
```

`ratio_type` is `"dairy_per_beef"` or `"beef_per_dairy"`, matching `optigob`'s own convention. Requires the `optimise`/`full` extra (`highspy`) installed. Run `tests/example.py` to see a side-by-side comparison of the heuristic vs. optimiser split on the same scenario. See `tests/test_livestock_optimisation.py` for further worked examples, and `claude-docs/cattle-optimisation.md` in the parent monorepo for the design rationale.

## License

MIT.
