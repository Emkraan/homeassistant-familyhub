"""Config flow for Samsung Family Hub."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow

from .api import AuthenticationError, FamilyHubAPI
from .auth import AuthError, get_samsung_iot_credentials
from .const import (
    AUTH_MODE_OAUTH,
    AUTH_MODE_PAT,
    CONF_AUTH_MODE,
    CONF_DEVICE_ID,
    CONF_LINKED_SMARTTHINGS_ENTRY_ID,
    CONF_SAMSUNG_EMAIL,
    CONF_SAMSUNG_IOT_AUTH_SERVER,
    CONF_SAMSUNG_IOT_REFRESH_TOKEN,
    CONF_SAMSUNG_PASSWORD,
    CONF_TOKEN,
    DOMAIN,
    SAMSUNG_AUTH_SERVER,
    SMARTTHINGS_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _smartthings_entries(hass):
    from homeassistant.config_entries import SOURCE_IGNORE

    return [
        e
        for e in hass.config_entries.async_entries(SMARTTHINGS_DOMAIN)
        if e.source != SOURCE_IGNORE
    ]


class FamilyHubConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Samsung Family Hub."""

    VERSION = 1

    def __init__(self) -> None:
        self._linked_entry_id: str | None = None
        self._device_id: str | None = None
        self._st_token: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step — show menu if SmartThings is available."""
        if _smartthings_entries(self.hass):
            return self.async_show_menu(
                step_id="user",
                menu_options=["oauth", "pat"],
            )
        return await self.async_step_pat()

    # ---- OAuth path ----

    async def async_step_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select SmartThings entry and enter Samsung Account for IoT token."""
        entries = _smartthings_entries(self.hass)
        errors: dict[str, str] = {}
        options = {e.entry_id: e.title or e.entry_id for e in entries}

        if user_input is not None:
            self._linked_entry_id = user_input[CONF_LINKED_SMARTTHINGS_ENTRY_ID]
            self._device_id = user_input.get(CONF_DEVICE_ID) or None
            return await self.async_step_samsung_account()

        return self.async_show_form(
            step_id="oauth",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LINKED_SMARTTHINGS_ENTRY_ID): vol.In(options),
                    vol.Optional(CONF_DEVICE_ID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_samsung_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect Samsung Account credentials to obtain the IoT image token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_SAMSUNG_EMAIL].strip()
            password = user_input[CONF_SAMSUNG_PASSWORD]

            smartthings_entry = self.hass.config_entries.async_get_entry(
                self._linked_entry_id
            )
            impl = await config_entry_oauth2_flow.async_get_config_entry_implementation(
                self.hass, smartthings_entry
            )
            session = config_entry_oauth2_flow.OAuth2Session(
                self.hass, smartthings_entry, impl
            )
            try:
                await session.async_ensure_token_valid()
                st_token = session.token["access_token"]

                api = FamilyHubAPI(self.hass, token=st_token, device_id=self._device_id)
                api.attach_oauth_session(session)
                await api.async_authenticate()
                if not self._device_id:
                    self._device_id = api.device_id

                iot_creds = await self.hass.async_add_executor_job(
                    get_samsung_iot_credentials, email, password
                )
            except AuthError as ex:
                if "Invalid Samsung" in str(ex) or "password" in str(ex).lower():
                    errors["base"] = "invalid_samsung_auth"
                elif "2FA" in str(ex):
                    errors["base"] = "samsung_2fa"
                else:
                    errors["base"] = "samsung_auth_error"
                _LOGGER.warning("Samsung Account auth failed: %s", ex)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(self._device_id or self._linked_entry_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Samsung Family Hub",
                    data={
                        CONF_AUTH_MODE: AUTH_MODE_OAUTH,
                        CONF_LINKED_SMARTTHINGS_ENTRY_ID: self._linked_entry_id,
                        CONF_DEVICE_ID: self._device_id,
                        CONF_SAMSUNG_IOT_REFRESH_TOKEN: iot_creds.refresh_token,
                        CONF_SAMSUNG_IOT_AUTH_SERVER: iot_creds.auth_server_url,
                    },
                )

        return self.async_show_form(
            step_id="samsung_account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SAMSUNG_EMAIL): str,
                    vol.Required(CONF_SAMSUNG_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "help": "Enter your Samsung Account credentials (the same account used in the SmartThings app). 2FA must be disabled."
            },
        )

    # ---- PAT path (legacy) ----

    async def async_step_pat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter a SmartThings Personal Access Token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            device_id = user_input.get(CONF_DEVICE_ID) or None
            try:
                api = FamilyHubAPI(self.hass, token=token, device_id=device_id)
                await api.async_authenticate()
                if not device_id:
                    device_id = api.device_id
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during PAT validation")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(device_id or token[:8])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Samsung Family Hub",
                    data={
                        CONF_AUTH_MODE: AUTH_MODE_PAT,
                        CONF_TOKEN: token,
                        CONF_DEVICE_ID: device_id,
                    },
                )

        return self.async_show_form(
            step_id="pat",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Optional(CONF_DEVICE_ID): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "help": "Create a token at https://account.smartthings.com/tokens — note tokens expire after 24 hours."
            },
        )

    # ---- Reauth ----

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Re-authenticate when the token has expired."""
        if entry_data.get(CONF_AUTH_MODE) == AUTH_MODE_OAUTH:
            return await self.async_step_samsung_account()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            try:
                api = FamilyHubAPI(
                    self.hass,
                    token=user_input[CONF_TOKEN].strip(),
                    device_id=reauth_entry.data.get(CONF_DEVICE_ID),
                )
                await api.async_authenticate()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_TOKEN: user_input[CONF_TOKEN].strip(),
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )
