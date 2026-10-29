"""Collect ship positions into the SQLite database.

Usage:
    python collector.py          # keep running, one snapshot every COLLECT_MINUTES
    python collector.py --once   # store one snapshot and exit (for cron / scheduled jobs)
"""

import sys
import time
from datetime import datetime, timedelta, timezone

import emissions
import settings
import ship_types
import storage
from ais_client import fetch_latest_positions


def _is_fresh(ship, now):
    msgtime = ship.get("msgtime")
    if not msgtime:
        return False
    age = now - datetime.fromisoformat(msgtime)
    return age <= timedelta(minutes=settings.MAX_POSITION_AGE_MINUTES)


def build_rows(raw_ships, now):
    """Keep fresh positions with a known speed and attach category and CO2 per hour."""
    rows = []
    for s in raw_ships:
        if s.get("latitude") is None or s.get("longitude") is None or not _is_fresh(s, now):
            continue
        category = ship_types.category(s.get("shipType"))
        est = emissions.estimate_ship(category, s.get("shipLength"), s.get("speedOverGround"))
        if est is None:
            continue
        rows.append({
            "mmsi": s["mmsi"],
            "name": s.get("name"),
            "category": category,
            "lat": s["latitude"],
            "lon": s["longitude"],
            "speed": s.get("speedOverGround"),
            "co2_kg_h": est.co2_kg_per_h,
        })
    return rows


def collect_once():
    now = datetime.now(timezone.utc)
    rows = build_rows(fetch_latest_positions(), now)
    conn = storage.connect()
    try:
        hours = storage.save_snapshot(conn, now, rows)
        storage.delete_older_than(conn, settings.KEEP_DAYS)
    finally:
        conn.close()
    co2 = sum(r["co2_kg_h"] for r in rows) * hours
    print(f"{now:%Y-%m-%d %H:%M} UTC: lagret {len(rows)} skip, {hours * 60:.0f} min, {co2:.0f} kg CO2")


def main():
    if "--once" in sys.argv:
        collect_once()
        return
    print(f"Samler inn hvert {settings.COLLECT_MINUTES}. minutt. Stopp med Ctrl + C.")
    while True:
        try:
            collect_once()
        except Exception as err:  # keep running through network errors
            print(f"Feil ved innsamling: {err}")
        time.sleep(settings.COLLECT_MINUTES * 60)


if __name__ == "__main__":
    main()
