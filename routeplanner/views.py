from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation
from .serializers import RouteRequestSerializer


class RouteView(APIView):
    def post(self, request):
        ser = RouteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        start, finish = ser.validated_data["start"], ser.validated_data["finish"]

        # TODO: geocode -> route -> stations near route -> optimizer
        return Response(
            {
                "start": start,
                "finish": finish,
                "stations_in_db": FuelStation.objects.count(),
                "status": "skeleton: geocoding, routing and optimizer not wired yet",
            }
        )
