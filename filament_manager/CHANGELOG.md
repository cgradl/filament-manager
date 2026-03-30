# Changelog

## 0.5.5

- Automatically inherit language from Home Assistant instance on first load
- User-selected language (via in-app switcher) still takes precedence

## 0.5.4

- Full EN / DE / ES interface translations with in-app language switcher
- Language preference persisted across sessions (localStorage)
- Date-fns relative times now locale-aware in dashboard and print history
- Settings page data-transfer section redesigned to match dark card style

## 0.5.3

- Fix startup crash: copy config.yaml into Docker image and use absolute path for version lookup
- Show app icon in collapsed sidebar and mobile drawer header

## 0.5.2

- Add data export / import feature (Settings → Export / Import)
- Remove personal spool seed data — new installs start empty
- Version number now visible in Settings header
- Version endpoint: GET /api/settings/version

## 0.5.0

- Initial public release
- Automatic print detection via Bambu Lab HA integration
- AMS filament tracking with per-spool consumption calculation
- Full spool inventory management (brand, material, color, weight, cost)
- Cost analytics and dashboard with charts
- Printer auto-discovery for Bambu Lab entities
- Multi-architecture support: aarch64, amd64, armhf, armv7
