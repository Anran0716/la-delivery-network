"""Continuous-allocation CFLP v1 with optional strong opening links."""

import os
import re
import time
from pathlib import Path

import pulp

from lanet.check import check_solution
from lanet.problem import FacilityData


def build_model(
    data: FacilityData,
    linking: str = "strong",
    *,
    full_service: bool = False,
    single_source: bool = False,
    fixed_openings: dict | None = None,
) -> tuple:
    """x and s are fractions; capacity and demand are parcels per day."""
    data.validate()
    if linking not in {"strong", "weak"}:
        raise ValueError("Linking must be strong or weak")
    problem = pulp.LpProblem(f"cflp_{linking}", pulp.LpMinimize)
    y = {i: pulp.LpVariable(f"y_{k:04d}", cat=pulp.LpBinary) for k, i in enumerate(data.capacity)}
    if fixed_openings is not None:
        if fixed_openings.keys() != data.capacity.keys() or any(
            value not in (0, 1) for value in fixed_openings.values()
        ):
            raise ValueError("Fixed openings must specify every station as 0 or 1")
        for station, value in fixed_openings.items():
            y[station].bounds(value, value)
    x = {arc: pulp.LpVariable(f"x_{k:06d}", 0, 1) for k, arc in enumerate(data.unit_cost)}
    s = {
        j: pulp.LpVariable(f"s_{k:05d}", 0, 0 if full_service else 1)
        for k, j in enumerate(data.demand)
    }
    w = (
        {
            arc: pulp.LpVariable(f"w_{k:06d}", cat=pulp.LpBinary)
            for k, arc in enumerate(data.unit_cost)
        }
        if single_source
        else {}
    )
    if single_source and full_service:
        # With s=0, sum(x)=1, x<=w and sum(w)<=1 imply x=w exactly.
        # Eliminate the duplicate continuous columns for hard-service v2 runs.
        x = w
    by_station = {i: [] for i in y}
    by_cell = {j: [] for j in s}
    for (i, j), variable in x.items():
        by_station[i].append(data.demand[j] * variable)
        by_cell[j].append(variable)
        if single_source:
            if not full_service:
                problem += variable <= w[i, j], f"service_link_{len(problem.constraints)}"
            problem += w[i, j] <= y[i], f"opening_link_{len(problem.constraints)}"
        elif linking == "strong":
            problem += variable <= y[i], f"link_{len(problem.constraints)}"
    problem += (
        pulp.lpSum(data.fixed_cost[i] * variable for i, variable in y.items())
        + pulp.lpSum(data.unit_cost[i, j] * data.demand[j] * var for (i, j), var in x.items())
        + data.unmet_penalty * pulp.lpSum(data.demand[j] * var for j, var in s.items())
    )
    for k, j in enumerate(s):
        problem += pulp.lpSum(by_cell[j]) + s[j] == 1, f"balance_{k}"
        if single_source and not full_service:
            problem += pulp.lpSum(w[i, j] for i in y if (i, j) in w) <= 1, f"single_source_{k}"
    for k, i in enumerate(y):
        problem += (
            pulp.lpSum(by_station[i]) <= data.utilization_limit * data.capacity[i] * y[i],
            f"capacity_{k}",
        )
    return problem, y, x, s, w


def parse_cbc_log(log: str) -> dict:
    """Use CBC's actual termination/bounds, not PuLP's coarse status alone."""

    def number(pattern):
        matches = re.findall(pattern, log, flags=re.MULTILINE)
        return float(matches[-1]) if matches else None

    numeric = r"([-+0-9.eE]+)"
    result_lines = re.findall(r"^Result - (.+)$", log, flags=re.MULTILINE)
    reason = result_lines[-1].strip() if result_lines else "No final CBC result line"
    objective = number(r"^Objective value:\s*" + numeric)
    lower = number(r"^Lower bound:\s*" + numeric)
    proven = reason == "Optimal solution found"
    if proven and objective is not None:
        lower = objective
    gap = (
        max(0.0, objective - lower) / max(abs(objective), 1e-12)
        if (objective is not None and lower is not None)
        else None
    )
    return {
        "termination_reason": reason,
        "proven_optimal": proven,
        "incumbent_objective_log": objective,
        "best_bound": lower,
        "relative_gap": gap,
        "gap_definition": "(incumbent - lower_bound) / abs(incumbent)",
        "initial_lp_objective": number(r"Continuous objective value is " + numeric),
        "cbc_wall_seconds": number(r"^Time \(Wallclock seconds\):\s*" + numeric),
        "enumerated_nodes": number(r"^Enumerated nodes:\s*" + numeric),
    }


