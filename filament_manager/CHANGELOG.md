# Changelog

## 0.23.1

- Security: email addresses are now masked in all log output (e.g. `c*****n@example.com`) — fixes CodeQL CWE-532 clear-text logging of sensitive data

## 0.23.0

- Settings → Appearance: new "Regional Settings" section — timezone, currency, and country can now be overridden independently of Home Assistant; overrides are stored in the database and take precedence over HA-derived values; leave blank to inherit from HA as before
- When all three values are overridden the app no longer calls the HA Supervisor API at all, making it fully functional without an active HA connection
- Overrides are included in the full JSON backup/restore so they survive data migrations
- Supported in all three languages (EN / DE / ES)

## 0.22.10

- Settings → Filament Catalog: added "Export CSV" button; exports all catalog entries as a semicolon-delimited CSV with UTF-8 BOM (Excel compatible); header row included; import already skips the header row automatically

## 0.22.9

- Fixed: full JSON backup crashed for any installation with a printer configured — printer config export/import referenced removed fields (`device_slug`, `ams_device_slug`, `sensor_*`) from the pre-v0.20 greghesp integration; now exports only current fields (`name`, `bambu_serial`, `bambu_source`, `ams_unit_count`, `is_active`, `auto_deduct`) and deduplicates on import by `bambu_serial`

## 0.22.8

- Settings → Export / Import: reorganised into four sub-tabs — Filament Manager (full JSON backup/restore), Spools (CSV export/import), Bambu Cloud (import print history), Experimental (Spoolman export); each tab has a short description of its functionality

## 0.22.7

- Settings → Export / Import: added "Import Spools CSV" button; accepts the CSV format produced by the export; upserts by ID (updates existing spools, creates new ones for unrecognised IDs); shows created / updated / skipped counts

## 0.22.6

- Settings → Export / Import: added "Export Spools as CSV" button; downloads all spool fields including computed remaining % and price/kg

## 0.22.5

- Spools table: added Article Number column between Color and Remaining %

## 0.22.4

- Global "actions at end" setting (Appearance tab) now applies to all tables and lists in the app: Spools table, Filament Catalog table, and all Settings→Data flex lists (Brand Weights, Brands, Materials, Subtypes, Purchase Locations, Storage Locations)
- Renamed localStorage key from `fm_spools_actions_last` to `fm_actions_last`; existing preference is reset to default (actions at start)

## 0.22.3

- Spool form: color hex field now validates for a valid `#rrggbb` format; red border + error message shown on invalid input; Save button disabled until corrected

## 0.22.2

- Fixed: AMS mismatch warning on Dashboard now triggers for any non-empty tray (remaining > 0%) — previously trays with < 5% remaining were silently ignored

## 0.22.1

- Fixed: AMS auto-match now matches materials stored with a subtype (e.g. spool `material=TPU, subtype=for AMS` now matches printer-reported `"TPU for AMS"`)

## 0.22.0

- AMS tray assignment: spool dropdown now sorted by Brand → Material → Color
- AMS tray assignment: per-tray ✦ button finds the best matching spool by material + color (amber = match available, green = already optimal, gray = none found); tooltip shows the candidate
- AMS tray assignment: "Auto-match" header button assigns the best spool to all trays in the visible AMS unit at once; tiebreakers: lowest remaining weight first, then oldest purchase date (FiFo)
- Dashboard: amber warning card shown when an AMS tray reports a filament (≥ 5% remaining) that has no matching spool in inventory

## 0.21.9

- Fixed: spool weight history popup was too narrow (`max-w-2xl` → `max-w-4xl`); print name column no longer truncated

## 0.21.8

- Fixed: spools table action icons (edit / duplicate / history / delete) were overlapping in a 2×2 grid — changed to a single flex row

## 0.21.7

- Fixed: auto-deduct checkbox was missing from the printer form — the setting was stored and sent to the backend but never shown in the UI, making it impossible to enable without manual DB edits; checkbox now appears in the printer edit/add dialog below "Monitor this printer"

## 0.21.6

- Fixed: print edit form now pre-populates filament usages from the cloud snapshot (`suggested_usages`) for unconfirmed auto prints, so the correct print-time spool is shown instead of "No usages recorded" — prevents the user from accidentally loading current AMS state via "Load from AMS" and storing the wrong spool

## 0.21.5

- Fixed: editing a print's name, notes, or time without touching usages no longer creates spurious `print_delete` + `print_manual` audit pairs — the backend now only reverts and re-applies spool weights when the user explicitly enters usage edit mode

