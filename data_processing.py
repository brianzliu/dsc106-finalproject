"""
Data pipeline + orbit math  (Brian's part)
==========================================

Parses and cleans the NASA Near-Earth Object dataset, computes 3-D orbital
ellipse coordinates from the Keplerian elements, flattens the per-asteroid
close-approach history into individual flyby events, and exports a single
lean JSON file that both the Three.js solar-system scene and the D3 charts
can consume.

Run:  python3 data_processing.py
Out:  data/asteroids.json
"""

import ast
import json
import math
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "asteroids_data.csv")
# Split outputs so each consumer loads only what it needs: the 3-D scene
# wants orbits, the D3 charts want flyby events.
ASTEROIDS_OUT = os.path.join(HERE, "data", "asteroids.json")
APPROACHES_OUT = os.path.join(HERE, "data", "close_approaches.json")

# Orbit polyline resolution. 96 segments draws smoothly while keeping the
# exported JSON small.
SEGMENTS = 96

# Map NASA's three-letter orbit-class codes to the names the front-end uses.
ORBIT_CLASS = {
    "APO": "Apollo",
    "AMO": "Amor",
    "ATE": "Aten",
    "IEO": "Atira",  # interior-Earth orbit
}


# ----------------------------------------------------------------------------
# Orbit math: Keplerian elements -> 3-D ellipse coordinates (in AU)
# ----------------------------------------------------------------------------
def keplerian_to_points(a, e, inc_deg, lon_asc_node_deg, arg_peri_deg, segments=SEGMENTS):
    """Sample an orbit ellipse as (x, y, z) points in heliocentric AU.

    Sweeps the eccentric anomaly E over [0, 2pi] and rotates each in-plane
    point by the argument of perihelion (om), inclination (inc) and longitude
    of the ascending node (Om). The axis convention matches the Three.js
    scene: y is the out-of-orbital-plane axis, x/z span the ecliptic.
    """
    inc = math.radians(inc_deg)
    Om = math.radians(lon_asc_node_deg)
    om = math.radians(arg_peri_deg)

    b = a * math.sqrt(max(0.0, 1.0 - e * e))  # semi-minor axis
    c = a * e                                  # focus offset (Sun sits at a focus)

    cosOm, sinOm = math.cos(Om), math.sin(Om)
    cosom, sinom = math.cos(om), math.sin(om)
    cosI, sinI = math.cos(inc), math.sin(inc)

    pts = []
    for i in range(segments + 1):
        E = 2.0 * math.pi * i / segments
        x_orb = a * math.cos(E) - c
        y_orb = b * math.sin(E)

        x = (cosOm * cosom - sinOm * sinom * cosI) * x_orb + (-cosOm * sinom - sinOm * cosom * cosI) * y_orb
        z = (sinOm * cosom + cosOm * sinom * cosI) * x_orb + (-sinOm * sinom + cosOm * cosom * cosI) * y_orb
        y = (sinom * sinI) * x_orb + (cosom * sinI) * y_orb

        # 3 decimals (~0.001 AU) is well below one rendered pixel at scene scale.
        pts.append([round(x, 3), round(y, 3), round(z, 3)])
    return pts


# ----------------------------------------------------------------------------
# Cleaning helpers
# ----------------------------------------------------------------------------
def display_name(row):
    """Short, human-friendly label. Prefer NASA's short_name, fall back to
    stripping the catalog number / provisional designation off the full name."""
    sn = row.get("short_name")
    if isinstance(sn, str) and sn.strip():
        return sn.strip()
    full = str(row["name"]) if pd.notna(row.get("name")) else ""
    if "(" in full and full.split()[:1] and full.split()[0].isdigit():
        return full.split(" (", 1)[0].split(" ", 1)[-1]
    return full.strip("() ").strip()


def parse_close_approaches(cad_raw, name, diameter_m, is_hazardous):
    """Flatten one asteroid's close_approach_data string into Earth flyby
    events the D3 charts can plot directly."""
    if pd.isna(cad_raw):
        return []
    try:
        events = ast.literal_eval(cad_raw)
    except (ValueError, SyntaxError):
        return []

    out = []
    for ev in events:
        if ev.get("orbiting_body") != "Earth":
            continue
        try:
            v_kms = float(ev["relative_velocity"]["kilometers_per_second"])
            miss_ld = float(ev["miss_distance"]["lunar"])
            miss_au = float(ev["miss_distance"]["astronomical"])
            date = ev["close_approach_date"]
        except (KeyError, ValueError, TypeError):
            continue
        out.append({
            "name": name,
            "date": date,
            "year": int(date[:4]),
            "miss_distance_ld": round(miss_ld, 4),
            "miss_distance_au": round(miss_au, 6),
            "velocity_kms": round(v_kms, 3),
            "diameter_m": None if pd.isna(diameter_m) else round(float(diameter_m), 1),
            "is_hazardous": bool(is_hazardous),
        })
    return out


