"""SQLite storage of ship positions and their estimated emissions.

Each run of the collector stores one snapshot: all ships in the area at that
moment, with the CO2 they are estimated to emit during the snapshot's interval.

Besides the raw positions, each snapshot is added to two summary tables:
    hourly_totals  CO2 per hour and ship type (for the charts)
    heat_cells     CO2 per hour, ship type and map grid cell (for the heatmap)
The app reads only the summaries, so the pages stay fast and few rows are
read from the cloud database.

The database is a local SQLite file, or a Turso cloud database (SQLite
compatible) when TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set. Turso is
used on Render, whose free plan deletes local files on every restart.

Times are stored as UTC text ("2026-10-29T21:05:00+00:00", hours as
"2026-10-29T21"), which sorts correctly as text. A snapshot is counted in the
hour it was taken, even if its interval started in the previous hour.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import settings

CELL_DEG = 0.005  # heatmap grid cell size in degrees (about 550 x 300 m around Bergen)

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    taken_at TEXT NOT NULL,   -- UTC time of the snapshot
    hours REAL NOT NULL       -- length of the interval this snapshot represents
);
CREATE INDEX IF NOT EXISTS snapshots_taken_at ON snapshots (taken_at);

CREATE TABLE IF NOT EXISTS positions (
    snapshot_id INTEGER NOT NULL,
    mmsi INTEGER NOT NULL,
    name TEXT,
    category TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    speed REAL,
    co2_kg REAL NOT NULL      -- estimated CO2 during the snapshot's interval
);
CREATE INDEX IF NOT EXISTS positions_snapshot ON positions (snapshot_id);

CREATE TABLE IF NOT EXISTS hourly_totals (
    hour TEXT NOT NULL,       -- UTC hour, e.g. 2026-10-29T21
    category TEXT NOT NULL,
    co2_kg REAL NOT NULL,
    PRIMARY KEY (hour, category)
);

CREATE TABLE IF NOT EXISTS heat_cells (
    hour TEXT NOT NULL,
    category TEXT NOT NULL,
    lat_cell INTEGER NOT NULL,   -- latitude / CELL_DEG, rounded
    lon_cell INTEGER NOT NULL,
    co2_kg REAL NOT NULL,
    PRIMARY KEY (hour, category, lat_cell, lon_cell)
);
"""


def db_path():
    return Path(os.getenv("DB_PATH", settings.DB_PATH))


def uses_turso():
    return bool(os.getenv("TURSO_DATABASE_URL"))


def no_data_message():
    """Norwegian hint shown when there is no stored data yet."""
    if uses_turso():
        return (
            f"Ingen lagrede data for perioden ennå. Data samles inn omtrent hvert "
            f"{settings.COLLECT_MINUTES}. minutt, så tallene dukker opp snart."
        )
    return (
        "Ingen lagrede data for perioden ennå. Start innsamlingen i en egen terminal med "
        "`python collector.py`, så dukker tallene opp her etter noen minutter."
    )


