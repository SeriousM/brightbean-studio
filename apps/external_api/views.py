"""External API views — v1.

All endpoints require the ``X-Api-Key: {API_TOKEN}`` header.

Endpoints
---------
GET  /external-api/v1/workspaces/
GET  /external-api/v1/workspaces/{workspace_id}/accounts/
POST /external-api/v1/posts/
GET  /external-api/v1/posts/{post_id}/
PATCH /external-api/v1/posts/{post_id}/
DELETE /external-api/v1/posts/{post_id}/
GET  /external-api/v1/posts/{post_id}/composer-url/
GET  /external-api/v1/posts/{post_id}/engagement/
"""

import json
import logging
from uuid import UUID

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.composer.models import PlatformPost, Post, PostMedia
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

from .auth import require_api_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_body(request) -> tuple[dict, JsonResponse | None]:
    """Parse JSON request body; return (data, None) or ({}, error_response)."""
    if not request.body:
        return {}, None
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError as exc:
        return {}, JsonResponse({"error": "Invalid JSON", "detail": str(exc)}, status=400)


def _post_status(post: Post) -> str:
    """Derive a simplified status string from a Post's platform_posts."""
    statuses = set(pp.status for pp in post.platform_posts.all())
    if not statuses:
        return "draft"
    if "failed" in statuses:
        return "failed"
    if "publishing" in statuses:
        return "publishing"
    if statuses == {"published"}:
        return "published"
    if "published" in statuses:
        return "partially_published"
    if "scheduled" in statuses:
        return "scheduled"
    return "draft"


def _composer_url(post: Post) -> str:
    app_url = (getattr(settings, "APP_URL", "") or "").rstrip("/")
    return f"{app_url}/workspace/{post.workspace_id}/compose/{post.pk}/"


