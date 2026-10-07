from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from routeplanner.exceptions import NoFeasiblePlan
from routeplanner.services.optimizer import plan_fuel_stops

from .serializers import RouteRequestSerializer
from .services.routing import (
    GeocodingError,
    RoutingError,
    geocode_location,
    get_route,
)
from .services.stations import DEFAULT_RADIUS_MILES, stations_near_route


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

        nearby = stations_near_route(
            route["geometry"],
            route_distance_miles=route["distance_miles"],
            radius_miles=DEFAULT_RADIUS_MILES,
        )

        stations_payload = [
            {
                "opis_id": n["station"].opis_id,
                "name": n["station"].name,
                "address": n["station"].address,
                "city": n["station"].city,
                "state": n["station"].state,
                "price": float(n["station"].price),
                "lat": n["station"].lat,
                "lon": n["station"].lon,
                "mile_marker": round(n["mile_marker"], 2),
                "distance_to_route_miles": round(n["distance_to_route_miles"], 2),
            }
            for n in nearby
        ]

        try:
            fuel_plan = plan_fuel_stops(nearby, route["distance_miles"])
        except NoFeasiblePlan as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

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
                "geometry": route["geometry"],
                "fuel_plan": fuel_plan,
                "total_fuel_cost": fuel_plan["total_fuel_cost"],
                "stations_near_route_count": len(stations_payload),
                "stations_near_route": stations_payload,
            }
        )
