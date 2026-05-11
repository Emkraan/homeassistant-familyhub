"""Samsung Account authentication for IoT-scoped image download tokens."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import requests

from .const import SAMSUNG_AUTH_SERVER, SAMSUNG_IOT_CLIENT_ID, SAMSUNG_LOGIN_CLIENT_ID

_LOGGER = logging.getLogger(__name__)

_SAMSUNG_AUTH_URL = f"{SAMSUNG_AUTH_SERVER}/auth/oauth2/requestAuthentication"
_SAMSUNG_TOKEN_URL = f"{SAMSUNG_AUTH_SERVER}/auth/oauth2/authWithTncMandatory"
_SAMSUNG_IOT_AUTHORIZE_URL = f"{SAMSUNG_AUTH_SERVER}/auth/oauth2/v2/authorize"
_SAMSUNG_IOT_TOKEN_URL = f"{SAMSUNG_AUTH_SERVER}/auth/oauth2/token"

_TIMEOUT = 30


class AuthError(Exception):
    """Raised when Samsung Account authentication fails."""


@dataclass
class SamsungIoTCredentials:
    """Samsung Account IoT-scoped token pair for client.smartthings.com."""

    access_token: str
    refresh_token: str
    auth_server_url: str = SAMSUNG_AUTH_SERVER


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _device_id(email: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(email.encode()).digest()[:8])
        .rstrip(b"=")
        .decode()
    )


def get_samsung_iot_credentials(email: str, password: str) -> SamsungIoTCredentials:
    """Log in with Samsung Account credentials and return IoT-scoped tokens.

    Three-step flow:
      1. requestAuthentication (email+password) → userauth_token
      2. /v2/authorize (userauth_token) → auth code
      3. /token (auth code) → access_token + refresh_token
    """
    did = _device_id(email)
    physical = f"IMEI%3A{did}"

    # Step 1: get userauth_token
    resp = requests.post(
        _SAMSUNG_AUTH_URL,
        data={
            "signin_client_id": SAMSUNG_LOGIN_CLIENT_ID,
            "signin_client_secret": "",
            "check_2factor_authentication": "Y",
            "originalAppID": SAMSUNG_LOGIN_CLIENT_ID,
            "devicePhysicalAddressText": physical,
            "customerCode": "NEE",
            "deviceMultiUserID": "0",
            "phoneNumberText": "",
            "deviceName": "HomeAssistant",
            "client_id": SAMSUNG_LOGIN_CLIENT_ID,
            "deviceTypeCode": "PHONE DEVICE",
            "password": password,
            "deviceUniqueID": physical,
            "scope": "iot.client+mcs.client",
            "serviceRequired": "N",
            "physical_address_text": physical,
            "login_id_type": "email_id",
            "mobileCountryCode": "310",
            "mobileNetworkCode": "00",
            "deviceNetworkAddressText": "02%3A00%3A00%3A00%3A00%3A00",
            "service_type": "M",
            "isRegisterDevice": "Y",
            "deviceModelID": "SM-G991B",
            "deviceSerialNumberText": did,
            "softwareVersion": "RP1A.200720.012",
            "username": email,
            "login_id": email,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 401:
        raise AuthError("Invalid Samsung Account email or password.")
    if resp.status_code == 403:
        raise AuthError(
            "Samsung Account login blocked. If 2FA is enabled on your account, "
            "this integration cannot authenticate. Disable 2FA or use a sub-account."
        )
    resp.raise_for_status()
    body = resp.json()
    userauth_token = body.get("userauth_token")
    if not userauth_token:
        raise AuthError(
            f"Samsung login did not return userauth_token: {body.get('error_description', body)}"
        )

    return get_samsung_iot_token(userauth_token, login_id=email)


def get_samsung_iot_token(
    userauth_token: str,
    login_id: str = "",
    auth_server_url: str = SAMSUNG_AUTH_SERVER,
) -> SamsungIoTCredentials:
    """Exchange a userauth_token for an IoT-scoped access + refresh token pair."""
    verifier, challenge = _pkce_pair()
    device_id = base64.urlsafe_b64encode(os.urandom(8)).rstrip(b"=").decode()

    params: dict = {
        "response_type": "code",
        "client_id": SAMSUNG_IOT_CLIENT_ID,
        "scope": "iot.client",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "userauth_token": userauth_token,
        "serviceType": "M",
        "childAccountSupported": "Y",
        "physical_address_text": device_id,
    }
    if login_id:
        params["login_id"] = login_id

    resp = requests.get(
        f"{auth_server_url}/auth/oauth2/v2/authorize",
        params=params,
        allow_redirects=False,
        timeout=_TIMEOUT,
    )
    if resp.status_code not in (200, 302):
        raise AuthError(
            f"IoT authorize failed: HTTP {resp.status_code} — {resp.text[:200]}"
        )

    auth_code: str | None = None
    if resp.status_code == 302:
        loc = resp.headers.get("Location", "")
        codes = parse_qs(urlparse(loc).query).get("code", [])
        if codes:
            auth_code = codes[0]
    if not auth_code:
        try:
            body = resp.json()
            auth_code = body.get("code") or body.get("auth_code")
        except Exception:
            pass
    if not auth_code:
        raise AuthError(f"IoT authorize returned no code: {resp.text[:300]}")

    resp = requests.post(
        f"{auth_server_url}/auth/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": SAMSUNG_IOT_CLIENT_ID,
            "code": auth_code,
            "code_verifier": verifier,
            "physical_address_text": device_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise AuthError(
            f"IoT token exchange failed: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    body = resp.json()
    access = body.get("access_token")
    refresh = body.get("refresh_token")
    if not access or not refresh:
        raise AuthError(f"IoT token response missing tokens: {body}")

    return SamsungIoTCredentials(
        access_token=access,
        refresh_token=refresh,
        auth_server_url=auth_server_url,
    )


def refresh_samsung_iot_token(
    refresh_token: str,
    auth_server_url: str = SAMSUNG_AUTH_SERVER,
) -> SamsungIoTCredentials:
    """Refresh a Samsung IoT token, returning new access + refresh tokens."""
    resp = requests.post(
        f"{auth_server_url}/auth/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": SAMSUNG_IOT_CLIENT_ID,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 401:
        raise AuthError("Samsung IoT refresh token expired — re-authenticate.")
    resp.raise_for_status()
    body = resp.json()
    return SamsungIoTCredentials(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", refresh_token),
        auth_server_url=auth_server_url,
    )
