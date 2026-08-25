from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import ContributionStatus, ExpertInvitation, ProjectContribution
from .services import resolve_dispute


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
    actions = ("arbitrate_confirm", "arbitrate_reject", "arbitrate_return_to_expert")

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.status == ContributionStatus.CONFIRMED:
            return tuple(fields) + ProjectContribution.PROTECTED_FIELDS + (
                "status",
                "confirmed_at",
            )
        return fields

    def _arbitrate(self, request, queryset, outcome):
        """Run the service state machine for every selected dispute."""
        resolved = 0
        for contribution in queryset.filter(status=ContributionStatus.DISPUTED):
            resolve_dispute(contribution, request.user, outcome=outcome)
            resolved += 1
        self.message_user(
            request,
            f"{resolved} dispute(s) resolved as '{outcome}'.",
        )

    @admin.action(description=_("Arbitrate: certify as declared"))
    def arbitrate_confirm(self, request, queryset):
        self._arbitrate(request, queryset, "confirm")

    @admin.action(description=_("Arbitrate: side with the expert (reject)"))
    def arbitrate_reject(self, request, queryset):
        self._arbitrate(request, queryset, "reject")

    @admin.action(description=_("Arbitrate: return to expert for confirmation"))
    def arbitrate_return_to_expert(self, request, queryset):
        self._arbitrate(request, queryset, "return_to_expert")


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
