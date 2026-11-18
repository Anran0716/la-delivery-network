"""Download and join the official ACS and TIGER county block-group inputs."""

import argparse
import json

from lanet.download import run_download

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    print(json.dumps(run_download(args.config), indent=2))
