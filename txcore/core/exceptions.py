import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            "error": {
                "status_code": response.status_code,
                "detail": response.data,
            }
        }
        return response

    logger.exception("Unhandled exception in view %s", context.get("view"))
    return Response(
        {"error": {"status_code": 500, "detail": "Internal server error"}},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
