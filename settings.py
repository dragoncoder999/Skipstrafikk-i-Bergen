"""Project settings. Change the area or refresh interval here."""

from pathlib import Path

from dotenv import load_dotenv

# Secrets (API keys, database token) come from environment variables.
# Locally they are read from nokler.env; on Render and GitHub they are set as secrets.
load_dotenv(Path(__file__).parent / "nokler.env")

# Area of interest: Bergen and surroundings (decimal degrees, WGS84).
# Covers roughly Sotra/Askøy in the west to Osterøy in the east,
# and Fedjefjorden in the north to Austevoll in the south.
AREA = {
    "min_lat": 60.10,
    "max_lat": 60.80,
    "min_lon": 4.70,
    "max_lon": 5.60,
}

# Map start view
MAP_CENTER = {"lat": 60.40, "lon": 5.20}
MAP_ZOOM = 9

# How often the map refreshes, and how long API responses are cached (seconds).
# Keep the cache at least as long as the refresh so all visitors share one API call.
REFRESH_SECONDS = 60
CACHE_SECONDS = 60

# BarentsWatch endpoints (https://developer.barentswatch.no/docs/AIS/live-ais-api)
TOKEN_URL = "https://id.barentswatch.no/connect/token"
AIS_LATEST_URL = "https://live.ais.barentswatch.no/v1/latest/combined"
AIS_SCOPE = "ais"

# --- Data collection (step 4) ---
# Local SQLite file for stored positions. Can be overridden with the DB_PATH environment variable.
# If TURSO_DATABASE_URL is set, the Turso cloud database is used instead.
DB_PATH = "data/skipstrafikk.db"

# How often collector.py stores a snapshot of all ships (minutes).
# Matches the schedule in .github/workflows/collect.yml.
COLLECT_MINUTES = 10

# A snapshot normally counts for the time since the previous one. If the gap is
# longer than this (collector stopped, server asleep), the gap is not counted and
# the snapshot only counts for COLLECT_MINUTES. Gaps therefore lower the totals.
MAX_GAP_MINUTES = 30

# Positions older than this are skipped: the ship has likely left the area or
# turned off AIS.
MAX_POSITION_AGE_MINUTES = 30

# Stored positions older than this are deleted to keep the database small.
KEEP_DAYS = 30

# Periods offered for stored history (label -> days)
HISTORY_PERIODS = {"Siste 24 timer": 1, "Siste 7 døgn": 7, "Siste 30 døgn": 30}
