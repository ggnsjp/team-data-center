"""Names on the maps are shown as text: markup or script in a name must not reach the browser as code
(review issue #45). Facility names come from OpenStreetMap, which anyone can edit."""
import re
from pathlib import Path

import folium

from dcopt.common.style import map_tip

ROOT = Path(__file__).resolve().parents[1]
HOSTILE = '<img src=x onerror=alert(1)> ${alert(2)} `x` \\ "q" & co'


def test_every_line_is_escaped_and_joined():
    assert map_tip("<b>x</b>", "a & b") == "&lt;b&gt;x&lt;/b&gt;<br>a &amp; b"
    assert map_tip("石狩小学校", "", None, "需要 1,200 MWh/年") == "石狩小学校<br>需要 1,200 MWh/年"
    assert map_tip(12.5) == "12.5"


def test_characters_with_a_meaning_in_html_or_in_a_template_literal_are_gone():
    tip = map_tip(HOSTILE)
    for ch in "<>$`\\\"":
        assert ch not in tip
    assert tip.count("&amp;") == 1


def test_a_hostile_name_does_not_reach_the_rendered_map_as_code():
    m = folium.Map(location=[43.2, 141.3], zoom_start=12, tiles=None)
    folium.CircleMarker([43.2, 141.3], tooltip=map_tip(HOSTILE, "school")).add_to(m)
    page = m.get_root().render()
    assert "<img src=x" not in page and "${alert" not in page
    assert "&lt;img src=x onerror=alert(1)&gt; &#36;{alert(2)} &#96;x&#96; &#92;" in page
    assert "<br>school" in page


def test_every_map_tooltip_of_the_app_goes_through_map_tip():
    """A marker tooltip written as a bare string would bring the problem back."""
    pages = sorted((ROOT / "app" / "pages").glob("*.py"))
    assert pages
    for page in pages:
        source = page.read_text(encoding="utf-8")
        for m in re.finditer(r"\btooltip=(?!\[)", source):            # a list is an Altair chart tooltip
            rest = source[m.end():m.end() + 12]
            assert rest.startswith(("map_tip(", "tip)")), f"{page.name}: tooltip={rest!r}"
        if "tooltip=tip)" in source:
            assert "tip = map_tip(" in source, page.name
