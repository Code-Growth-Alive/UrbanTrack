from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import ContributionStatus, ExpertInvitation, ProjectContribution


@admin.register(ProjectContribution)
class ProjectContributionAdmin(admin.ModelAdmin):
    """
    Admin surface for the certification heart.

    Certified contributions are displayed read-only for protected data —
    admins never edit certified wording; they only arbitrate disputes
    (business rule 7).
    """

    list_display = (
        "project",
        "expert",
        "invited_email",
        "role_type",
        "status",
        "pending_company_validation",
        "confirmed_at",
    )
    list_filter = ("status", "role_type", "project__status")
    search_fields = (
        "invited_email",
        "expert__email",
        "expert__professional_id",
        "project__official_name",
    )
    readonly_fields = ("created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.status == ContributionStatus.CONFIRMED:
            return tuple(fields) + ProjectContribution.PROTECTED_FIELDS + (
                "status",
                "confirmed_at",
            )
        return fields

    @admin.action(description=_("Mark selected as disputed (admin arbitration)"))
    def mark_disputed(self, request, queryset):
        queryset.update(status=ContributionStatus.DISPUTED)


@admin.register(ExpertInvitation)
class ExpertInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "contribution",
        "status",
        "sent_at",
        "expires_at",
        "reminder_count",
    )
    list_filter = ("status",)
    search_fields = ("email", "token")
    readonly_fields = ("token", "sent_at")
