"""Config flow for Samsung Family Hub."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, SOURCE_IGNORE
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

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
    return [
        e
        for e in hass.config_entries.async_entries(SMARTTHINGS_DOMAIN)
        if e.source != SOURCE_IGNORE
    ]


def _find_family_hub_devices(hass) -> list[dict]:
    """Return Family Hub devices from all loaded SmartThings entries."""
    results = []
    for entry in hass.config_entries.async_entries(SMARTTHINGS_DOMAIN):
        if entry.source == SOURCE_IGNORE:
            continue
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None:
            continue
        devices = getattr(runtime, "devices", {})
        for device_id, full_device in devices.items():
            main_status = getattr(full_device, "status", {}).get("main", {})
            if "samsungce.viewInside" in main_status:
                label = (
                    getattr(getattr(full_device, "device", None), "label", None)
                    or device_id
                )
                results.append(
                    {
                        "device_id": device_id,
                        "label": label,
                        "entry_id": entry.entry_id,
                    }
                )
    return results


class FamilyHubConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Samsung Family Hub."""

    VERSION = 1

    def __init__(self) -> None:
        self._linked_entry_id: str | None = None
        self._device_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if _smartthings_entries(self.hass):
            return self.async_show_menu(
                step_id="user",
                menu_options=["oauth", "pat"],
            )
        return await self.async_step_pat()

    # ── OAuth path ────────────────────────────────────────────────────────────

    async def async_step_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select SmartThings entry and pick the Family Hub device."""
        errors: dict[str, str] = {}
        st_entries = _smartthings_entries(self.hass)
        st_options = {e.entry_id: e.title or e.entry_id for e in st_entries}

        # Find Family Hub devices already known to SmartThings
        fh_devices = _find_family_hub_devices(self.hass)

        if user_input is not None:
            self._linked_entry_id = user_input[CONF_LINKED_SMARTTHINGS_ENTRY_ID]
            selected = user_input.get(CONF_DEVICE_ID) or None
            if selected and selected != "__manual__":
                self._device_id = selected
            else:
                self._device_id = None
            return await self.async_step_samsung_credentials()

        # Build device options — filter to devices from selected ST entry if possible
        device_options: list[SelectOptionDict] = []
        for d in fh_devices:
            device_options.append(
                SelectOptionDict(value=d["device_id"], label=d["label"])
            )
        device_options.append(SelectOptionDict(value="__manual__", label="Auto-detect"))

        schema_fields: dict = {
            vol.Required(CONF_LINKED_SMARTTHINGS_ENTRY_ID): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=k, label=v)
                        for k, v in st_options.items()
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required(CONF_DEVICE_ID, default="__manual__"): SelectSelector(
                SelectSelectorConfig(
                    options=device_options,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }

        return self.async_show_form(
            step_id="oauth",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    async def async_step_samsung_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Get Samsung IoT token via email + password (no 2FA accounts only)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_SAMSUNG_EMAIL].strip()
            password = user_input[CONF_SAMSUNG_PASSWORD]
            try:
                api = await self._build_api()
                if not self._device_id:
                    await api.async_authenticate()
                    self._device_id = api.device_id

                iot_creds = await self.hass.async_add_executor_job(
                    get_samsung_iot_credentials, email, password
                )
            except AuthError as ex:
                msg = str(ex)
                if "Invalid Samsung" in msg or "password" in msg.lower():
                    errors["base"] = "invalid_samsung_auth"
                elif "2FA" in msg or "blocked" in msg:
                    errors["base"] = "samsung_2fa"
                else:
                    errors["base"] = "samsung_auth_error"
                _LOGGER.warning("Samsung credentials auth failed: %s", ex)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during Samsung credential auth")
                errors["base"] = "unknown"
            else:
                return await self._create_oauth_entry(iot_creds.refresh_token)

        return self.async_show_form(
            step_id="samsung_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SAMSUNG_EMAIL): str,
                    vol.Required(CONF_SAMSUNG_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "samsung_account_url": "https://account.samsung.com",
            },
        )

    async def _build_api(self) -> FamilyHubAPI:
        """Build a FamilyHubAPI using the linked SmartThings OAuth session."""
        smartthings_entry = self.hass.config_entries.async_get_entry(
            self._linked_entry_id
        )
        impl = await config_entry_oauth2_flow.async_get_config_entry_implementation(
            self.hass, smartthings_entry
        )
        session = config_entry_oauth2_flow.OAuth2Session(
            self.hass, smartthings_entry, impl
        )
        await session.async_ensure_token_valid()
        api = FamilyHubAPI(
            self.hass,
            token=session.token["access_token"],
            device_id=self._device_id,
        )
        api.attach_oauth_session(session)
        return api

    async def _create_oauth_entry(self, iot_refresh_token: str) -> ConfigFlowResult:
        await self.async_set_unique_id(self._device_id or self._linked_entry_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Samsung Family Hub",
            data={
                CONF_AUTH_MODE: AUTH_MODE_OAUTH,
                CONF_LINKED_SMARTTHINGS_ENTRY_ID: self._linked_entry_id,
                CONF_DEVICE_ID: self._device_id,
                CONF_SAMSUNG_IOT_REFRESH_TOKEN: iot_refresh_token,
                CONF_SAMSUNG_IOT_AUTH_SERVER: SAMSUNG_AUTH_SERVER,
            },
        )

    # ── PAT path ──────────────────────────────────────────────────────────────

    async def async_step_pat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                "token_url": "https://account.smartthings.com/tokens",
            },
        )

    # ── Reauth ────────────────────────────────────────────────────────────────

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        if entry_data.get(CONF_AUTH_MODE) == AUTH_MODE_OAUTH:
            self._linked_entry_id = entry_data.get(CONF_LINKED_SMARTTHINGS_ENTRY_ID)
            self._device_id = entry_data.get(CONF_DEVICE_ID)
            return await self.async_step_samsung_credentials()
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
