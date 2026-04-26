# Filament Manager

A Home Assistant add-on for tracking 3D printer filament inventory, monitoring print history, and calculating material costs. Integrates natively with Bambu Lab printers via **Bambu Lab Cloud (MQTT)**.

![Version](https://img.shields.io/badge/version-0.33.0-blue) ![Platform](https://img.shields.io/badge/platform-Home%20Assistant-teal)

---

## ⚠️ Breaking Change — v0.20.0

**The [greghesp/ha-bambulab](https://github.com/greghesp/ha-bambulab) Home Assistant integration is no longer required and is no longer supported.**

If you were using the HA integration as the data source for your printer, your printer configuration will be removed on upgrade. You must reconfigure your printer using **Bambu Lab Cloud** (Settings → Cloud Config → Bambu Lab Cloud → connect with your Bambu account, then add your printer under Settings → Printers).

Spools, print history, and all other data are unaffected.

---

## Features

- **Automatic print detection** — monitors your Bambu Lab printer via Bambu Cloud MQTT; creates print records automatically when a print starts
- **AMS filament tracking** — snapshots filament levels at print start/end; calculates grams used per spool per tray
- **Suggested filament usage** — on print completion the app pre-fills grams used per tray for review; spool identity is snapshotted at print start so suggestions always reference the correct spool even if the AMS is changed afterwards; an optional per-printer *auto-deduct* flag applies the deduction immediately without confirmation
- **Multi-spool print support** — manual spool swaps (runout pause + replace) and AMS auto-switches (backup tray same material) are both detected; the Log Usage modal shows two rows for the affected slot with the split pre-calculated from print-start stock; all estimates are editable
- **Live print status** — active print jobs show real-time stage, progress, remaining time, and active tray from Bambu Cloud MQTT
- **Spool inventory** — full CRUD for filament spools with brand, material, subtype, color, article number, weight, cost, purchase location, and storage location
- **Filament catalog** — manage a master list of filament products (brand, material, subtype, color, article number, hex); CSV import and export (semicolon or comma delimited, Excel UTF-8 BOM supported); selecting a catalog entry auto-fills the spool form; an optional checkbox propagates catalog changes to all spools sharing the same article number
- **Home Assistant sensor entities** — three sensors pushed automatically via the HA States API: pending filament usage confirmations, low-stock spool count, and unmatched AMS trays; sensors update on print completion, spool change, and every 5 minutes; no HA configuration required
- **Print description & model URL** — descriptions show below the print name in history; each print can have a URL (MakerWorld, Printables, etc.) shown as a clickable link icon
- **Energy tracking** — configure a cumulative kWh HA sensor (e.g. Shelly plug) and an optional electricity price sensor per printer; energy consumed (kWh) and cost (€) are recorded per print and aggregated on projects; standby energy (idle between prints) is tracked separately per printer with a reset button in Settings
- **Print Projects** — group print jobs into named projects; each project aggregates print count, total time, total filament, total cost, energy (kWh), energy cost, materials used, and nozzle diameters; per-print cost breakdown (material, energy, total) shown in the expanded project view; prints can be individually marked as test prints with the flask icon; assign prints from the project page or from the print form; full export/import support
- **AMS spool auto-match** — per-tray sparkle button and "Auto-match" header button find the best inventory spool by material + color; tiebreakers: lowest remaining weight first, then oldest purchase date (FiFo); Dashboard warns when a loaded AMS tray has no matching spool in inventory
- **Cost analytics** — per-print cost, price per kg, inventory value, and spend by purchase location
- **Dashboard** — overview charts, low-stock alerts, and recent print history
- **Print history search & date filter** — filter by name, printer, material, color; quick presets (this/last week/month)
- **EN / DE / ES interface** — full translations; inherits language from your HA instance by default
- **HA day/night theme** — follows Home Assistant light/dark mode and accent color
- **Data export / import** — organised into four tabs: full JSON backup/restore (Filament Manager), spool CSV export/import (Spools), Bambu Cloud print history import, and experimental Spoolman export and import
- **Spool CSV export / import** — export all spool data as a semicolon-delimited CSV; re-import to update or restore spools; upserts by ID
- **Spool weight history** — every weight change is logged with action type, before/after values, and linked print name; viewable per spool via the history icon
- **Spool archive** — retire empty or inactive spools with the archive action; archived spools are hidden from inventory, excluded from AMS auto-match, and do not trigger low-stock alerts; toggle "Show archived" in the toolbar to view or restore them
- **Configurable spool table columns** — show or hide individual columns in the spool table via the column picker; selection is saved locally and persists across sessions
- **Regional overrides** — timezone, currency, and country can be set manually in Settings → Appearance; overrides take precedence over Home Assistant; app works fully without HA when all three are set

---

## Screenshots

![Dashboard](filament_manager/docs/dashboard.png)

![Spools](filament_manager/docs/spools1.png)

![Spool Tiles](filament_manager/docs/spools2.png)

![Print History](filament_manager/docs/prints.png)

![Settings](filament_manager/docs/settings1.png)
![Settings](filament_manager/docs/settings2.png)
![Settings](filament_manager/docs/settings3.png)
![Settings](filament_manager/docs/settings4.png)
![Settings](filament_manager/docs/settings5.png)

---

## Requirements

- Home Assistant with Supervisor (HassOS / Home Assistant OS)
- A Bambu Lab account (email + password) for cloud connection

---

## Installation

Go to **Settings → Add-ons → Add-on Store** → click the three-dot menu → **Repositories** → paste `https://github.com/cgradl/filament-manager` → **Add**.

Once the add-on appears, click it and press **Install**.

---

## Configuration

1. Open the add-on and go to **Settings → Cloud Config**
2. Under **Bambu Lab Cloud**, enter your Bambu account email and password and click **Connect** (2FA if required)
3. Go to **Settings → Printers → Add Printer**, select your device from the dropdown, and save
4. Add your filament spools under **Spools**

---

## How It Works

### Automatic Print Tracking

Bambu Lab printers push state changes via MQTT. When `gcode_state` transitions to `RUNNING`, a new `PrintJob` is created. On `FINISH` / `FAILED` / `IDLE`, the job is closed and filament usage is fetched from the Bambu Cloud task API.

```
idle → RUNNING     Creates PrintJob, fetches real start time + designTitle from cloud
RUNNING → FINISH   Closes job, fetches weight + per-tray breakdown from cloud task API
RUNNING → FAILED   Closes job with failed flag
```

### Filament Consumption

Per-tray breakdown comes from the Bambu Cloud task API (`amsDetailMapping`). The spool's `current_weight_g` is updated automatically when auto-deduct is enabled.

### Cost Tracking

- `price_per_kg` = purchase price ÷ net weight
- Per-print cost = Σ (grams_used × cost_per_gram) across all spools used

---

## Data & Persistence

- Database: SQLite at `/data/filament.db` (survives updates)
- Schema migrations run automatically on startup

---

## License

MIT License. Not affiliated with Bambu Lab or Home Assistant.

---

## Makerworld

Check out my 3D models at https://makerworld.com/en/@carasak/
