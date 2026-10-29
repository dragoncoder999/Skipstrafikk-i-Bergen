"""Page: live map of ship traffic, with an optional heatmap of stored emissions."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pydeck as pdk
import streamlit as st

import emissions
import settings
import ship_types
import storage
from ais_client import AisError, fetch_latest_positions
from formatting import num as _num

OSLO = ZoneInfo("Europe/Oslo")

def _co2_text(kg_per_h):
    if kg_per_h is None:
        return "ukjent"
    if kg_per_h >= 1000:
        return f"{_num(kg_per_h / 1000, 1)} tonn/time"
    return f"{_num(kg_per_h)} kg/time"


def _with_display_fields(ship):
    """Add category, colour, emission estimate and formatted text for the map and info panel."""
    cat = ship_types.category(ship.get("shipType"))
    length = ship.get("shipLength")
    speed = ship.get("speedOverGround")
    course = ship.get("courseOverGround")
    # AIS uses 102.3 knots for "speed not available" and 360 for "course not available".
    speed_ok = speed is not None and speed < 102.3
    course_ok = course is not None and course < 360
    est = emissions.estimate_ship(cat, length, speed)
    return {
        **ship,
        "name": ship.get("name") or "Uten navn",
        "category": cat,
        "color": list(ship_types.CATEGORIES[cat]),
        "length_text": f"{length} m" if length else "ukjent",
        "speed_text": f"{_num(speed, 1)} knop" if speed_ok else "ukjent",
        "course_text": f"{course:.0f}°" if course_ok else "ukjent",
        "co2_kg_h": est.co2_kg_per_h if est else None,
        "co2_text": _co2_text(est.co2_kg_per_h if est else None),
        "power_text": (
            f"{_num(est.power_kw)} kW" + (" (bare hjelpemotorer)" if est.main_kw == 0 else "")
            if est
            else "ukjent"
        ),
        "fuel_text": f"{_num(est.fuel_kg_per_h)} kg/time" if est else "ukjent",
        "engine_source": emissions.engine_profile(cat, length).source,
    }


@st.cache_data(ttl=settings.CACHE_SECONDS, show_spinner=False)
def _fetch_cached():
    """Cached raw API response, shared by all visitors. Errors are not cached."""
    return fetch_latest_positions(), datetime.now(OSLO)


def load_ships():
    # Display fields are added after the cache, so changes to them never meet stale cached data.
    ships, fetched_at = _fetch_cached()
    ships = [
        _with_display_fields(s)
        for s in ships
        if s.get("latitude") is not None and s.get("longitude") is not None
    ]
    return ships, fetched_at


@st.cache_data(ttl=600, show_spinner=False)  # new data arrives every 10 min
def load_heat(days, categories):
    """Stored emissions on a grid for the heatmap, as dicts with lat, lon and co2."""
    conn = storage.connect()
    try:
        rows = storage.heat_points(conn, days, categories=list(categories))
    finally:
        conn.close()
    return [{"lat": lat, "lon": lon, "co2": co2} for lat, lon, co2 in rows]


def ship_map(ships, selected, heat=None):
    layers = []
    if heat:
        # Drawn first so the ships stay on top
        layers.append(
            pdk.Layer(
                "HeatmapLayer",
                id="heat",
                data=heat,
                get_position=["lon", "lat"],
                get_weight="co2",
                aggregation="SUM",
                radius_pixels=40,
                opacity=0.6,
            )
        )
    layers += [
        pdk.Layer(
            "ScatterplotLayer",
            id="ships",
            data=ships,
            get_position=["longitude", "latitude"],
            get_fill_color="color",
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
            stroked=True,
            get_radius=120,
            radius_min_pixels=4,
            radius_max_pixels=12,
            pickable=True,
        )
    ]
    if selected:
        # Ring around the selected ship
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                id="selected",
                data=[selected],
                get_position=["longitude", "latitude"],
                filled=False,
                stroked=True,
                get_line_color=[0, 0, 0],
                line_width_min_pixels=3,
                get_radius=300,
                radius_min_pixels=10,
            )
        )
    view = pdk.ViewState(
        latitude=settings.MAP_CENTER["lat"],
        longitude=settings.MAP_CENTER["lon"],
        zoom=settings.MAP_ZOOM,
    )
    return pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_provider="carto",
        map_style="light",
        tooltip={"text": "{name}\n{category}\nCO₂: {co2_text}"},
    )


def _format_time(msgtime):
    if not msgtime:
        return "ukjent"
    t = datetime.fromisoformat(msgtime).astimezone(OSLO)
    return f"{t:%d.%m. kl. %H:%M}"


def info_panel(ship):
    if not ship:
        st.info("Klikk på et skip i kartet for å se detaljer.")
        return
    st.subheader(ship["name"])
    rows = {
        "MMSI": ship["mmsi"],
        "Skipstype": f"{ship['category']} (AIS-kode {ship.get('shipType') or '–'})",
        "Lengde": ship["length_text"],
        "Fart": ship["speed_text"],
        "Kurs": ship["course_text"],
        "Sist meldt": _format_time(ship.get("msgtime")),
    }
    st.markdown("\n".join(f"- **{k}:** {v}" for k, v in rows.items()))

    st.markdown("**Anslått utslipp nå**")
    estimate_rows = {
        "Motorkraft i bruk": ship["power_text"],
        "Drivstoff": ship["fuel_text"],
        "CO₂": ship["co2_text"],
    }
    st.markdown("\n".join(f"- **{k}:** {v}" for k, v in estimate_rows.items()))
    st.caption(
        "Grovt anslag ut fra skipstype, lengde og fart. "
        f"Motordata: {ship['engine_source']}."
    )


def legend(ships):
    counts = {}
    for s in ships:
        counts[s["category"]] = counts.get(s["category"], 0) + 1
    items = []
    for cat, (r, g, b) in ship_types.CATEGORIES.items():
        if cat in counts:
            dot = f'<span style="color:rgb({r},{g},{b})">●</span>'
            items.append(f"{dot} {cat} ({counts[cat]})")
    st.markdown(" &nbsp; ".join(items), unsafe_allow_html=True)


st.title("Skipstrafikk rundt Bergen")
st.caption("Posisjoner fra BarentsWatch sitt åpne AIS-API. Kartet oppdateres omtrent hvert minutt.")

def _remember_clicked_ship():
    """Runs before the rerun that a map click triggers, so the ring and info panel update at once."""
    clicked = st.session_state["ship_map"].selection.get("objects", {}).get("ships", [])
    if clicked:
        st.session_state["selected_mmsi"] = clicked[0]["mmsi"]


@st.fragment(run_every=settings.REFRESH_SECONDS)
def live_view():
    try:
        with st.spinner("Henter skipsposisjoner …"):
            ships, fetched_at = load_ships()
    except AisError as err:
        st.error(str(err))
        return
    except Exception as err:  # network errors etc.
        st.error(f"Noe gikk galt ved henting av data: {err}")
        return

    chosen = set(st.session_state.get("type_filter", []))
    ships = [s for s in ships if s["category"] in chosen]

    # The selected ship is remembered by MMSI so it survives the minute-by-minute refresh.
    by_mmsi = {s["mmsi"]: s for s in ships}
    selected = by_mmsi.get(st.session_state.get("selected_mmsi"))

    heat = None
    if st.session_state.get("show_heat"):
        period = st.session_state.get("period", next(iter(settings.HISTORY_PERIODS)))
        heat = load_heat(settings.HISTORY_PERIODS[period], tuple(sorted(chosen)))
        if heat:
            st.caption(f"Varmekartet viser hvor de lagrede utslippene er størst · {period.lower()}.")
        else:
            st.info(storage.no_data_message())

    total_co2 = sum(s["co2_kg_h"] for s in ships if s["co2_kg_h"] is not None)
    st.markdown(
        f"**{len(ships)} skip** vises · anslått samlet utslipp akkurat nå: "
        f"**{_co2_text(total_co2).replace('/time', ' CO₂ per time')}** · "
        f"sist hentet kl. {fetched_at:%H:%M:%S}"
    )
    col_map, col_info = st.columns([3, 1])
    with col_map:
        st.pydeck_chart(
            ship_map(ships, selected, heat),
            height=650,
            on_select=_remember_clicked_ship,
            selection_mode="single-object",
            key="ship_map",
        )
        legend(ships)

    with col_info:
        info_panel(selected)


live_view()
