"""Build the GeoJSON layers used by the map from Natural Earth (public domain).

Input : ne_50m_land.geojson, ne_50m_antarctic_ice_shelves_polys.geojson
        (downloaded from the Natural Earth GitHub mirror if not cached)
Output: data/geo/coastline.geojson, data/geo/iceshelves.geojson
        clipped to the Indian sector of East Antarctica (lon -10..120, lat -80..-56).

Run once. The generated files are committed, so the app never needs internet.
"""
import json, pathlib, urllib.request
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo"
TMP = ROOT / "scripts" / ".cache"
BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
FILES = ["ne_50m_land.geojson", "ne_50m_antarctic_ice_shelves_polys.geojson"]
CLIP = box(-10, -80, 120, -56)


def fetch(name):
    TMP.mkdir(exist_ok=True)
    p = TMP / name
    if not p.exists():
        print("downloading", name)
        urllib.request.urlretrieve(BASE + name, p)
    return json.loads(p.read_text())


def build(gj, min_area=0.01):
    geoms = []
    for f in gj["features"]:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        c = g.intersection(CLIP)
        if not c.is_empty:
            geoms.append(c)
    u = unary_union(geoms).simplify(0.02, preserve_topology=True)
    parts = list(u.geoms) if hasattr(u, "geoms") else [u]
    feats = []
    for g in parts:
        if g.geom_type != "Polygon" or g.area < min_area:
            continue
        m = mapping(g)
        m["coordinates"] = json.loads(json.dumps(m["coordinates"]), parse_float=lambda x: round(float(x), 3))
        feats.append({"type": "Feature", "properties": {}, "geometry": m})
    return {"type": "FeatureCollection", "features": feats}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    land = build(fetch(FILES[0]))
    land["properties"] = {"source": "Natural Earth 1:50m land (public domain)"}
    shelf = build(fetch(FILES[1]), min_area=0.005)
    shelf["properties"] = {"source": "Natural Earth 1:50m Antarctic ice shelves (public domain)"}
    (OUT / "coastline.geojson").write_text(json.dumps(land, separators=(",", ":")))
    (OUT / "iceshelves.geojson").write_text(json.dumps(shelf, separators=(",", ":")))
    print("coastline features:", len(land["features"]), "iceshelves:", len(shelf["features"]))