# ----------------------------------------------------------------------------
# Main pipeline
# ----------------------------------------------------------------------------
def main():
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df):,} rows from {os.path.basename(CSV_PATH)}")

    # Keep rows with the orbital elements needed to draw an orbit.
    required = [
        "eccentricity", "semi_major_axis", "inclination",
        "ascending_node_longitude", "perihelion_argument",
    ]
    df = df.dropna(subset=required).copy()

    # Physically sane bounds: bound ellipses only (e < 1) with a sensible size.
    df = df[(df["eccentricity"] >= 0) & (df["eccentricity"] < 1)]
    df = df[(df["semi_major_axis"] > 0) & (df["semi_major_axis"] < 50)]
    print(f"{len(df):,} rows after cleaning orbital elements")

    df["discovery_year"] = pd.to_datetime(
        df["first_observation_date"], errors="coerce"
    ).dt.year

    asteroids = []
    close_approaches = []

    for _, row in df.iterrows():
        name = display_name(row)
        is_haz = bool(row["potentially_hazardous"])
        cls = ORBIT_CLASS.get(row.get("orbit_class_type"), "Other")

        a = float(row["semi_major_axis"])
        e = float(row["eccentricity"])
        inc = float(row["inclination"])
        lon_node = float(row["ascending_node_longitude"])
        arg_peri = float(row["perihelion_argument"])

        def num(col):
            v = row.get(col)
            return None if pd.isna(v) else float(v)

        asteroids.append({
            "name": str(row["name"]),
            "short_name": name,
            "magnitude": num("magnitude"),
            "potentially_hazardous": int(is_haz),
            "diameter_min_m": num("diameter_min_m"),
            "diameter_max_m": num("diameter_max_m"),
            "eccentricity": round(e, 4),
            "semi_major_axis": round(a, 4),
            "inclination": round(inc, 3),
            "ascending_node_longitude": round(lon_node, 3),
            "perihelion_argument": round(arg_peri, 3),
            "orbital_period": num("orbital_period"),
            "perihelion_distance": num("perihelion_distance"),
            "aphelion_distance": num("aphelion_distance"),
            "min_orbit_intersection": num("min_orbit_intersection"),
            "orbit_class_type": cls,
            "discovery_year": None if pd.isna(row["discovery_year"]) else int(row["discovery_year"]),
            # Precomputed orbit ellipse in heliocentric AU (multiply by the
            # scene's AU display scale to render).
            "orbit": keplerian_to_points(a, e, inc, lon_node, arg_peri),
        })

        close_approaches.extend(
            parse_close_approaches(
                row["close_approach_data"], name, row.get("diameter_max_m"), is_haz
            )
        )

    # Sort close approaches chronologically for predictable plotting.
    close_approaches.sort(key=lambda d: d["date"])

    n_future = sum(1 for c in close_approaches if 2026 <= c["year"] <= 2125)
    n_hazardous = sum(a["potentially_hazardous"] for a in asteroids)
    source = "NASA Near-Earth Object dataset (asteroids_data.csv)"

    asteroids_payload = {
        "meta": {
            "source": source,
            "units": "heliocentric AU; y is the out-of-orbital-plane axis",
            "orbit_segments": SEGMENTS,
            "n_asteroids": len(asteroids),
            "n_hazardous": n_hazardous,
        },
        "asteroids": asteroids,
    }
    approaches_payload = {
        "meta": {
            "source": source,
            "units": {
                "miss_distance_ld": "lunar distances (1 LD = 384,400 km)",
                "velocity_kms": "km/s relative to Earth at close approach",
            },
            "n_close_approaches": len(close_approaches),
            "n_close_approaches_2026_2125": n_future,
        },
        "close_approaches": close_approaches,
    }

    os.makedirs(os.path.dirname(ASTEROIDS_OUT), exist_ok=True)
    for path, payload in ((ASTEROIDS_OUT, asteroids_payload),
                          (APPROACHES_OUT, approaches_payload)):
        with open(path, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
        print(f"Wrote {os.path.relpath(path, HERE)}  "
              f"({os.path.getsize(path) / 1e6:.2f} MB)")

    print(f"  asteroids:        {len(asteroids):,}  ({n_hazardous:,} hazardous)")
    print(f"  close approaches: {len(close_approaches):,}  "
          f"({n_future:,} in 2026-2125)")


if __name__ == "__main__":
    main()
