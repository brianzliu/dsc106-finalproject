# Data pipeline

Source: NASA Near-Earth Object dataset → `asteroids_data.csv` (2,000 NEOs).

Run `python3 ../data_processing.py` to regenerate the two JSON files below from
the CSV. The pipeline cleans the orbital elements, computes each orbit's 3-D
ellipse from the Keplerian elements, and flattens every Earth close-approach
into an individual event.

## `asteroids.json` — for the 3-D solar-system scene

```jsonc
{
  "meta": { "n_asteroids": 2000, "n_hazardous": 533, "orbit_segments": 96, ... },
  "asteroids": [
    {
      "name": "1620 Geographos (1951 RA)",
      "short_name": "Geographos",
      "magnitude": 15.26,
      "potentially_hazardous": 1,            // 0 | 1
      "diameter_min_m": 2358.1,
      "diameter_max_m": 5272.8,
      "eccentricity": 0.3355,
      "semi_major_axis": 1.2458,             // AU
      "inclination": 13.336,                 // degrees
      "ascending_node_longitude": 337.141,   // degrees (real, not faked)
      "perihelion_argument": 277.018,        // degrees
      "orbital_period": 507.88,              // days
      "perihelion_distance": 0.8278,         // AU
      "aphelion_distance": 1.6638,           // AU
      "min_orbit_intersection": 0.0294,      // AU (MOID with Earth)
      "orbit_class_type": "Apollo",          // Apollo | Amor | Aten | Atira | Other
      "discovery_year": 1951,
      "orbit": [[x, y, z], ...]              // 97 points, heliocentric AU
    }
  ]
}
```

**`orbit`** is the precomputed ellipse in heliocentric AU. `y` is the
out-of-orbital-plane axis; `x`/`z` span the ecliptic — the same axis convention
the Three.js scene uses. Multiply each coordinate by the scene's AU display
scale (e.g. `1.8`) to draw. The math lives in `keplerian_to_points()` in
`data_processing.py`, so the renderer can either use these points directly or
recompute from the elements.

## `close_approaches.json` — for the D3 charts

```jsonc
{
  "meta": { "n_close_approaches": 41939, "n_close_approaches_2026_2125": 13691, ... },
  "close_approaches": [
    {
      "name": "Geographos",
      "date": "2026-08-12",
      "year": 2026,
      "miss_distance_ld": 66.30,    // lunar distances (1 LD = 384,400 km)
      "miss_distance_au": 0.170437,
      "velocity_kms": 8.362,        // relative to Earth
      "diameter_m": 5272.8,         // max diameter estimate
      "is_hazardous": true
    }
  ]
}
```

Only Earth close approaches are included, sorted by date. For the
year-vs-miss-distance scatter, filter `2026 <= year <= 2125`.

### Loading in the browser

```js
const { asteroids } = await (await fetch("data/asteroids.json")).json();
const { close_approaches } = await (await fetch("data/close_approaches.json")).json();
// or with D3: d3.json("data/close_approaches.json")
```
