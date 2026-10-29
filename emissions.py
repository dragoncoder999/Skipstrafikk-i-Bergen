"""Rough CO2 estimate for a single ship, based only on what AIS tells us.

AIS gives ship type, length and speed, but not engine power or fuel use.
Everything else is assumed. The method is a simplified version of the
"bottom-up" approach used in AIS-based emission inventories:

    1. Installed main engine power, design speed and auxiliary power are
       looked up from ship category and length (table PROFILES below).
    2. The share of main engine power in use follows the propeller law:
           load = (speed / design_speed) ** 3
       capped at 1 (we assume ships never use more than full power) and at least
       MIN_LOAD (engines idle, manoeuvre and run fixed loads at very low speed).
    3. Below STATIONARY_SPEED knots the ship is treated as lying still: the main
       engine is off and only auxiliary engines (generators) run, at a fixed
       power per category and size.
    4. Fuel = power x specific fuel oil consumption (SFOC).
    5. CO2 = fuel x CARBON_FACTOR.

Simplifications worth knowing:
    - While moving, only the main engine is counted. Auxiliary engines and
      boilers at sea are left out, which underestimates somewhat.
    - All fuel is treated as marine diesel. Battery ferries, LNG and hybrid
      ships (common around Bergen) are overestimated.
    - Ships on shore power at quay are overestimated, since we still count
      auxiliary engines for them. The exception is cruise ships: Bergen Havn
      requires all cruise ships to use shore power at quay from 2026, so
      cruise ships lying still are counted with no emissions.
    - Weather, current, hull fouling and loading condition are ignored.
    - The tables are averages for a type and size class. A single ship can be
      off by a factor of two or more; totals over many ships are more reliable
      than any one ship.
"""

from dataclasses import dataclass

# --- Constants ---------------------------------------------------------------

SFOC_MAIN = 190  # g fuel per kWh, main engine (typical medium/slow-speed diesel)
SFOC_AUX = 220  # g fuel per kWh, auxiliary engines (smaller, less efficient)
CARBON_FACTOR = 3.206  # t CO2 per t fuel (IMO value for marine diesel oil)

MIN_LOAD = 0.02  # lowest main engine load share while moving (2 %)
STATIONARY_SPEED = 1.0  # knots; below this only auxiliary engines are counted
SPEED_NOT_AVAILABLE = 102.3  # AIS code for "speed unknown"

# --- Ship profiles -------------------------------------------------------------
# Source: Third IMO GHG Study 2014, fleet averages for 2012 (IMO, 2015),
# table of average installed power, design speed and annual fuel use per ship
# type and size class. Taken from the data sheet of the IMO CO2 calculator that
# accompanies "Ship Emissions Toolkit Guide No.1: Rapid Assessment of Ship
# Emissions in the National Context". IMO describes these results as
# indicative, not exact.
#
# That calculator assumes heavy fuel oil (3.114 t CO2 per t fuel). We use the
# marine diesel factor instead (CARBON_FACTOR), since ships along the Norwegian
# coast are inside the North Sea emission control area and mostly burn
# low-sulphur distillate fuel.
#
#   main_kw       = "Average installed power"
#   design_speed  = "Average 'design' speed" (knots), used as the reference
#                   speed in the propeller law
#   aux_kw        = "Average annual fuel consumption in aux engines" (tonnes)
#                   converted to a constant power:
#                   tonnes * 1e6 g / (SFOC_AUX g/kWh * 8760 h)
#   Values are rounded to the nearest 10.
#
# The IMO study gives size in dwt, GT or TEU, while AIS only gives length.
# Each IMO size class is therefore mapped to a length range using typical
# length-to-size ratios for that ship type. This mapping is our own and adds
# uncertainty. AIS ship type codes are also coarser than IMO's types, so each
# category uses the IMO type that is most common around Bergen.
#
# The IMO study covers ships in the IHS fleet register, which are mostly above
# 100 GT (roughly 24 m). Boats up to SMALL_VESSEL_LENGTH have no IMO match and
# use our own rough estimates instead, marked "eget anslag".

SMALL_VESSEL_LENGTH = 24  # metres
INF = float("inf")


@dataclass(frozen=True)
class EngineProfile:
    max_length: float  # applies to ships up to this length (m)
    main_kw: float
    design_speed: float  # knots
    aux_kw: float
    source: str  # shown to users, so in Norwegian
    shore_power: bool = False  # uses shore power instead of auxiliary engines when lying still


def _imo(max_length, main_kw, design_speed, aux_kw, imo_class, shore_power=False):
    return EngineProfile(
        max_length, main_kw, design_speed, aux_kw, f"IMO GHG3: {imo_class}", shore_power
    )


def _own(main_kw, design_speed, aux_kw):
    return EngineProfile(SMALL_VESSEL_LENGTH, main_kw, design_speed, aux_kw, "eget anslag for små fartøy")


