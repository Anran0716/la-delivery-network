"""Road-tag fixtures verify the offline driving filter without downloading OSM."""

import pytest

from lanet.osm_extract import is_drivable_way


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"highway": "residential"}, True),
        ({"highway": "motorway", "oneway": "yes"}, True),
        ({"highway": "footway"}, False),
        ({"highway": "service"}, False),
        ({"highway": "residential", "access": "private"}, False),
        ({"highway": "residential", "motor_vehicle": "no"}, False),
        ({"highway": "residential", "motorcar": "no"}, False),
        ({"highway": "residential", "area": "yes"}, False),
    ],
)
def test_offline_drive_filter(tags, expected):
    assert is_drivable_way(tags) is expected
