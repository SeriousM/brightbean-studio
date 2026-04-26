from allauth.account.views import SignupView
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from apps.members.models import Invitation


class InvitePrefillSignupView(SignupView):
    """Signup view that pre-fills and locks the email when a pending
    invite token is in the session.

    When ``SIGNUP_DISABLED=True`` every GET/POST is redirected to the
    login page with an informational message.
    """

    def dispatch(self, request, *args, **kwargs):
        if getattr(settings, "SIGNUP_DISABLED", False):
            messages.info(request, "New sign-ups are not open at the moment.")
            return redirect("account_login")
        return super().dispatch(request, *args, **kwargs)

    def _invited_email(self):
        token = self.request.session.get("pending_invite_token")
        if not token:
            return None
        invitation = Invitation.objects.filter(
            token=token,
            accepted_at__isnull=True,
        ).first()
        if invitation and not invitation.is_expired:
            return invitation.email
        return None

    def get_initial(self):
        initial = super().get_initial()
        email = self._invited_email()
        if email:
            initial["email"] = email
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invited_email_locked"] = bool(self._invited_email())
        return ctx