def connect():
    if uses_turso():
        import certifi
        import turso_serverless  # only needed when the cloud database is used

        # turso_serverless uses Python's urllib, which on python.org builds for
        # macOS has no root certificates. Use certifi's bundle (as requests does).
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        conn = turso_serverless.connect(
            os.environ["TURSO_DATABASE_URL"], auth_token=os.getenv("TURSO_AUTH_TOKEN")
        )
    else:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def _utc(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _since(days):
    return _utc(datetime.now(timezone.utc) - timedelta(days=days))


def _hour(iso_time):
    return iso_time[:13]  # "2026-10-29T21:05:00+00:00" -> "2026-10-29T21"


def interval_hours(conn, taken_at):
    """Hours since the previous snapshot, or COLLECT_MINUTES after a long gap."""
    row = conn.execute("SELECT MAX(taken_at) FROM snapshots").fetchone()
    if row[0]:
        gap_minutes = (taken_at - datetime.fromisoformat(row[0])).total_seconds() / 60
        if 0 < gap_minutes <= settings.MAX_GAP_MINUTES:
            return gap_minutes / 60
    return settings.COLLECT_MINUTES / 60


def save_snapshot(conn, taken_at, ships):
    """Store one snapshot and add it to the summary tables.

    ships: dicts with mmsi, name, category, lat, lon, speed and co2_kg_h.
    Returns the interval in hours that the snapshot was counted for.

    Uses one multi-row INSERT and INSERT ... SELECT for the summaries, so a
    snapshot needs only a handful of requests to the cloud database.
    """
    taken_at = taken_at.replace(microsecond=0)  # stored with whole seconds
    hours = interval_hours(conn, taken_at)
    hour = _hour(_utc(taken_at))
    with conn:
        snapshot_id = conn.execute(
            "INSERT INTO snapshots (taken_at, hours) VALUES (?, ?)", (_utc(taken_at), hours)
        ).lastrowid
        if not ships:
            return hours

        values = []
        for s in ships:
            values += [snapshot_id, s["mmsi"], s["name"], s["category"], s["lat"], s["lon"],
                       s["speed"], s["co2_kg_h"] * hours]
        conn.execute(
            "INSERT INTO positions (snapshot_id, mmsi, name, category, lat, lon, speed, co2_kg) "
            "VALUES " + ", ".join(["(?, ?, ?, ?, ?, ?, ?, ?)"] * len(ships)),
            values,
        )
        # "WHERE true" is required by SQLite when an upsert reads from a SELECT.
        conn.execute(
            "INSERT INTO hourly_totals (hour, category, co2_kg) "
            "SELECT ?, category, SUM(co2_kg) FROM positions WHERE snapshot_id = ? AND true "
            "GROUP BY category "
            "ON CONFLICT (hour, category) DO UPDATE SET co2_kg = co2_kg + excluded.co2_kg",
            (hour, snapshot_id),
        )
        conn.execute(
            "INSERT INTO heat_cells (hour, category, lat_cell, lon_cell, co2_kg) "
            "SELECT ?, category, CAST(ROUND(lat / ?) AS INTEGER), CAST(ROUND(lon / ?) AS INTEGER), "
            "SUM(co2_kg) FROM positions WHERE snapshot_id = ? AND true "
            "GROUP BY 2, 3, 4 "
            "ON CONFLICT (hour, category, lat_cell, lon_cell) "
            "DO UPDATE SET co2_kg = co2_kg + excluded.co2_kg",
            (hour, CELL_DEG, CELL_DEG, snapshot_id),
        )
    return hours


def delete_older_than(conn, days):
    since = _since(days)
    with conn:
        conn.execute(
            "DELETE FROM positions WHERE snapshot_id IN (SELECT id FROM snapshots WHERE taken_at < ?)",
            (since,),
        )
        conn.execute("DELETE FROM snapshots WHERE taken_at < ?", (since,))
        conn.execute("DELETE FROM hourly_totals WHERE hour < ?", (_hour(since),))
        conn.execute("DELETE FROM heat_cells WHERE hour < ?", (_hour(since),))


# --- Queries used by the app ---------------------------------------------------


def hourly(conn, days):
    """Rows of (hour, category, co2_kg) for the last `days`, hour as "2026-10-29T21" (UTC)."""
    return conn.execute(
        "SELECT hour, category, co2_kg FROM hourly_totals WHERE hour >= ? ORDER BY hour",
        (_hour(_since(days)),),
    ).fetchall()


def heat_points(conn, days, categories):
    """Emissions summed per grid cell for the given ship types: (lat, lon, co2_kg)."""
    if not categories:
        return []
    marks = ", ".join("?" * len(categories))
    return conn.execute(
        f"SELECT lat_cell * ?, lon_cell * ?, SUM(co2_kg) FROM heat_cells "
        f"WHERE hour >= ? AND category IN ({marks}) GROUP BY lat_cell, lon_cell",
        (CELL_DEG, CELL_DEG, _hour(_since(days)), *categories),
    ).fetchall()


def coverage(conn, days):
    """(number of snapshots, first time, last time, hours covered) in the last `days`."""
    return conn.execute(
        "SELECT COUNT(*), MIN(taken_at), MAX(taken_at), COALESCE(SUM(hours), 0) "
        "FROM snapshots WHERE taken_at >= ?",
        (_hour(_since(days)),),  # whole hours, same window as hourly()
    ).fetchone()
