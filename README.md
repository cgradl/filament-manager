# Filament Manager

A Home Assistant add-on for tracking 3D printer filament inventory, monitoring print history, and calculating material costs. Integrates natively with Bambu Lab printers via **Bambu Lab Cloud (MQTT)**.

![Version](https://img.shields.io/badge/version-0.22.3-blue) ![Platform](https://img.shields.io/badge/platform-Home%20Assistant-teal)

---

## ⚠️ Breaking Change — v0.20.0

**The [greghesp/ha-bambulab](https://github.com/greghesp/ha-bambulab) Home Assistant integration is no longer required and is no longer supported.**

If you were using the HA integration as the data source for your printer, your printer configuration will be removed on upgrade. You must reconfigure your printer using **Bambu Lab Cloud** (Settings → Experiments → Bambu Lab Cloud → connect with your Bambu account, then add your printer).

Spools, print history, and all other data are unaffected.

---

## Features

- **Automatic print detection** — monitors your Bambu Lab printer via Bambu Cloud MQTT; creates print records automatically when a print starts
- **Accurate print naming** — uses the Makerworld design title (`designTitle`) when available, falls back to the slicer job title; real print start time fetched from the Bambu Cloud task API
- **AMS filament tracking** — snapshots filament levels at print start/end; calculates grams used per spool per tray
- **Suggested filament usage** — on print completion the app pre-fills grams used per tray for review; an optional per-printer *auto-deduct* flag applies the deduction immediately without confirmation
- **Live print status** — active print jobs show real-time stage, progress, remaining time, and active tray from Bambu Cloud MQTT
- **Spool inventory** — full CRUD for filament spools with brand, material, color, weight, cost, and storage location data
- **Filament catalog** — manage a master list of filament products; bulk import via CSV (semicolon or comma, Excel UTF-8 with BOM supported)
- **Cost analytics** — per-print cost, price per kg, inventory value, and spend by purchase location
- **Dashboard** — overview charts, low-stock alerts, and recent print history
- **Print history search & date filter** — filter by name, printer, material, color; quick presets (this/last week/month)
- **EN / DE / ES interface** — full translations; inherits language from your HA instance by default
- **HA day/night theme** — follows Home Assistant light/dark mode and accent color
- **Data export / import** — backup and restore all spools, prints, and settings as a JSON bundle; import historical print jobs directly from Bambu Lab Cloud
- **Spool weight history** — every weight change is logged with action type, before/after values, and linked print name; viewable per spool via the history icon
- **Spoolman export** *(experimental)* — export spool inventory in [Spoolman](https://github.com/Donkie/Spoolman)-compatible format
- **AMS spool auto-match** — per-tray sparkle button and "Auto-match" header button find the best inventory spool by material + color; tiebreakers: lowest remaining weight first, then oldest purchase date (FiFo); Dashboard warns when a loaded AMS filament has no matching spool in inventory

---

## Screenshots

![Dashboard](filament_manager/docs/Dashboard.png)

![Spools](filament_manager/docs/spools.png)

![Spool Tiles](filament_manager/docs/spoolstiles.png)

![Print History](filament_manager/docs/prints.png)

![Settings](filament_manager/docs/settings.png)

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
