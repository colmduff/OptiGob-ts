from .common.keys import *
from .common.gwp import get_gwp_values

from .resource_manager.database_manager import DatabaseManager

from .systems.cattle_agriculture import CattleAgriculture, DEFAULT_DEPLOYMENT_YEAR
from .systems.forestry import Forestry
from .systems.non_cattle_agriculture import NonCattleAgriculture
from .systems.organic_soils import OrganicSoils
from .systems.ad_emissions import AnaerobicDigestion
from .scalers import apply_scalers
from .balancing import balance_areas, validate_land_balance


class Optigob:
    """Top-level orchestrator for a single scenario run.

    Builds one `Field` per land-use system present in `json_config`
    (forestry, non_cattle_agriculture, cattle_systems, organic_soils,
    ad_emissions -- each a top-level config key), loads their baseline data
    from the bundled DB, and exposes methods to run the scenario forward to
    `target_year` and read back results.

    This class is intentionally thin: scaler calibration lives in
    `scalers.py`, cross-field area reconciliation in `balancing.py`,
    whole-scenario emissions math in `emissions.py`, and all reporting/
    presentation in the `results` package -- `Optigob` only wires those
    together in the right order.

    Typical usage:
        optigob = Optigob(json_config=config, db_file_path=db_path)
        optigob.run()
        results = optigob.get_results()
    """

    def __init__(self, json_config, db_file_path):
        self.baseline_year = json_config[BASELINE_YEAR]
        self.target_year = json_config[TARGET_YEAR]
        self.gwp = get_gwp_values(json_config.get(AR, "AR5"))
        self.fields = []
        self.db_manager = DatabaseManager(db_file_path)

        # Forestry anchors its whole time series to the database's first year
        # (it reads the full year-ordered trajectory and treats row 0 as the
        # baseline), while every other sector anchors to `baseline_year`. If
        # the two disagree, forestry would silently misalign against everything
        # else (bug #11), so require them to match up front.
        db_baseline_year = self.db_manager.get_baseline_year()
        if db_baseline_year is not None and self.baseline_year != db_baseline_year:
            raise ValueError(
                f"baseline_year={self.baseline_year} does not match the "
                f"database's first year ({db_baseline_year}). Forestry anchors "
                f"its time series to the database's first year, so the two must "
                f"be equal -- set baseline_year={db_baseline_year}, or supply a "
                f"database whose first year is {self.baseline_year}."
            )

        # The year a selected cattle abatement/productivity reaches full effect.
        # Deliberately independent of target_year and of the waypoints: it is a
        # scenario property, not a user target, so "Frontier" must mean the same
        # deployment rate no matter where the user puts their checkpoints. See
        # claude-docs/abatement-deployment-ramp.md.
        self.deployment_year = json_config.get(DEPLOYMENT_YEAR, DEFAULT_DEPLOYMENT_YEAR)
        if self.deployment_year <= self.baseline_year:
            raise ValueError(
                f"deployment_year must be after baseline_year "
                f"({self.baseline_year}), got {self.deployment_year!r}"
            )

        self.split_gas = json_config.get(SPLIT_GAS, False)
        self.split_gas_frac = json_config.get(SPLIT_GAS_FRAC, None)
        if self.split_gas and self.split_gas_frac is None:
            raise ValueError(
                "split_gas=True requires split_gas_frac to be set (fraction of "
                "baseline whole-AFOLU CH4 that may remain, e.g. 0.7 for a 30% "
                "reduction target)."
            )
        if self.split_gas_frac is not None and not (0 <= self.split_gas_frac <= 1):
            raise ValueError(f"split_gas_frac must be between 0 and 1, got {self.split_gas_frac!r}")

        # Fraction of baseline allowed to remain for the net-zero check --
        # "how much remains" convention, same as `scaler`/`split_gas_frac`
        # (0 = must reach net zero exactly, today's default behaviour).
        self.net_zero_frac = json_config.get(NET_ZERO_FRAC, 0)
        if not (0 <= self.net_zero_frac <= 1):
            raise ValueError(f"net_zero_frac must be between 0 and 1, got {self.net_zero_frac!r}")

        if FORESTRY in json_config:
            self.fields.append(Forestry(json_config[FORESTRY]))

        if NON_CATTLE_AGRICULTURE in json_config:
            self.fields.append(NonCattleAgriculture(json_config[NON_CATTLE_AGRICULTURE]))

        if CATTLE_AGRICULTURE in json_config:
            self.fields.append((CattleAgriculture(json_config[CATTLE_AGRICULTURE])))

        if ORGANIC_SOILS in json_config:
            self.fields.append(OrganicSoils(json_config[ORGANIC_SOILS]))

        if AD_EMISSIONS in json_config:
            self.fields.append(AnaerobicDigestion(json_config[AD_EMISSIONS]))

        for fi in self.fields:
            fi.load_data(self.db_manager, self.gwp)

        apply_scalers(self.fields, self.db_manager, self.baseline_year)

    def run(self):
        """Advance every field's time series from `baseline_year` to
        `target_year` and reconcile cross-field area dependencies.

        Order matters: every field runs its own `run()` first (this is where
        non-cattle agriculture and forestry's waypoints get resolved), then
        `CattleAgriculture.run_cattle_systems()` runs separately because it
        needs non-cattle's already-resolved emissions to compute its own
        budget, then `balancing.validate_land_balance()` checks that no
        land pool would ever go negative (raising `ValueError` if this
        scenario's config asks for more land than exists), and finally
        `balancing.balance_areas()` reconciles area that one field's
        growth/shrinkage displaces into another (e.g. spared cattle land
        absorbed by afforestation or AD feedstock area) -- validation runs
        first specifically so that bookkeeping can never go negative.
        """
        nca = None
        forestry = None
        ad_emissions = None
        for fi in self.fields:
            fi.run(self.baseline_year, self.target_year, self.db_manager, self.gwp)

            if isinstance(fi, NonCattleAgriculture):
                nca = fi
            elif isinstance(fi, Forestry):
                forestry = fi
            elif isinstance(fi, AnaerobicDigestion):
                ad_emissions = fi

        for fi in self.fields:
            if isinstance(fi, CattleAgriculture):
                fi.run_cattle_systems(self.baseline_year, self.target_year, self.db_manager, nca,
                                      forestry=forestry, ad_emissions=ad_emissions,
                                      gwp=self.gwp, split_gas=self.split_gas,
                                      deployment_year=self.deployment_year)

        validate_land_balance(self.fields, self.baseline_year, self.target_year)
        balance_areas(self.fields, self.baseline_year, self.target_year)

    def get_field(self, name):
        """Look up one of this scenario's `Field`s by its `common/keys.py`
        name constant (e.g. `FORESTRY`, `CATTLE_AGRICULTURE`), or `None` if
        that field wasn't included in this scenario's config.
        """
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def get_net_zero_calculations(self):
        """Whole-scenario net-zero emissions series -- see
        `emissions.compute_net_zero` for exactly what `co2e`,
        `co2e_split_gas`, and `total_ch4` each mean (they are NOT three
        interchangeable CO2e figures).
        """
        from .emissions import compute_net_zero
        time_span = self.target_year - self.baseline_year + 1
        return compute_net_zero(self.fields, self.gwp, time_span)

    def check_net_zero_status(self, epsilon=1e-6):
        """Whole-scenario pass/fail against two independent, purely post-hoc
        targets -- unrelated to whatever the cattle waypoints' own `scaler`/
        `ch4_scaler` envelopes actually enforced along the way. Both use the
        "fraction of baseline that remains" convention (same as `scaler`):
        `net_zero_frac`/`split_gas_frac` are the maximum allowed residual
        fraction of baseline, not a reduction fraction. `epsilon` is only
        float-comparison slack, not a meaningful tolerance band.

        - "net_zero": final `co2e` (all gases, if `split_gas=False`) or final
          `co2_n2o_co2e` (CO2+N2O only, if `split_gas=True`) is at most
          `net_zero_frac` of that same metric's baseline value.
        - "split_gas_ch4": final whole-AFOLU `total_ch4` (every sector, not
          just cattle) is at most `split_gas_frac` of baseline CH4. `None` if
          `split_gas_frac` was never configured (no target to check against).
          Deliberately independent of the cattle waypoints' own `ch4_scaler`
          values -- a scenario can hit every one of its own waypoint targets
          and still fail this whole-sector scorecard if those targets weren't
          ambitious enough.

        Unlike OptiGob's method of the same name (which returns a single bool,
        picked by its SIP's `split_gas` flag), this always returns both.
        """
        co2e, co2_n2o_co2e, total_ch4 = self.get_net_zero_calculations()

        net_zero_metric = co2_n2o_co2e if self.split_gas else co2e
        net_zero = bool(net_zero_metric[-1] <= net_zero_metric[0] * self.net_zero_frac + epsilon)

        split_gas_ch4 = None
        if self.split_gas_frac is not None:
            split_gas_ch4 = bool(total_ch4[-1] <= total_ch4[0] * self.split_gas_frac + epsilon)

        return {"net_zero": net_zero, "split_gas_ch4": split_gas_ch4}

    def target_achieved(self, epsilon=1e-6):
        """Single pass/fail for whichever target this scenario's config
        actually set out to hit -- resolved automatically from `split_gas`,
        so callers don't need to know or care which mode a scenario is in.
        This is the single-bool convenience OptiGob's `check_net_zero_status()`
        provides directly; here it's built on top of this package's
        `check_net_zero_status()`, which always returns both booleans.

        Returns `check_net_zero_status(epsilon)["split_gas_ch4"]` if
        `split_gas=True` (guaranteed to be a real bool in that case, since
        `split_gas=True` requires `split_gas_frac` -- see `__init__`), else
        `check_net_zero_status(epsilon)["net_zero"]`.
        """
        status = self.check_net_zero_status(epsilon)
        return status["split_gas_ch4"] if self.split_gas else status["net_zero"]

    def get_results(self):
        """Return a `Results` (see `results.py`): this run's output
        organized by category -- `.area`, `.ghg`, `.protein`,
        `.biodiversity`, `.energy`, `.hwp`, `.substitution`,
        `.livestock_population` each a DataFrame, plus `.net_zero()` and
        `.plot(category)`.
        """
        from .results import Results
        return Results(self)
