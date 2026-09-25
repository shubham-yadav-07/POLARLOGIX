"""Generate the synthetic operational datasets in ./data (CSV + JSON).

Everything here is SYNTHETIC except:
  * station coordinates for Bharati and Maitri (published station positions)
  * the cargo / air-freight rules, which are taken from NCPOR ISEA expedition
    advertisements (each rule carries its source and a verified flag).

Timestamps are stored relative to "now" (minutes_ago / hours_ago) so the data is
always fresh whenever the database is seeded.

Run:  python scripts/generate_data.py      (deterministic, seed = 46)
"""
import csv, json, math, pathlib, random

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
rnd = random.Random(46)


def write_csv(name, rows, fields):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{name:22s} {len(rows):5d} rows")


def jitter(v, d):
    return round(v + rnd.uniform(-d, d), 4)


# ------------------------------------------------------------------ stations
BHARATI = (-69.4083, 76.1867)
MAITRI = (-70.7667, 11.7333)
BRAVO = (-71.0, 74.8)
VESSEL = (-63.2, 47.0)
stations = [
    dict(code="Bharati", name="Bharati Station", kind="station", lat=BHARATI[0], lon=BHARATI[1], approx=0, note="Larsemann Hills, Prydz Bay"),
    dict(code="Maitri", name="Maitri Station", kind="station", lat=MAITRI[0], lon=MAITRI[1], approx=0, note="Schirmacher Oasis"),
    dict(code="Sandhi", name="Sandhi summer base", kind="summer_base", lat=-70.6, lon=69.6, approx=1, note="Planned; exact location not confirmed"),
    dict(code="Himadri", name="Himadri Station", kind="arctic_station", lat=78.92, lon=11.93, approx=1, note="Ny-Alesund, Svalbard"),
    dict(code="Himansh", name="Himansh Station", kind="himalayan_station", lat=32.33, lon=77.6, approx=1, note="Spiti, Himachal Pradesh"),
    dict(code="Cape Town hub", name="Cape Town hub", kind="hub", lat=-33.92, lon=18.42, approx=0, note="Logistics hub for ISEA"),
    dict(code="NCPOR Goa", name="NCPOR Goa (HQ)", kind="hq", lat=15.39, lon=73.83, approx=1, note="Headquarters, Vasco da Gama"),
    dict(code="Vessel", name="Ice-class vessel", kind="vessel", lat=VESSEL[0], lon=VESSEL[1], approx=1, note="Demo position"),
    dict(code="Traverse", name="Traverse party", kind="field", lat=BRAVO[0], lon=BRAVO[1], approx=1, note="Demo position"),
]
write_csv("stations.csv", stations, list(stations[0].keys()))

# ------------------------------------------------------------------ users
users = [
    dict(username="control", full_name="BHARATI-CONTROL-1", role="manager", station="Bharati"),
    dict(username="leader", full_name="Station Leader, Bharati", role="leader", station="Bharati"),
    dict(username="bravo", full_name="Team Bravo field tablet", role="field", station="Traverse"),
    dict(username="logistics", full_name="Logistics Officer, Goa", role="logistics", station="NCPOR Goa"),
]
write_csv("users.csv", users, list(users[0].keys()))

# ------------------------------------------------------------------ missions
missions = [
    dict(id="EXP-46-ISEA", name="46th Indian Scientific Expedition to Antarctica", org="Ice-core and atmospheric science / NCPOR, MoES", base="Bharati", destination="Sandhi summer-base traverse", status="ACTIVE", risk_rating="MEDIUM", progress=62, start_date="2026-11-01", end_date="2027-03-31", objective="Deep ice-core drilling and an automated weather buoy deployment.", permit_valid_until="2027-04-15", route_id="R-TRAV-1"),
    dict(id="EXP-MAITRI", name="Maitri resupply and winter changeover", org="Logistics / NCPOR, MoES", base="Maitri", destination="Cape Town to Maitri, air and ship legs", status="ACTIVE", risk_rating="HIGH", progress=44, start_date="2026-11-10", end_date="2027-02-20", objective="Move fuel, food and spares through the Cape Town hub inside the weather window.", permit_valid_until="2027-03-01", route_id="R-VESSEL-A"),
    dict(id="EXP-HIMADRI", name="Himadri Arctic summer campaign", org="Arctic research / NCPOR, MoES", base="Himadri", destination="Kongsfjorden field sites", status="PLANNED", risk_rating="LOW", progress=15, start_date="2027-06-01", end_date="2027-08-31", objective="Fjord sampling and atmospheric sensor servicing.", permit_valid_until="", route_id=""),
    dict(id="EXP-HIMANSH", name="Himansh glacier monitoring", org="Cryosphere / NCPOR, MoES", base="Himansh", destination="Glacier monitoring transect", status="ACTIVE", risk_rating="MEDIUM", progress=78, start_date="2026-08-01", end_date="2026-10-31", objective="Seasonal mass-balance readings and stake replacement.", permit_valid_until="2026-12-10", route_id=""),
]
write_csv("missions.csv", missions, list(missions[0].keys()))