# Per category (same names as ship_types.CATEGORIES):
#   rows:           EngineProfile rows sorted by max_length. The first row whose
#                   max_length is >= the ship's length is used.
#   typical_length: used when AIS does not report a length.
PROFILES = {
    "Passasjerskip": {  # car ferries, coastal ships, cruise ships
        "typical_length": 90,
        "rows": [
            _own(400, 12, 20),
            _imo(70, 1_510, 13.0, 100, "Ferry-RoPax 0–1999 GT"),
            _imo(200, 15_490, 21.6, 710, "Ferry-RoPax 2000+ GT"),
            # Cruise ships: shore power at quay, required in Bergen from 2026
            _imo(230, 19_660, 19.9, 4_800, "Cruise 10000–59999 GT", shore_power=True),
            _imo(290, 53_290, 22.2, 13_560, "Cruise 60000–99999 GT", shore_power=True),
            _imo(INF, 76_120, 22.7, 13_250, "Cruise 100000+ GT", shore_power=True),
        ],
    },
    "Hurtigbåt": {  # fast passenger catamarans
        "typical_length": 35,
        "rows": [
            _own(1_000, 25, 20),
            _imo(60, 1_890, 22.7, 180, "Ferry-pax only 0–1999 GT"),
            _imo(INF, 6_590, 16.6, 530, "Ferry-pax only 2000+ GT"),
        ],
    },
    "Lasteskip": {  # general cargo, well boats, container, bulk
        "typical_length": 90,
        "rows": [
            _own(300, 9, 20),
            _imo(100, 1_120, 11.6, 80, "General cargo 0–4999 dwt"),
            _imo(130, 3_320, 13.6, 220, "General cargo 5000–9999 dwt"),
            _imo(160, 7_420, 15.8, 620, "General cargo 10000+ dwt"),
            _imo(INF, 9_020, 15.3, 360, "Bulk carrier 35000–59999 dwt"),
        ],
    },
    "Tankskip": {  # oil, chemical and gas tankers
        "typical_length": 110,
        "rows": [
            _own(300, 9, 20),
            _imo(100, 1_270, 11.5, 330, "Oil tanker 0–4999 dwt"),
            _imo(125, 3_290, 13.4, 290, "Chemical tanker 5000–9999 dwt"),
            _imo(150, 5_260, 14.1, 290, "Chemical tanker 10000–19999 dwt"),
            _imo(200, 9_300, 15.0, 710, "Chemical tanker 20000+ dwt"),
            _imo(INF, 13_810, 15.3, 1_330, "Oil tanker 80000–119999 dwt"),
        ],
    },
    "Fiskefartøy": {
        "typical_length": 30,
        "rows": [
            _own(300, 9, 15),
            _imo(INF, 960, 11.5, 200, "Miscellaneous – fishing"),
        ],
    },
    "Slepebåt": {
        "typical_length": 30,
        "rows": [
            _own(1_000, 10, 20),
            _imo(INF, 2_310, 11.8, 50, "Service – tug"),
        ],
    },
    "Service- og spesialfartøy": {  # pilot, rescue, police, research, dredging ...
        "typical_length": 25,
        "rows": [
            _own(800, 20, 10),
            _imo(INF, 3_180, 12.8, 220, "Service – other"),
        ],
    },
    "Fritidsbåt": {
        "typical_length": 15,
        "rows": [
            _own(300, 15, 10),
            _imo(INF, 2_850, 16.5, 270, "Yacht"),
        ],
    },
    "Annet": {  # in Norway often offshore supply and construction vessels
        "typical_length": 50,
        "rows": [
            _own(300, 10, 15),
            _imo(INF, 4_710, 13.8, 320, "Offshore"),
        ],
    },
    "Ukjent": {
        "typical_length": 30,
        "rows": [
            _own(300, 10, 15),
            _imo(INF, 2_000, 12.7, 190, "Miscellaneous – other"),
        ],
    },
}


@dataclass
class Estimate:
    """Hourly estimate for one ship."""

    main_kw: float  # main engine power in use
    aux_kw: float  # auxiliary engine power in use
    fuel_kg_per_h: float
    co2_kg_per_h: float
    shore_power: bool = False  # lying still on shore power, so no emissions

    @property
    def power_kw(self):
        return self.main_kw + self.aux_kw


# --- Calculation ---------------------------------------------------------------


def engine_profile(category, length):
    """Engine data for a ship, from category and length (m)."""
    profile = PROFILES.get(category, PROFILES["Ukjent"])
    if not length or length <= 0:
        length = profile["typical_length"]
    for row in profile["rows"]:
        if length <= row.max_length:
            return row
    return profile["rows"][-1]


def load_factor(speed, design_speed):
    """Share of main engine power in use, by the propeller law, clamped to [MIN_LOAD, 1]."""
    load = (speed / design_speed) ** 3
    return min(1.0, max(MIN_LOAD, load))


def estimate_from_power(installed_kw, design_speed, speed, aux_kw):
    """Hourly fuel and CO2 from engine data and current speed (knots)."""
    if speed < STATIONARY_SPEED:
        main_kw = 0.0
        used_aux_kw = aux_kw
    else:
        main_kw = installed_kw * load_factor(speed, design_speed)
        used_aux_kw = 0.0

    fuel_g = main_kw * SFOC_MAIN + used_aux_kw * SFOC_AUX
    fuel_kg = fuel_g / 1000
    co2_kg = fuel_kg * CARBON_FACTOR
    return Estimate(main_kw, used_aux_kw, fuel_kg, co2_kg)


def estimate_ship(category, length, speed):
    """Estimate for a ship seen in AIS. Returns None if speed is unknown."""
    if speed is None or speed >= SPEED_NOT_AVAILABLE:
        return None
    row = engine_profile(category, length)
    on_shore_power = row.shore_power and speed < STATIONARY_SPEED
    est = estimate_from_power(
        installed_kw=row.main_kw,
        design_speed=row.design_speed,
        speed=speed,
        aux_kw=0 if on_shore_power else row.aux_kw,
    )
    est.shore_power = on_shore_power
    return est
