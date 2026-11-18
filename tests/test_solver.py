"""Verify CBC executes a tiny MILP without downloading any study data."""

import pulp


def test_bundled_cbc_solves_smoke_problem(tmp_path, monkeypatch):
    assert "PULP_CBC_CMD" in pulp.listSolvers(onlyAvailable=True)
    # PuLP 3.x splits CBC's command string on whitespace. Relative filenames
    # avoid breaking temporary paths when the Windows workspace contains spaces.
    monkeypatch.chdir(tmp_path)
    problem = pulp.LpProblem("cbc_smoke", pulp.LpMinimize)
    opened = pulp.LpVariable("opened", cat=pulp.LpBinary)
    problem += opened
    problem += opened >= 1
    status = problem.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=10, keepFiles=True))
    assert pulp.LpStatus[status] == "Optimal"
    assert pulp.value(opened) == 1
