<p align="center">
  <img src="https://raw.githubusercontent.com/Emkraan/homeassistant-familyhub/main/.github/homeassistant-familyhub.png" alt="Samsung Family Hub" width="120" />
</p>

<h1 align="center">Samsung Family Hub — Home Assistant Integration</h1>

<p align="center">
  Local camera integration for the Samsung Family Hub refrigerator.<br>
  No cloud. No Samsung account. Just your fridge on your LAN.
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

- **Fully local** — communicates directly with the refrigerator over your LAN. No Samsung cloud account required.
- **GUI setup** — configure from Settings → Devices & Services. No YAML editing needed.
- **Camera entity** — exposes a composite still image from all refrigerator cameras (inner fridge, inner freezer, door).
- **Proper device registry** — appears as a Samsung Family Hub device with all entities grouped.
- **Graceful error handling** — marks integration as unavailable if the refrigerator is unreachable at startup, retries automatically.

---

## Requirements

| Requirement | Detail |
|---|---|
| Home Assistant | 2024.1.0 or newer |
| HACS | 1.34.0 or newer |
| Refrigerator | Samsung Family Hub (any model with local API on port 17654) |
| Network | HA host must be able to reach the refrigerator on port 17654 |

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
2. Copy the `custom_components/familyhub/` folder into `<config>/custom_components/`.
3. Restart Home Assistant.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Samsung Family Hub**.
3. Enter the refrigerator's **IP address** and an optional **name**.
4. Click **Submit**.

> Find the refrigerator's IP address in your router's DHCP client list or the SmartThings app under device details.

---

## Entities

### Camera

| Entity | Description |
|---|---|
| Camera | Composite still image stitched from all refrigerator cameras (inner fridge, inner freezer). Updated on each request. |

> **Note:** The Family Hub caches images on the device. Images may be up to 1 hour old depending on your refrigerator's firmware version. There is no known way to force a live capture via the local API.

---

## Automations

### Notify when someone opens the fridge

```yaml
automation:
  - alias: "Family Hub — Fridge opened notification"
    trigger:
      - platform: state
        entity_id: camera.samsung_family_hub_camera
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "The fridge was opened!"
          data:
            image: /api/camera_proxy/camera.samsung_family_hub_camera
```

### Capture a snapshot on motion (if using MotionEye)

```yaml
automation:
  - alias: "Family Hub — Save snapshot hourly"
    trigger:
      - platform: time_pattern
        hours: "/1"
    action:
      - service: camera.snapshot
        target:
          entity_id: camera.samsung_family_hub_camera
        data:
          filename: "/config/www/familyhub_snapshot.jpg"
```

### Use image in a dashboard card

```yaml
type: picture-entity
entity: camera.samsung_family_hub_camera
camera_view: auto
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Integration stuck on "Configuring" | Refrigerator unreachable at HA startup | Ensure fridge is powered on and reachable on port 17654; HA retries automatically |
| Camera entity unavailable | Network issue or wrong IP | Confirm `curl http://<ip>:17654/.krate/owner/share/scloud/glazeCameraInfo.txt` returns JSON from your HA host |
| Images are old / stale | Family Hub caches camera images | This is a device limitation — no live capture is possible via the local API |
| Camera entity shows but image fails | Pillow not installed | Restart HA after HACS install to ensure Pillow is loaded |
| Cannot connect error during setup | Firewall or VLAN blocking port 17654 | Ensure HA host can reach the fridge on TCP port 17654 |

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

The Samsung Family Hub refrigerator runs a local HTTP server on port 17654. This integration communicates directly with that server — no Samsung account, no cloud, no external API required.

**Endpoints used:**

| Request | URL | Returns |
|---|---|---|
| Camera manifest | `http://<ip>:17654/.krate/owner/share/scloud/glazeCameraInfo.txt` | JSON with `GlazeURL` array of image paths |
| Camera image(s) | `http://<ip>:17654/.krate/owner/share/scloud/<path>` | Raw JPEG bytes per camera |

The integration fetches the manifest to discover which camera image paths are available, downloads each image, then stitches them vertically into a single composite JPEG using Pillow. This is the same approach used by the original `pyfamilyhublocal` library, rewritten directly into the integration without any external package dependency (except Pillow, which HA already includes).

---

## License

Licensed under the MIT License. See [LICENSE](LICENSE) for details.
