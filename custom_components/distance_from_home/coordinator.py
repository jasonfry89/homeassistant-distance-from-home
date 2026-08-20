"""Data update coordinator for Distance from Home."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from .api import (
    GoogleMapsApiError,
    GoogleMapsClient,
    InvalidApiKeyError,
    RouteResult,
)
from .const import CONF_PLACE_ID, DOMAIN, TRAVEL_MODES, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
CACHE_DURATION = UPDATE_INTERVAL


@dataclass
class DistanceFromHomeData:
    """Everything the platforms and subentry flow need at runtime."""
    client: GoogleMapsClient
    origin_place_id: str
    coordinators: dict[str, DistanceUpdateCoordinator]


type DistanceFromHomeConfigEntry = ConfigEntry[DistanceFromHomeData]


class DistanceUpdateCoordinator(DataUpdateCoordinator[dict[str, RouteResult]]):
    """Fetch distance data for every location subentry and enabled travel mode."""

    def __init__(
            self,
            hass: HomeAssistant,
            entry: DistanceFromHomeConfigEntry,
            subentry: ConfigSubentry,
            origin_place_id: str,
            client: GoogleMapsClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.origin_place_id = origin_place_id
        self.destination_place_id = subentry.data[CONF_PLACE_ID]
        self.title = subentry.title
        self.modes = [mode for mode in TRAVEL_MODES if subentry.data.get(mode)]
        self._store = Store[dict[str, dict]](hass, STORAGE_VERSION, f"{DOMAIN}_{subentry.subentry_id}")

    async def _async_update_data(self) -> dict[str, RouteResult | None]:
        cache = await self._store.async_load() or {}
        now = dt_util.utcnow()
        data: dict[str, RouteResult | None] = {}
        cache_changed = False

        for mode in self.modes:
            cached = cache.get(mode)
            if cached is not None:
                cached_at = dt_util.parse_datetime(cached["cached_at"])
                if cached_at is not None and now - cached_at < CACHE_DURATION:
                    data[mode] = RouteResult(
                        distance_meters=cached["distance_meters"],
                        duration_seconds=cached["duration_seconds"],
                    )
                    continue

            try:
                result = await self.client.async_compute_route(
                    self.origin_place_id,
                    self.destination_place_id,
                    mode)
            except InvalidApiKeyError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except GoogleMapsApiError as err:
                data[mode] = None
                _LOGGER.warning(
                    "Could not compute %s route for %s: %s",
                    mode,
                    self.title,
                    err,
                )
                continue

            data[mode] = result
            cache[mode] = {
                "distance_meters": result.distance_meters,
                "duration_seconds": result.duration_seconds,
                "cached_at": now.isoformat(),
            }
            cache_changed = True

        if cache_changed:
            await self._store.async_save(cache)

        return data
