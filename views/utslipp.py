"""Page: stored emissions summed per hour and per day, split by ship type."""

from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

import settings
import ship_types
import storage
from formatting import num

OSLO = ZoneInfo("Europe/Oslo")

COLOR_SCALE = alt.Scale(
    domain=list(ship_types.CATEGORIES),
    range=[f"rgb{rgb}" for rgb in ship_types.CATEGORIES.values()],
)


@st.cache_data(ttl=600, show_spinner=False)  # new data arrives every 10 min
def load_history(days):
    conn = storage.connect()
    try:
        rows = storage.hourly(conn, days)
        cov = storage.coverage(conn, days)
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=["hour", "category", "co2_kg"])
    # Hours are stored in UTC. Norway's offset is whole hours, so converting
    # gives local hours without ambiguity when daylight saving time ends.
    utc = pd.to_datetime(df["hour"] + ":00:00+00:00", utc=True)
    local = utc.dt.tz_convert(OSLO)
    df["hour"] = local.dt.tz_localize(None)
    df["day"] = local.dt.strftime("%Y-%m-%d")
    return df, cov


def stacked_bars(tonnes, x, tooltip_x):
    """Stacked bar chart of tonnes CO2 per ship type. x and tooltip_x are Altair encodings."""
    return (
        alt.Chart(tonnes)
        .mark_bar()
        .encode(
            x=x,
            y=alt.Y("sum(tonn):Q", title="Tonn CO₂"),
            color=alt.Color("category:N", title="Skipstype", scale=COLOR_SCALE),
            tooltip=[
                tooltip_x,
                alt.Tooltip("category:N", title="Skipstype"),
                alt.Tooltip("tonn:Q", title="Tonn CO₂", format=".2f"),
            ],
        )
    )


def per_hour_chart(df):
    tonnes = df.groupby(["hour", "category"], as_index=False)["co2_kg"].sum()
    tonnes["tonn"] = tonnes["co2_kg"] / 1000
    return stacked_bars(
        tonnes,
        alt.X("hour:T", title=None, axis=alt.Axis(format="%d.%m. %H:%M", labelAngle=-40)),
        alt.Tooltip("hour:T", title="Time", format="%d.%m. kl. %H"),
    )


def per_day_chart(df):
    tonnes = df.groupby(["day", "category"], as_index=False)["co2_kg"].sum()
    tonnes["tonn"] = tonnes["co2_kg"] / 1000
    tonnes["dato"] = pd.to_datetime(tonnes["day"]).dt.strftime("%d.%m.")
    return stacked_bars(
        tonnes,
        # sort=None keeps the data order, which is chronological
        alt.X("dato:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
        alt.Tooltip("dato:O", title="Dato"),
    )


st.title("Utslipp over tid")
st.caption(
    "Anslått CO₂ fra skipene i området, summert over lagrede målinger. "
    "Tallene er grove anslag. Velg periode og skipstyper i menyen til venstre."
)

period = st.session_state.get("period", next(iter(settings.HISTORY_PERIODS)))
days = settings.HISTORY_PERIODS[period]
df, (n_snapshots, first, last, hours_covered) = load_history(days)

if df.empty:
    st.info(storage.no_data_message())
    st.stop()

chosen = set(st.session_state.get("type_filter", []))
df = df[df["category"].isin(chosen)]
if df.empty:
    st.info("Ingen av de valgte skipstypene har lagrede data i perioden.")
    st.stop()

total_kg = df["co2_kg"].sum()
first_local = pd.Timestamp(first).tz_convert(OSLO)
last_local = pd.Timestamp(last).tz_convert(OSLO)

c1, c2, c3 = st.columns(3)
c1.metric(f"CO₂ · {period.lower()}", f"{num(total_kg / 1000, 1)} tonn")
c2.metric("Gjennomsnitt per time", f"{num(total_kg / 1000 / hours_covered, 2)} tonn")
c3.metric("Timer med data", num(hours_covered, 1))
st.caption(
    f"{n_snapshots} målinger fra {first_local:%d.%m. kl. %H:%M} til {last_local:%d.%m. kl. %H:%M}. "
    "Tidsrom uten innsamling er ikke med i summene."
)

st.subheader("Per time")
st.altair_chart(per_hour_chart(df), width="stretch")

st.subheader("Per døgn")
st.altair_chart(per_day_chart(df), width="stretch")

st.subheader("Fordelt på skipstype")
by_type = (
    df.groupby("category", as_index=False)["co2_kg"].sum()
    .sort_values("co2_kg", ascending=False)
)
by_type["Tonn CO₂"] = by_type["co2_kg"] / 1000
by_type["Andel"] = by_type["co2_kg"] / total_kg
st.dataframe(
    by_type.rename(columns={"category": "Skipstype"})[["Skipstype", "Tonn CO₂", "Andel"]],
    hide_index=True,
    column_config={
        # "localized" and "percent" follow the viewer's browser language (decimal comma in Norwegian)
        "Tonn CO₂": st.column_config.NumberColumn(format="localized"),
        "Andel": st.column_config.NumberColumn(format="percent"),
    },
)
