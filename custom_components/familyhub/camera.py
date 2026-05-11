"""Camera platform for Samsung Family Hub."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FamilyHubData
from .api import FamilyHubCoordinator
from .const import DOMAIN

_CAMERAS = [
    ("top", 0, "Top Camera"),
    ("middle", 1, "Middle Camera"),
    ("bottom", 2, "Bottom Camera"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: FamilyHubData = entry.runtime_data
    async_add_entities(
        FamilyHubCamera(entry, data.coordinator, key, idx, label)
        for key, idx, label in _CAMERAS
    )


class FamilyHubCamera(CoordinatorEntity[FamilyHubCoordinator], Camera):
    """A single refrigerator camera slot."""

    _attr_has_entity_name = True
    content_type = "image/jpeg"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: FamilyHubCoordinator,
        key: str,
        index: int,
        label: str,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._index = index
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Samsung Family Hub",
            "manufacturer": "Samsung",
            "model": "Family Hub",
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        images = self.coordinator.api.downloaded_images
        if self._index < len(images):
            return images[self._index]
        return None
