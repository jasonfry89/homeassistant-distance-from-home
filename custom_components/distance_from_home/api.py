"""Thin async client for the Google Geocoding and Routes APIs."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiohttp import ClientError, ClientSession

from .const import TRAVEL_MODE_TO_API

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

_LOGGER = logging.getLogger(__name__)


class GoogleMapsApiError(Exception):
    """Base error for the Google Maps API client."""


class InvalidApiKeyError(GoogleMapsApiError):
    """Raised when the API key is rejected by Google."""


class RouteNotFoundError(GoogleMapsApiError):
    """Raised when no route can be computed for the given input."""


@dataclass
class RouteResult:
    """Result of a computed route."""

    distance_meters: int
    duration_seconds: int


class GoogleMapsClient:
    """Client wrapping the Geocoding API and Routes API."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key

    async def async_reverse_geocode(self, latitude: float, longitude: float) -> str:
        """Reverse geocode coordinates to a Google Place ID."""
        try:
            async with self._session.get(
                GEOCODE_URL,
                params={"latlng": f"{latitude},{longitude}", "key": self._api_key},
            ) as resp:
                payload = await resp.json()
        except ClientError as err:
            raise GoogleMapsApiError(f"Error contacting Geocoding API: {err}") from err

        status = payload.get("status")
        if status == "REQUEST_DENIED":
            raise InvalidApiKeyError(payload.get("error_message", status))
        if status != "OK":
            raise GoogleMapsApiError(f"Geocoding API returned status {status}")

        results = payload.get("results") or []
        if not results:
            raise GoogleMapsApiError("Geocoding API returned no results")

        return results[0]["place_id"]

    async def async_get_place_display_name(self, place_id: str) -> str:
        """Look up the display name of a Place ID using the Places API."""
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": "displayName",
        }
        try:
            async with self._session.get(
                PLACE_DETAILS_URL.format(place_id=place_id), headers=headers
            ) as resp:
                payload = await resp.json()
                status = resp.status
        except ClientError as err:
            raise GoogleMapsApiError(f"Error contacting Places API: {err}") from err

        if status == 403:
            message = payload.get("error", {}).get("message", "Permission denied")
            raise InvalidApiKeyError(message)
        if status != 200:
            message = payload.get("error", {}).get("message", f"HTTP {status}")
            raise GoogleMapsApiError(message)

        display_name = payload.get("displayName", {}).get("text")
        if not display_name:
            raise GoogleMapsApiError("Places API returned no display name")

        return display_name

    async def async_compute_route(
        self, origin_place_id: str, destination_place_id: str, mode: str
    ) -> RouteResult:
        """Compute a route between two Place IDs for the given travel mode."""
        body = {
            "origin": {"placeId": origin_place_id},
            "destination": {"placeId": destination_place_id},
            "travelMode": TRAVEL_MODE_TO_API[mode],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
        }
        try:
            async with self._session.post(
                ROUTES_URL, json=body, headers=headers
            ) as resp:
                payload = await resp.json()
                status = resp.status
        except ClientError as err:
            raise GoogleMapsApiError(f"Error contacting Routes API: {err}") from err

        if status == 403:
            message = payload.get("error", {}).get("message", "Permission denied")
            raise InvalidApiKeyError(message)
        if status != 200:
            message = payload.get("error", {}).get("message", f"HTTP {status}")
            raise GoogleMapsApiError(message)

        routes = payload.get("routes") or []
        if not routes:
            raise RouteNotFoundError(
                f"No route found for mode {mode} between {origin_place_id} "
                f"and {destination_place_id}"
            )

        route = routes[0]
        duration_str = route.get("duration", "0s")
        duration_seconds = int(float(duration_str.rstrip("s"))) if duration_str else 0

        return RouteResult(
            distance_meters=route["distanceMeters"],
            duration_seconds=duration_seconds,
        )
