"""
Seed data from the user's spreadsheet (imported 2026-03-28).
Run once: python -m app.seed_data
Or triggered automatically on first start if the spools table is empty.
"""
from datetime import datetime

# Color name → hex mapping
COLOR_HEX = {
    "Black":                    "#1a1a1a",
    "White":                    "#f0f0f0",
    "Gray":                     "#888888",
    "Space Gray":               "#6b7280",
    "Ash Gray":                 "#b0b0b0",
    "Titan Gray":               "#757575",
    "Red":                      "#e53935",
    "Olive Green":              "#6b8e23",
    "Coffee Brown":             "#6f4e37",
    "Transparent Light Blue":   "#90caf9",
    "Clear":                    "#e3f2fd",
    "Luminous Orange":          "#ff6f00",
    "White Marble":             "#f5f5f0",
    "Metallic Cobalt Blue":     "#1565c0",
    "Black Walnut":             "#4e342e",
    "Jade White":               "#c8e6c9",
    "Silver":                   "#c0c0c0",
    "Copper":                   "#b87333",
    "Gold":                     "#ffd700",
    "Yellow":                   "#fdd835",
}

def _hex(color_name: str) -> str:
    return COLOR_HEX.get(color_name, "#888888")


def _date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y")
    except Exception:
        return None


