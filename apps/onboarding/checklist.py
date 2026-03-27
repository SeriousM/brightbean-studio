"""Onboarding checklist evaluation logic.

Computes the 5 checklist items and their completion status for a workspace.
Used by the workspace dashboard to render the dynamic "Get Started" card.
"""

from django.urls import reverse

from apps.workspaces.models import Workspace


def get_checklist_items(workspace):
    """Return a list of checklist item dicts with dynamic completion status.

    Each item has: key, title, description, completed (bool), url, icon_color, icon_svg
    """
    from apps.calendar.models import PostingSlot
    from apps.composer.models import Post
    from apps.members.models import WorkspaceMembership
    from apps.social_accounts.models import SocialAccount

    workspace_id = workspace.id

    items = [
        {
            "key": "connect_accounts",
            "title": "Connect social accounts",
            "description": "Link your Instagram, LinkedIn, or other platforms",
            "completed": SocialAccount.objects.for_workspace(workspace_id).exists(),
            "url": reverse(
                "social_accounts:connect",
                kwargs={"workspace_id": workspace_id},
            ),
            "icon_color": "sky",
            "icon_svg": '<path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101"/><path d="M10.172 13.828a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>',
        },
        {
            "key": "create_post",
            "title": "Create your first post",
            "description": "Draft and schedule content for your audience",
            "completed": Post.objects.for_workspace(workspace_id).exists(),
            "url": reverse(
                "composer:compose",
                kwargs={"workspace_id": workspace_id},
            ),
            "icon_color": "sky",
            "icon_svg": '<path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>',
        },
        {
            "key": "invite_members",
            "title": "Invite your team",
            "description": "Add team members to collaborate on content",
            "completed": WorkspaceMembership.objects.filter(
                workspace_id=workspace_id,
                workspace_role=WorkspaceMembership.WorkspaceRole.CLIENT,
            ).exists(),
            "url": reverse("members:list"),
            "icon_color": "sky",
            "icon_svg": '<path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M20 8v6m3-3h-6"/>',
        },        
    ]
    return items
