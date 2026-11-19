"""Pass only independently validated PuLP initial values to HiGHS."""

import numpy as np
import pulp


class CheckedHiGHS(pulp.HiGHS):
    def callSolver(self, lp):
        variables = [v for v in lp.variables() if v.varValue is not None]
        if variables:
            status = lp.solverModel.setSolution(
                len(variables),
                np.array([v.index for v in variables], dtype=np.int32),
                np.array([v.varValue for v in variables], dtype=np.float64),
            )
            if str(status) != "HighsStatus.kOk":
                raise ValueError(f"HiGHS rejected checked start: {status}")
        super().callSolver(lp)