def _post_to_dict(post: Post) -> dict:
    platform_posts = list(post.platform_posts.select_related("social_account").all())
    return {
        "id": str(post.pk),
        "workspace_id": str(post.workspace_id),
        "caption": post.caption,
        "status": _post_status(post),
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "composer_url": _composer_url(post),
        "accounts": [
            {
                "id": str(pp.social_account_id),
                "platform": pp.social_account.platform,
                "account_name": pp.social_account.account_name,
                "status": pp.status,
            }
            for pp in platform_posts
            if pp.social_account_id
        ],
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Discovery: workspaces
# ---------------------------------------------------------------------------

@require_api_key
@require_http_methods(["GET"])
def list_workspaces(request):
    """GET /external-api/v1/workspaces/ — list all workspaces."""
    workspaces = Workspace.objects.all().order_by("name")
    data = [{"id": str(w.pk), "name": w.name} for w in workspaces]
    return JsonResponse({"workspaces": data})


# ---------------------------------------------------------------------------
# Discovery: social accounts
# ---------------------------------------------------------------------------

@require_api_key
@require_http_methods(["GET"])
def list_accounts(request, workspace_id: UUID):
    """GET /external-api/v1/workspaces/{workspace_id}/accounts/"""
    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except Workspace.DoesNotExist:
        return JsonResponse({"error": "Workspace not found"}, status=404)

    accounts = (
        SocialAccount.objects.filter(workspace=workspace)
        .order_by("platform", "account_name")
    )
    data = [
        {
            "id": str(a.pk),
            "platform": a.platform,
            "account_name": a.account_name,
            "account_platform_id": a.account_platform_id,
            "status": a.connection_status,
        }
        for a in accounts
    ]
    return JsonResponse({"accounts": data})


# ---------------------------------------------------------------------------
# Posts — create
# ---------------------------------------------------------------------------

@csrf_exempt
@require_api_key
@require_http_methods(["POST"])
def create_post(request):
    """POST /external-api/v1/posts/

    Body:
        workspace_id   (str UUID, required)
        caption        (str, required)
        account_ids    (list[str UUID], required — SocialAccount PKs)
        scheduled_at   (ISO-8601 str, optional)
        media_url      (str, optional — URL of existing media; stored as external reference)
    """
    body, err = _json_body(request)
    if err:
        return err

    # Validate required fields
    workspace_id = body.get("workspace_id")
    caption = body.get("caption", "").strip()
    account_ids = body.get("account_ids", [])

    if not workspace_id:
        return JsonResponse({"error": "workspace_id is required"}, status=400)
    if not caption:
        return JsonResponse({"error": "caption is required"}, status=400)
    if not account_ids:
        return JsonResponse({"error": "account_ids must be a non-empty list"}, status=400)

    try:
        workspace = Workspace.objects.get(pk=workspace_id)
    except (Workspace.DoesNotExist, ValueError):
        return JsonResponse({"error": "Workspace not found"}, status=404)

    # Resolve social accounts
    accounts = SocialAccount.objects.filter(
        pk__in=account_ids,
        workspace=workspace,
    )
    if accounts.count() != len(account_ids):
        found_ids = set(str(a.pk) for a in accounts)
        missing = [aid for aid in account_ids if aid not in found_ids]
        return JsonResponse(
            {"error": "Some account_ids not found or not in this workspace", "missing": missing},
            status=404,
        )

    # Parse scheduled_at
    scheduled_at = None
    if body.get("scheduled_at"):
        try:
            from datetime import datetime
            scheduled_at = datetime.fromisoformat(body["scheduled_at"])
            if not scheduled_at.tzinfo:
                scheduled_at = timezone.make_aware(scheduled_at)
        except (ValueError, TypeError):
            return JsonResponse({"error": "scheduled_at must be ISO-8601 datetime"}, status=400)

    # Get a system user to use as author (the first superuser, or None)
    author = None
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        author = User.objects.filter(is_superuser=True).first()
    except Exception:
        pass

    # Create the Post
    post = Post.objects.create(
        workspace=workspace,
        author=author,
        caption=caption,
        scheduled_at=scheduled_at,
    )

    # Create PlatformPost for each account
    for account in accounts:
        PlatformPost.objects.create(
            post=post,
            social_account=account,
            status=PlatformPost.Status.SCHEDULED if scheduled_at else PlatformPost.Status.DRAFT,
            scheduled_at=scheduled_at,
        )

    # Handle optional media_url (store as a note in internal_notes for now;
    # full media attachment support requires uploading to BrightBean's media library)
    media_url = body.get("media_url", "").strip()
    if media_url:
        post.internal_notes = f"[external_api] media_url: {media_url}"
        post.save(update_fields=["internal_notes"])

    logger.info("external_api: created post %s in workspace %s", post.pk, workspace.pk)

    return JsonResponse(_post_to_dict(post), status=201)


# ---------------------------------------------------------------------------
# Posts — retrieve
# ---------------------------------------------------------------------------

@require_api_key
@require_http_methods(["GET"])
def get_post(request, post_id: UUID):
    """GET /external-api/v1/posts/{post_id}/"""
    try:
        post = Post.objects.prefetch_related(
            "platform_posts__social_account"
        ).get(pk=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found"}, status=404)

    return JsonResponse(_post_to_dict(post))


# ---------------------------------------------------------------------------
# Posts — update
# ---------------------------------------------------------------------------

@csrf_exempt
@require_api_key
@require_http_methods(["PATCH"])
def update_post(request, post_id: UUID):
    """PATCH /external-api/v1/posts/{post_id}/

    Body (all optional):
        caption       (str)
        scheduled_at  (ISO-8601 str or null to clear)
        media_url     (str)
    """
    try:
        post = Post.objects.prefetch_related(
            "platform_posts__social_account"
        ).get(pk=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found"}, status=404)

    body, err = _json_body(request)
    if err:
        return err

    update_fields = []

    if "caption" in body:
        post.caption = body["caption"]
        update_fields.append("caption")

    if "scheduled_at" in body:
        raw = body["scheduled_at"]
        if raw is None:
            post.scheduled_at = None
        else:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(raw)
                if not dt.tzinfo:
                    dt = timezone.make_aware(dt)
                post.scheduled_at = dt
            except (ValueError, TypeError):
                return JsonResponse({"error": "scheduled_at must be ISO-8601 or null"}, status=400)
        update_fields.append("scheduled_at")

        # Propagate scheduled_at to PlatformPosts that are still in draft/scheduled
        new_status = PlatformPost.Status.SCHEDULED if post.scheduled_at else PlatformPost.Status.DRAFT
        post.platform_posts.filter(
            status__in=[PlatformPost.Status.DRAFT, PlatformPost.Status.SCHEDULED]
        ).update(
            scheduled_at=post.scheduled_at,
            status=new_status,
        )

    if "media_url" in body:
        media_url = body["media_url"].strip() if body["media_url"] else ""
        notes = post.internal_notes or ""
        # Replace or add the media_url annotation
        import re
        notes = re.sub(r"\[external_api\] media_url: .*", "", notes).strip()
        if media_url:
            notes = (notes + f"\n[external_api] media_url: {media_url}").strip()
        post.internal_notes = notes
        update_fields.append("internal_notes")

    if update_fields:
        update_fields.append("updated_at")
        post.save(update_fields=update_fields)

    return JsonResponse(_post_to_dict(post))


# ---------------------------------------------------------------------------
# Posts — delete
# ---------------------------------------------------------------------------

@csrf_exempt
@require_api_key
@require_http_methods(["DELETE"])
def delete_post(request, post_id: UUID):
    """DELETE /external-api/v1/posts/{post_id}/"""
    try:
        post = Post.objects.get(pk=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found"}, status=404)

    post_pk_str = str(post.pk)
    workspace_id_str = str(post.workspace_id)
    post.delete()
    logger.info("external_api: deleted post %s", post_pk_str)
    return JsonResponse({"deleted": post_pk_str, "workspace_id": workspace_id_str})


# ---------------------------------------------------------------------------
# Posts — composer URL
# ---------------------------------------------------------------------------

@require_api_key
@require_http_methods(["GET"])
def get_composer_url(request, post_id: UUID):
    """GET /external-api/v1/posts/{post_id}/composer-url/"""
    try:
        post = Post.objects.only("pk", "workspace_id").get(pk=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found"}, status=404)

    return JsonResponse({"url": _composer_url(post)})


# ---------------------------------------------------------------------------
# Posts — engagement (stub; populated after publishing)
# ---------------------------------------------------------------------------

@require_api_key
@require_http_methods(["GET"])
def get_engagement(request, post_id: UUID):
    """GET /external-api/v1/posts/{post_id}/engagement/

    Returns per-account engagement stats synced from each platform after
    the post is published.  Returns empty/zero stats if the post has not
    been published yet or if the platform hasn't reported stats.
    """
    try:
        post = Post.objects.prefetch_related(
            "platform_posts__social_account"
        ).get(pk=post_id)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found"}, status=404)

    engagement = []
    for pp in post.platform_posts.all():
        # ``platform_extra`` is a JSONField that BrightBean's publisher
        # populates with native platform metrics after publishing.
        stats = pp.platform_extra.get("engagement", {}) if pp.platform_extra else {}
        engagement.append(
            {
                "account_id": str(pp.social_account_id),
                "platform": pp.social_account.platform if pp.social_account_id else None,
                "reactions": stats.get("reactions", 0),
                "shares": stats.get("shares", 0),
                "comments": stats.get("comments", 0),
                "impressions": stats.get("impressions", 0),
                "status": pp.status,
            }
        )

    return JsonResponse(
        {
            "post_id": str(post.pk),
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "engagement": engagement,
        }
    )
