import pytest

from atc.data import airports


@pytest.fixture(scope="session")
def ksfo():
    try:
        airport = airports.find("KSFO")
    except OSError:
        airport = None
    if airport is None:
        pytest.skip("X-Plane data not found")
    return airport
