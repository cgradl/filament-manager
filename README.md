# Filament Manager

A Home Assistant app for tracking 3D printer filament inventory, monitoring print history, and calculating material costs. Integrates natively with Bambu Lab printers via the [greghesp Bambu Lab integration](https://github.com/greghesp/ha-bambulab).

![Version](https://img.shields.io/badge/version-0.5.0-blue) ![Platform](https://img.shields.io/badge/platform-Home%20Assistant-teal)

---

## Features

- **Automatic print detection** — monitors your Bambu Lab printer state via HA sensors and creates print records automatically
- **AMS filament tracking** — snapshots filament levels at print start/end and calculates grams used per spool
- **Spool inventory** — full CRUD for filament spools with brand, material, color, weight, and cost data
- **Cost analytics** — per-print cost, price per kg, inventory value, and spend by purchase location
- **Dashboard** — overview charts, low-stock alerts, and recent print history
- **Printer discovery** — scans Home Assistant for your Bambu Lab entities automatically

---

## Screenshots

| Dashboard | Spools | Print History | Settings |
|-----------|--------|---------------|----------|
| Stats, charts, alerts | Inventory with weight/cost | Timeline with filament breakdown | Printer & AMS setup |

---

## Requirements

- Home Assistant with Supervisor (HassOS / Home Assistant OS)
- [Bambu Lab integration by greghesp](https://github.com/greghesp/ha-bambulab) already configured
- SSH or Samba access to your HA host

---

## Installation

See [INSTALL.md](INSTALL.md) for full step-by-step instructions.

**Quick start:**

```bash
# Copy app to HA via SSH
scp -r filament-manager/ root@homeassistant.local:/addons/filament_manager/
```

Then in HA: **Settings → Apps → App Store → ⋮ → Check for updates** → install **Filament Manager**.

---

## Architecture

```
filament-manager/
├── backend/               # FastAPI + SQLite
│   └── app/
│       ├── main.py        # App entry point & lifecycle
│       ├── models.py      # SQLAlchemy models (8 tables)
│       ├── print_monitor.py  # Background job: polls HA every 30s
│       ├── ha_client.py   # Home Assistant API client
│       └── routers/       # REST API endpoints
└── frontend/              # React + TypeScript + Vite
    └── src/
        └── pages/         # Dashboard, Spools, Prints, Settings
```

### Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 · FastAPI · SQLite · APScheduler |
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS · Recharts |
| Container | Multi-stage Docker (Node 20 → Python 3.11, Alpine) |
| HA integration | App with `homeassistant_api: true` · Ingress on port 8099 |

---

## How It Works

### Automatic Print Tracking

A background job polls `sensor.{device_slug}_current_stage` every 30 seconds.

```
idle → printing         Creates a new PrintJob + captures AMS snapshot
printing → finished     Closes job, calculates filament delta, updates spool weights
printing → failed       Closes job with failed flag
```

### Filament Consumption Calculation

At print start, the app records the remaining percentage of each AMS tray. On print end, it computes:

```
grams_used = initial_weight_g × (pct_start − pct_end) / 100
```

The spool's `current_weight_g` is updated automatically.

### Cost Tracking

Each spool stores a purchase price. The app derives:

- `price_per_kg` = price ÷ net weight (kg)
- `cost_per_gram` = price_per_kg ÷ 1000
- Per-print cost = Σ (grams_used × cost_per_gram) across all spools used

---

## API Overview

| Resource | Endpoints |
|----------|-----------|
| Spools | `GET/POST /api/spools` · `GET/PATCH/DELETE /api/spools/{id}` |
| Prints | `GET/POST /api/prints` · `GET/PATCH/DELETE /api/prints/{id}` |
| Printers | `GET/POST /api/printers` · `GET /api/printers/discover/{slug}` |
| Dashboard | `GET /api/dashboard` |
| Settings | `GET /api/app-settings` · `GET /api/app-settings/ha-connected` |

Full interactive docs available at `http://<ha-host>:8099/docs` (FastAPI Swagger UI).

---

## Data & Persistence

- Database: SQLite at `/data/filament.db` (persists across app updates)
- Schema migrations run automatically on startup — no manual steps required
- Updating the app never touches the database

---

## Development

### Backend

```bash
cd filament-manager/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8099
```

### Frontend

```bash
cd filament-manager/frontend
npm install
npm run dev        # dev server on :5173, proxies /api → :8099
npm run build      # production build → dist/
```

### Docker build

```bash
cd filament-manager
docker build -t filament-manager .
```

---

## Configuration

The app exposes no user-visible `config.yaml` options. All configuration is done inside the app's **Settings** page after first launch:

1. Verify **HA Connected** shows green
2. Click **Add Printer** and enter your device slug (e.g. `h2s`)
3. Use the auto-discovery search to map your AMS tray entities
4. Add your filament spools under **Spools**

---

## Supported Architectures

`aarch64` · `amd64` · `armhf` · `armv7`

---

## License

Private / personal use. Not affiliated with Bambu Lab or Home Assistant.
