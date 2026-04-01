# Changelog

## 0.9.15

- Fix MQTT rc=5: Bambu tokens returned after 2FA are opaque (not standard JWTs), so uid could not be extracted from the token payload — MQTT username fell back to the email address which Bambu Cloud rejects
- After every successful login (begin_login, verify_2fa) and silent re-auth, uid is now fetched from `GET /v1/user-service/my/profile` and saved alongside the credentials
- `_mqtt_username()` reads the saved uid from credentials first; falls back to JWT decode only when no saved uid is present
- `_is_token_valid()` now treats non-decodable tokens as valid (opaque post-2FA tokens are valid — let the broker reject with rc=5 if actually expired rather than triggering re-auth on every restart)

## 0.9.14

- Add diagnostic logging to MQTT startup: logs the computed MQTT username, extracted uid, and JWT payload field names so rc=5 auth failures can be diagnosed

## 0.9.13

- Fix authentication loop: when automatic token re-auth requires 2FA (Bambu has no silent refresh), stop spamming the user's inbox — instead set status to error with a clear message directing the user to log in manually from the Experiments tab; 2FA is only triggered when the user explicitly initiates login

## 0.9.12

- Fix: Experiments tab showed empty data — MQTT was only started for printers with `bambu_source=cloud`, but the source toggle was disabled; now MQTT starts for any active printer with a `bambu_serial` set, regardless of source setting
- Fix: `register_printer` (called on printer save) now registers the serial whenever a serial is present, not only when source is cloud

## 0.9.11

- Fix: Experiments tab printer/AMS values now always read from Bambu Cloud MQTT cache (by serial), not from HA entities — previous version used the same status endpoint as the Printers tab which branched on bambu_source and returned HA data when source was not set to cloud
- Add `GET /api/bambu-cloud/printer/{serial}/status` and `GET /api/bambu-cloud/printer/{serial}/ams` endpoints that read directly from the MQTT cache regardless of printer config

## 0.9.10

- Fix: Printers tab — cloud source button restored as disabled (greyed out, not removed); shows a checkmark when cloud is currently active; tooltip directs to Experiments tab to configure
- Fix: Experiments tab — cloud live data now shows for all printers that have a Bambu serial assigned (not only those already set to cloud source); uses dedicated query keys so it does not conflict with the HA polling queries

## 0.9.9

- Data tab: "Add" form moved to the top of each list (above existing entries) with Enter key support
- Data tab sub-tabs: added top padding so tab headers are not clipped
- Printers tab: AMS Tray Assignment is always visible — no expand/collapse toggle; multiple AMS units shown as tabs within the tray panel
- Printers tab: when more than one printer is configured, printers shown as sub-tabs (one printer visible at a time)
- Printers tab: cloud source selector removed (configure cloud in Experiments tab)
- Experiments tab: shows live printer sensor values and AMS tray data (material, color, remaining %) per cloud-source printer, auto-refreshed every 10 s

## 0.9.8

- Redesign Settings page into four top-level tabs: **Printers**, **Data**, **Export / Import**, **Experiments**
- Printers tab: HA connection status + Add Printer button + printer card list (cloud source selector still inline on each card)
- Data tab: five sub-tabs — Spool Weights, Brands, Materials, Subtypes, Locations
- Export / Import tab: existing data transfer section
- Experiments tab: Bambu Lab Cloud integration (moved from Printers tab); green dot on tab when cloud is connected
- EN / DE / ES translations for all new tab labels

## 0.9.7

- Fix Bambu Cloud authentication loop (three root causes):
  1. `_is_token_valid` returned `False` when the JWT has no `exp` claim — Bambu tokens sometimes omit it, so every container restart triggered `_reauthenticate()` → 2FA prompt; now assumes valid when `exp` is absent
  2. `_connect_mqtt_for_cloud_printers` did not await the executor tasks — new MQTT clients were not yet registered when the function returned, creating a race window
  3. `_reauth_in_progress` was cleared before new clients were registered in both `_reauthenticate` and `verify_2fa` — a stale rc=5 callback could restart the loop in that window; flag is now cleared after `_connect_mqtt_for_cloud_printers` completes

## 0.9.6

- Fix Bambu Cloud status panel showing no values: MQTT partial updates (e.g. AMS-only messages) were overwriting the full status cache with null values — status fields are now merged, preserving previously received data (stage, temps, progress) across incremental updates
- Status panel now shows all non-empty fields including print stage; shows "no data" message instead of empty panel when cache has nothing yet

## 0.9.5

- Fix Bambu Cloud token persistence: on container restart, check JWT `exp` claim before connecting — if still valid, use saved token directly without any re-auth; only trigger re-auth when the token is actually expired
- Removes the rc=5 → 2FA loop caused by attempting MQTT with a stale token on every restart
- `reconnect` endpoint now also checks token validity before attempting MQTT

## 0.9.4

- Fix TypeScript build error: `selectedPrinter` used before declaration in auto-load AMS `useEffect` — moved declaration above the effect and use `printerId` as dependency
- Restore suffix override fields (`_type`, `_color`, `_remain`) in the AMS entity overrides section

## 0.9.3

- Fix AMS default entity pattern: the greghesp Bambu Lab integration exposes each AMS unit as a separate HA device `{slug}_ams_{u}` (e.g. `my_printer_ams_1`) with tray entities `sensor.my_printer_ams_1_tray_1` in attribute mode — this is now the default, no AMS device slug config needed
- Remove the separate `_type`/`_color`/`_remain` suffix override fields (only applied to the old combined-entity pattern which the integration no longer uses)
- Discover endpoint now also searches for `{slug}_ams_1` entities in the fuzzy match list
- AMS tray pattern hint and entity override hint updated in all three locales

