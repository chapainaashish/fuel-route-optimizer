from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation
from .serializers import (
    RouteRequestSerializer,
)
from .services.routing import (
    GeocodingError,
    RoutingError,
    geocode_location,
    get_route,
)


class RouteView(APIView):
    def post(self, request):
        ser = RouteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        start_in = ser.validated_data["start"]
        finish_in = ser.validated_data["finish"]

        try:
            start = geocode_location(start_in)
            finish = geocode_location(finish_in)
        except GeocodingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            route = get_route(start, finish)
        except RoutingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        # TODO: stations near route -> mile markers -> optimizer
        return Response(
            {
                "start": {"query": start_in["query"], "lat": start[0], "lon": start[1]},
                "finish": {
                    "query": finish_in["query"],
                    "lat": finish[0],
                    "lon": finish[1],
                },
                "distance_miles": round(route["distance_miles"], 2),
                "duration_seconds": round(route["duration_seconds"]),
                "geometry_points": len(route["geometry"]),
                "geometry": route["geometry"],  # [(lat, lon), ...]
                "stations_in_db": FuelStation.objects.count(),
                "status": "routing wired; fuel optimizer not wired yet",
            }
        )
