"""Cache the mainland OSM driving graph for snapping and later travel-time analysis."""

import argparse
import hashlib
import json
import pickle
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import shapely

from lanet import load_config
from lanet.download import download_file


def main(config_path: str) -> None:
    path = Path(config_path).resolve()
    config = load_config(path)
    raw = path.parent / config["data"]["raw_dir"]
    raw.mkdir(parents=True, exist_ok=True)
    graph_path = raw / config["travel"]["graph_filename"]
    if graph_path.exists():
        print(f"Reusing cached graph: {graph_path}", flush=True)
        return
    year = config["data"]["acs_year"]
    county_id = config["study"]["state_fips"] + config["study"]["county_fips"]
    joined = gpd.read_file(raw / f"block_groups_{county_id}_acs{year}.gpkg")
    projected = joined.to_crs(config["study"]["projected_crs"])
    county = projected.geometry.union_all()
    mainland = max(shapely.get_parts(county), key=lambda part: part.area)
    polygon = gpd.GeoSeries([mainland], crs=projected.crs).to_crs(4326).iloc[0]
    ox.settings.use_cache = True
    ox.settings.cache_folder = raw / "osm_cache"
    ox.settings.log_console = True
    ox.settings.requests_timeout = config["travel"]["request_timeout_seconds"]
    ox.settings.overpass_url = config["travel"]["overpass_url"]
    ox.settings.http_user_agent = config["travel"]["http_user_agent"]
    started = time.monotonic()
    print(f"Downloading mainland {config['travel']['network_type']} graph", flush=True)
    source_details = {}
    if config["travel"]["network_source"] == "geofabrik":
        import osmium

        from lanet.osm_extract import graph_from_extract

        if config["travel"]["network_type"] != "drive":
            raise ValueError("Offline extract filter currently supports drive networks")
        pbf = download_file(config["data"]["osm_extract_url"], raw)
        buffered = (
            gpd.GeoSeries(
                [mainland.buffer(config["travel"]["graph_query_buffer_m"])], crs=projected.crs
            )
            .to_crs(4326)
            .iloc[0]
        )
        graph = graph_from_extract(pbf, polygon, buffered, raw)
        with pbf.open("rb") as stream:
            sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        header = osmium.FileProcessor(pbf).header
        source_details = {
            "pbf_url": config["data"]["osm_extract_url"],
            "pbf_sha256": sha256,
            "pbf_replication_timestamp": header.get("osmosis_replication_timestamp"),
        }
    elif config["travel"]["network_source"] == "overpass":
        graph = ox.graph_from_polygon(
            polygon, network_type=config["travel"]["network_type"], retain_all=True
        )
    else:
        raise ValueError("Unsupported network source")
    # A locally generated binary cache avoids GraphML's large XML parse on reload.
    pickle_path = graph_path.with_suffix(".pickle")
    pickle_partial = pickle_path.with_name(pickle_path.name + ".part")
    with pickle_partial.open("wb") as stream:
        pickle.dump(graph, stream, protocol=pickle.HIGHEST_PROTOCOL)
    pickle_partial.replace(pickle_path)
    partial = graph_path.with_name(graph_path.name + ".part")
    ox.save_graphml(graph, filepath=partial)
    partial.replace(graph_path)
    report = {
        "source": "OpenStreetMap via " + config["travel"]["network_source"],
        **source_details,
        "network_type": config["travel"]["network_type"],
        "nodes": len(graph),
        "edges": graph.number_of_edges(),
        "seconds": time.monotonic() - started,
        "graph": graph_path.name,
        "graph_pickle": pickle_path.name,
        "overpass_url": config["travel"]["overpass_url"],
        "osmnx_version": ox.__version__,
    }
    (raw / "drive_graph_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    main(parser.parse_args().config)
