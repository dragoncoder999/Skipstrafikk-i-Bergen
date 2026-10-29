"""Number formatting for Norwegian text."""


def num(value, decimals=0):
    """Space as thousands separator, comma as decimal mark: 12 345,6"""
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
