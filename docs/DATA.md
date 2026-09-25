# Data sources

| Dataset | Source | Real or synthetic |
|---|---|---|
| Coastline, ice shelves | Natural Earth 1:50m (public domain), `scripts/build_geo.py` | Real |
| Sea-ice concentration | Distance-from-coast approximation, `services/geo.py::sea_ice()` | Synthetic — replace with NSIDC/Copernicus for real use |
| Cargo rules (air weight limit, hazardous cargo) | NCPOR ISEA expedition advertisements | Real rules, see `verified` flags in `data/cargo_rules.json` |
| Personnel, assets, cargo manifests, inventory, weather | `scripts/generate_data.py` (seed=46, deterministic) | Synthetic demo data |
| Station coordinates (Bharati, Maitri) | Published station positions | Real |
| Sandhi summer-base location | Not confirmed | Marked `approx: true` everywhere it appears |

Regenerate the synthetic datasets at any time:
```bash
python scripts/generate_data.py
```
Regenerate the coastline GeoJSON (downloads from Natural Earth's GitHub mirror once,
then caches locally in `scripts/.cache/`):
```bash
python scripts/build_geo.py
```
