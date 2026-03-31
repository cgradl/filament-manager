# Filament Manager

Track 3D printer filament inventory, print history, and material costs. Integrates with Bambu Lab printers via the [greghesp Bambu Lab integration](https://github.com/greghesp/ha-bambulab).

## Prerequisites

- Bambu Lab integration by **greghesp** must be installed and configured before using this app.

## First-time Setup

1. Open the app from the HA sidebar.
2. Go to **Settings** and verify **HA Connected** shows green.
3. Click **Add Printer** and enter your device slug (e.g. `my_printer`).
4. Use the auto-discovery search to find your Bambu Lab entity IDs.
5. Add your AMS unit(s) and map each tray to a filament spool.
6. Go to **Spools** and add your filament inventory.

## Features

- **Automatic print tracking** — detects print start/end from HA sensor state
- **AMS filament tracking** — calculates grams used per spool per print
- **Spool inventory** — manage brand, material, color, weight, and cost
- **Cost analytics** — per-print cost, price per kg, inventory value
- **Dashboard** — charts, low-stock alerts, recent print history

## Printer Discovery

When adding a printer, click the search icons to auto-discover your Bambu Lab entity IDs. Look for entities starting with your printer's device slug, e.g. `sensor.my_printer_current_stage`.

## Data

All data is stored in `/data/filament.db`. This file is never modified by app updates — your inventory and print history are safe across upgrades.

## Support

Report issues at [github.com/cgradl/filament-manager](https://github.com/cgradl/filament-manager/issues).
