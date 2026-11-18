"""Flag and summarize low-demand cells while retaining every demand record."""

import argparse
import json
from pathlib import Path

import pandas as pd

from lanet import load_config
from lanet.demand import mark_low_demand


def main(config_path: str) -> None:
    path = Path(config_path).resolve()
    config = load_config(path)
    processed = path.parent / config["data"]["processed_dir"]
    cells_path = processed / "demand_cells.parquet"
    original = pd.read_parquet(cells_path)
    cells, report = mark_low_demand(
        original,
        config["demand"]["low_demand_parcels_per_day"],
        config["demand"]["parcels_per_household_per_day"],
    )
    assert len(cells) == len(original)
    assert cells.parcels.sum() == original.parcels.sum()
    cells.to_parquet(cells_path, index=False)
    cells.loc[cells.low_demand].to_csv(processed / "low_demand_cells.csv", index=False)
    (processed / "low_demand_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    demand_path = processed / "demand_report.json"
    demand_report = json.loads(demand_path.read_text(encoding="utf-8"))
    demand_report["low_demand"] = report
    demand_path.write_text(json.dumps(demand_report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    main(parser.parse_args().config)
