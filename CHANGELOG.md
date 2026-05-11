# Changelog

## 2026.5.1-beta (2026-05-11)

Rebuilt for Tizen 4+ firmware — local HTTP API no longer available on newer Samsung firmware.

- Switch to SmartThings cloud API (local port 17654 API removed in Tizen 4+)
- Config flow now collects Samsung Account credentials inline — no external scripts needed
- OAuth mode: piggybacks on existing HA core SmartThings integration, tokens auto-refresh
- PAT fallback mode retained for users without HA core SmartThings integration
- Three camera entities: top, middle, bottom refrigerator cameras
- Sensor: image last-updated timestamp
- Auto-refresh images on door close (via SmartThings contact sensor)
- Manual refresh via `familyhub.refresh` service call
- Samsung IoT token persisted and auto-refreshed on startup

## 2026.5.0-beta (2026-05-11)

Initial beta release (local API — superseded by 2026.5.1-beta).