# ------------------------------------------------------------------ personnel
FIRST = ["Aarav", "Ananya", "Vikram", "Meera", "Rohan", "Kavya", "Arjun", "Divya", "Sanjay", "Neha", "Karthik", "Priya", "Rahul", "Sneha", "Manoj", "Isha", "Deepak", "Lakshmi", "Suresh", "Pooja", "Nikhil", "Tanvi", "Harish", "Anjali", "Varun", "Ritu", "Amit", "Shreya", "Gautam", "Farah", "Joseph", "Tenzin", "Rajesh", "Sunita", "Imran", "Bhavna", "Zoya"]
LAST = ["Roy", "Verma", "Bhatt", "Menon", "Dorjee", "Iyer", "Nair", "Fernandes", "Kulkarni", "Rao", "Sharma", "Pillai", "Das", "Singh", "Reddy", "Joshi", "Chatterjee", "Naik", "Gupta", "Thomas", "Mehta", "Patil", "Khan", "Bose", "Shetty", "Kamath", "D'Souza", "Ghosh", "Yadav", "Sethi", "Mishra", "Lal", "Rane", "Sawant", "Pandey", "Kapoor", "Warrier"]
names = [f"{f} {l}" for f, l in zip(FIRST, rnd.sample(LAST, len(LAST)))]
rnd.shuffle(names)

# (team, mission, station, count, interval_min, roles, position)
teams = [
    ("Alpha", "EXP-46-ISEA", "Bharati", 6, 180, ["Glaciologist", "Field engineer", "Glaciologist", "Mechanic", "Radio operator", "Field engineer"], BHARATI),
    ("Bravo", "EXP-46-ISEA", "Traverse", 3, 180, ["Team lead", "Medical officer", "Mountaineer"], BRAVO),
    ("Base-Bharati", "EXP-46-ISEA", "Bharati", 8, 240, ["Station leader", "Met observer", "Cook", "Electrician", "Doctor", "Logistics officer", "Mechanic", "IT engineer"], BHARATI),
    ("Base-Maitri", "EXP-MAITRI", "Maitri", 8, 240, ["Station leader", "Met observer", "Cook", "Electrician", "Doctor", "Mechanic", "Radio operator", "Pilot"], MAITRI),
    ("Logistics-Maitri", "EXP-MAITRI", "Maitri", 3, 240, ["Logistics lead", "Flight coordinator", "Storekeeper"], MAITRI),
    ("Himadri", "EXP-HIMADRI", "Himadri", 2, 360, ["Campaign lead", "Field scientist"], (78.92, 11.93)),
    ("Himansh", "EXP-HIMANSH", "Himansh", 2, 360, ["Glaciologist", "Field assistant"], (32.33, 77.6)),
    ("Vessel", "EXP-MAITRI", "Vessel", 5, 240, ["Master", "Chief officer", "Chief engineer", "Ice pilot", "Voyage doctor"], VESSEL),
]
personnel, k = [], 0
for team, mission, station, n, interval, roles, pos in teams:
    for i in range(n):
        k += 1
        if team == "Bravo":
            ago = interval - 10                 # next check-in due in 10 minutes
        else:
            ago = rnd.randint(10, interval - 45)
        personnel.append(dict(id=f"P-{k:03d}", name=names[k - 1], role=roles[i], team=team, mission_id=mission, station=station,
                              lat=jitter(pos[0], 0.004), lon=jitter(pos[1], 0.01), checkin_interval_min=interval, last_checkin_min_ago=ago))
