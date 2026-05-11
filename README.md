<p align="center">
  <img src="https://raw.githubusercontent.com/Emkraan/homeassistant-familyhub/main/.github/homeassistant-familyhub.png" alt="Samsung Family Hub" width="120" />
</p>

<h1 align="center">Samsung Family Hub — Home Assistant Integration</h1>

<p align="center">
  SmartThings-powered camera integration for the Samsung Family Hub refrigerator.<br>
  GUI setup. Three camera entities. Auto-refreshes on door close.
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-blue.svg?style=for-the-badge" alt="HACS Custom"></a>
  <a href="https://github.com/Emkraan/homeassistant-familyhub/releases"><img src="https://img.shields.io/github/v/release/Emkraan/homeassistant-familyhub?style=for-the-badge" alt="Latest release"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white" alt="HA 2024.1+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"></a>
</p>

<div align="center">

⚠️ 🚨 **This is an unofficial integration and is not affiliated with or endorsed by Samsung.** 🚨 ⚠️

</div>

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Automations](#automations)
- [Troubleshooting](#troubleshooting)
- [How It Works](#how-it-works)
- [License](#license)

---

## Features

- **GUI setup** — configure from Settings → Devices & Services, no YAML required
- **Three camera entities** — top, middle, and bottom refrigerator camera slots
- **Auto-refresh on door close** — detects fridge door events via SmartThings and triggers a fresh image capture
- **Manual refresh** — `familyhub.refresh` service call triggers an immediate capture
- **SmartThings OAuth** — reuses your existing HA SmartThings integration credentials, tokens auto-refresh
- **Last updated sensor** — timestamp of when images were last downloaded
- **Full model support** — works with any Family Hub model visible in SmartThings

---

## Requirements

| Requirement | Detail |
|---|---|
| Home Assistant | 2024.1.0 or newer |
| HACS | 1.34.0 or newer |
| SmartThings | HA core SmartThings integration configured with your Samsung account |
| Samsung Account | Required for image downloads (separate IoT token — one-time setup) |
| Firmware | Tizen 4+ (newer Family Hub models) — uses SmartThings cloud API |

> **Note:** Older firmware (Tizen 3 and earlier) used a local HTTP API on port 17654. That API is no longer available on current firmware. This integration uses the SmartThings cloud API instead.

---

## Installation

### HACS (Recommended)

Click the badge below to open HACS and add this repository in one step:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Emkraan&repository=homeassistant-familyhub&category=integration)

Or manually:

1. Open **HACS → Integrations**.
2. Click the menu (⋮) → **Custom repositories**.
3. Add `https://github.com/Emkraan/homeassistant-familyhub` — category: **Integration**.
4. Search for **Samsung Family Hub** and click **Download**.
5. Restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/Emkraan/homeassistant-familyhub/releases/latest).
2. Copy `custom_components/familyhub/` into `<config>/custom_components/`.
3. Restart Home Assistant.

---

## Configuration

**Before you start:** Make sure the HA core [SmartThings integration](https://www.home-assistant.io/integrations/smartthings/) is set up and your Family Hub refrigerator is visible in it.

1. Go to **Settings → Devices & Services → Add Integration → Samsung Family Hub**
2. Choose **Use existing SmartThings integration**
3. Select your SmartThings entry and your refrigerator from the dropdown
4. Choose how to authenticate your Samsung Account for image downloads:

### Option A — Email and password (no 2FA)

Enter your Samsung Account credentials directly. 2FA must be disabled on the account.

### Option B — Refresh token (2FA accounts)

If 2FA is enabled, you need to capture a Samsung IoT refresh token once from your browser:

1. Open [account.samsung.com](https://account.samsung.com) in a browser and open **Developer Tools → Network tab**
2. Log in with your Samsung Account (complete 2FA when prompted)
3. Filter network requests for `samsungosp.com`
4. Look for a POST request to `/auth/oauth2/token` — open its response
5. Copy the `refresh_token` value and paste it into the integration

The token is long-lived and auto-refreshes — you only do this once.

---

## Entities

### Cameras

| Entity | Description |
|---|---|
| Top Camera | Inner top camera slot |
| Middle Camera | Inner middle camera slot |
| Bottom Camera | Inner bottom / drawer camera slot |

> Images are captured when the fridge door closes. They may be a few minutes old depending on your fridge's polling interval. Trigger `familyhub.refresh` to force an immediate capture.

### Sensor

| Entity | Description |
|---|---|
| Images Last Updated | Timestamp of the most recent successful image download |

---

## Automations

### Notify when fridge images update

```yaml
automation:
  - alias: "Family Hub — Fridge image updated"
    trigger:
      - platform: state
        entity_id: sensor.samsung_family_hub_images_last_updated
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "Fridge images updated"
          data:
            image: /api/camera_proxy/camera.samsung_family_hub_top_camera
```

### Manual camera refresh

```yaml
service: familyhub.refresh
```

### Show camera in a dashboard card

```yaml
type: picture-entity
entity: camera.samsung_family_hub_top_camera
camera_view: auto
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Cannot connect" during setup | SmartThings token invalid or expired | Re-authenticate the SmartThings integration |
| Camera entities unavailable | SmartThings API unreachable | Check internet connectivity from HA host |
| Images never update | Samsung IoT token invalid | Reconfigure the integration and re-enter credentials |
| Wrong images / no images | Fridge not detected in SmartThings | Ensure the refrigerator appears in your SmartThings integration with the `samsungce.viewInside` capability |
| 2FA error during setup | 2FA enabled on Samsung Account | Use the refresh token option instead of email/password |
| Images are stale | No door-close event received | Trigger manually via `familyhub.refresh` service |

**Enable debug logging:**

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.familyhub: debug
```

---

## How It Works

Samsung Family Hub refrigerators on Tizen 4+ firmware expose their camera images through the SmartThings cloud API rather than a local HTTP endpoint.

**Authentication — two tokens required:**

| Token | Purpose | Source |
|---|---|---|
| SmartThings OAuth | Device status polling, refresh commands | Reused from HA core SmartThings integration |
| Samsung IoT token | Image downloads from `client.smartthings.com` | Samsung Account credentials (one-time setup) |

**Endpoints used:**

| Purpose | URL |
|---|---|
| List devices | `https://client.smartthings.com/devices/status` |
| Device status | `https://api.smartthings.com/v1/devices/{id}/components/main/status` |
| Trigger image capture | `https://api.smartthings.com/v1/devices/{id}/commands` |
| Download image | `https://client.smartthings.com/udo/file_links/{fileId}?cid=...&di={deviceId}` |

The coordinator polls device status every 10 seconds. When the contact sensor reports the door was closed, it sends an OCF refresh command to the fridge which triggers new images to be captured and uploaded. The coordinator detects the new file IDs and downloads them.

---

## License

Licensed under the MIT License. See [LICENSE](LICENSE) for details.
