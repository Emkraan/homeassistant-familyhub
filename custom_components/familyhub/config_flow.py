"""Config flow for Samsung Family Hub."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .hub import FamilyHub, FamilyHubError

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Samsung Family Hub"

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


class FamilyHubConfigFlow(ConfigFlow, domain="familyhub"):
    """Handle a config flow for Samsung Family Hub."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input[CONF_IP_ADDRESS].strip()
            await self.async_set_unique_id(ip)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            hub = FamilyHub(ip, session)
            try:
                await hub.async_verify_connection()
            except FamilyHubError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error connecting to Family Hub")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_IP_ADDRESS: ip,
                        CONF_NAME: user_input[CONF_NAME],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "help": "Find your refrigerator's IP address in your router's DHCP client list or the SmartThings app."
            },
        )
