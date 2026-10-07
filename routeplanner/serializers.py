import re
import unicodedata

from rest_framework import serializers

# Contiguous USA bounding box (lower 48)
LAT_MIN, LAT_MAX = 24.4, 49.6
LON_MIN, LON_MAX = -125.0, -66.9

LATLON = re.compile(r"^(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)$")


class LocationField(serializers.Field):
    """
    Accepts:
      - 'City, ST'
      - an address
      - 'lat,lon'

    Returns a normalized dictionary.
    """

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("Must be a string.")

        # Reject control/invisible characters
        if any(
            unicodedata.category(ch).startswith("C") and ch not in "\t\n\r "
            for ch in data
        ):
            raise serializers.ValidationError("Contains invalid control characters.")

        # Normalize whitespace
        text = " ".join(data.split())
        if len(text) < 2:
            raise serializers.ValidationError("Too short.")
        if len(text) > 120:
            raise serializers.ValidationError("Too long (max 120 characters).")

        # Check whether input is latitude,longitude
        match = LATLON.match(text)

        if match:
            lat = float(match.group(1))
            lon = float(match.group(2))

            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                raise serializers.ValidationError(
                    "Coordinates must be within the contiguous USA "
                    "(format: 'lat,lon', for example '32.79,-96.77')."
                )

            return {
                "query": text,
                "kind": "coords",
                "lat": lat,
                "lon": lon,
            }

        # Otherwise treat it as an address/place query.
        if not any(ch.isalpha() for ch in text):
            raise serializers.ValidationError("Must contain a place name or address.")

        return {
            "query": text,
            "kind": "address",
        }


class RouteRequestSerializer(serializers.Serializer):
    start = LocationField()
    finish = LocationField()

    def to_internal_value(self, data):
        # Reject unknown fields instead of silently ignoring them.
        if isinstance(data, dict):
            extra = set(data) - set(self.fields)
            if extra:
                raise serializers.ValidationError(
                    {key: "Unknown field." for key in sorted(extra)}
                )

        return super().to_internal_value(data)

    def validate(self, attrs):
        start = attrs["start"]
        finish = attrs["finish"]

        if start["query"].casefold() == finish["query"].casefold():
            raise serializers.ValidationError("Start and finish must be different.")

        return attrs