def solve_model(
    data: FacilityData,
    linking: str,
    work_dir: str | Path,
    time_limit_seconds: float = 600,
    relative_gap: float = 0.005,
    *,
    full_service: bool = False,
    single_source: bool = False,
    fixed_openings: dict | None = None,
    warm_start: dict | None = None,
) -> dict:
    """Run CBC sequentially in an isolated directory with relative filenames.

    PuLP 3.3 splits its CBC command on spaces, so all solver input/output names
    are relative to work_dir. This function changes cwd and is not thread-safe.
    """
    started = time.perf_counter()
    problem, y_vars, x_vars, s_vars, w_vars = build_model(
        data,
        linking,
        full_service=full_service,
        single_source=single_source,
        fixed_openings=fixed_openings,
    )
    warm_validation = None
    if warm_start is not None:
        warm_validation = check_solution(
            warm_start["y"],
            warm_start["x"],
            warm_start["s"],
            data,
            w=warm_start.get("w"),
            single_source=single_source,
            require_full_service=full_service,
            fixed_openings=fixed_openings,
        )
        for variables, values in (
            (y_vars, warm_start["y"]),
            (x_vars, warm_start["x"]),
            (s_vars, warm_start["s"]),
            (w_vars, warm_start.get("w", {})),
        ):
            for key, variable in variables.items():
                variable.setInitialValue(
                    max(variable.lowBound, min(variable.upBound, values.get(key, 0)))
                )
    build_seconds = time.perf_counter() - started
    folder = Path(work_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    try:
        os.chdir(folder)
        solver = pulp.PULP_CBC_CMD(
            timeLimit=time_limit_seconds,
            gapRel=relative_gap,
            msg=False,
            keepFiles=True,
            logPath="cbc.log",
            warmStart=warm_start is not None,
            # CBC 0 selects native serial execution. A worker setting of 1
            # still creates parallel coordination threads in the bundled build.
            threads=0,
            options=["randomSeed 1", "randomCbcSeed 1"],
            timeMode="elapsed",
        )
        solve_started = time.perf_counter()
        problem.solve(solver)
        solve_seconds = time.perf_counter() - solve_started
    finally:
        os.chdir(previous)
    metadata = parse_cbc_log((folder / "cbc.log").read_text(encoding="utf-8"))
    metadata.update(
        {
            "linking": linking,
            "pulp_status": pulp.LpStatus[problem.status],
            "pulp_solution_status": pulp.LpSolution[problem.sol_status],
            "build_seconds": build_seconds,
            "solve_wall_seconds": solve_seconds,
            "time_limit_seconds": time_limit_seconds,
            "requested_relative_gap": relative_gap,
            "cbc_threads_parameter": 0,
            "execution_mode": "native_serial",
            "random_seed": 1,
            "warm_start": warm_start is not None,
            "warm_start_checked": warm_validation is not None,
            "warm_start_objective": warm_validation["objective"] if warm_validation else None,
            "full_service": full_service,
            "single_source": single_source,
            "variables": len(problem.variables()),
            "constraints": len(problem.constraints),
        }
    )
    if problem.sol_status not in {pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible}:
        raise ValueError(f"CBC has no integer feasible incumbent: {metadata}")
    y = {i: var.value() for i, var in y_vars.items()}
    x = {arc: var.value() for arc, var in x_vars.items()}
    s = {j: var.value() for j, var in s_vars.items()}
    w = {arc: var.value() for arc, var in w_vars.items()}
    objective = float(pulp.value(problem.objective))
    validation = check_solution(
        y,
        x,
        s,
        data,
        objective=objective,
        w=w if single_source else None,
        single_source=single_source,
        require_full_service=full_service,
        fixed_openings=fixed_openings,
    )
    return {"y": y, "x": x, "s": s, "w": w, "validation": validation, "solver": metadata}