## 0.9.2

- Print form now auto-loads AMS spool assignments on open when a printer is matched and no usages are set yet — no need to click "Load from AMS" manually on first edit
- Switch "current file" sensor from `{slug}_gcode_file` to `{slug}_task_name` to match the Bambu Lab HA integration entity that shows the print task name

## 0.9.1

- Fix TypeScript build errors: `bambuCloudCancel2fa` now uses `request<void>` (consistent with other API methods); `PrinterStatus` interface gains an index signature so it can be used as `Record<string, string | null>` in printer card rendering

## 0.9.0

- Redesign Settings → Printers into a unified tabbed card: "Home Assistant" tab (HA connection status + Add Printer) and "Bambu Lab Cloud" tab (login, 2FA, device list), with the configured printer list always visible below both tabs
- Data source selection (HA vs Cloud) moves from a separate Cloud section into each printer card — source toggle and serial selector appear inline when cloud is connected
- Printer card shows a source badge (HA / Cloud), and the test/refresh button for live MQTT status is inline in the card when cloud source is selected
- Source selection is atomic: switching to Cloud sets both printer monitoring and AMS to MQTT; switching to HA uses only HA entities — no mixing
- HA and Cloud config no longer shown in separate top-level cards; layout is simplified to one Printers card

## 0.8.11

- Fix 2FA cancel breaking HA config: cancel now calls a dedicated `POST /api/bambu-cloud/cancel-2fa` endpoint that only clears the pending state and resets to disconnected — does not delete credentials or touch HA printer configs
- Move AMS Device Name field from the main printer form into the collapsible AMS Entity Overrides section, so device name and tray pattern are configured together in one place

## 0.8.10

- Fix 2FA cancel button doing nothing: it now calls logout on the backend to clear the pending_2fa state, so the login form is restored instead of the useEffect immediately flipping back to the code-entry form

## 0.8.9

- Fix spurious re-auth after successful login: when a new MQTT client is created (e.g. after login), the replaced old client's in-flight `on_connect` callback could fire with rc=5 and trigger another re-authentication cycle — now ignored by checking `_mqtt_clients[serial] is c`
- Same stale-client guard applied to `on_disconnect` to suppress noise from replaced clients

## 0.8.8

- Fix repeated 2FA prompt loop: `_reauth_in_progress` is now left `True` while waiting for 2FA code entry, so further rc=5 MQTT callbacks don't re-trigger re-auth
- `_reauth_in_progress` is reset to `False` only on successful token refresh, hard error, or when the user completes 2FA verification or logs out
- paho `disconnect()` is called before `loop_stop()` on rc=5 to reliably suppress the auto-reconnect

## 0.8.7

- Fix infinite reconnect loop when Bambu Cloud session expires: on rc=5 (Not Authorised) the paho client loop is stopped immediately and re-auth is attempted exactly once
- When re-auth requires 2FA, the backend automatically sends the verification email and transitions the UI to the code-entry form — no manual logout/login required
- Show backend error message (e.g. "Session expired") in the UI when cloud status is error
- Cloud status polled every 5 s (was 30 s) so the UI reacts promptly to reconnection events

## 0.8.6

- Fix Bambu Cloud MQTT authentication failure after token expiry (rc=5): on connect rejection, automatically re-logs in using the saved encrypted password and restarts all MQTT connections without requiring manual re-login
- If re-login itself requires 2FA the status is set to error with a clear message prompting manual re-login

## 0.8.5

- Add `GET /api/bambu-cloud/debug` endpoint: shows MQTT client connection state, token validity/expiry, printer status cache, and AMS cache keys — useful for diagnosing MQTT issues
- Add `POST /api/bambu-cloud/reconnect` endpoint: force-restarts all MQTT connections from saved credentials without restarting the container
- Improve MQTT callback logging: `on_connect`, `on_message`, `on_disconnect` now log at INFO/DEBUG level with rc codes; paho internal log forwarded at DEBUG level

## 0.8.4

- Fix Bambu Cloud MQTT silently failing on paho-mqtt 2.x: `mqtt.Client()` in paho-mqtt 2.0+ requires a `callback_api_version` argument, otherwise raises `ValueError` which was swallowed by the exception handler — MQTT never connected, leaving all live-status and AMS tray data empty
- MQTT client creation now uses `CallbackAPIVersion.VERSION1` on paho-mqtt 2.x with fallback to the 1.x API

## 0.8.3

- Fix Bambu Cloud integration actually using MQTT data: cloud-source printers now read AMS tray state from the live MQTT cache instead of HA entities across all three paths (print-end consumption tracking, AMS tray display, spool weight sync)
- AMS cache now stores full tray detail (remain %, material, color) from MQTT messages for display in the AMS assignment panel
- `get_ams_detail_for_serial` added to `bambu_cloud_client` for rich tray display

## 0.8.2

- Add per-printer custom AMS entity pattern/suffix overrides — users with non-English HA installations can now override the AMS tray entity pattern (default `ams_{u}_tray_{t}`) and the three attribute suffixes (`_type`, `_color`, `_remain`)
- When an AMS device slug is set, only the tray pattern is configurable (`tray_{t}` default); the three suffixes are hidden as they don't apply in attribute mode
- Configured under Settings → Printer → Custom Sensor Entity IDs → AMS Sensors (same collapsible)
- EN / DE / ES translations for new fields

## 0.8.1

- Bambu Cloud: add "Test" button per cloud-source printer in Settings → Bambu Lab Cloud
- Clicking Test fetches live MQTT values (stage, progress, remaining time, nozzle/bed temp, current file) and shows them in a status panel — mirrors the HA entity discovery result
- EN / DE / ES translations for new UI

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
