"""Colors, fonts, map tiles and the tooltip text of map markers, shared by the app pages."""

import html

# Categorical colors, used in this fixed order.
SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
FONT = 'system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans CJK JP", sans-serif'

GSI_PALE = "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"
GSI_STD = "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"
GSI_ATTR = ('<a href="https://maps.gsi.go.jp/development/ichiran.html">地理院タイル GSI tiles</a>'
            ' / © OpenStreetMap contributors')


def map_tip(*lines) -> str:
    """Tooltip HTML for a map marker: every line as plain text, joined by line breaks.

    Names come from OpenStreetMap and from exported files, and anyone can edit OpenStreetMap. The map
    library writes a tooltip into a JavaScript template literal and then into the page as HTML, so
    markup in a name would be rendered and `${...}` would be evaluated. Here the characters that
    matter in either place become character references: the name is shown as written and nothing runs.
    Empty lines are dropped.
    """
    def text(line) -> str:
        escaped = html.escape(str(line), quote=True)
        return escaped.replace("$", "&#36;").replace("`", "&#96;").replace("\\", "&#92;")
    return "<br>".join(text(line) for line in lines if line not in (None, ""))
