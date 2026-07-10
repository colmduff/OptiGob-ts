from pyomo.environ import ConcreteModel, Var, Constraint, Objective, NonNegativeReals, maximize, SolverFactory

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
    """

    def __init__(self, solver_name="highs"):
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

        model = ConcreteModel()
        model.x = Var(domain=NonNegativeReals)  # beef_scaler
        model.y = Var(domain=NonNegativeReals)  # dairy_scaler

        model.area_constraint = Constraint(
            expr=(model.x * beef_area + model.y * dairy_area) <= area_commitment
        )

        if ratio_type == "dairy_per_beef":
            model.ratio_constraint = Constraint(expr=model.y == ratio_value * model.x)
        elif ratio_type == "beef_per_dairy":
            model.ratio_constraint = Constraint(expr=model.x == ratio_value * model.y)
        else:
            raise ValueError(f"Invalid ratio_type: {ratio_type}. Must be 'dairy_per_beef' or 'beef_per_dairy'.")

        model.emissions_constraint = Constraint(
            expr=(model.x * beef_metric + model.y * dairy_metric) <= emissions_budget
        )

        if ch4_budget is not None:
            dairy_ch4 = self.scalar(dairy_waypoint_data["ch4"])
            beef_ch4 = self.scalar(beef_waypoint_data["ch4"])
            model.ch4_constraint = Constraint(
                expr=(model.x * beef_ch4 + model.y * dairy_ch4) <= ch4_budget
            )

        model.obj = Objective(expr=model.x + model.y, sense=maximize)

        solver = SolverFactory(self.solver_name)
        # load_solutions=False: some solver backends raise instead of
        # returning gracefully when the model is infeasible if solutions are
        # loaded eagerly. Inspect termination_condition first, and only load
        # variable values once we know a solution actually exists.
        result = solver.solve(model, load_solutions=False)
        termination = str(result.solver.termination_condition).lower()

        if "infeasible" in termination:
            error_msg = (
                "Livestock optimisation infeasible: no feasible dairy/beef split exists for this "
                "waypoint's ratio, area, and emissions budget combination.\n"
                f"emissions_budget={emissions_budget}, area_commitment={area_commitment}, "
                f"ratio_type={ratio_type}, ratio_value={ratio_value}, ch4_budget={ch4_budget}."
            )
            logger.warning("optimise: INFEASIBLE (termination_condition=%s)", termination)
            return OptimisationResult({
                "status": "infeasible",
                "message": error_msg,
                "dairy_scaler": 0.0,
                "beef_scaler": 0.0,
            })

        model.solutions.load_from(result)
        beef_scaler = model.x.value
        dairy_scaler = model.y.value

        if beef_scaler is None or dairy_scaler is None:
            error_msg = (
                "Livestock optimisation did not return a usable solution "
                f"(termination_condition={termination})."
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
