"""Outbound webhook delivery for the external API.

When a BrightBean post changes state (scheduled / published / failed),
a webhook event is sent to the URL configured in ``BRIGHTBEAN_WEBHOOK_URL``.

Delivery is dispatched as a background task (django-background-tasks) so
the publishing signal chain is not blocked and retries are handled by the
worker process.

Payload format
--------------
All events share this envelope:

    {
        "event":      "post.published",
        "post_id":    "550e8400-e29b-41d4-a716-446655440000",
        "workspace_id": "...",
        <event-specific fields>
    }

Authentication
--------------
When ``BRIGHTBEAN_WEBHOOK_SECRET`` is set the request carries an
``X-BB-Signature`` header containing ``HMAC-SHA256(secret, raw_body)``
as a hex string.  The receiver can verify authenticity by computing the
same HMAC over the raw request body.
"""

import hashlib
import hmac
import json
import logging

import httpx
from background_task import background
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_webhook_url() -> str:
    return getattr(settings, "BRIGHTBEAN_WEBHOOK_URL", "") or ""


def _get_webhook_secret() -> str:
    return getattr(settings, "BRIGHTBEAN_WEBHOOK_SECRET", "") or ""


def _sign_payload(body: bytes) -> str | None:
    secret = _get_webhook_secret()
    if not secret:
        return None
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@background(schedule=0)
def deliver_webhook(payload: dict) -> None:
    """Background task: HTTP POST the payload to the configured webhook URL.

    This is called by the signal handlers.  Django-background-tasks will
    retry on failure according to its default retry policy.
    """
    url = _get_webhook_url()
    if not url:
        return  # webhooks disabled

    body = json.dumps(payload, default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "BrightBeanStudio/1.0 Webhook",
    }
    sig = _sign_payload(body)
    if sig:
        headers["X-BB-Signature"] = sig

    try:
        response = httpx.post(url, content=body, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(
            "external_api webhook delivered: event=%s status=%s",
            payload.get("event"),
            response.status_code,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "external_api webhook delivery failed: event=%s status=%s body=%s",
            payload.get("event"),
            exc.response.status_code,
            exc.response.text[:200],
        )
        raise  # re-raise so background-tasks records the failure and retries
    except Exception as exc:
        logger.error(
            "external_api webhook delivery error: event=%s error=%s",
            payload.get("event"),
            exc,
        )
        raise


def fire_post_event(event: str, post, **extra) -> None:
    """Enqueue a webhook delivery for a post state-change event.

    ``extra`` allows callers to attach event-specific fields such as
    ``scheduled_at``, ``published_at``, or ``error_message``.
    """
    if not _get_webhook_url():
        return  # fast-path: nothing configured

    payload = {
        "event": event,
        "post_id": str(post.pk),
        "workspace_id": str(post.workspace_id),
        **extra,
    }
    deliver_webhook(payload)
