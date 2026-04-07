import uuid

from django.db import models

from apps.common.encryption import EncryptedJSONField
from apps.common.managers import OrgScopedManager


class PlatformCredential(models.Model):
    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"
        INSTAGRAM_PERSONAL = "instagram_personal", "Instagram (Personal)"
        LINKEDIN_PERSONAL = "linkedin_personal", "LinkedIn (Personal Profile)"
        LINKEDIN_COMPANY = "linkedin_company", "LinkedIn (Company Page)"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        PINTEREST = "pinterest", "Pinterest"
        THREADS = "threads", "Threads"
        BLUESKY = "bluesky", "Bluesky"
        GOOGLE_BUSINESS = "google_business", "Google Business Profile"
        MASTODON = "mastodon", "Mastodon"

    class TestResult(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        UNTESTED = "untested", "Untested"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="platform_credentials",
    )
    platform = models.CharField(max_length=30, choices=Platform.choices)
    credentials = EncryptedJSONField(
        default=dict,
        help_text="Encrypted JSON containing platform-specific credential fields",
    )
    is_configured = models.BooleanField(default=False)
    tested_at = models.DateTimeField(blank=True, null=True)
    test_result = models.CharField(
        max_length=20,
        choices=TestResult.choices,
        default=TestResult.UNTESTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrgScopedManager()

    class Meta:
        db_table = "credentials_platform_credential"
        unique_together = [("organization", "platform")]

    def __str__(self):
        return f"{self.organization.name} - {self.get_platform_display()}"

    @property
    def masked_credentials(self):
        """Return credentials with secrets masked (last 4 chars only)."""
        masked = {}
        for key, value in (self.credentials or {}).items():
            if isinstance(value, str) and len(value) > 4:
                masked[key] = "****" + value[-4:]
            else:
                masked[key] = "****"
        return masked