## 0.21.4

- Settings → Appearance tab: new option to move the spools table action icons (edit / duplicate / history / delete) to the last column instead of the first; preference is stored in the browser

## 0.21.3

- UX: add spool form now auto-focuses the article number dropdown when opened
- UX: after selecting a filament from the catalog, focus jumps to the nominal weight field

## 0.21.2

- Fixed: when prints are started in quick succession directly on the printer, each new print job now gets the correct start time (current time) instead of inheriting the first print's start time from the Bambu Cloud task API. The cloud task list lags a few seconds behind the printer — the app no longer falls back to the most-recent cloud task when the expected task ID isn't found yet.

## 0.21.1

- Fixed: print confirmation modal now uses the spool that was physically in the AMS slot at print-end time — changing spools between print finish and confirmation no longer shows the wrong spool
- Fixed: yellow "confirm usage" icon no longer reappears on already-confirmed auto prints after navigating away
- Fixed: confirming 0 g usage (e.g. failed prints) no longer causes the print list to go blank until reload

## 0.21.0

- **Spool weight history** — each weight change is now recorded in an immutable audit log with action type (auto-deduct, manual print, print deleted, manual edit), before/after weights, delta, and the associated print name
- History icon added to each spool (2×2 icon grid: Edit + Duplicate on top, History + Delete on bottom) in both grid and table views
- Audit log viewable as a popup directly from the spool list
- Each audit entry has a reverse (↺) button that creates a correction entry with the opposite delta and updates the spool weight accordingly — original entry is never removed

## 0.20.2

- Filament catalog CSV import: switched to fixed positional column order (`Brand;Material;Subtype;Subtype 2;Color name;Article number;Hex-Code`) — no header row required, all lines are treated as data; BOM stripping and Excel quote handling retained

## 0.20.1

- Renamed "Experiments" tab in Settings to "Cloud Config" (EN: Cloud Config / DE: Cloud-Konfiguration / ES: Config. Cloud)

## 0.20.0

### ⚠️ Breaking Change