# (material, subtype, color_name, brand, cost_eur, purchase_date, pct_left, weight_kg)
RAW: list[tuple] = [
    ("PETG", "Basic",      "Black",                    "SUNLU",     11.59, "29/11/2025",  0, 1.00),
    ("PETG", "Basic",      "Black",                    "SUNLU",     11.59, "29/11/2025",  0, 1.00),
    ("PETG", "Basic",      "Black",                    "SUNLU",      8.97, "19/01/2026",  0, 1.00),
    ("PETG", "Basic",      "Black",                    "SUNLU",      8.97, "19/01/2026", 60, 1.00),
    ("PETG", "Basic",      "Black",                    "SUNLU",      8.97, "19/01/2026",100, 1.00),
    ("PETG", "HF",         "Black",                    "Bambu Lab", 11.18, "23/11/2025",  0, 1.00),
    ("PETG", "Basic",      "Black",                    "SUNLU",     11.59, "29/11/2025",  0, 1.00),
    ("PETG", "Translucent","Transparent Light Blue",   "Bambu Lab", 11.18, "23/11/2025", 90, 1.00),
    ("PETG", "Translucent","Clear",                    "Bambu Lab", 11.18, "23/11/2025",100, 1.00),
    ("PETG", "Basic",      "Olive Green",              "SUNLU",     16.14, "29/11/2025", 90, 1.00),
    ("PETG", "Basic",      "Gray",                     "SUNLU",     14.99, "29/11/2025", 90, 1.00),
    ("PETG", "Basic",      "Red",                      "SUNLU",     15.99, "29/11/2025", 90, 1.00),
    ("PETG", "Basic",      "Coffee Brown",             "SUNLU",     16.99, "29/11/2025",100, 1.00),
    ("PETG", "Elite",      "Space Gray",               "SUNLU",      9.22, "03/01/2026",100, 1.00),
    ("PETG", "Elite",      "White",                    "SUNLU",      9.22, "03/01/2026",100, 1.00),
    ("PETG", "Basic",      "White",                    "SUNLU",     11.15, "03/01/2026",100, 1.00),
    ("PETG", "Basic",      "White",                    "SUNLU",     11.15, "03/01/2026",100, 1.00),
    ("PETG", "Basic",      "White",                    "SUNLU",     11.15, "03/01/2026", 90, 1.00),
    ("PETG", "Matte",      "White",                    "SUNLU",      9.38, "03/01/2026",  0, 1.00),
    ("PETG", "Matte",      "White",                    "SUNLU",      9.38, "03/01/2026",  0, 1.00),
    ("PETG", "Matte",      "White",                    "SUNLU",      9.38, "03/01/2026",  0, 1.00),
    ("PLA",  "Matte",      "Gray",                     "SUNLU",     11.11, "03/01/2026",100, 1.00),
    ("PLA",  "Matte",      "Gray",                     "SUNLU",     11.11, "03/01/2026",100, 1.00),
    ("PLA",  "Matte",      "Gray",                     "SUNLU",     11.11, "03/01/2026",100, 1.00),
    ("PLA",  "Matte",      "Gray",                     "SUNLU",     11.11, "03/01/2026",100, 1.00),
    ("PLA",  "Matte",      "Gray",                     "SUNLU",     11.11, "03/01/2026",100, 1.00),
    ("PLA",  "Shiny Silk", "Yellow",                   "SUNLU",      8.22, "03/01/2026", 80, 0.25),
    ("PLA",  "Matte",      "Ash Gray",                 "Bambu Lab", 11.18, "23/11/2025",  5, 1.00),
    ("PLA",  "Wood",       "Black Walnut",             "Bambu Lab", 22.39, "23/11/2025", 59, 1.00),
    ("PLA",  "Metal",      "Metallic Cobalt Blue",     "Bambu Lab", 22.39, "23/11/2025", 50, 1.00),
    ("PLA",  "Basic",      "Black",                    "Bambu Lab", 11.18, "23/11/2025",  0, 1.00),
    ("PLA",  "Glow",       "Luminous Orange",          "Bambu Lab", 22.39, "23/11/2025", 90, 1.00),
    ("PLA",  "Marble",     "White Marble",             "Bambu Lab", 22.39, "23/11/2025", 80, 1.00),
    ("PLA",  "Basic",      "Jade White",               "Bambu Lab", 11.18, "23/11/2025",  0, 1.00),
    ("PLA",  "Plus",       "Black",                    "SUNLU",     11.72, "29/11/2025",  0, 1.00),
    ("PLA",  "Silk+",      "Titan Gray",               "Bambu Lab", 21.79, "19/01/2026",100, 1.00),
    ("TPU",  "4AMS",       "Black",                    "Bambu Lab", 30.18, "19/01/2026",100, 1.00),
    ("PLA",  "Basic",      "Black",                    "Jayo",       9.47, "22/01/2026", 50, 1.10),
    ("PLA",  "Basic",      "Black",                    "Jayo",       9.47, "22/01/2026",  0, 1.10),
    ("PLA",  "Basic",      "Black",                    "Jayo",       9.47, "22/01/2026",  0, 1.10),
    ("PLA",  "Basic",      "Black",                    "Jayo",       9.47, "22/01/2026", 60, 1.10),
    ("PLA",  "Basic",      "Black",                    "Jayo",       9.47, "22/01/2026",100, 1.10),
    ("PLA",  "Silk",       "Silver",                   "Geeetech",   8.69, "03/02/2026",100, 1.00),
    ("PLA",  "Silk",       "Copper",                   "Geeetech",   8.99, "03/02/2026",100, 1.00),
    ("PLA",  "Silk",       "Gold",                     "Geeetech",   8.99, "03/02/2026",100, 1.00),
    ("PETG", "HSM",        "Black",                    "Jayo",       9.99, "08/03/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       9.99, "08/03/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       9.99, "08/03/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       9.99, "08/03/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       9.99, "08/03/2026",100, 1.10),
    ("PLA",  "Matte",      "Black",                    "Jayo",      10.32, "08/03/2026",100, 1.10),
    ("PLA",  "Matte",      "Black",                    "Jayo",      10.32, "08/03/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",100, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026", 50, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       7.30, "11/02/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
    ("PETG", "HSM",        "Black",                    "Jayo",       6.94, "23/01/2026",  0, 1.10),
]


def build_spools() -> list[dict]:
    spools = []
    for material, subtype, color_name, brand, cost, date_str, pct, weight_kg in RAW:
        initial_g = weight_kg * 1000
        current_g = round(initial_g * pct / 100, 1)
        spools.append(dict(
            brand=brand,
            material=material,
            subtype=subtype,
            color_name=color_name,
            color_hex=_hex(color_name),
            diameter_mm=1.75,
            initial_weight_g=initial_g,
            current_weight_g=current_g,
            spool_weight_g=0,
            purchase_price=cost,
            purchased_at=_date(date_str),
        ))
    return spools


def run_seed(db_path: str | None = None) -> int:
    """Insert seed spools. Returns number inserted."""
    import os
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    path = db_path or os.environ.get("DATA_DIR", "/data")
    url = f"sqlite:///{path}/filament.db" if not db_path or not db_path.endswith(".db") else f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    # Ensure tables exist
    from .database import Base
    from .models import Spool
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        existing = session.execute(text("SELECT COUNT(*) FROM spools")).scalar()
        if existing and existing > 0:
            print(f"Spools table already has {existing} rows — skipping seed.")
            return 0

        spools = build_spools()
        for s in spools:
            session.add(Spool(**s))
        session.commit()
        print(f"Seeded {len(spools)} spools.")
        return len(spools)


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_seed(db_path)
