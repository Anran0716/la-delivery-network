"""Cache the Geofabrik land-use polygons used to derive industrial candidates."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import requests

from lanet import load_config
from lanet.download import download_file


def main():
    config = load_config()
    raw = Path(config["data"]["raw_dir"])
    url = config["data"]["osm_landuse_url"]
    print("Downloading regional land-use archive", flush=True)
    archive = download_file(url, raw)
    checksum = requests.get(url + ".md5", timeout=(15, 60))
    if checksum.status_code == 404:
        expected = None  # This daily GIS archive does not always publish a sidecar.
    else:
        checksum.raise_for_status()
        expected = checksum.text.split()[0].lower()
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "md5").hexdigest()
    if expected is not None and actual != expected:
        raise ValueError("Land-use ZIP differs from its published MD5; inspect snapshot change")
    folder = raw / "osm_landuse"
    folder.mkdir(exist_ok=True)
    names = []
    with ZipFile(archive) as source:
        for name in source.namelist():
            if Path(name).name == name and ("landuse" in name or "protected_areas" in name):
                destination = folder / name
                partial = destination.with_name(destination.name + ".part")
                with source.open(name) as src, partial.open("wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
                partial.replace(destination)
                names.append(name)
    if not any(name.endswith(".shp") for name in names):
        raise ValueError("No land-use shapefile in the source archive")
    with archive.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {
        "url": url,
        "md5": actual,
        "published_md5_verified": expected is not None,
        "sidecar_status": checksum.status_code,
        "validation": "ZIP CRC checked while reading every selected land-use member",
        "sha256": sha256,
        "members": names,
    }
    (raw / "landuse_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
