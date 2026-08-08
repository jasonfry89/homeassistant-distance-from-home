"""The Distance from Home integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GoogleMapsClient
from .const import SUBENTRY_TYPE_LOCATION
from .coordinator import DistanceFromHomeConfigEntry, DistanceUpdateCoordinator, DistanceFromHomeData

PLATFORMS = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: DistanceFromHomeConfigEntry
) -> bool:
    """Set up Distance from Home from a config entry."""
    client = GoogleMapsClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    origin_place_id = await client.async_reverse_geocode(hass.config.latitude, hass.config.longitude)

    coordinators = {
        subentry_id: DistanceUpdateCoordinator(hass, entry, subentry, origin_place_id, client)
        for subentry_id, subentry
        in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_TYPE_LOCATION
    }

    await asyncio.gather(
        *(coordinator.async_refresh() for coordinator in coordinators.values())
    )
    if coordinators and not any(
            coordinator.last_update_success for coordinator in coordinators.values()
    ):
        raise ConfigEntryNotReady("Could not fetch distance for any configured places")

    entry.runtime_data = DistanceFromHomeData(client, origin_place_id, coordinators)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the entry whenever a location subentry is added, changed or removed.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: DistanceFromHomeConfigEntry
) -> None:
    """Reload the config entry when it is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: DistanceFromHomeConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