**The [greghesp/ha-bambulab](https://github.com/greghesp/ha-bambulab) Home Assistant integration is no longer required and no longer supported.**

Printer configurations that used the HA integration as their data source will be removed on upgrade. Reconfigure your printer via **Settings → Experiments → Bambu Lab Cloud**. All spools, print history, and other data are unaffected.

### Changes

- Removed greghesp Bambu Lab HA integration — only Bambu Lab Cloud (MQTT) is supported from now on
- Printer form always uses the cloud flow; HA source type, sensor entity config, and device slug fields are removed
- Database migration: HA-source printer configs are dropped on upgrade; cloud printers are preserved
- Settings: removed "Experimental" badge from the Bambu Lab Cloud section
- Print job naming: `designTitle` (Makerworld design name) fetched from Bambu Cloud task API at job creation — previously the MQTT `gcode_state=RUNNING` message arrived before `designTitle`, causing the slicer title to always be used instead
- Print job start time: fetched from Bambu Cloud task API so the record reflects when printing actually began, even when the app was down at print start
- Fixed: app startup crash caused by dangling APScheduler job referencing the removed `print_monitor` import — active print tracking (MQTT callbacks) was broken as a result
- Fixed: stale open print jobs (container crashed mid-print) are now closed automatically when the printer reports IDLE/FINISH/FAILED on reconnect
- Fixed: if a new RUNNING message names a different file than the stale open job, the stale job is closed and a new one created
- Fixed: filament catalog CSV import handles BOM-prefixed files (Excel UTF-8 export) and quoted header/cell values
- Fixed: AMS snapshot crash (`KeyError: 'remain'`) when a tray exists in cache without a remaining-percentage value
- Fixed: spool form `diameter_mm` type mismatch causing TypeScript build failure

## 0.14.10

- Cloud prints: print name now uses `designTitle` (Makerworld design name) first, falls back to `title` (slicer job name), then to the gcode filename — previously the gcode/slicer title was always shown instead of the design name

## 0.14.9

- Print jobs: filament usage on existing prints is now shown read-only by default; an "Edit Usages" button (pencil icon) unlocks per-row editing, preventing accidental overwrites
- Print jobs: "Load from AMS" and "Add spool" controls are hidden until edit mode is entered
- Print jobs: auto-loading AMS tray data is now limited to new prints only — existing jobs never have their stored usages overwritten on open

## 0.14.8

- Spools table: fixed summary row misalignment — label colspan corrected from 4 to 5 so aggregate values (avg %, total weight, avg price) line up with their respective columns
- Spools table filters: date column now filters against the displayed DD.MM.YYYY value instead of the raw ISO string; numeric inputs accept locale decimal comma (e.g. `0,5`) as well as dot; filter placeholders show format hints per column type (e.g. `TT.MM.JJJJ` / `DD.MM.AAAA` for date, `=, >=, < (kg, z.B. 0,5)` for weight) in the active language

## 0.14.7

- Filament Catalog table: replaced the separate filter bar with Spools-style inline column filters (per-column text inputs in a sticky filter row) and clickable column headers for ascending/descending sort; sort indicator icons match the Spools table; actions column moved to the left

## 0.14.6

- Frontend: `index.html` now served with `Cache-Control: no-cache` headers so the browser always fetches the latest version after an update; hashed `/assets/*` files remain browser-cached for fast loads

## 0.14.5

- Filament Catalog: search box filters across brand, material, subtypes, color name, and article number; brand and material dropdowns narrow the list further; entry count shown; "Clear" resets all filters at once

## 0.14.4

- Filament Catalog: CSV import button — upload a semicolon- or comma-separated file; rows are upserted by (brand, article number): existing entries are updated, new ones added; result banner shows counts of added and updated rows

## 0.14.3

- Data export: spools now include `article_number`; settings bundle now includes the full filament catalog
- Data import: `article_number` restored on spool import; filament catalog entries imported with deduplication (by article number when present, else by brand + material + color name); cloud-imported print usages with null spool_id are preserved rather than skipped

## 0.14.2

- Settings → Data → Filament Data: subtab scrollbar hidden; table now uses full browser width (max-w-2xl lifted when Filament Data is active; section renders outside the card)
- Spools add/edit: new "Article No." dropdown populated from Filament Catalog entries; selecting an article number auto-fills brand, material, subtypes, color name, and color hex from the catalog entry
- Backend: `article_number` column added to spools table (migration applied on first startup)

## 0.14.1

- Filament Data: fixed "Add does nothing" bug — inner form was a component defined inside the parent, causing React to remount it on every keystroke and swallow mutations; extracted to module-level `CatalogEditRow`
- Filament Data: redesigned layout — add form shown as a card above the table with a 4-column grid; table uses `<table>` with `overflow-x-auto` so it scrolls instead of wrapping; columns no longer squish

## 0.14.0

- Settings → Data → Filament Data: new subtab with a full filament product catalog (brand, material, subtype 1 & 2, color name, color hex, article number); brand/material/subtypes are dropdowns from the existing lists; inline add and edit; color picker for hex code

## 0.13.10

- Print form (add & edit): "Deduct from spool" checkbox (enabled by default) controls whether saving the form adjusts spool current weight — uncheck when correcting which spool was used without wanting to change inventory counts

## 0.13.9

- Print form: spool dropdowns now show remaining % next to each spool name, matching the AMS tray assignment style
- Print form: "Show empty" checkbox above the spool rows toggles visibility of 0% spools (hidden by default); currently selected spools are always shown regardless

## 0.13.8

- Live print tracking: when a Bambu Cloud printer starts a new job via MQTT, the job name now uses `designTitle` (Makerworld design name) and falls back to `subtask_name` (gcode filename) — consistent with the cloud import behaviour

## 0.13.7

- Bambu Cloud import: print name now uses `designTitle` (Makerworld design title) and falls back to `title` (gcode filename) when absent
- Bambu Cloud import: real `PrintUsage` rows are created for each AMS tray entry in `amsDetailMapping` — weight and slot are recorded, spool assignment is left blank for the user to fill in via Print History
- Backend: `PrintUsage.spool_id` is now nullable — import entries without spool assignment no longer block editing or deleting the job

## 0.13.6

- Experiments: "Tasks" download button in the cloud printer card header fetches the full Bambu Cloud task list for that printer (all pages) and saves it as `tasks_{serial}.json` — raw API response useful for diagnosing task/weight data

## 0.13.5

- Experiments: "Download JSON" button next to the Raw MQTT cache header downloads a JSON file with the full cache for that printer (`printer_status`, `ams_cache`, `mqtt_client`) — useful for diagnosing what Bambu Lab is sending over MQTT

## 0.13.4

- Spools table: action buttons (edit / duplicate / delete) moved to first column
- Export / Import: fixed several missing fields — `custom_id`, `storage_location` on spools; all Bambu enrichment fields (`task_id`, `project_id`, `nozzle_*`, `print_weight_g`, `suggested_usages`, etc.) on print jobs; `auto_deduct`, `bambu_serial/source`, all sensor overrides on printer configs; `storage_locations` in settings

## 0.13.3

- Dashboard: "Mark as done" button on the running job card lets users force-close a stuck print; a confirmation dialog warns that filament usage will not be calculated automatically and must be adjusted manually in Print History

## 0.13.2

- Dashboard: currency in the inventory table now reads the ISO 4217 currency code from HA config (`/api/config` → `currency`) and formats with `Intl.NumberFormat` — no more hardcoded €; works for any HA-configured currency (USD, GBP, CHF…)
- Backend `/api/settings/ha-locale` now also returns `currency`

## 0.13.1

- Dashboard: Inventory card redesigned as a 3×3 table (rows: Total purchased / Printed–spent / Available; columns: Spools / Weight / €) for a cleaner at-a-glance overview

## 0.13.0

- Spools: new **Storage Location** field — track physical storage (shelf, drawer, box…) per spool
- Storage locations are configurable in Settings → Data → Storage tab (full CRUD, same pattern as Purchase Locations)
- Storage location shown as a dropdown in the Add/Edit Spool form (next to Purchase Location)
- Storage location column added to the Spools table and badge shown on Spool cards
- Backend: `StorageLocation` model, `spools.storage_location` column, `/api/settings/storage-locations` CRUD endpoints; automatic DB migration on startup

## 0.12.4

- `GET /api/settings/ha-locale` now also returns `country` (ISO 3166-1, e.g. `"DE"`) from the HA core config
- `document.documentElement.lang` is set to `{language}-{COUNTRY}` (e.g. `en-DE`) so that browser datetime/number formatting follows the HA regional setting independently of the UI language — fixes 12 h AM/PM in `datetime-local` inputs for users running English UI with a 24 h country locale

## 0.12.2

- Prints date filter: preset buttons (This Month / Last Month / This Week / Last Week / Today / Yesterday) now populate the date picker with the resolved date immediately, so the picker always shows the active period
- Week picker: selecting any day of a week snaps the picker to that week's Monday; a "DD.MM. – DD.MM." range label shows the full Mon–Sun span
- Switching filter mode (Month / Week / Day) also pre-fills the picker with the current period

## 0.12.1

- Prints: edit form now shows `started_at` and `finished_at` in the HA timezone instead of raw UTC — fixes "started after finish" display for auto-monitored prints in non-UTC timezones
- `utcToLocalInput` / `localInputToUTC` helpers added to `utils/time.ts` to convert between UTC ISO strings and `datetime-local` input values in any IANA timezone; save path converts back to UTC before submitting to the backend

## 0.12.0

- Theme: app now follows Home Assistant's day/night mode — surfaces, borders, and text automatically switch between dark and light based on HA's theme or the OS `prefers-color-scheme` setting
- In HA: theme is detected from `--primary-background-color` CSS variable on the parent frame (same-origin ingress); HA's configured accent color is mirrored to the app's accent if set
- Standalone / dev: theme tracks the OS dark/light preference and updates in real time
- No flash of unstyled content — theme class is set synchronously before first paint via an inline script in `index.html`

## 0.11.1

- Prints: search and date filter now query the backend — results are complete regardless of how many pages have been loaded; search is debounced (300 ms); date boundaries are converted to UTC using the HA timezone so "today" correctly reflects the user's local time
- Backend: `GET /api/prints` and `GET /api/prints/count` accept `search`, `date_from`, `date_to` (YYYY-MM-DD), and `timezone` query params; search matches print name, printer name, and linked spool brand/material/color via a subquery
- Added `tzdata` Python package to requirements for IANA timezone support on Alpine Linux

## 0.11.0

- Prints: added date filter bar — filter by Month (this/last/custom month picker), Week (this/last/custom week, Mon–Sun), or Day (today/yesterday/custom date picker); all filtering is client-side on loaded prints; counts in the header update to reflect the active filter
- Dashboard: fixed materials pie chart labels overflowing outside the chart container for small slices; counts are now shown in the legend

## 0.10.31

- Timestamps now display in the timezone configured in Home Assistant (from HA config API)
- Backend: `GET /api/settings/ha-locale` now returns `time_zone` alongside `language`
- Frontend: all backend timestamps (naive UTC) are correctly parsed as UTC before display
- Prints page: job start times shown in HA timezone; print form "Started At" default is current time in HA timezone
- Dashboard: relative times (formatDistanceToNow) use UTC-corrected dates; timeline chart day labels use UTC noon to avoid DST/timezone off-by-one
- Spools page: purchase dates formatted directly from ISO date string (no TZ conversion needed for calendar dates)

## 0.10.30

- Settings: removed "Auto-deduct filament on print completion" checkbox from both HA and Cloud printer forms

## 0.10.29

- Dashboard: added "Prints / Day" timeline chart tab showing a bar per day from first print to today; days with no prints show as dark zero bars; month labels auto-space to avoid overlap

## 0.10.28

- Settings: "Import from Bambu Cloud" button is now always visible in the Export/Import tab; disabled (greyed out) when not connected to Bambu Cloud instead of hidden

## 0.10.27

- Dashboard: merged cost, filament and spool metric cards into one combined Inventory card
- Dashboard: spool stats now show Active spools and Empty spools (replacing low stock count and total prints)
- Dashboard: new Running Job card appears at the top when a print is active, showing live stage/progress/remaining/weight/tray; hidden when no print is running

## 0.10.26

- Data Import: added "Import from Bambu Cloud" button (visible when cloud is connected) — fetches all historical print jobs from the Bambu Cloud task API; deduplicates by task ID; stores per-tray weight data as suggested usages for manual spool assignment

## 0.10.25

- Settings: removed region dropdown from Bambu Cloud login form (all regions use the same login endpoint)

## 0.10.24

- Print History: added search box to filter jobs by name, printer, or spool material/color

## 0.10.23

- Edit Print form: removed Model File input (set automatically by print detection, not user-editable)
- Edit Print form: Printer field is now read-only when editing an existing job (shown as static text)
- Edit Print form: Finished At is read-only when the job already has a completion time (auto-filled by print detection)

## 0.10.22

- Fixed: adding a cloud printer while already connected now correctly starts MQTT — register_printer now schedules _connect_mqtt_for_cloud_printers on the async event loop (via asyncio.run_coroutine_threadsafe) instead of calling _start_mqtt_for_serial directly from the sync route handler thread, which was unreliable
- Reconnect button: polls debug endpoint until MQTT shows connected (up to 15s) instead of a fixed 3s sleep, so the UI refreshes as soon as data is actually available

## 0.10.21

- Experiments tab: live status card now shows MQTT connection state (green MQTT / red not connected) per printer
- Added "Reconnect" button that restarts all MQTT connections and waits 3s for pushall response before refreshing the UI
- api.ts: expose mqtt_clients from debug endpoint; add bambuCloudReconnect()

## 0.10.20

- HA and Cloud printers: print completion now stores suggested_usages and waits for user confirmation via the Scale button — no automatic deduction without consent
- HA printers: AMS delta (start vs end remain%) converted to suggested_usages in the same format as Cloud, including spool name and color
- HA printers: print_weight sensor attributes (per-tray breakdown) used as fallback suggestions when no AMS snapshot was available at job start
- New per-printer setting: "Auto-deduct filament on print completion" — when enabled, applies suggested_usages immediately without user interaction (equivalent to the old HA auto-deduct behaviour, now available for both HA and Cloud printers)
- Added `auto_deduct` column to printer_configs with migration

## 0.10.19

- Prints page: active (open) print jobs now show a live status bar with stage, progress, remaining time, print weight, AMS active, and active tray — polled every 10s
- HA printers: values read from HA sensor entities (respects custom overrides); Cloud printers: values read from MQTT cache
- Backend: cloud printer status endpoint now also returns print_weight (gcode_file_weight), ams_active, and active_tray alongside the existing fields

## 0.10.18

- Hide device serial numbers in UI — shown as ••••••••XXXX (last 4 digits only) in device list, edit modal, and live status card

## 0.10.17

- Fixed Bambu Cloud: MQTT client now starts immediately when a cloud printer is saved while already connected — previously adding a printer after login produced no data until the next re-login or restart

## 0.10.16

- Fixed Bambu Cloud MQTT: added region selection (Global/US, Europe, China) to the login form
- Region is stored in credentials and used to connect to the correct regional MQTT broker (us/eu/cn.mqtt.bambulab.com)
- Fixed trailing comma JSON syntax error in all three locale files that caused Docker build failure

## 0.10.15

- Removed ams_suffix_type/color/remain fields entirely — they were dead code (assigned in get_ams_config but never referenced in entity construction; no matching entities exist in the greghesp ha-bambulab integration)
- Removed from model, migration list, router schemas, frontend state, save payload, UI, and all locale files

## 0.10.14

- HA printer config: added `binary_sensor.{slug}_ams_1_active` (AMS active tray indicator) as a new configurable sensor with entity ID override support
- HA printer config: sensor overrides for print_progress, remaining_time, nozzle_temp, bed_temp are now correctly exposed (they were always used in the status endpoint but missing from the override form)
- Sensor override placeholder now shows the correct domain (binary_sensor vs sensor) per field

## 0.10.13

- Cloud printer config: removed HA-only fields (device_slug, ams_unit_count, sensor overrides, ams_tray_pattern/suffix) — backend strips them on create/update; frontend no longer sends them
- Printer card: hide "N AMS" label for cloud printers (count is derived from MQTT data, not config)

## 0.10.12

- AMS slot count is now derived from actual data instead of being hardcoded to 4 per unit
- Cloud printers: AMS slots are enumerated from the MQTT cache keys exactly as Bambu reports them — AMS HT (1 slot) and any future AMS variants are handled automatically
- HA printers: tray count per unit is discovered by checking which `sensor.{slug}_ams_{u}_tray_{t}` entities actually exist in HA — AMS HT units will show only 1 slot
- Fixed `tray_now` global index → slot key conversion to use per-unit tray counts from MQTT data, so the active tray is correctly identified in mixed AMS setups (e.g. standard AMS + AMS HT)

## 0.10.11

- Spools: new "#" field — user-assigned reference number (1–9999, integers only, optional); first column in the table; sortable and filterable (numeric operators =, >=, <=, >, <); shown in add/edit spool form

## 0.10.10

- AMS tray assignment: selecting a spool that is already assigned to another tray/printer now automatically removes it from the previous slot and shows a warning ("Spool was already assigned to Printer / AMS 1 Tray 2 — it has been moved here")
- AMS tray assignment: all printer AMS views are refreshed after assignment so the cleared slot is reflected immediately across printers
- Fix: cloud printer AMS material name was reverting to base type ("PETG") after any incremental MQTT update — incremental updates only carry `remain`, not `tray_sub_brands`, so the cache was being overwritten with empty material; now merges updates instead of replacing the whole cache
- Cloud printer AMS trays: remaining % is no longer shown for non-Bambu spools / untracked slots (was "-1.0%", now "—")
- AMS tray remaining % consistently displayed as rounded integer for both cloud and HA printers

## 0.10.9

- Fix: AMS tray assignment dropdown hides spools that display as 0% remaining — catches both truly empty spools (current_weight_g = 0) and spools with sub-gram residue (e.g. 0.0003g) that round to 0%

## 0.10.8

- Fix: AMS tray assignment dropdown no longer shows empty spools (current_weight_g = 0)

## 0.10.7

- HA printer sensor entity IDs are now auto-discovered via the HA entity registry (`GET /api/config/entity_registry_entries/sensor`) — works correctly regardless of HA language or device name
- Discovery matches by `unique_id` suffix (ha-bambulab always sets `unique_id = "{serial}_{key}"`) so German `sensor.bambooo_aktueller_arbeitsschritt` is found just as reliably as English `sensor.bambooo_current_stage`
- Registry results are cached per serial for the process lifetime; cache is invalidated on printer create/update so config changes take effect immediately
- Manual sensor overrides in printer settings still take highest priority; English defaults remain as last-resort fallback for installations without a bambu_serial set

## 0.10.6

- HA-source printers: `sensor.{slug}_print_weight` attributes now read per-tray grams at print end; `suggested_usages` pre-filled in LogUsageModal same as cloud printers
- HA-source printers: works for both LAN/FTP mode (3mf parsed by ha-bambulab) and cloud-authenticated HA mode; ha-bambulab exposes per-AMS-tray grams as sensor attributes (`AMS 1 Tray 2: 17.32`, etc.)
- HA-source printers: delta-based AMS usage recording is still used for auto-commit (as before); `suggested_usages` is an additional hint for manual confirmation

## 0.10.5

- Cloud prints: filament usage is no longer auto-recorded via AMS delta; user must confirm via the yellow usage icon (LogUsageModal) — eliminates ghost 0g usage records from sensor noise
- Cloud prints: after print end, Bambu Cloud task API `amsDetailMapping` is fetched to get per-tray grams used; values are stored as `suggested_usages` on the print job
- Cloud prints: LogUsageModal pre-fills gram inputs from cloud-sourced `suggested_usages` when available; a blue banner indicates the values are cloud suggestions to verify before saving
- Cloud prints: if `amsDetailMapping` is unavailable but total weight is known and only one tray was active, a single-tray suggestion is generated automatically
- Backend: `tray_now` MQTT field is now continuously tracked per serial during a print to support single-tray weight attribution

## 0.10.4

- AMS tray assignment: per-tray sync icon now only appears when the AMS reports a valid remaining % (≥ 0); non-Bambu Lab spools (reported as -1%) no longer show the icon
- AMS tray assignment: add "Sync All" button that syncs remaining weight for all Bambu Lab spools at once; backend skips trays where AMS reports negative remaining (non-Bambu spools), preventing accidental weight corruption

## 0.10.3

- Experiments tab: raw MQTT cache now shows ALL fields the printer sends (previously only ~15 pre-selected fields were stored); any new field appearing in any future firmware update is automatically captured
- Experiments tab: raw cache section now shows both printer status fields and AMS tray fields (remain, material, color, remain_flag per slot) in separate labelled blocks, sorted alphabetically
- Backend: `get_debug_info` now returns the full `ams_cache` detail (not just slot key names)

## 0.10.2

- Fix: yellow "add filament usage" icon not showing on finished auto prints — condition was `usages.length === 0` but AMS percent drift can create 0g ghost usage records; changed to `total_grams === 0`
- Fix: PAUSE state was incorrectly closing open print jobs — reverted end-detection to only trigger on FINISH, FAILED, IDLE
- Fix: poll_printers now queries only HA-source printers and returns early if none configured, eliminating noisy APScheduler log entries when all printers use cloud mode

## 0.10.1

- Fix: cloud print end not detected — `_process_device_message` was firing `on_cloud_print_end` on every incremental MQTT update (temperature, progress) because it used the *cached* `gcode_state` instead of the value in the current message; rapid duplicate coroutines hit SQLite write conflicts and prevented `db.commit()`
- Fix: `_on_print_end` now commits the job close *before* the HTTP weight fetch — a slow or failed Bambu Cloud task API call can no longer block or prevent the job record from being saved
- Fix: `on_cloud_print_end` now catches exceptions from `_on_print_end` and always resets `_state` to idle so a failed close attempt never permanently blocks future end events
- Improvement: end detection now triggers on any non-printing MQTT state (not just FINISH/FAILED/IDLE) — covers firmware variations and any unknown terminal states

## 0.10.0

- Add `print_weight_g` field to print jobs: automatically captured at print end from the Bambu Cloud task API (cloud-source printers) or from the `sensor.{slug}_print_weight` HA entity (HA-source printers)
- Add "Print Weight (g)" custom sensor entity ID override to HA printer settings form (for non-standard HA installations)

## 0.9.33

- Remove mc_print_filament_used and mc_lifetime_filament_usage from MQTT tracking — these fields are not sent by the O1S; no filament weight equivalent exists in the MQTT payload for this printer
- Fix tray_now capture: the field lives inside the AMS dict in the MQTT message, not in the print dict — now correctly captured from the AMS section
- Clean up filament_used / lifetime_filament from status endpoint and frontend labels

## 0.9.32

- Experiments tab: add collapsible "Raw MQTT cache" section per printer showing every field/value the printer has sent via MQTT — needed to identify actual field names for filament/tray data

## 0.9.31

- Fix: new Experiments fields (active tray, filament used, lifetime filament) were wired to the wrong endpoint (`/api/printers/{id}/status`) instead of the one the Experiments tab actually calls (`/api/bambu-cloud/printer/{serial}/status`)

## 0.9.30

- Experiments tab: cloud printer live status now shows active AMS tray (`tray_now` → T1–T4), filament used in current/last print (`mc_print_filament_used`), and lifetime filament total (`mc_lifetime_filament_usage`); all three fields are now captured in the MQTT status cache

## 0.9.29

- Remove Hours / Printer tab from dashboard chart section

## 0.9.28

- Fix Hours/Printer chart missing bars: every active printer now always appears in the chart; previously a printer was omitted entirely if its HA entity / MQTT cache returned no data and it had no recorded jobs — it now shows 0 h in that case

## 0.9.27

- Dashboard Hours/Printer chart: cloud-source printers now read `mc_print_tick_cnt` from the MQTT status cache (lifetime print seconds, same source as the HA integration's `total_usage` entity) and convert to hours; falls back to job aggregation if the value is not yet in the cache

## 0.9.26

- Dashboard Hours/Printer chart: HA-source printers now read total hours from `sensor.{device_slug}_total_usage` (the Bambu Lab HA integration's lifetime usage counter) instead of aggregating from tracked print jobs; cloud-source printers and any printer whose HA entity is unavailable still fall back to the job-based aggregation

## 0.9.25

- Fix cloud AMS tray material name: MQTT payloads contain `tray_sub_brands` ("Bambu PLA Silk+") in addition to `tray_type` ("PLA"); now prefer `tray_sub_brands` over `tray_type`, matching the detail level shown by the HA integration
- Fix cloud AMS empty tray display: slots with no filament loaded had an absent/unparseable `remain` field which caused the slot to be skipped entirely; empty trays are now included in the cache with `remain=null` and material label "Empty", matching the HA integration

## 0.9.24

- AMS slot display: spool list now shows the printer name as a prefix on the AMS slot (e.g. `MyPrinter:ams1_tray2`) so slots are unambiguous when multiple printers are configured
- Assignment endpoint now stores `{printer_name}:{slot_key}` instead of the bare slot key; all read paths (AMS panel, sync, print consumption tracking) use the prefixed key with a fallback to the bare key for spools assigned before this version

## 0.9.23

- Fix duplicate print jobs created for cloud printers after app restart: when MQTT reconnects it sends a `pushall` command and the printer responds with its full current state including `gcode_state=RUNNING`; because `_state` (the in-memory tracking dict) is empty after a restart, the duplicate-job guard in `on_cloud_print_start` did not fire and a new PrintJob was created; fix mirrors the DB-recovery logic already used by HA-source printers — on the first MQTT event after restart, if an open PrintJob already exists in the DB it is recovered into `_state` and no new job is created

## 0.9.22

- Fix Cost and Filament chart tooltips: "Available" bar label was showing as literal key `common.available` (key did not exist in `dashboard.chart`); added `dashboard.chart.available` to all three locales
- Fix Cost and Filament chart tooltip formatting: value was shown as `: €74.45` (colon with no name before it) because Recharts renders the separator even when the item name is empty; added `separator=""` to suppress the colon

## 0.9.21

- Dashboard: add "Hours / Printer" tab to the chart section — bar chart showing total print hours per printer (aggregated from print jobs that have both a printer name and a duration); uses the same dark tooltip style as the other chart tabs

## 0.9.20

- Fix chart tooltip readability: label and item text now render in light grey/white instead of recharts default black, matching the dark tooltip background on all four dashboard charts (Materials, Cost, Filament, Avg Price/Location)

## 0.9.19

- Cloud printer form: device picker is now a dropdown (select) instead of a button list; already-configured cloud printer serials are excluded from the dropdown so the same printer cannot be added twice
- File name (current_file) in printer status grids now truncates with ellipsis and shows the full name as a tooltip, spanning the full width of the status row
- Printer sub-tabs in the Printers tab: added correct vertical padding so the tab bar no longer causes a scrollbar

## 0.9.18

- Redesign printer configuration: Add Printer modal now has two tabs — "Home Assistant" (existing HA config form) and "Bambu Lab Cloud" (pick device from cloud, shows live status + AMS preview with tabs per unit)
- Source type is locked at creation — editing a printer shows only its own config form (no switching allowed)
- Printer card: remove HA/Cloud toggle buttons, show a small "HA" or "Cloud" badge next to the printer name; status values shown for both HA and cloud printers
- Experiments tab AMS display: slot keys shown in full (`ams1_tray1` etc.) without truncation; AMS units shown in tabs when printer has multiple units
- Fix: AMS tray panel and sync endpoints now require `bambu_source=cloud` (not just `bambu_serial` being set) before reading from MQTT cache — prevents cloud MQTT data from overriding HA entity values for HA-source printers

## 0.9.17

- Fix: AMS tray assignment panel was showing cloud MQTT data for HA-source printers — the `bambu_serial` field is now set just to enable Experiments tab live view, so all three AMS endpoints (get trays, sync all, sync single) now require `bambu_source=cloud` before reading from the MQTT cache; HA-source printers always read from HA entities

## 0.9.16

- PrintJob now stores Bambu Cloud MQTT enrichment fields: `task_id`, `project_id`, `total_layer_num`, `layer_num` (final layer at end), `nozzle_diameter`, `nozzle_type`, `print_type` (cloud/local/sdcard), `error_code` — populated automatically for cloud-source printers; null for HA/manual jobs
- AMS tray MQTT cache now includes `remain_flag` (0/null = reliable reading, 1 = rough estimate); exposed in `GET /api/bambu-cloud/printer/{serial}/ams`
- Fix: Bambu Cloud MQTT callbacks (`on_cloud_print_start`, `on_cloud_print_end`) now skip printers with `bambu_source=ha` — MQTT is connected for the Experiments tab but must not interfere with HA-based print tracking or overwrite HA AMS snapshots

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
