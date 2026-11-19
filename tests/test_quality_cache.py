import importlib.util
from pathlib import Path

import pandas as pd
import pytest
from test_v2 import toy


def test_quality_cache_preserves_checked_metadata_without_resolving(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "04_quality.py"
    spec = importlib.util.spec_from_file_location("quality_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = toy()
    frames = {
        "candidates": pd.DataFrame({"candidate_id": list(data.capacity)}),
        "demand": pd.DataFrame({"h3": list(data.demand), "parcels": list(data.demand.values())}),
        "excluded": pd.DataFrame(columns=["h3", "parcels"]),
    }
    module.run(tmp_path, data, frames, single=True, full=True, seconds=10)

    def forbidden(*args, **kwargs):
        pytest.fail("A checked matching cache must not invoke the solver")

    monkeypatch.setattr(module, "solve_model", forbidden)
    result, summary = module.run(tmp_path, data, frames, single=True, full=True, seconds=10)
    assert result["validation"]["objective"] == pytest.approx(100)
    assert result["solver"] == summary["solver"]
    with pytest.raises(ValueError, match="settings differ"):
        module.run(tmp_path, data, frames, single=True, full=True, seconds=20)
