"""Tests for SIGNUP_DISABLED and GOOGLE_LOGIN_DISABLED feature flags.

Covers:
- Signup view blocked when SIGNUP_DISABLED=True
- Signup view accessible when SIGNUP_DISABLED=False (default)
- Social adapter is_open_for_signup returns False when SIGNUP_DISABLED=True
- Google pre_social_login raises ImmediateHttpResponse when GOOGLE_LOGIN_DISABLED=True
- Google pre_social_login passes through when GOOGLE_LOGIN_DISABLED=False
- Login template hides signup link when SIGNUP_DISABLED=True
- Login template shows signup link when SIGNUP_DISABLED=False
- Login/Signup templates hide Google button when GOOGLE_LOGIN_DISABLED=True
"""

import pytest
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount as AllAuthSocialAccount
from allauth.socialaccount.models import SocialLogin
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.accounts.adapters import SocialAccountAdapter
from apps.accounts.models import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter():
    return SocialAccountAdapter()


@pytest.fixture
def existing_user(db):
    return User.objects.create_user(
        email="google@example.com",
        password="pass1234",
        name="Google User",
    )


@pytest.fixture
def google_sociallogin(existing_user):
    account = AllAuthSocialAccount(provider="google", uid="uid-google-001")
    account.user = existing_user
    sociallogin = SocialLogin(user=existing_user, account=account)
    return sociallogin


@pytest.fixture
def rf():
    return RequestFactory()


# ---------------------------------------------------------------------------
# InvitePrefillSignupView – SIGNUP_DISABLED
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSignupViewDisabled:
    """Signup view is blocked when SIGNUP_DISABLED=True."""

    @override_settings(SIGNUP_DISABLED=True)
    def test_get_redirects_to_login(self, client):
        url = reverse("accounts:account_signup")
        response = client.get(url)
        assert response.status_code == 302
        assert response["Location"] == reverse("account_login")

    @override_settings(SIGNUP_DISABLED=True)
    def test_post_redirects_to_login(self, client):
        url = reverse("accounts:account_signup")
        response = client.post(url, {"email": "new@example.com", "password1": "strongpass1", "password2": "strongpass1"})
        assert response.status_code == 302
        assert response["Location"] == reverse("account_login")

    @override_settings(SIGNUP_DISABLED=True)
    def test_redirect_carries_info_message(self, client):
        url = reverse("accounts:account_signup")
        response = client.get(url, follow=True)
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        assert any("not open" in m.lower() or "sign-up" in m.lower() for m in msgs)


@pytest.mark.django_db
class TestSignupViewEnabled:
    """Signup view is reachable when SIGNUP_DISABLED=False (default)."""

    @override_settings(SIGNUP_DISABLED=False)
    def test_get_returns_200(self, client):
        url = reverse("accounts:account_signup")
        response = client.get(url)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# SocialAccountAdapter – is_open_for_signup
# ---------------------------------------------------------------------------


class TestIsOpenForSignup:
    """Adapter blocks social signup when SIGNUP_DISABLED=True."""

    def test_blocked_when_signup_disabled(self, adapter, rf):
        request = rf.get("/")
        with override_settings(SIGNUP_DISABLED=True):
            assert adapter.is_open_for_signup(request) is False

    def test_open_when_signup_enabled(self, adapter, rf):
        request = rf.get("/")
        with override_settings(SIGNUP_DISABLED=False):
            # Default allauth behaviour returns True when no app restrictions apply
            result = adapter.is_open_for_signup(request)
            assert result is True


# ---------------------------------------------------------------------------
# SocialAccountAdapter – pre_social_login / GOOGLE_LOGIN_DISABLED
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPreSocialLoginGoogleDisabled:
    """Google OAuth is blocked when GOOGLE_LOGIN_DISABLED=True."""

    def _request_with_messages(self, rf):
        """Create a RequestFactory request with message storage attached."""
        request = rf.get("/")
        request.session = {}  # minimal session
        storage = FallbackStorage(request)
        request._messages = storage
        return request

    @override_settings(GOOGLE_LOGIN_DISABLED=True)
    def test_raises_immediate_http_response_for_google(self, adapter, rf, google_sociallogin):
        request = self._request_with_messages(rf)
        with pytest.raises(ImmediateHttpResponse) as exc_info:
            adapter.pre_social_login(request, google_sociallogin)
        response = exc_info.value.response
        # Should redirect to the login page
        assert response.status_code == 302

    @override_settings(GOOGLE_LOGIN_DISABLED=False)
    def test_does_not_raise_when_google_enabled(self, adapter, rf, google_sociallogin, db):
        request = self._request_with_messages(rf)
        # account.pk is None → is_existing is False → _sync_oauth_connection not called
        # No ImmediateHttpResponse should be raised.
        try:
            adapter.pre_social_login(request, google_sociallogin)
        except ImmediateHttpResponse:
            pytest.fail("pre_social_login raised ImmediateHttpResponse when GOOGLE_LOGIN_DISABLED=False")


# ---------------------------------------------------------------------------
# Template rendering – login page
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLoginTemplateFlags:
    """Template hides/shows signup link and Google button based on flags."""

    @override_settings(SIGNUP_DISABLED=True)
    def test_signup_link_hidden_when_signup_disabled(self, client):
        response = client.get(reverse("account_login"))
        assert response.status_code == 200
        content = response.content.decode()
        # The "Sign up" footer link should not be present
        assert "Sign up" not in content

    @override_settings(SIGNUP_DISABLED=False)
    def test_signup_link_shown_when_signup_enabled(self, client):
        response = client.get(reverse("account_login"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Sign up" in content

    @override_settings(GOOGLE_LOGIN_DISABLED=True, GOOGLE_AUTH_CLIENT_ID="fake-id", GOOGLE_AUTH_CLIENT_SECRET="fake-secret")
    def test_google_button_hidden_when_google_disabled(self, client):
        response = client.get(reverse("account_login"))
        assert response.status_code == 200
        content = response.content.decode()
        # Google SVG / "Continue with Google" should not be rendered
        assert "Continue with Google" not in content

    @override_settings(GOOGLE_LOGIN_DISABLED=False, GOOGLE_AUTH_CLIENT_ID="fake-id", GOOGLE_AUTH_CLIENT_SECRET="fake-secret")
    def test_google_button_shown_when_google_enabled(self, client):
        response = client.get(reverse("account_login"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Continue with Google" in content


# ---------------------------------------------------------------------------
# Template rendering – signup page
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSignupTemplateFlags:
    """Signup template hides Google button when GOOGLE_LOGIN_DISABLED=True."""

    @override_settings(
        SIGNUP_DISABLED=False,
        GOOGLE_LOGIN_DISABLED=True,
        GOOGLE_AUTH_CLIENT_ID="fake-id",
        GOOGLE_AUTH_CLIENT_SECRET="fake-secret",
    )
    def test_google_button_hidden_on_signup_when_disabled(self, client):
        response = client.get(reverse("accounts:account_signup"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Continue with Google" not in content

    @override_settings(
        SIGNUP_DISABLED=False,
        GOOGLE_LOGIN_DISABLED=False,
        GOOGLE_AUTH_CLIENT_ID="fake-id",
        GOOGLE_AUTH_CLIENT_SECRET="fake-secret",
    )
    def test_google_button_shown_on_signup_when_enabled(self, client):
        response = client.get(reverse("accounts:account_signup"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Continue with Google" in content
