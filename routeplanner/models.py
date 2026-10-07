from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models


class FuelStation(models.Model):
    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200, blank=False)
    address = models.CharField(max_length=255, blank=False)
    city = models.CharField(max_length=100, blank=False)
    state = models.CharField(
        max_length=2,
        blank=False,
        validators=[
            RegexValidator(
                regex=r"^[A-Z]{2}$",
                message="State must be a 2-letter US state code.",
            )
        ],
    )
    price = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        validators=[
            MinValueValidator(0),
        ],
    )
    lat = models.FloatField(
        db_index=True,
        validators=[
            MinValueValidator(-90),
            MaxValueValidator(90),
        ],
    )
    lon = models.FloatField(
        db_index=True,
        validators=[
            MinValueValidator(-180),
            MaxValueValidator(180),
        ],
    )

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price:.3f}"
