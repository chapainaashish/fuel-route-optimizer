import re

import pandas as pd

FUEL_IN = "fuel-prices-for-be-assessment.csv"
CITIES = "uscities.csv"
FUEL_OUT = "fuel_prices_with_coords.csv"
UNMATCHED_OUT = "unmatched_cities.csv"


def norm_city(s) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"^st\.?\s", "saint ", s)
    s = re.sub(r"^ste\.?\s", "sainte ", s)
    s = re.sub(r"^ft\.?\s", "fort ", s)
    s = re.sub(r"^mt\.?\s", "mount ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- cities lookup ----------
cities = pd.read_csv(
    CITIES, usecols=["city_ascii", "state_id", "lat", "lng", "population"]
)
cities["key"] = cities["city_ascii"].map(norm_city)
cities["key2"] = cities["key"].str.replace(
    " ", "", regex=False
)  # fallback: ignore spaces
cities = cities.sort_values(
    "population", ascending=False
)  # biggest city wins on duplicates

by_key = cities.drop_duplicates(["key", "state_id"])[["key", "state_id", "lat", "lng"]]
by_key2 = cities.drop_duplicates(["key2", "state_id"])[
    ["key2", "state_id", "lat", "lng"]
].rename(columns={"lat": "lat2", "lng": "lng2"})

# fuel stations
fuel = pd.read_csv(FUEL_IN)
fuel.columns = [c.strip() for c in fuel.columns]
for col in ["Truckstop Name", "Address", "City", "State"]:
    fuel[col] = fuel[col].astype(str).str.strip()

fuel["state_id"] = fuel["State"].str.upper()
fuel["key"] = fuel["City"].map(norm_city)
fuel["key2"] = fuel["key"].str.replace(" ", "", regex=False)

# join (pass 1: exact, pass 2: ignore spaces)
fuel = fuel.merge(by_key, on=["key", "state_id"], how="left")
fuel = fuel.merge(by_key2, on=["key2", "state_id"], how="left")

fuel["lat"] = fuel["lat"].fillna(fuel["lat2"])
fuel["lon"] = fuel["lng"].fillna(fuel["lng2"])

# report
unique = fuel.drop_duplicates("OPIS Truckstop ID")
matched = unique["lat"].notna().sum()
print(f"Rows in CSV:        {len(fuel)}")
print(f"Unique stations:    {len(unique)}")
print(f"Stations matched:   {matched} ({matched / len(unique):.1%})")

unmatched = (
    unique[unique["lat"].isna()][["City", "State"]]
    .drop_duplicates()
    .sort_values(["State", "City"])
)
unmatched.to_csv(UNMATCHED_OUT, index=False)
print(f"Unmatched cities:   {len(unmatched)} (saved to {UNMATCHED_OUT})")
print(unmatched.head(30).to_string(index=False))

# save
fuel = fuel.drop(columns=["key", "key2", "state_id", "lng", "lat2", "lng2"])
fuel.to_csv(FUEL_OUT, index=False)
print(f"\nSaved {FUEL_OUT}")
