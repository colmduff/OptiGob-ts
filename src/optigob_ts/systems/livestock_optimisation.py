from ..common.logger import get_logger

logger = get_logger("livestock_optimisation")


class OptimisationResult(dict):
    """
    A convenience wrapper for optimisation outputs that always includes status and message,
    and supports a .feasible property for quick checks.
    """
    @property
    def feasible(self):
        return self.get("status", "ok") == "ok"


class LivestockOptimisation:
    """
    Solves for the dairy/beef scalers to apply to a pair of reference DB rows
    (the same rows CattleWayPoint.get_data() already fetches for the
    heuristic split), subject to a fixed dairy:beef ratio, an area budget,
    and an emissions budget -- the OptiGob-ts analogue of OptiGob's
    livestock/livestock_optimisation.py, adapted to OptiGob-ts's reference-row
    data shape instead of OptiGob's per-unit scaler tables.

    The LP is solved by calling HiGHS **in-process via highspy directly**, not
    through Pyomo's ``SolverFactory``. This is deliberate: both Pyomo solver
    interfaces for HiGHS wrap every solve in ``capture_output(capture_fd=True)``
    (executable *and* APPSI), which redirects the process-global stdout/stderr
    file descriptors and spawns a ``_mergedReader`` thread to drain them on every
    solve. run_cattle_systems() re-solves once per simulation year, so a single
    run spawned dozens of those reader threads; under the dashboard's repeated
    reruns (Streamlit runs the script in a worker thread and re-executes it on
    every widget interaction) the fd-level capture raced across threads and one
    ``_mergedReader`` eventually crashed, wedging the app. Calling highspy
    directly with ``output_flag=False`` avoids the tee entirely -- no subprocess,
    no fd capture, no reader thread -- and is markedly faster (no per-solve
    model-file write / process spawn).
    """

    def __init__(self, solver_name="highs"):
        # Retained for backward compatibility (and the SIP ``solver_name`` field);
        # no longer used to select a Pyomo solver plugin -- the optimiser now calls
        # HiGHS directly via highspy in optimise().
        self.solver_name = solver_name or "highs"

    def scalar(self, x):
        if hasattr(x, "item"):
            return float(x.item())
        return float(x)

    def optimise(self,
                 dairy_waypoint_data,
                 beef_waypoint_data,
                 scale_parameter,
                 ratio_type,
                 ratio_value,
                 emissions_budget,
                 area_commitment,
                 ch4_budget=None):
        """
        Solve for dairy_scaler/beef_scaler such that:
          - dairy_scaler / beef_scaler honour the given ratio,
          - combined area used (dairy's own area_dairy+area_beef, beef's area_beef)
            does not exceed area_commitment,
          - combined `scale_parameter` (e.g. co2e) does not exceed emissions_budget,
          - if ch4_budget is not None (split-gas mode), combined raw CH4 does not
            exceed ch4_budget -- a second, independent hard constraint, mirroring
            OptiGob's split-gas livestock optimiser. In that mode scale_parameter
            is expected to already be "co2_n2o_co2e" (CO2+N2O only, CH4 excluded)
            so the primary budget and the CH4 budget are never double-counting CH4.
          - subject to those constraints, total (dairy_scaler + beef_scaler) is maximised.

        Returns an OptimisationResult with "dairy_scaler"/"beef_scaler" -- a
        drop-in replacement for the values the heuristic split computes today.
        """
        dairy_area = self.scalar(dairy_waypoint_data["area_dairy"]) + self.scalar(dairy_waypoint_data["area_beef"])
        beef_area = self.scalar(beef_waypoint_data["area_beef"])

        dairy_metric = self.scalar(dairy_waypoint_data[scale_parameter])
        beef_metric = self.scalar(beef_waypoint_data[scale_parameter])

        logger.debug(
            "optimise: ratio_type=%s ratio_value=%s emissions_budget=%.1f area_commitment=%.1f "
            "dairy_area(per unit)=%.4f beef_area(per unit)=%.4f dairy_%s(per unit)=%.4f beef_%s(per unit)=%.4f",
            ratio_type, ratio_value, emissions_budget, area_commitment,
            dairy_area, beef_area, scale_parameter, dairy_metric, scale_parameter, beef_metric,
        )

        if ratio_type not in ("dairy_per_beef", "beef_per_dairy"):
            raise ValueError(f"Invalid ratio_type: {ratio_type}. Must be 'dairy_per_beef' or 'beef_per_dairy'.")

        try:
            import highspy
        except ImportError as e:  # pragma: no cover - environment guard
            raise ImportError(
                "highspy is required for livestock optimisation. Install the 'optimise' "
                "or 'full' extra (e.g. `poetry install -E full`)."
            ) from e

        h = highspy.Highs()
        # Silence the solver: no console output means Pyomo-style output capture
        # (TeeStream / _mergedReader / fd redirection) is never needed. Keeps the
        # solve fully in-process and thread-safe under the dashboard's reruns.
        h.setOptionValue("output_flag", False)

        beef = h.addVariable(lb=0)   # beef_scaler  (was model.x)
        dairy = h.addVariable(lb=0)  # dairy_scaler (was model.y)

        h.addConstr(beef * beef_area + dairy * dairy_area <= area_commitment)

        if ratio_type == "dairy_per_beef":
            h.addConstr(dairy == ratio_value * beef)
        else:  # beef_per_dairy (validated above)
            h.addConstr(beef == ratio_value * dairy)

        h.addConstr(beef * beef_metric + dairy * dairy_metric <= emissions_budget)

        if ch4_budget is not None:
            dairy_ch4 = self.scalar(dairy_waypoint_data["ch4"])
            beef_ch4 = self.scalar(beef_waypoint_data["ch4"])
            h.addConstr(beef * beef_ch4 + dairy * dairy_ch4 <= ch4_budget)

        h.maximize(beef + dairy)

        status = h.getModelStatus()
        if status != highspy.HighsModelStatus.kOptimal:
            error_msg = (
                "Livestock optimisation infeasible: no feasible dairy/beef split exists for this "
                "waypoint's ratio, area, and emissions budget combination.\n"
                f"emissions_budget={emissions_budget}, area_commitment={area_commitment}, "
                f"ratio_type={ratio_type}, ratio_value={ratio_value}, ch4_budget={ch4_budget}, "
                f"model_status={h.modelStatusToString(status)}."
            )
            logger.warning("optimise: INFEASIBLE (model_status=%s)", h.modelStatusToString(status))
            return OptimisationResult({
                "status": "infeasible",
                "message": error_msg,
                "dairy_scaler": 0.0,
                "beef_scaler": 0.0,
            })

        beef_scaler = h.variableValue(beef)
        dairy_scaler = h.variableValue(dairy)

        if beef_scaler is None or dairy_scaler is None:
            error_msg = (
                "Livestock optimisation did not return a usable solution "
                f"(model_status={h.modelStatusToString(status)})."
            )
            return OptimisationResult({
                "status": "infeasible",
                "message": error_msg,
                "dairy_scaler": 0.0,
                "beef_scaler": 0.0,
            })

        area_used = beef_scaler * beef_area + dairy_scaler * dairy_area
        emissions_used = beef_scaler * beef_metric + dairy_scaler * dairy_metric
        if ratio_type == "dairy_per_beef":
            achieved_ratio = dairy_scaler / beef_scaler if beef_scaler > 0 else float("inf")
        else:
            achieved_ratio = beef_scaler / dairy_scaler if dairy_scaler > 0 else float("inf")
        logger.info(
            "optimise: OK dairy_scaler=%.6f beef_scaler=%.6f achieved_%s=%.6f (configured ratio_value=%s) "
            "area_used=%.1f/%.1f (%.1f%% of area_commitment) emissions_used=%.1f/%.1f (%.1f%% of emissions_budget)",
            dairy_scaler, beef_scaler, ratio_type, achieved_ratio, ratio_value,
            area_used, area_commitment, 100 * area_used / area_commitment if area_commitment else 0.0,
            emissions_used, emissions_budget, 100 * emissions_used / emissions_budget if emissions_budget else 0.0,
        )

        return OptimisationResult({
            "status": "ok",
            "dairy_scaler": dairy_scaler,
            "beef_scaler": beef_scaler,
        })
