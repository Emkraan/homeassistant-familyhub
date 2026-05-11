"""Samsung Family Hub local API client."""

from __future__ import annotations

import asyncio
import io
import json
import logging

from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

_PORT = 17654
_SERVER_PATH = ".krate/owner/share/scloud"
_CAM_INFO_FILE = "glazeCameraInfo.txt"
_REQUEST_TIMEOUT = 10


class FamilyHubError(Exception):
    """Raised when communication with the Family Hub fails."""


class FamilyHub:
    """Local HTTP client for the Samsung Family Hub refrigerator camera."""

    def __init__(self, ip_address: str, session: ClientSession) -> None:
        self._base_url = f"http://{ip_address}:{_PORT}/{_SERVER_PATH}"
        self._session = session

    async def async_verify_connection(self) -> None:
        """Verify we can reach the device by fetching camera info."""
        await self._async_get_cam_info()

    async def async_get_cam_image(self) -> bytes | None:
        """Return a composite still image from all refrigerator cameras."""
        try:
            cam_info = await self._async_get_cam_info()
            image_urls = cam_info.get("GlazeURL", [])
            if not image_urls:
                _LOGGER.warning("Family Hub returned no camera URLs")
                return None
            images = await self._async_get_images(image_urls)
            return self._stitch_images(images)
        except FamilyHubError:
            raise
        except Exception as ex:
            raise FamilyHubError(f"Failed to retrieve camera image: {ex}") from ex

    async def _async_get_cam_info(self) -> dict:
        """Fetch the camera manifest JSON from the device."""
        url = f"{self._base_url}/{_CAM_INFO_FILE}"
        try:
            async with asyncio.timeout(_REQUEST_TIMEOUT):
                async with self._session.get(url) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    return json.loads(text)
        except asyncio.TimeoutError as ex:
            raise FamilyHubError(f"Timeout connecting to Family Hub at {url}") from ex
        except Exception as ex:
            raise FamilyHubError(f"Error fetching camera info: {ex}") from ex

    async def _async_get_images(self, image_urls: list[str]) -> list[io.BytesIO]:
        """Fetch each camera image and return as BytesIO objects."""
        images = []
        for path in image_urls:
            url = f"{self._base_url}/{path.lstrip('/')}"
            try:
                async with asyncio.timeout(_REQUEST_TIMEOUT):
                    async with self._session.get(url) as resp:
                        resp.raise_for_status()
                        data = await resp.read()
                        images.append(io.BytesIO(data))
            except Exception as ex:
                _LOGGER.warning("Failed to fetch camera image from %s: %s", url, ex)
        return images

    @staticmethod
    def _stitch_images(images: list[io.BytesIO]) -> bytes | None:
        """Stitch multiple camera images vertically into one JPEG."""
        if not images:
            return None
        try:
            from PIL import Image

            pil_images = [Image.open(img) for img in images]
            total_width = max(i.width for i in pil_images)
            total_height = sum(i.height for i in pil_images)
            composite = Image.new("RGB", (total_width, total_height))
            y_offset = 0
            for img in pil_images:
                composite.paste(img, (0, y_offset))
                y_offset += img.height
            buf = io.BytesIO()
            composite.save(buf, format="JPEG")
            return buf.getvalue()
        except Exception as ex:
            _LOGGER.warning("Failed to stitch camera images: %s", ex)
            return None
