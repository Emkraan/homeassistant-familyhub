"""The Samsung Family Hub integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_entry_oauth2_flow

from .api import FamilyHubAPI, FamilyHubCoordinator
from .auth import AuthError, refresh_samsung_iot_token
from .const import (
    AUTH_MODE_OAUTH,
    AUTH_MODE_PAT,
    CONF_AUTH_MODE,
    CONF_DEVICE_ID,
    CONF_LINKED_SMARTTHINGS_ENTRY_ID,
    CONF_SAMSUNG_IOT_AUTH_SERVER,
    CONF_SAMSUNG_IOT_REFRESH_TOKEN,
    CONF_TOKEN,
    DOMAIN,
    SAMSUNG_AUTH_SERVER,
    SMARTTHINGS_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CAMERA, Platform.SENSOR]


@dataclass
class FamilyHubData:
    api: FamilyHubAPI
    coordinator: FamilyHubCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Samsung Family Hub from a config entry."""
    auth_mode = entry.data.get(CONF_AUTH_MODE, AUTH_MODE_PAT)
    device_id = entry.data.get(CONF_DEVICE_ID)

    if auth_mode == AUTH_MODE_OAUTH:
        api = await _build_oauth_api(hass, entry, device_id)
    else:
        token = entry.data.get(CONF_TOKEN)
        if not token:
            raise ConfigEntryNotReady("No token found — reconfigure the integration.")
        api = FamilyHubAPI(hass, token=token, device_id=device_id)

    coordinator = FamilyHubCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = FamilyHubData(api=api, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_refresh(call: ServiceCall) -> None:
        await api.async_ensure_fresh_token()
        await hass.async_add_executor_job(api.send_refresh_command)
        _LOGGER.info("Manual camera refresh command sent")

    hass.services.async_register(DOMAIN, "refresh", _handle_refresh)
    return True


async def _build_oauth_api(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str | None
) -> FamilyHubAPI:
    linked_id = entry.data.get(CONF_LINKED_SMARTTHINGS_ENTRY_ID)
    if not linked_id:
        raise ConfigEntryNotReady(
            "OAuth mode entry missing linked SmartThings entry — reconfigure."
        )

    smartthings_entry = hass.config_entries.async_get_entry(linked_id)
    if smartthings_entry is None or smartthings_entry.domain != SMARTTHINGS_DOMAIN:
        raise ConfigEntryNotReady(
            f"Linked SmartThings entry {linked_id} not found. "
            "Re-add SmartThings and reconfigure this integration."
        )

    impl = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, smartthings_entry
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, smartthings_entry, impl)
    try:
        await session.async_ensure_token_valid()
    except Exception as ex:
        raise ConfigEntryNotReady(
            f"Failed to obtain fresh SmartThings token: {ex}"
        ) from ex

    api = FamilyHubAPI(hass, token=session.token["access_token"], device_id=device_id)
    api.attach_oauth_session(session)

    iot_refresh = entry.data.get(CONF_SAMSUNG_IOT_REFRESH_TOKEN)
    iot_server = entry.data.get(CONF_SAMSUNG_IOT_AUTH_SERVER, SAMSUNG_AUTH_SERVER)
    if iot_refresh:
        try:
            iot_creds = await hass.async_add_executor_job(
                refresh_samsung_iot_token, iot_refresh, iot_server
            )
            api.set_iot_token(iot_creds.access_token)
            if iot_creds.refresh_token != iot_refresh:
                hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_SAMSUNG_IOT_REFRESH_TOKEN: iot_creds.refresh_token,
                    },
                )
            _LOGGER.debug("Samsung IoT token refreshed")
        except AuthError as ex:
            _LOGGER.warning(
                "Could not refresh Samsung IoT token — images may not download: %s", ex
            )

    return api


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        try:
            hass.services.async_remove(DOMAIN, "refresh")
        except Exception:
            pass
    return unload_ok