assert len(personnel) == 37, len(personnel)
write_csv("personnel.csv", personnel, list(personnel[0].keys()))

# ------------------------------------------------------------------ assets (126)
spec = [  # type, code, count, name, station spread, mission
    ("Snowcat", "SNOW", 14, "Snowcat, tracked"), ("UAV", "UAV", 12, "Fixed-wing survey UAV"), ("Sledge", "SLED", 30, "Traverse sledge"),
    ("Generator", "GEN", 10, "Generator 150 kVA"), ("Cold storage", "CRYO", 8, "Cryo container"), ("Boat", "BOAT", 6, "Rigid inflatable boat"),
    ("Drill rig", "DRILL", 4, "Ice-core drill rig"), ("Satcom terminal", "SAT", 12, "Satcom terminal"), ("Beacon", "PLB", 30, "Personal locator beacon"),
]
assets = []
for typ, code, n, name in spec:
    for i in range(1, n + 1):
        r = rnd.random()
        if code in ("SNOW", "SLED", "UAV", "CRYO", "PLB", "SAT") and r < .34:
            st, pos = "Traverse", BRAVO
        elif r < .7:
            st, pos = "Bharati", BHARATI
        elif r < .93:
            st, pos = "Maitri", MAITRI
        else:
            st, pos = "Cape Town hub", (-33.92, 18.42)
        if code == "GEN" and st == "Traverse":
            st, pos = "Bharati", BHARATI
        status = rnd.choices(["Available", "In use", "Maintenance"], [.45, .48, .07])[0]
        if code == "GEN":
            status = "Running" if rnd.random() < .8 else "Available"
        lvl = 0 if code == "SLED" else rnd.randint(35, 100)
        assets.append(dict(id=f"AST-{code}-{i:02d}", name=name, type=typ, station=st, status=status, level_pct=lvl,
                           lat=jitter(pos[0], 0.02 if st != "Cape Town hub" else 0.01), lon=jitter(pos[1], 0.05), mission_id="EXP-46-ISEA" if st in ("Bharati", "Traverse") else ""))
# pin the assets the demo story talks about
for a in assets:
    if a["id"] == "AST-SNOW-02": a.update(station="Traverse", status="Available", level_pct=88, lat=-70.90, lon=74.90)
    if a["id"] == "AST-UAV-04": a.update(station="Traverse", status="Available", level_pct=71, lat=-70.95, lon=74.85)
    if a["id"] == "AST-SNOW-01": a.update(station="Traverse", status="In use", level_pct=64, lat=-71.02, lon=74.78)
    if a["id"] == "AST-CRYO-09": a.update(station="Traverse", status="In use", level_pct=82, lat=-71.0, lon=74.8)
assert len(assets) == 126
write_csv("assets.csv", assets, list(assets[0].keys()))

# ------------------------------------------------------------------ inventory
inventory = [
    dict(id="INV-FOOD", name="Ration packs", category="food", qty=312, unit="packs", daily_use=40, min_qty=200, station="Traverse"),
    dict(id="INV-DIESEL-T", name="Diesel (traverse)", category="fuel", qty=1250, unit="L", daily_use=190, min_qty=800, station="Traverse"),
    dict(id="INV-MELT", name="Melt-water fuel", category="water", qty=96, unit="kg", daily_use=16, min_qty=60, station="Traverse"),
    dict(id="INV-MED", name="Medical kits", category="medical", qty=14, unit="kits", daily_use=0.3, min_qty=8, station="Traverse"),
    dict(id="INV-LI", name="Li-ion spare cells", category="spare", qty=22, unit="cells", daily_use=1.2, min_qty=10, station="Traverse"),
    dict(id="INV-DIESEL-S", name="Bulk diesel (station)", category="station_fuel", qty=48500, unit="L", daily_use=420, min_qty=20000, station="Bharati"),
    dict(id="INV-GAS", name="Cooking gas cylinders", category="station_fuel", qty=64, unit="cylinders", daily_use=1.5, min_qty=20, station="Bharati"),
    dict(id="INV-FLARE", name="Signal flares", category="safety", qty=36, unit="flares", daily_use=0.1, min_qty=12, station="Bharati"),
]
write_csv("inventory.csv", inventory, list(inventory[0].keys()))

