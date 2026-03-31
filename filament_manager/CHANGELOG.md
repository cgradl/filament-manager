# Changelog

## 0.8.0

- Add per-printer custom sensor entity ID overrides — users with non-English HA installations (or renamed entities) can now specify the exact entity ID for each of the 6 printer sensors (print stage, progress, remaining time, nozzle/bed temp, current file)
- Overrides are configured under Settings → Printer → Custom Sensor Entity IDs (collapsible)
- EN / DE / ES translations for all new UI
- When blank, the auto-computed default (`sensor.{slug}_current_stage` etc.) is used as before

## 0.7.1

- Fix Docker build on Alpine aarch64: replace `bambu-lab-cloud-api` (which transitively required `opencv-python` from source) with direct `paho-mqtt` + `requests` calls
- Rewrite Bambu Cloud auth and MQTT client using Bambu REST API and raw paho-mqtt — no external wrappers needed

## 0.7.0

- Add Bambu Lab Cloud integration (experimental) — direct MQTT connection to `us.mqtt.bambulab.com:8883`
- Email + 2FA login flow in Settings; credentials stored Fernet-encrypted at `/data/.bambu_cloud.json` (0600)
- Per-printer data source selector: Home Assistant or Bambu Cloud — both coexist
- Cloud printers skip HA polling; MQTT events drive the same print tracking state machine
- Printer status endpoint serves real-time MQTT data for cloud-source printers
- Auto-reconnects MQTT on container restart if credentials are saved
- EN / DE / ES translations for all new UI

## 0.6.2

- Fix Spoolman export: embed full filament object (with full vendor) in each spool, matching Spoolman's native GET response shape so import tools can read brand, material and color correctly
- Add `initial_weight`, `first_used`, `last_used`, `lot_nr`, and `extra` fields to match Spoolman schema
- Mark Spoolman export button as Experimental

## 0.6.1

- Fix Spoolman export: filament price is now price/kg (not raw purchase price), avoiding incorrect values for partial spools
- Fix Spoolman export: floating point rounding on remaining_weight / used_weight
- Fix Spoolman export: purchase_location moved to spool comment instead of location field (Spoolman's location = physical storage slot)

## 0.6.0

- Add Spoolman-compatible export (Settings → Export for Spoolman)
- Generates a JSON file with deduplicated filament types and spool inventory matching the Spoolman API schema
- Available in EN / DE / ES

## 0.5.7

- Fix device name slugification to handle special characters (dots, parentheses, exclamation marks, etc.) so printer entity lookups work for any HA device name, not just simple ones
- Same fix applied in backend `ha_client.slugify()` to stay in sync with frontend logic

## 0.5.6

- Fix TypeScript build error: missing Locale type import in Dashboard.tsx

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
