"""Round and repair a seed, then validate it before permitting MIP-start use."""

from lanet.check import check_solution


def single_source_start(data, preferred, *, full_service=False, fixed_openings=None):
    candidates = {j: [] for j in data.demand}
    for i, j in data.unit_cost:
        if fixed_openings is None or fixed_openings[i] == 1:
            candidates[j].append(i)
    initial_y = {i: int(preferred["y"].get(i, 0) > 0.5) for i in data.capacity}
    if fixed_openings is not None:
        initial_y = dict(fixed_openings)

    def checked(seed):
        return check_solution(
            seed["y"],
            seed["x"],
            seed["s"],
            data,
            w=seed["w"],
            single_source=True,
            require_full_service=full_service,
            fixed_openings=fixed_openings,
        )

    naive = {"y": dict(initial_y), "x": {}, "s": {}, "w": {}}
    for j in data.demand:
        choices = [i for i in candidates[j] if initial_y[i]]
        if choices:
            i = min(
                choices,
                key=lambda i: (-preferred["x"].get((i, j), 0), data.travel_minutes[i, j], i),
            )
            naive["x"][i, j] = naive["w"][i, j] = 1
            naive["s"][j] = 0
        else:
            naive["s"][j] = 1
    audit = {"naive_rounding_checked": True}
    try:
        report = checked(naive)
        audit.update(
            {
                "naive_rounding_passed": True,
                "repair_used": False,
                "warm_start_checked": True,
                "warm_start_objective": report["objective"],
            }
        )
        return naive, audit
    except ValueError as error:
        audit.update({"naive_rounding_passed": False, "naive_rejection": str(error)})

    # Most constrained cells first protects rare coverage; large demand first
    # avoids consuming the only large residual slots with tiny cells.
    orders = [
        sorted(data.demand, key=lambda j: (len(candidates[j]), -data.demand[j], j)),
        sorted(data.demand, key=lambda j: (-data.demand[j], len(candidates[j]), j)),
    ]
    for all_open in (False, True):
        if all_open and fixed_openings is not None:
            continue
        for order in orders:
            seed = {"y": dict(initial_y), "x": {}, "s": {}, "w": {}}
            if all_open:
                seed["y"] = dict.fromkeys(data.capacity, 1)
            residual = {i: data.capacity[i] * data.utilization_limit for i in data.capacity}
            failed = False
            for j in order:
                choices = candidates[j]
                fitting = [i for i in choices if residual[i] + 1e-9 >= data.demand[j]]
                if fitting:
                    i = min(
                        fitting,
                        key=lambda i: (
                            not seed["y"][i],
                            -preferred["x"].get((i, j), 0),
                            data.travel_minutes[i, j],
                            i,
                        ),
                    )
                    fraction = 1.0
                elif full_service:
                    failed = True
                    break
                else:
                    available = [i for i in choices if residual[i] > 1e-9]
                    if not available:
                        seed["s"][j] = 1.0
                        continue
                    i = min(available, key=lambda i: (-residual[i], data.travel_minutes[i, j], i))
                    fraction = min(1.0, residual[i] / data.demand[j])
                seed["y"][i] = 1
                seed["x"][i, j] = fraction
                seed["w"][i, j] = 1
                seed["s"][j] = 1 - fraction
                residual[i] = max(0.0, residual[i] - fraction * data.demand[j])
            if failed:
                continue
            if fixed_openings is None:
                used = {i for (i, _), value in seed["x"].items() if value > 0}
                seed["y"] = {i: int(i in used) for i in data.capacity}
            try:
                report = checked(seed)
            except ValueError:
                continue
            audit.update(
                {
                    "repair_used": True,
                    "warm_start_checked": True,
                    "warm_start_objective": report["objective"],
                    "warm_start_open_stations": report["open_stations"],
                }
            )
            return seed, audit
    audit.update(
        {
            "repair_used": True,
            "warm_start_checked": False,
            "warm_start_skipped": "No validated rounded/repaired seed; solve cold",
        }
    )
    return None, audit
