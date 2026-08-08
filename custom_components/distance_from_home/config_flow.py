"""Config flow for the Distance from Home integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import BooleanSelector, TextSelector

from .api import GoogleMapsApiError, GoogleMapsClient, InvalidApiKeyError
from .const import (
    CONF_PLACE_ID,
    DOMAIN,
    MODE_BICYCLING,
    MODE_DRIVING,
    MODE_TRANSIT,
    MODE_WALKING,
    SUBENTRY_TYPE_LOCATION,
    TRAVEL_MODES,
)

_LOGGER = logging.getLogger(__name__)

CONF_NAME = "name"

LOCATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLACE_ID): TextSelector(),
        vol.Optional(CONF_NAME): TextSelector(),
        vol.Optional(MODE_WALKING, default=True): BooleanSelector(),
        vol.Optional(MODE_BICYCLING, default=False): BooleanSelector(),
        vol.Optional(MODE_TRANSIT, default=False): BooleanSelector(),
        vol.Optional(MODE_DRIVING, default=False): BooleanSelector(),
    }
)


async def _async_validate_api_key(hass, api_key: str) -> None:
    """Validate an API key by reverse geocoding the home coordinates.

    Raises InvalidApiKeyError or GoogleMapsApiError on failure.
    """
    client = GoogleMapsClient(async_get_clientsession(hass), api_key)
    await client.async_reverse_geocode(hass.config.latitude, hass.config.longitude)


class DistanceFromHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Distance from Home."""

    VERSION = 1

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: collect and validate the API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _async_validate_api_key(self.hass, user_input[CONF_API_KEY])
            except InvalidApiKeyError:
                errors["base"] = "invalid_auth"
            except GoogleMapsApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Distance from Home", data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): TextSelector()}),
            errors=errors,
        )

    async def async_step_reauth(
            self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication when the API key is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key and update the existing entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _async_validate_api_key(self.hass, user_input[CONF_API_KEY])
            except InvalidApiKeyError:
                errors["base"] = "invalid_auth"
            except GoogleMapsApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): TextSelector()}),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
            cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_LOCATION: LocationSubentryFlowHandler}


class LocationSubentryFlowHandler(ConfigSubentryFlow):
    """Handle adding and reconfiguring a location subentry."""

    description_placeholders = dict(
        google_places_website="https://developers.google.com/maps/documentation/places/web-service/place-id")

    async def _async_validate_and_resolve_title(
            self, user_input: dict[str, Any]
    ) -> tuple[str | None, dict[str, str]]:
        """Validate the submitted location data.

        Returns a tuple of (title, errors). If errors is non-empty, title is None.
        If the user didn't supply a name, it is looked up via the Places API.
        """
        if not any(user_input.get(mode) for mode in TRAVEL_MODES):
            return None, {"base": "no_modes_selected"}

        entry = self._get_entry()
        client = GoogleMapsClient(
            async_get_clientsession(self.hass), entry.data[CONF_API_KEY]
        )
        origin_place_id = await client.async_reverse_geocode(
            self.hass.config.latitude, self.hass.config.longitude
        )
        mode = next(mode for mode in TRAVEL_MODES if user_input.get(mode))
        try:
            await client.async_compute_route(
                origin_place_id, user_input[CONF_PLACE_ID], mode
            )
        except InvalidApiKeyError:
            return None, {"base": "invalid_auth"}
        except GoogleMapsApiError:
            return None, {CONF_PLACE_ID: "invalid_place_id"}

        title = user_input.get(CONF_NAME) or None
        if not title:
            try:
                title = await client.async_get_place_display_name(
                    user_input[CONF_PLACE_ID]
                )
            except InvalidApiKeyError:
                return None, {"base": "invalid_auth"}
            except GoogleMapsApiError:
                return None, {"base": "name_lookup_failed"}

        return title, {}

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new location."""
        errors: dict[str, str] = {}
        if user_input is not None:
            title, errors = await self._async_validate_and_resolve_title(user_input)
            if not errors:
                user_input.pop(CONF_NAME, None)
                return self.async_create_entry(data=user_input, title=title)

        data_schema = LOCATION_SCHEMA
        if user_input is not None:
            data_schema = self.add_suggested_values_to_schema(data_schema, user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=self.description_placeholders
        )

    async def async_step_reconfigure(
            self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an existing location."""
        errors: dict[str, str] = {}
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            title, errors = await self._async_validate_and_resolve_title(user_input)
            if not errors:
                user_input.pop(CONF_NAME, None)
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data=user_input, title=title
                )

        suggested = user_input or {CONF_NAME: subentry.title, **subentry.data}
        data_schema = self.add_suggested_values_to_schema(LOCATION_SCHEMA, suggested)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=self.description_placeholders
        )
