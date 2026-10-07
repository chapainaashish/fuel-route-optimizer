import logging

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class LocationNotFound(APIException):
    status_code = 400
    default_detail = "Location could not be found."
    default_code = "location_not_found"


class GeocodingError(Exception):
    pass


class RoutingError(Exception):
    pass


class NoFeasiblePlan(Exception):
    pass


class NoStationInRange(APIException):
    status_code = 422
    default_detail = "No fuel station within range along this route."
    default_code = "no_station_in_range"


class UpstreamServiceError(APIException):
    status_code = 502
    default_detail = "Routing service is unavailable. Try again shortly."
    default_code = "upstream_error"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled error", exc_info=exc)
        return Response(
            {"error": "internal_error", "detail": "Something went wrong."}, status=500
        )
    return response
