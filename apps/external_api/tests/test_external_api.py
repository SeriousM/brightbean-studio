"""Tests for apps.external_api.

Coverage:
    auth.py        — API key check decorator
    views.py       — all 8 endpoints (happy path + error cases)
    webhooks.py    — payload signing, fire_post_event guard
    signals.py     — status-transition detection
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.composer.models import PlatformPost, Post
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace

API_TOKEN = "test-api-token-abc123"
HEADERS = {"HTTP_X_API_KEY": API_TOKEN}


# ---------------------------------------------------------------------------
# Autouse fixture: patch settings defaults for all tests in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def default_settings(settings):
    """Apply API settings defaults for every test in this file."""
    settings.API_TOKEN = API_TOKEN
    settings.APP_URL = "https://bb.example.com"
    settings.BRIGHTBEAN_WEBHOOK_URL = ""
    settings.BRIGHTBEAN_WEBHOOK_SECRET = ""


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org")


@pytest.fixture
def workspace(db, org):
    return Workspace.objects.create(name="MindMag WS", organization=org)


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        email="su@example.com", password="pass", name="Super"
    )


@pytest.fixture
def account_linkedin(db, workspace):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="linkedin_personal",
        account_platform_id="li-personal-001",
        account_name="Bernhard Millauer",
        connection_status="connected",
    )


@pytest.fixture
def account_instagram(db, workspace):
    return SocialAccount.objects.create(
        workspace=workspace,
        platform="instagram",
        account_platform_id="ig-001",
        account_name="MindMag Official",
        connection_status="connected",
    )


@pytest.fixture
def post_draft(db, workspace, superuser, account_linkedin):
    post = Post.objects.create(
        workspace=workspace,
        author=superuser,
        caption="Test post caption",
    )
    PlatformPost.objects.create(
        post=post,
        social_account=account_linkedin,
        status=PlatformPost.Status.DRAFT,
    )
    return post


# ---------------------------------------------------------------------------
# Auth decorator tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRequireApiKey:
    def test_valid_key_passes(self, client):
        response = client.get("/external-api/v1/workspaces/", **HEADERS)
        assert response.status_code == 200

    def test_missing_key_returns_401(self, client):
        response = client.get("/external-api/v1/workspaces/")
        assert response.status_code == 401
        assert response.json()["error"] == "Unauthorized"

    def test_wrong_key_returns_401(self, client):
        response = client.get(
            "/external-api/v1/workspaces/", HTTP_X_API_KEY="wrong-token"
        )
        assert response.status_code == 401

    def test_unconfigured_token_returns_503(self, client, settings):
        settings.API_TOKEN = ""
        response = client.get("/external-api/v1/workspaces/", **HEADERS)
        assert response.status_code == 503
        assert "API_TOKEN" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /external-api/v1/workspaces/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestListWorkspaces:
    def test_returns_workspace_list(self, client, workspace):
        response = client.get("/external-api/v1/workspaces/", **HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        ids = [w["id"] for w in data["workspaces"]]
        assert str(workspace.pk) in ids

    def test_workspace_shape(self, client, workspace):
        response = client.get("/external-api/v1/workspaces/", **HEADERS)
        ws = next(
            w for w in response.json()["workspaces"] if w["id"] == str(workspace.pk)
        )
        assert ws["name"] == workspace.name


# ---------------------------------------------------------------------------
# GET /external-api/v1/workspaces/{id}/accounts/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestListAccounts:
    def test_returns_accounts(self, client, workspace, account_linkedin, account_instagram):
        url = f"/external-api/v1/workspaces/{workspace.pk}/accounts/"
        response = client.get(url, **HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "accounts" in data
        platforms = {a["platform"] for a in data["accounts"]}
        assert "linkedin_personal" in platforms
        assert "instagram" in platforms

    def test_account_shape(self, client, workspace, account_linkedin):
        url = f"/external-api/v1/workspaces/{workspace.pk}/accounts/"
        response = client.get(url, **HEADERS)
        acc = next(
            a for a in response.json()["accounts"] if a["id"] == str(account_linkedin.pk)
        )
        assert acc["platform"] == "linkedin_personal"
        assert acc["account_name"] == "Bernhard Millauer"
        assert acc["status"] == "connected"

    def test_invalid_workspace_returns_404(self, client):
        url = "/external-api/v1/workspaces/00000000-0000-0000-0000-000000000000/accounts/"
        response = client.get(url, **HEADERS)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /external-api/v1/posts/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreatePost:
    def _payload(self, workspace, *accounts, **extra):
        data = {
            "workspace_id": str(workspace.pk),
            "caption": "New post about mindfulness",
            "account_ids": [str(a.pk) for a in accounts],
        }
        data.update(extra)
        return data

    def test_creates_post_returns_201(self, client, workspace, superuser, account_linkedin):
        response = client.post(
            "/external-api/v1/posts/",
            data=json.dumps(self._payload(workspace, account_linkedin)),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["caption"] == "New post about mindfulness"
        assert data["status"] == "draft"
        assert "composer_url" in data
        assert "bb.example.com" in data["composer_url"]

    def test_creates_platform_post(self, client, workspace, superuser, account_linkedin):
        response = client.post(
            "/external-api/v1/posts/",
            data=json.dumps(self._payload(workspace, account_linkedin)),
            content_type="application/json",
            **HEADERS,
        )
        post_id = response.json()["id"]
        post = Post.objects.get(pk=post_id)
        assert post.platform_posts.count() == 1
        pp = post.platform_posts.first()
        assert pp.social_account_id == account_linkedin.pk

    def test_scheduled_at_propagated(self, client, workspace, superuser, account_linkedin):
        payload = self._payload(
            workspace, account_linkedin, scheduled_at="2025-12-01T10:00:00Z"
        )
        response = client.post(
            "/external-api/v1/posts/",
            data=json.dumps(payload),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scheduled_at"] is not None
        assert data["status"] == "scheduled"

    def test_multiple_accounts(
        self, client, workspace, superuser, account_linkedin, account_instagram
    ):
        response = client.post(
            "/external-api/v1/posts/",
            data=json.dumps(self._payload(workspace, account_linkedin, account_instagram)),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 201
        post_id = response.json()["id"]
        assert Post.objects.get(pk=post_id).platform_posts.count() == 2

    def test_missing_caption_returns_400(self, client, workspace, account_linkedin):
        payload = {
            "workspace_id": str(workspace.pk),
            "account_ids": [str(account_linkedin.pk)],
        }
        response = client.post(
            "/external-api/v1/posts/",
            data=json.dumps(payload),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 400

    def test_invalid_workspace_returns_404(self, client, account_linkedin):
        payload = {
            "workspace_id": "00000000-0000-0000-0000-000000000000",
            "caption": "test",
            "account_ids": [str(account_linkedin.pk)],
        }
        response = client.post(
            "/external-api/v1/posts/",
            data=json.dumps(payload),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 404

    def test_invalid_account_id_returns_404(self, client, workspace):
        payload = {
            "workspace_id": str(workspace.pk),
            "caption": "test",
            "account_ids": ["00000000-0000-0000-0000-000000000000"],
        }
        response = client.post(
            "/external-api/v1/posts/",
            data=json.dumps(payload),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /external-api/v1/posts/{id}/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetPost:
    def test_returns_post(self, client, post_draft):
        response = client.get(f"/external-api/v1/posts/{post_draft.pk}/", **HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(post_draft.pk)
        assert data["caption"] == "Test post caption"
        assert len(data["accounts"]) == 1

    def test_missing_post_returns_404(self, client):
        response = client.get(
            "/external-api/v1/posts/00000000-0000-0000-0000-000000000000/", **HEADERS
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /external-api/v1/posts/{id}/update/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUpdatePost:
    def test_update_caption(self, client, post_draft):
        response = client.patch(
            f"/external-api/v1/posts/{post_draft.pk}/update/",
            data=json.dumps({"caption": "Updated caption"}),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["caption"] == "Updated caption"
        post_draft.refresh_from_db()
        assert post_draft.caption == "Updated caption"

    def test_update_scheduled_at(self, client, post_draft):
        response = client.patch(
            f"/external-api/v1/posts/{post_draft.pk}/update/",
            data=json.dumps({"scheduled_at": "2025-12-15T09:30:00Z"}),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scheduled_at"] is not None
        assert data["status"] == "scheduled"

    def test_clear_scheduled_at(self, client, workspace, superuser, account_linkedin):
        post = Post.objects.create(
            workspace=workspace,
            author=superuser,
            caption="To be rescheduled",
            scheduled_at=timezone.now(),
        )
        PlatformPost.objects.create(
            post=post,
            social_account=account_linkedin,
            status=PlatformPost.Status.SCHEDULED,
            scheduled_at=post.scheduled_at,
        )
        response = client.patch(
            f"/external-api/v1/posts/{post.pk}/update/",
            data=json.dumps({"scheduled_at": None}),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["scheduled_at"] is None

    def test_missing_post_returns_404(self, client):
        response = client.patch(
            "/external-api/v1/posts/00000000-0000-0000-0000-000000000000/update/",
            data=json.dumps({"caption": "x"}),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 404

    def test_invalid_scheduled_at_returns_400(self, client, post_draft):
        response = client.patch(
            f"/external-api/v1/posts/{post_draft.pk}/update/",
            data=json.dumps({"scheduled_at": "not-a-date"}),
            content_type="application/json",
            **HEADERS,
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /external-api/v1/posts/{id}/delete/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeletePost:
    def test_deletes_post_returns_200(self, client, post_draft):
        post_pk = str(post_draft.pk)
        response = client.delete(
            f"/external-api/v1/posts/{post_pk}/delete/", **HEADERS
        )
        assert response.status_code == 200
        assert response.json()["deleted"] == post_pk
        assert not Post.objects.filter(pk=post_pk).exists()

    def test_missing_post_returns_404(self, client):
        response = client.delete(
            "/external-api/v1/posts/00000000-0000-0000-0000-000000000000/delete/",
            **HEADERS,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /external-api/v1/posts/{id}/composer-url/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestComposerUrl:
    def test_returns_correct_url(self, client, post_draft):
        response = client.get(
            f"/external-api/v1/posts/{post_draft.pk}/composer-url/", **HEADERS
        )
        assert response.status_code == 200
        url = response.json()["url"]
        assert "bb.example.com" in url
        assert str(post_draft.workspace_id) in url
        assert str(post_draft.pk) in url

    def test_missing_post_returns_404(self, client):
        response = client.get(
            "/external-api/v1/posts/00000000-0000-0000-0000-000000000000/composer-url/",
            **HEADERS,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /external-api/v1/posts/{id}/engagement/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEngagement:
    def test_returns_zero_stats_for_draft(self, client, post_draft):
        response = client.get(
            f"/external-api/v1/posts/{post_draft.pk}/engagement/", **HEADERS
        )
        assert response.status_code == 200
        data = response.json()
        assert "engagement" in data
        assert len(data["engagement"]) == 1
        stat = data["engagement"][0]
        assert stat["reactions"] == 0
        assert stat["shares"] == 0
        assert stat["comments"] == 0

    def test_returns_stored_stats(self, client, workspace, superuser, account_linkedin):
        post = Post.objects.create(
            workspace=workspace,
            author=superuser,
            caption="Published post",
            published_at=timezone.now(),
        )
        PlatformPost.objects.create(
            post=post,
            social_account=account_linkedin,
            status=PlatformPost.Status.PUBLISHED,
            platform_extra={"engagement": {"reactions": 42, "shares": 7, "comments": 3}},
        )
        response = client.get(
            f"/external-api/v1/posts/{post.pk}/engagement/", **HEADERS
        )
        assert response.status_code == 200
        stat = response.json()["engagement"][0]
        assert stat["reactions"] == 42
        assert stat["shares"] == 7
        assert stat["comments"] == 3

    def test_missing_post_returns_404(self, client):
        response = client.get(
            "/external-api/v1/posts/00000000-0000-0000-0000-000000000000/engagement/",
            **HEADERS,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Webhook signing
# ---------------------------------------------------------------------------


class TestWebhookSigning:
    def test_signature_is_valid_hmac(self, settings):
        settings.BRIGHTBEAN_WEBHOOK_SECRET = "mysecret"
        from apps.external_api.webhooks import _sign_payload

        body = b'{"event": "post.published"}'
        sig = _sign_payload(body)
        expected = hmac.new(b"mysecret", body, hashlib.sha256).hexdigest()
        assert sig == expected

    def test_no_secret_returns_none(self, settings):
        settings.BRIGHTBEAN_WEBHOOK_SECRET = ""
        from apps.external_api.webhooks import _sign_payload

        assert _sign_payload(b"payload") is None


# ---------------------------------------------------------------------------
# fire_post_event guard
# ---------------------------------------------------------------------------


class TestFirePostEvent:
    def test_no_url_does_not_enqueue(self, settings):
        settings.BRIGHTBEAN_WEBHOOK_URL = ""
        from apps.external_api.webhooks import fire_post_event

        post = MagicMock()
        post.pk = "fake-id"
        post.workspace_id = "ws-id"
        with patch("apps.external_api.webhooks.deliver_webhook") as mock_deliver:
            fire_post_event("post.published", post)
            mock_deliver.assert_not_called()

    def test_with_url_enqueues_task(self, settings):
        settings.BRIGHTBEAN_WEBHOOK_URL = "https://mmm.example.com/hook/"
        from apps.external_api.webhooks import fire_post_event

        post = MagicMock()
        post.pk = "fake-id"
        post.workspace_id = "ws-id"
        with patch("apps.external_api.webhooks.deliver_webhook") as mock_deliver:
            fire_post_event("post.scheduled", post, scheduled_at="2025-12-01T10:00:00Z")
            mock_deliver.assert_called_once()
            payload = mock_deliver.call_args[0][0]
            assert payload["event"] == "post.scheduled"
            assert payload["post_id"] == "fake-id"


# ---------------------------------------------------------------------------
# Signal handler: status transitions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSignals:
    def test_scheduled_transition_fires_event(
        self, settings, workspace, superuser, account_linkedin
    ):
        settings.BRIGHTBEAN_WEBHOOK_URL = "https://mmm.example.com/hook/"
        post = Post.objects.create(
            workspace=workspace, author=superuser, caption="signal test"
        )
        pp = PlatformPost.objects.create(
            post=post,
            social_account=account_linkedin,
            status=PlatformPost.Status.DRAFT,
        )
        with patch("apps.external_api.signals.fire_post_event") as mock_fire:
            pp.status = PlatformPost.Status.SCHEDULED
            pp.save()
            events = [c[0][0] for c in mock_fire.call_args_list]
            assert "post.scheduled" in events

    def test_published_transition_fires_event(
        self, settings, workspace, superuser, account_linkedin
    ):
        settings.BRIGHTBEAN_WEBHOOK_URL = "https://mmm.example.com/hook/"
        post = Post.objects.create(
            workspace=workspace, author=superuser, caption="signal test published"
        )
        pp = PlatformPost.objects.create(
            post=post,
            social_account=account_linkedin,
            status=PlatformPost.Status.SCHEDULED,
        )
        with patch("apps.external_api.signals.fire_post_event") as mock_fire:
            pp.status = PlatformPost.Status.PUBLISHED
            pp.published_at = timezone.now()
            pp.save()
            events = [c[0][0] for c in mock_fire.call_args_list]
            assert any("published" in e for e in events)

    def test_failed_transition_fires_event(
        self, settings, workspace, superuser, account_linkedin
    ):
        settings.BRIGHTBEAN_WEBHOOK_URL = "https://mmm.example.com/hook/"
        post = Post.objects.create(
            workspace=workspace, author=superuser, caption="signal test failed"
        )
        pp = PlatformPost.objects.create(
            post=post,
            social_account=account_linkedin,
            status=PlatformPost.Status.PUBLISHING,
        )
        with patch("apps.external_api.signals.fire_post_event") as mock_fire:
            pp.status = PlatformPost.Status.FAILED
            pp.publish_error = "API rate limit exceeded"
            pp.save()
            events = [c[0][0] for c in mock_fire.call_args_list]
            assert "post.failed" in events