# ------------------------------------------------------------------ cargo
NON_HAZ = [("Drill spares", 180, ""), ("Ice-core tubes", 95, ""), ("Radar antenna", 40, ""), ("Tents and stoves", 120, ""), ("Dry rations pallet", 300, ""),
           ("Fresh produce crate", 60, ""), ("Medical kit boxes", 45, ""), ("Lab consumables", 70, ""), ("Winter clothing bales", 150, ""),
           ("Spare snowcat tracks", 220, ""), ("Solar panels", 85, ""), ("Comms terminal", 18, ""), ("Sample freezer parts", 55, ""), ("Soil test kit", 12, "soil")]
HAZ = [("Li-ion battery pack", 64, "battery"), ("Jet A-1 drums", 208, "fuel"), ("Propane cylinders", 110, "gas"), ("Lab chemicals (flammable)", 35, "chemical"), ("Diesel drums", 400, "fuel")]
cargo, in_transit = [], 0
# the consignment used in the demo
demo = [("Drill spares", 180, "", "air"), ("Li-ion battery pack", 64, "battery", "ship"), ("Jet A-1 drums", 208, "fuel", "ship"), ("Soil test kit", 12, "soil", "air")]
for i, (n, w, cat, route) in enumerate(demo, 1):
    cargo.append(dict(id=f"CRG-0231-{i}", consignment="CRG-0231", name=n, weight_kg=w, category=cat, hazard=int(cat in ("battery", "fuel", "gas", "chemical")), route=route, current_node="Cape Town hub", status="in_transit"))
    in_transit += 1
AIR = ["NCPOR Goa", "Cape Town hub", "Novo airfield (Maitri)", "Air leg to Bharati", "Bharati"]
SHIP = ["NCPOR Goa", "Cape Town hub", "Ice-class vessel", "Bharati"]
for c in range(232, 244):
    cid = f"CRG-{c:04d}"
    n_items = rnd.randint(2, 4)
    air_total = 0
    for j in range(1, n_items + 1):
        if rnd.random() < .25:
            n, w, cat = rnd.choice(HAZ); route = "ship"
        else:
            n, w, cat = rnd.choice(NON_HAZ); route = rnd.choice(["air", "ship"])
            if route == "air" and air_total + w > 1400:
                route = "ship"
            if route == "air":
                air_total += w
        path = AIR if route == "air" else SHIP
        status = rnd.choices(["in_transit", "delivered", "packed"], [.42, .38, .20])[0]
        if in_transit >= 18 and status == "in_transit":
            status = "delivered"
        if status == "in_transit":
            node = path[rnd.randint(1, len(path) - 2)]; in_transit += 1
        elif status == "delivered":
            node = "Bharati"
        else:
            node = "NCPOR Goa"
        cargo.append(dict(id=f"{cid}-{j}", consignment=cid, name=n, weight_kg=w, category=cat, hazard=int(cat in ("battery", "fuel", "gas", "chemical")), route=route, current_node=node, status=status))
# top up to exactly 18 items in transit
for c in cargo:
    if in_transit >= 18: break
    if c["status"] == "packed":
        path = AIR if c["route"] == "air" else SHIP
        c.update(status="in_transit", current_node=path[1]); in_transit += 1
assert sum(1 for c in cargo if c["status"] == "in_transit") == 18, sum(1 for c in cargo if c["status"] == "in_transit")
write_csv("cargo.csv", cargo, list(cargo[0].keys()))

rules = {
    "air_limit_kg": {"min": 1500, "max": 1800,
                     "note": "Small flights from Cape Town carry about 1,500 to 1,800 kg including people, personal and scientific cargo and emergency kits.",
                     "source": "NCPOR ISEA expedition advertisement", "verified": True},
    "hazard_categories": ["battery", "fuel", "gas", "chemical"],
    "hazard_rule": {"text": "Hazardous cargo (gases, chemicals, fuel, lithium-ion batteries) cannot go by air; arrange at Cape Town or ship it.",
                    "source": "NCPOR ISEA expedition advertisement", "verified": True},
    "arrange_at_cape_town": ["fuel"],
    "declaration_required": {"soil": "Cleanliness / biosecurity declaration required before dispatch",
                             "source": "Assumption for the prototype (Antarctic Treaty biosecurity practice)", "verified": False},
    "air_nodes": ["Novo airfield (Maitri)", "Air leg to Bharati"],
    "routes": {"air": AIR, "ship": SHIP},
}
(OUT / "cargo_rules.json").write_text(json.dumps(rules, indent=2))
print("cargo_rules.json")

