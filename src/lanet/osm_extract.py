"""Build a driving graph from a regional OSM extract when Overpass is unavailable."""

import re
import tempfile
from pathlib import Path

import osmnx as ox
import shapely
from shapely.geometry import LineString

# OSMnx 2.1.2's drive-way exclusions, retained explicitly for the offline source.
DRIVE_EXCLUSIONS = {
    "area": "yes",
    "access": "private",
    "highway": (
        "abandoned|bridleway|bus_guideway|construction|corridor|cycleway|elevator|"
        "escalator|footway|no|path|pedestrian|planned|platform|proposed|raceway|"
        "razed|rest_area|service|services|steps|track"
    ),
    "motor_vehicle": "no",
    "motorcar": "no",
    "service": "alley|driveway|emergency_access|parking|parking_aisle|private",
}


def is_drivable_way(tags: dict[str, str]) -> bool:
    """Apply the project's explicit OSMnx-equivalent public driving filter."""
    return bool(tags.get("highway")) and not any(
        re.search(pattern, tags.get(key, "")) for key, pattern in DRIVE_EXCLUSIONS.items()
    )


def graph_from_extract(pbf: Path, polygon, buffered_polygon, raw: Path):
    """Preserve original node IDs/tags/one-way ways, then simplify with OSMnx."""
    import osmium

    xml = raw / "la_mainland_drive.osm"
    if not xml.exists():
        partial = raw / "la_mainland_drive.partial.osm"
        shapely.prepare(buffered_polygon)
        minx, miny, maxx, maxy = buffered_polygon.bounds

        class RoadCrop(osmium.SimpleHandler):
            def __init__(self, writer):
                super().__init__()
                self.writer = writer
                self.kept = 0

            def way(self, way):
                tags = dict(way.tags)
                if not is_drivable_way(tags) or len(way.nodes) < 2:
                    return
                coordinates = [(node.lon, node.lat) for node in way.nodes]
                xs, ys = zip(*coordinates, strict=True)
                if max(xs) < minx or min(xs) > maxx or max(ys) < miny or min(ys) > maxy:
                    return
                if not shapely.intersects(buffered_polygon, LineString(coordinates)):
                    return
                self.writer.add_way(way)
                self.kept += 1
                if self.kept % 10000 == 0:
                    print(f"Selected drive ways: {self.kept}", flush=True)

        # Windows can retain a libosmium mmap handle until process exit. A locked
        # scratch index must not invalidate the completed, closed OSM output.
        with tempfile.TemporaryDirectory(
            prefix="osm-index-", dir=raw, ignore_cleanup_errors=True
        ) as temp:
            if not Path(temp).resolve().is_relative_to(raw.resolve()):
                raise ValueError("Temporary OSM index escaped the raw data directory")
            index = "sparse_file_array," + str(Path(temp) / "nodes.idx")
            with osmium.BackReferenceWriter(
                partial, ref_src=pbf, overwrite=True, remove_tags=False, relation_depth=0
            ) as writer:
                crop = RoadCrop(writer)
                crop.apply_file(pbf, locations=True, idx=index)
                print(
                    f"Drive ways selected: {crop.kept}; gathering original referenced nodes",
                    flush=True,
                )
        partial.replace(xml)
    print(f"Building directed graph from {xml.name}", flush=True)
    graph = ox.graph_from_xml(xml, simplify=False, retain_all=True, bidirectional=False)
    graph = ox.truncate.truncate_graph_polygon(graph, buffered_polygon, truncate_by_edge=True)
    graph = ox.simplification.simplify_graph(graph)
    return ox.truncate.truncate_graph_polygon(graph, polygon, truncate_by_edge=False)
