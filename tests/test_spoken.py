import pytest

from atc import spoken


def words(text):
    return [t.lower() for t in spoken.tokens(text)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("runway two eight right", ["28R"]),
        ("hold short runway one eight", ["18"]),
        ("cleared to land runway niner left", ["09L"]),
        ("runway two eight right and runway one niner left", ["28R", "19L"]),
        ("taxi to the ramp", []),
    ],
)
def test_runways(text, expected):
    assert spoken.runways(words(text)) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("contact tower one two zero point five", [120500]),
        ("departure one three five point one zero zero", [135100]),
        ("one two one point eight then one one eight point two", [121800, 118200]),
        ("squawk four five two one", []),
    ],
)
def test_frequencies(text, expected):
    assert spoken.frequencies(words(text)) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("maintain eight thousand", [("alt", 8000)]),
        ("maintain three thousand five hundred", [("alt", 3500)]),
        ("climb and maintain one one thousand five hundred", [("alt", 11500)]),
        ("maintain one zero thousand", [("alt", 10000)]),
        ("descend and maintain eleven thousand", [("alt", 11000)]),
        ("maintain two thousand five", [("alt", 2005)]),
        ("climb flight level two four zero", [("fl", 24000)]),
        ("squawk four five two one heading two seven zero", []),
    ],
)
def test_altitudes(text, expected):
    assert spoken.altitudes(words(text)) == expected


def test_headings_and_squawks():
    w = words("turn left heading two seven zero, squawk four five two one")
    assert spoken.headings(w) == [270]
    assert spoken.squawks(w) == ["4521"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("taxi via alpha, bravo one, hold short runway two eight", ["A", "B1"]),
        ("taxi via alpha bravo", ["A", "B"]),
        ("cross taxiway charlie", ["C"]),
        ("taxi via charlie, cross runway one niner", ["C"]),
        ("runway two eight right", []),
    ],
)
def test_taxiways(text, expected):
    assert spoken.taxiways(words(text)) == expected
