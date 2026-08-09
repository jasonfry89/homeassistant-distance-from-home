"""Sensor platform for Distance from Home."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, TRAVEL_MODES
from .coordinator import DistanceFromHomeConfigEntry, DistanceUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DistanceFromHomeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up distance sensors for each location subentry."""

    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        entities = [
            DistanceSensor(entry.runtime_data.coordinators[subentry_id], subentry_id, mode)
            for mode in TRAVEL_MODES
            if coordinator.data.get(mode)
        ]
        async_add_entities(entities, config_subentry_id=subentry_id)


class DistanceSensor(CoordinatorEntity[DistanceUpdateCoordinator], SensorEntity):
    """Distance to a location for a single travel mode."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_suggested_unit_of_measurement = UnitOfLength.MILES
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: DistanceUpdateCoordinator,
        subentry_id: str,
        mode: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = f"{coordinator.title}_{mode}"
        self._attr_unique_id = self._key
        self._attr_translation_key = f"{mode}_distance"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=coordinator.title,
        )

    @property
    def native_value(self) -> int | None:
        """Return the distance in meters."""
        result = self.coordinator.data.get(self._key)
        return result.distance_meters if result else None

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        """Return the route duration as an extra attribute."""
        result = self.coordinator.data.get(self._key)
        if result is None:
            return None
        return {"duration_seconds": result.duration_seconds}
