"""Camera platform for Samsung Family Hub."""

from __future__ import annotations

import logging

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import FamilyHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Family Hub camera from a config entry."""
    hub: FamilyHub = entry.runtime_data
    async_add_entities([FamilyHubCamera(entry, hub)])


class FamilyHubCamera(Camera):
    """Camera entity for the Samsung Family Hub refrigerator."""

    _attr_has_entity_name = True
    _attr_translation_key = "camera"

    def __init__(self, entry: ConfigEntry, hub: FamilyHub) -> None:
        super().__init__()
        self._hub = hub
        self._attr_unique_id = f"{entry.entry_id}_camera"
        self._attr_device_info = {
            "identifiers": {("familyhub", entry.entry_id)},
            "name": entry.data[CONF_NAME],
            "manufacturer": "Samsung",
            "model": "Family Hub",
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image from the refrigerator camera."""
        return await self._hub.async_get_cam_image()
