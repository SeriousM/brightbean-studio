from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from apps.accounts.models import OAuthConnection


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom adapter that syncs Google social logins to OAuthConnection.

    Behaviour controlled by settings:
    - ``SIGNUP_DISABLED=True``      → rejects new social-account signups.
    - ``GOOGLE_LOGIN_DISABLED=True``→ blocks all Google OAuth flows
                                      (login *and* signup) for every user.
    """

    # ------------------------------------------------------------------
    # Access-control hooks
    # ------------------------------------------------------------------

    def is_open_for_signup(self, request, sociallogin=None):
        """Block social-account signup when SIGNUP_DISABLED is set."""
        if getattr(settings, "SIGNUP_DISABLED", False):
            return False
        return super().is_open_for_signup(request, sociallogin)

    def pre_social_login(self, request, sociallogin):
        """Block Google OAuth entirely when GOOGLE_LOGIN_DISABLED is set."""
        if getattr(settings, "GOOGLE_LOGIN_DISABLED", False) and sociallogin.account.provider == "google":
            messages.error(request, "Google login is currently disabled.")
            raise ImmediateHttpResponse(redirect("account_login"))

        super().pre_social_login(request, sociallogin)
        if sociallogin.is_existing:
            self._sync_oauth_connection(sociallogin.user, sociallogin)

    # ------------------------------------------------------------------
    # Profile / persistence helpers
    # ------------------------------------------------------------------

    def populate_user(self, request, sociallogin, data):
        """Set user.name from Google profile (custom User model has 'name', not first/last)."""
        user = super().populate_user(request, sociallogin, data)
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip()
        if full_name and not user.name:
            user.name = full_name
        return user

    def save_user(self, request, sociallogin, form=None):
        """Create OAuthConnection after saving a new social signup."""
        user = super().save_user(request, sociallogin, form)
        self._sync_oauth_connection(user, sociallogin)
        return user

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sync_oauth_connection(self, user, sociallogin):
        account = sociallogin.account
        if account.provider != "google":
            return
        provider_email = ""
        for ea in sociallogin.email_addresses:
            provider_email = ea.email
            break
        OAuthConnection.objects.update_or_create(
            provider=OAuthConnection.Provider.GOOGLE,
            provider_user_id=account.uid,
            defaults={"user": user, "provider_email": provider_email},
        )
