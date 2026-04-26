"""Signal handlers for the external API.

Hooks into ``PlatformPost`` state changes to fire outbound webhook events.

Events fired:
    post.scheduled  — when any PlatformPost transitions to ``scheduled``
    post.published  — when the parent Post becomes fully/partially published
                      (i.e., all platform_posts are published)
    post.failed     — when any PlatformPost transitions to ``failed``

Only fires when ``BRIGHTBEAN_WEBHOOK_URL`` is configured in settings.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.composer.models import PlatformPost

from .webhooks import fire_post_event

logger = logging.getLogger(__name__)

# Track previous status so we only fire on transitions, not on every save.
# This is a process-local cache; it works for the common case where the
# saving process is the web server or worker.  If you have multiple
# processes, events may fire more than once per transition — acceptable.


@receiver(post_save, sender=PlatformPost)
def _platform_post_saved(sender, instance: PlatformPost, created: bool, **kwargs):
    """Fire a webhook when a PlatformPost's status becomes an event-worthy value."""
    if not hasattr(instance, "_pre_save_status"):
        # No previous status captured (e.g., object loaded without pre_save hook).
        # We can still react to known terminal statuses.
        _handle_status_change(instance, previous_status=None)
        return

    previous = instance._pre_save_status
    if previous != instance.status:
        _handle_status_change(instance, previous_status=previous)


@receiver(post_save, sender=PlatformPost)
def _capture_pre_save_status(sender, instance: PlatformPost, **kwargs):
    """Capture the status before saving for transition detection.

    Django signals fire after save, so we attach the old value via a
    pre_save signal.  This receiver runs after the save; we use pre_save
    below to actually capture the old value.
    """


# Use pre_save to record the old status before the write.
from django.db.models.signals import pre_save  # noqa: E402


@receiver(pre_save, sender=PlatformPost)
def _capture_old_status(sender, instance: PlatformPost, **kwargs):
    if instance.pk:
        try:
            old = PlatformPost.objects.get(pk=instance.pk)
            instance._pre_save_status = old.status
        except PlatformPost.DoesNotExist:
            instance._pre_save_status = None
    else:
        instance._pre_save_status = None


def _handle_status_change(platform_post: PlatformPost, previous_status: str | None):
    """Inspect the new status and fire the appropriate webhook event."""
    status = platform_post.status
    post = platform_post.post

    if status == PlatformPost.Status.SCHEDULED:
        fire_post_event(
            "post.scheduled",
            post,
            scheduled_at=platform_post.scheduled_at,
            platform=platform_post.social_account.platform
            if platform_post.social_account_id
            else None,
        )

    elif status == PlatformPost.Status.PUBLISHED:
        # Check if all platform_posts for this Post are now published.
        all_statuses = list(
            post.platform_posts.values_list("status", flat=True)
        )
        event = "post.published" if all(s == "published" for s in all_statuses) else "post.partially_published"
        fire_post_event(
            event,
            post,
            published_at=platform_post.published_at,
            platform=platform_post.social_account.platform
            if platform_post.social_account_id
            else None,
            all_published=event == "post.published",
        )

    elif status == PlatformPost.Status.FAILED:
        fire_post_event(
            "post.failed",
            post,
            platform=platform_post.social_account.platform
            if platform_post.social_account_id
            else None,
            error_message=getattr(platform_post, "publish_error", ""),
        )
