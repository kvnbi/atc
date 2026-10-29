import pytest

from atc import spoken


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Runway 28R, squawk 1200, heading 270", "Runway two eight right, squawk one two zero zero, heading two seven zero"),
        ("Contact departure 135.1", "Contact departure one three five point one"),
        ("maintain 3,500 then 10000", "maintain three thousand five hundred then one zero thousand"),
        ("Climb FL240 via SSTIK5 departure", "Climb flight level two four zero via SSTIK five departure"),
        ("Cessna 1-2-3 Alpha Bravo", "Cessna one two three Alpha Bravo"),
        ("N123AB ready", "november one two three alpha bravo ready"),
        ("altimeter 2996", "altimeter two niner niner six"),
        ("Holding short runway 2-8 Right", "Holding short runway two eight Right"),
        ("no digits here", "no digits here"),
    ],
)
def test_normalize(text, expected):
    assert spoken.normalize(text) == expected


def test_spell():
    assert spoken.spell("N123AB") == "november one two three alpha bravo"
    assert spoken.spell("3AB") == "three alpha bravo"
