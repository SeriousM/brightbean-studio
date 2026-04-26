"""URL patterns for the external API.

Mounted at ``/external-api/`` in ``config/urls.py``:
    path("external-api/", include("apps.external_api.urls"))

All routes are prefixed with ``v1/`` so future breaking changes can be
introduced under ``v2/`` without removing existing routes.
"""

from django.urls import path

from . import views

app_name = "external_api"

urlpatterns = [
    # Discovery
    path("v1/workspaces/", views.list_workspaces, name="list_workspaces"),
    path("v1/workspaces/<uuid:workspace_id>/accounts/", views.list_accounts, name="list_accounts"),

    # Post management
    path("v1/posts/", views.create_post, name="create_post"),
    path("v1/posts/<uuid:post_id>/", views.get_post, name="get_post"),
    path("v1/posts/<uuid:post_id>/update/", views.update_post, name="update_post"),
    path("v1/posts/<uuid:post_id>/delete/", views.delete_post, name="delete_post"),
    path("v1/posts/<uuid:post_id>/composer-url/", views.get_composer_url, name="get_composer_url"),
    path("v1/posts/<uuid:post_id>/engagement/", views.get_engagement, name="get_engagement"),
]
