"""Streamlit app: ship traffic and estimated CO2 emissions around Bergen.

Run locally with:  streamlit run app.py

This file sets up navigation and the sidebar shared by all pages.
The pages themselves are in views/.
"""

import streamlit as st

import settings
import ship_types

st.set_page_config(page_title="Skipstrafikk i Bergen", page_icon="🚢", layout="wide")

page = st.navigation([
    st.Page("views/kart.py", title="Kart", icon="🗺️", default=True),
    st.Page("views/utslipp.py", title="Utslipp over tid", icon="📊"),
    st.Page("views/om.py", title="Om beregningen", icon="ℹ️"),
])

# Widgets live here so their values are kept when switching pages.
with st.sidebar:
    st.header("Filter")
    st.multiselect(
        "Skipstype",
        options=list(ship_types.CATEGORIES),
        default=list(ship_types.CATEGORIES),
        key="type_filter",
        placeholder="Velg skipstyper",
    )
    st.selectbox("Periode for lagrede data", list(settings.HISTORY_PERIODS), key="period")
    st.toggle(
        "Vis hvor utslippene er størst",
        key="show_heat",
        help="Legger et varmekart over kartet, laget av lagrede utslipp i valgt periode.",
    )

page.run()
