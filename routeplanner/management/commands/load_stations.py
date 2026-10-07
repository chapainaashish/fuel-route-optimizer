import pandas as pd
from django.core.management.base import BaseCommand

from routeplanner.models import FuelStation


class Command(BaseCommand):
    help = "Load fuel stations (with lat/lon) from the prepared CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "path", nargs="?", default="data/fuel_prices_with_coords.csv"
        )

    def handle(self, *args, **opts):
        df = pd.read_csv(opts["path"])
        df.columns = [c.strip() for c in df.columns]
        for col in ["Truckstop Name", "Address", "City", "State"]:
            df[col] = df[col].astype(str).str.strip()
        df["State"] = df["State"].str.upper()

        rows_in = len(df)
        df = df.dropna(subset=["lat", "lon", "Retail Price"])

        # one row per station: keep the lowest price
        df = df.sort_values("Retail Price").drop_duplicates(
            "OPIS Truckstop ID", keep="first"
        )

        stations = [
            FuelStation(
                opis_id=int(r["OPIS Truckstop ID"]),
                name=r["Truckstop Name"],
                address=r["Address"],
                city=r["City"],
                state=r["State"],
                price=float(r["Retail Price"]),
                lat=float(r["lat"]),
                lon=float(r["lon"]),
            )
            for r in df.to_dict("records")
        ]

        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(stations, batch_size=1000)
        self.stdout.write(
            self.style.SUCCESS(
                f"{rows_in} CSV rows -> {len(stations)} unique stations loaded"
            )
        )
