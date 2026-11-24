"""The animated map page (web/heat_story/index.html) knows every kind of heat user the model has.

A kind missing from its GROUP_OF table used to throw in the monthly chart before the map was drawn,
so the page stayed on "Drawing the map..." (public, hotel and factory were added to the model later)."""
import re
from pathlib import Path

from dcopt.heat.v1 import KINDS

PAGE = Path(__file__).resolve().parents[1] / "web" / "heat_story" / "index.html"


def test_every_model_kind_has_a_colour_group_on_the_map_page():
    table = re.search(r"const GROUP_OF = \{(.*?)\};", PAGE.read_text(encoding="utf-8")).group(1)
    groups = dict(re.findall(r"(\w+):\s*\"(\w+)\"", table))
    assert set(KINDS) <= set(groups), f"add to GROUP_OF in index.html: {sorted(set(KINDS) - set(groups))}"
    assert set(groups.values()) <= {"farm", "building", "snow"}
