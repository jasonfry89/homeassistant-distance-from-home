"""Data update coordinator for Distance from Home."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .api import (
    GoogleMapsApiError,
    GoogleMapsClient,
    InvalidApiKeyError,
    RouteResult,
)
from .const import CONF_PLACE_ID, DOMAIN, TRAVEL_MODES, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> dict[str, RouteResult | None]:
        data: dict[str, RouteResult | None] = {}
        for mode in self.modes:
            try:
                data[mode] = await self.client.async_compute_route(
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

        return data
