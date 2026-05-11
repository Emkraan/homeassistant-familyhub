"""Sensor platform for Samsung Family Hub — last image update timestamp."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FamilyHubData
from .api import FamilyHubCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: FamilyHubData = entry.runtime_data
    async_add_entities([LastUpdatedSensor(entry, data.coordinator)])


class LastUpdatedSensor(CoordinatorEntity[FamilyHubCoordinator], SensorEntity):
    """Sensor showing when the fridge images were last downloaded."""

    _attr_has_entity_name = True
    _attr_name = "Images Last Updated"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry, coordinator: FamilyHubCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_updated"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Samsung Family Hub",
            "manufacturer": "Samsung",
            "model": "Family Hub",
        }

    @property
    def native_value(self) -> datetime | None:
        if self.coordinator.last_updated_at:
            return datetime.fromtimestamp(self.coordinator.last_updated_at).astimezone()
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
