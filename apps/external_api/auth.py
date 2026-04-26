"""Authentication decorator for the external API.

All views in the external API are protected by an API key passed in the
``X-Api-Key`` HTTP header.  The key is compared against ``settings.API_TOKEN``
which is populated from the ``API_TOKEN`` environment variable.

If ``API_TOKEN`` is empty or unset the API is disabled (every request gets
401).  This is a deliberate safety default so an accidentally exposed instance
cannot be queried without explicit opt-in.
"""

import functools
import logging

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def require_api_key(view_func):
    """Decorator: reject requests that don't carry the correct API key."""

    @functools.wraps(view_func)
    def _wrapper(request, *args, **kwargs):
        expected = getattr(settings, "API_TOKEN", "") or ""
        if not expected:
            logger.warning(
                "external_api: request rejected — API_TOKEN is not configured"
            )
            return JsonResponse(
                {"error": "API not available", "detail": "API_TOKEN is not configured on this server."},
                status=503,
            )

        provided = request.META.get("HTTP_X_API_KEY", "")
        if not provided or provided != expected:
            return JsonResponse({"error": "Unauthorized"}, status=401)

        return view_func(request, *args, **kwargs)

    return _wrapper
