"""Grouping of AIS ship type codes into a few Norwegian categories.

AIS reports ship type as a number from 0 to 99 (ITU-R M.1371). The first
digit gives the main group (6x = passenger, 7x = cargo, 8x = tanker, ...),
while 3x and 5x are split into specific vessel kinds. The same categories
are used for the map colours, the filter and the emission estimate.
"""

UNKNOWN = "Ukjent"

# Category name -> map colour (RGB)
CATEGORIES = {
    "Passasjerskip": (214, 39, 40),
    "Hurtigbåt": (255, 127, 14),
    "Lasteskip": (31, 119, 180),
    "Tankskip": (140, 86, 75),
    "Fiskefartøy": (44, 160, 44),
    "Slepebåt": (148, 103, 189),
    "Service- og spesialfartøy": (23, 190, 207),
    "Fritidsbåt": (227, 119, 194),
    "Annet": (127, 127, 127),
    UNKNOWN: (188, 189, 34),
}

# Codes in the 3x and 5x ranges that have their own meaning
_SPECIFIC_CODES = {
    30: "Fiskefartøy",
    31: "Slepebåt",
    32: "Slepebåt",
    33: "Service- og spesialfartøy",  # dredging / underwater operations
    34: "Service- og spesialfartøy",  # diving operations
    35: "Service- og spesialfartøy",  # military
    36: "Fritidsbåt",  # sailing
    37: "Fritidsbåt",  # pleasure craft
    52: "Slepebåt",
}


def category(code):
    """Return the category name for an AIS ship type code."""
    if code is None or code <= 0 or code > 99:
        return UNKNOWN
    if code in _SPECIFIC_CODES:
        return _SPECIFIC_CODES[code]
    group = code // 10
    if group == 4:
        return "Hurtigbåt"
    if group == 5:
        return "Service- og spesialfartøy"  # pilot, rescue, port tender, police ...
    if group == 6:
        return "Passasjerskip"
    if group == 7:
        return "Lasteskip"
    if group == 8:
        return "Tankskip"
    return "Annet"