# ------------------------------------------------------------------ weather (Bharati 168 h, Maitri 72 h)
weather = []
def wx_series(station, hours, base_t, seed):
    r = random.Random(seed)
    t_drift, w_phase = 0.0, r.uniform(0, 6)
    for h in range(hours - 1, -1, -1):
        t_drift += r.uniform(-.25, .25); t_drift *= .97
        temp = base_t + 3.2 * math.sin(2 * math.pi * (h % 24) / 24 + 1.1) + t_drift + r.uniform(-.3, .3)
        wind = max(2, 17 + 8 * math.sin(2 * math.pi * h / 58 + w_phase) + r.uniform(-2.5, 2.5))
        gust = wind * r.uniform(1.15, 1.35)
        vis = min(20, max(.5, 9 - wind / 4.2 + r.uniform(-1.5, 1.5)))
        weather.append(dict(hours_ago=h, station=station, temp_c=round(temp, 1), wind_kt=round(wind, 1), gust_kt=round(gust, 1),
                            wind_dir=int(r.gauss(95, 12)) % 360, vis_km=round(vis, 1), pressure_hpa=round(985 + 2.5 * math.sin(h / 17) + r.uniform(-.4, .4), 1)))
wx_series("Bharati", 168, -26.5, 11)
wx_series("Maitri", 72, -22.0, 12)
for w in weather:      # the latest Bharati hour tells the dashboard story
    if w["station"] == "Bharati" and w["hours_ago"] == 0:
        w.update(temp_c=-28.4, wind_kt=24.0, gust_kt=30.0, wind_dir=95, vis_km=4.5, pressure_hpa=982.5)
write_csv("weather.csv", weather, list(weather[0].keys()))

# ------------------------------------------------------------------ cold-chain samples + sensor readings
samples = [
    dict(id="SMP-ICE-46-01", container_id="AST-CRYO-09", description="Deep ice-core section, borehole B1", limit_c=-15.0, mission_id="EXP-46-ISEA"),
    dict(id="SMP-ICE-46-02", container_id="AST-CRYO-04", description="Firn-air canister set", limit_c=-15.0, mission_id="EXP-46-ISEA"),
]
write_csv("samples.csv", samples, list(samples[0].keys()))
sensors = []
r = random.Random(5)
for m in range(24 * 60, -1, -10):                 # 24 h, one reading every 10 min
    h = m / 60
    if h > 6:
        t1, amb = -26.0 + r.uniform(-.18, .18), -19.5 + r.uniform(-.6, .6)
    else:
        t1, amb = -21.6 - 0.8 * h + r.uniform(-.1, .1), -12.0 + r.uniform(-.5, .5)
    if m == 200:
        t1 = -12.0                                # one sensor glitch to show outlier handling
    sensors.append(dict(sample_id="SMP-ICE-46-01", minutes_ago=m, temp_c=round(t1, 2), ambient_c=round(amb, 1)))
    sensors.append(dict(sample_id="SMP-ICE-46-02", minutes_ago=m, temp_c=round(-26.4 + r.uniform(-.15, .15), 2), ambient_c=-20.0))
write_csv("sensor_readings.csv", sensors, list(sensors[0].keys()))

# ------------------------------------------------------------------ routes
routes = [
    dict(id="R-VESSEL-A", name="Vessel approach A, direct to Bharati", kind="sea", waypoints=[[-60.0, 52.0], [-63.5, 62.0], [-66.6, 70.0], [-68.4, 74.2], [-68.9, 76.0]]),
    dict(id="R-VESSEL-B", name="Vessel approach B, northern detour", kind="sea", waypoints=[[-60.0, 52.0], [-62.0, 58.0], [-64.5, 65.0], [-66.0, 71.0], [-67.7, 74.6], [-68.9, 76.0]]),
    dict(id="R-TRAV-1", name="Traverse Bharati to Sandhi (surface)", kind="land", waypoints=[[-69.4083, 76.1867], [-71.0, 74.8], [-70.6, 69.6]]),
]
(OUT / "routes.json").write_text(json.dumps(routes, indent=2))
print("routes.json")
