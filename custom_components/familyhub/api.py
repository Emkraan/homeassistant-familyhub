"""Samsung Family Hub SmartThings API client and DataUpdateCoordinator."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING

import requests
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CID, DEFAULT_TIMEOUT, UPDATE_INTERVAL

if TYPE_CHECKING:
    from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

_LOGGER = logging.getLogger(__name__)

_ST_DEVICES_URL = "https://client.smartthings.com/devices/status"
_ST_DEVICE_STATUS_URL = (
    "https://api.smartthings.com/v1/devices/{device_id}/components/main/status"
)
_ST_COMMANDS_URL = "https://api.smartthings.com/v1/devices/{device_id}/commands"
_IMAGE_URL = (
    "https://client.smartthings.com/udo/file_links/{file_id}?cid={cid}&di={device_id}"
)

_REFRESH_COMMAND = {
    "commands": [
        {
            "component": "main",
            "capability": "execute",
            "command": "execute",
            "arguments": [
                "/udo/contents/provider/vs/0",
                {"x.com.samsung.da.control": {"x.com.samsung.da.command": "refresh"}},
            ],
        }
    ]
}


class AuthenticationError(Exception):
    """Raised when SmartThings API returns 401/403."""


class FamilyHubCoordinator(DataUpdateCoordinator):
    """Coordinator that polls SmartThings for fridge state and downloads images."""

    def __init__(self, hass: HomeAssistant, api: FamilyHubAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Samsung Family Hub",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.api = api
        self.last_file_ids: list[str] = []
        self.last_updated_at: float | None = None

    async def _async_update_data(self) -> None:
        try:
            await self.api.async_ensure_fresh_token()

            if self.api.device_id is None:
                status = await self.hass.async_add_executor_job(
                    self.api.get_all_device_status
                )
                self.api.set_device_status(status)

            if self.api.should_refresh:
                await self.hass.async_add_executor_job(self.api.send_refresh_command)
                self.api.should_refresh = False
            else:
                status = await self.hass.async_add_executor_job(
                    self.api.get_current_device_status
                )
                self.api.set_current_device_status(status)
                self.api.check_door_state()

            current_ids = self.api.get_file_ids()
            if set(current_ids) != set(self.last_file_ids):
                success = await self.hass.async_add_executor_job(
                    self.api.download_images
                )
                if success:
                    self.last_file_ids = current_ids
                    self.last_updated_at = time.time()

        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "SmartThings token expired or invalid."
            ) from err


class FamilyHubAPI:
    """Low-level SmartThings + Samsung IoT API client for the Family Hub fridge."""

    def __init__(
        self, hass: HomeAssistant, token: str, device_id: str | None = None
    ) -> None:
        self._hass = hass
        self._token = token
        self._device_id = device_id
        self._headers = {"Authorization": f"Bearer {token}"}
        self._iot_headers: dict | None = None
        self._oauth_session: OAuth2Session | None = None
        self._device_status: dict | None = None
        self._current_device_status: dict | None = None
        self._last_closed: str | None = None
        self.should_refresh = False
        self.downloaded_images: list[bytes | None] = [None, None, None]

    # --- Auth ---

    def set_iot_token(self, token: str) -> None:
        self._iot_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.smartthings+json;v=1",
        }

    def attach_oauth_session(self, session: OAuth2Session) -> None:
        self._oauth_session = session

    def update_token(self, token: str) -> None:
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}

    async def async_ensure_fresh_token(self) -> None:
        if self._oauth_session is None:
            return
        await self._oauth_session.async_ensure_token_valid()
        new_token = self._oauth_session.token.get("access_token")
        if new_token and new_token != self._token:
            self.update_token(new_token)

    # --- Device ID resolution ---

    @property
    def device_id(self) -> str | None:
        return self._device_id

    def set_device_status(self, status: dict) -> None:
        self._device_status = status
        if not self._device_id:
            self._resolve_device_id()

    def _resolve_device_id(self) -> None:
        if not self._device_status:
            return
        for item in self._device_status.get("items", []):
            if (
                item.get("capabilityId") == "samsungce.viewInside"
                and item.get("attributeName") == "contents"
            ):
                self._device_id = item["deviceId"]
                _LOGGER.debug("Resolved Family Hub device ID: %s", self._device_id)
                return

    # --- API calls ---

    def _check(self, resp: requests.Response) -> None:
        if resp.status_code in (401, 403):
            raise AuthenticationError(f"HTTP {resp.status_code}")
        if not resp.ok:
            _LOGGER.warning(
                "SmartThings API error: HTTP %s — %s",
                resp.status_code,
                resp.text[:200],
            )

    def get_all_device_status(self) -> dict:
        resp = requests.get(
            _ST_DEVICES_URL, headers=self._headers, timeout=DEFAULT_TIMEOUT
        )
        self._check(resp)
        return resp.json()

    def get_current_device_status(self) -> dict:
        resp = requests.get(
            _ST_DEVICE_STATUS_URL.format(device_id=self._device_id),
            headers=self._headers,
            timeout=DEFAULT_TIMEOUT,
        )
        self._check(resp)
        return resp.json()

    def set_current_device_status(self, status: dict) -> None:
        self._current_device_status = status

    def check_door_state(self) -> None:
        if not self._current_device_status:
            return
        try:
            contact = self._current_device_status["contactSensor"]["contact"]
        except KeyError:
            return
        first_poll = self._last_closed is None
        if contact["value"] == "closed" and (
            first_poll or contact["timestamp"] != self._last_closed
        ):
            self._last_closed = contact["timestamp"]
            self.should_refresh = True

    def get_file_ids(self) -> list[str]:
        if not self._current_device_status:
            return []
        try:
            contents = self._current_device_status["samsungce.viewInside"]["contents"]
            return [item["fileId"] for item in contents["value"]]
        except (KeyError, TypeError):
            return []

    def send_refresh_command(self) -> None:
        if not self._device_id:
            return
        resp = requests.post(
            _ST_COMMANDS_URL.format(device_id=self._device_id),
            headers=self._headers,
            json=_REFRESH_COMMAND,
            timeout=DEFAULT_TIMEOUT,
        )
        self._check(resp)
        _LOGGER.debug("Sent camera refresh command")

    def download_images(self) -> bool:
        if not self._current_device_status or not self._device_id:
            return False
        file_ids = self.get_file_ids()
        dl_headers = self._iot_headers or self._headers
        results: list[bytes | None] = list(self.downloaded_images)
        while len(results) < len(file_ids):
            results.append(None)

        successes = 0
        for idx, file_id in enumerate(file_ids):
            url = _IMAGE_URL.format(file_id=file_id, cid=CID, device_id=self._device_id)
            try:
                resp = requests.get(url, headers=dl_headers, timeout=DEFAULT_TIMEOUT)
                self._check(resp)
                results[idx] = resp.content
                successes += 1
            except AuthenticationError:
                raise
            except Exception as ex:
                _LOGGER.warning("Failed to download image[%d]: %s", idx, ex)

        self.downloaded_images = results
        return successes > 0

    async def async_authenticate(self) -> bool:
        """Verify connectivity by fetching device list."""
        status = await self._hass.async_add_executor_job(self.get_all_device_status)
        self.set_device_status(status)
        return True
