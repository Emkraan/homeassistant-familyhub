"""The Samsung Family Hub integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .hub import FamilyHub, FamilyHubError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Samsung Family Hub from a config entry."""
    session = async_get_clientsession(hass)
    hub = FamilyHub(entry.data[CONF_IP_ADDRESS], session)

    try:
        await hub.async_verify_connection()
    except FamilyHubError as ex:
        raise ConfigEntryNotReady(
            f"Cannot connect to Family Hub at {entry.data[CONF_IP_ADDRESS]}: {ex}"
        ) from ex

    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
