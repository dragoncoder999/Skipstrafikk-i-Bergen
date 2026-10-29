"""Client for the BarentsWatch open AIS API.

Credentials are read from the environment (BARENTSWATCH_CLIENT_ID and
BARENTSWATCH_CLIENT_SECRET), see settings.py.
"""

import os
import threading
import time

import requests

import settings

TIMEOUT = 30

# The token is shared by everyone using the app in this process.
_token = {"value": None, "expires_at": 0.0}
_token_lock = threading.Lock()


class AisError(Exception):
    """Raised with a user-facing (Norwegian) message when the API fails."""


def _credentials():
    client_id = os.getenv("BARENTSWATCH_CLIENT_ID", "").strip()
    client_secret = os.getenv("BARENTSWATCH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise AisError(
            "Mangler klient-ID eller klienthemmelighet. "
            "Fyll inn BARENTSWATCH_CLIENT_ID og BARENTSWATCH_CLIENT_SECRET i nokler.env."
        )
    return client_id, client_secret


def get_token():
    """Return a valid access token, fetching a new one shortly before expiry."""
    with _token_lock:
        # Renew one minute early so a token never expires mid-request.
        if _token["value"] and time.time() < _token["expires_at"] - 60:
            return _token["value"]

        client_id, client_secret = _credentials()
        response = requests.post(
            settings.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": settings.AIS_SCOPE,
            },
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            raise AisError(
                f"Innlogging mot BarentsWatch feilet (HTTP {response.status_code}). "
                "Sjekk klient-ID og klienthemmelighet."
            )
        body = response.json()
        _token["value"] = body["access_token"]
        _token["expires_at"] = time.time() + body.get("expires_in", 3600)
        return _token["value"]


def _area_polygon(area):
    """Turn the bounding box into a closed GeoJSON polygon ([lon, lat] order)."""
    w, e = area["min_lon"], area["max_lon"]
    s, n = area["min_lat"], area["max_lat"]
    return {
        "type": "Polygon",
        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    }


def fetch_latest_positions(area=settings.AREA):
    """Return the latest known position of every vessel inside the area.

    Each item is a dict with fields such as mmsi, name, latitude, longitude,
    speedOverGround, courseOverGround, shipType and shipLength.
    """
    payload = {
        "modelType": "Full",
        "modelFormat": "Json",
        "geometry": _area_polygon(area),
    }

    for attempt in range(2):
        response = requests.post(
            settings.AIS_LATEST_URL,
            json=payload,
            headers={"Authorization": f"Bearer {get_token()}"},
            timeout=TIMEOUT,
        )
        # A 401 can mean the token was revoked early: drop it and try once more.
        if response.status_code == 401 and attempt == 0:
            _token["value"] = None
            continue
        break

    if response.status_code != 200:
        raise AisError(f"Kunne ikke hente skipsposisjoner (HTTP {response.status_code}).")
    return response.json()
