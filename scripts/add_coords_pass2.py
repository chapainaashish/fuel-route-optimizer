import re

import pandas as pd

IN_FILE = "fuel_prices_with_coords.csv"
OUT_FILE = "fuel_prices_with_coords.csv"
GEONAMES = "US.txt"

US_STATES = set(
    """AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO
MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY""".split()
)


def norm_city(s) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"^st\.?\s", "saint ", s)
    s = re.sub(r"^ste\.?\s", "sainte ", s)
    s = re.sub(r"^ft\.?\s", "fort ", s)
    s = re.sub(r"^mt\.?\s", "mount ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


fuel = pd.read_csv(IN_FILE)

# 1) keep US only
before = fuel["OPIS Truckstop ID"].nunique()
fuel = fuel[fuel["State"].str.upper().isin(US_STATES)].copy()
print(f"Dropped non-US stations: {before - fuel['OPIS Truckstop ID'].nunique()}")

# 2) GeoNames lookup (populated places only: feature class 'P')
geo = pd.read_csv(
    GEONAMES,
    sep="\t",
    header=None,
    quoting=3,
    low_memory=False,
    usecols=[2, 4, 5, 6, 10, 14],
    names=["name", "glat", "glon", "fclass", "state_id", "population"],
)
geo = geo[geo["fclass"] == "P"]
geo["key"] = geo["name"].map(norm_city)
geo = geo.sort_values("population", ascending=False).drop_duplicates(
    ["key", "state_id"]
)[["key", "state_id", "glat", "glon"]]

# 3) fill only the rows still missing coordinates
fuel["key"] = fuel["City"].str.strip().map(norm_city)
fuel["state_id"] = fuel["State"].str.upper()
fuel = fuel.merge(geo, on=["key", "state_id"], how="left")
fuel["lat"] = fuel["lat"].fillna(fuel["glat"])
fuel["lon"] = fuel["lon"].fillna(fuel["glon"])

# 4) report
unique = fuel.drop_duplicates("OPIS Truckstop ID")
matched = unique["lat"].notna().sum()
print(f"US stations: {len(unique)}  matched: {matched} ({matched / len(unique):.1%})")

left = (
    unique[unique["lat"].isna()][["City", "State"]]
    .drop_duplicates()
    .sort_values(["State", "City"])
)
left.to_csv("unmatched_cities.csv", index=False)
print(f"Still unmatched cities: {len(left)}")
print(left.head(40).to_string(index=False))

fuel.drop(columns=["key", "state_id", "glat", "glon"]).to_csv(OUT_FILE, index=False)
print(f"Saved {OUT_FILE}")
