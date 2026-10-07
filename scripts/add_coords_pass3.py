import pandas as pd

FILE = "fuel_prices_with_coords.csv"

# (city, state) -> (lat, lon)
OVERRIDES = {
    ("Hot Springs National Park", "AR"): (34.50, -93.05),
    ("Willow Beach", "AZ"): (35.87, -114.66),
    ("East Lyme", "CT"): (41.32, -72.22),
    ("Willington", "CT"): (41.88, -72.26),
    ("Mc Alpin", "FL"): (30.07, -82.97),
    ("Dundee", "IL"): (42.10, -88.29),
    ("Baileyville", "ME"): (45.14, -67.35),
    ("Corinth", "ME"): (44.97, -69.01),
    ("Dover Foxcroft", "ME"): (45.18, -69.22),
    ("Sault Sainte Marie", "MI"): (46.50, -84.35),
    ("Bois D Arc", "MO"): (37.32, -93.43),
    ("Pueblo Of Acoma", "NM"): (35.04, -107.58),
    ("La Fayette", "NY"): (42.94, -76.11),
    ("S Coffeyville", "OK"): (36.96, -95.60),
    ("Crescent", "PA"): (40.55, -80.19),
    ("Feasterville Trevose", "PA"): (40.14, -74.99),
    ("Alburgh", "VT"): (44.98, -73.30),
    ("Derby", "VT"): (44.95, -72.13),
}

fuel = pd.read_csv(FILE)
fuel["City"] = fuel["City"].astype(str).str.strip()
fuel["State"] = fuel["State"].astype(str).str.strip().str.upper()

for (city, state), (lat, lon) in OVERRIDES.items():
    mask = (fuel["City"] == city) & (fuel["State"] == state) & fuel["lat"].isna()
    fuel.loc[mask, ["lat", "lon"]] = [lat, lon]

unique = fuel.drop_duplicates("OPIS Truckstop ID")
print(f"Stations with coords: {unique['lat'].notna().sum()} / {len(unique)}")
fuel.to_csv(FILE, index=False)
print("Saved", FILE)
