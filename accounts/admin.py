from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import (
    Company,
    CompanyMembership,
    ExpertProfile,
    Mandate,
    MediaAppearance,
    Position,
    Publication,
    Skill,
    TeachingEntry,
    Training,
    User,
)


class TrainingInline(admin.TabularInline):
    model = Training
    extra = 0


class PositionInline(admin.TabularInline):
    model = Position
    extra = 0


class MandateInline(admin.TabularInline):
    model = Mandate
    extra = 0


class PublicationInline(admin.TabularInline):
    model = Publication
    extra = 0


class TeachingInline(admin.TabularInline):
    model = TeachingEntry
    extra = 0


class MediaInline(admin.TabularInline):
    model = MediaAppearance
    extra = 0


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    """Membership audit trail (T2): the subscription lifecycle is reviewer-led."""

    list_display = (
        "user",
        "company",
        "status",
        "role",
        "requested_at",
        "reviewed_at",
    )
    list_filter = ("status", "role", "company")
    search_fields = ("user__username", "user__professional_id", "company__name")
    readonly_fields = ("requested_at", "reviewed_at", "requested_by", "reviewed_by")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "founded_year")
    search_fields = ("name", "country", "domains", "accreditations")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom User: role, company, confirmation and OX-ID."""

    list_display = (
        "username",
        "email",
        "role",
        "company",
        "professional_id",
        "email_confirmed",
        "is_active",
        "is_staff",
    )
    list_filter = ("role", "email_confirmed", "is_staff", "is_superuser", "is_active")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            _("Informations personnelles"),
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            _("Urban Track"),
            {
                "fields": (
                    "role",
                    "professional_id",
                    "company",
                    "email_confirmed",
                    "email_confirmed_at",
                    "confirmation_code",
                    "confirmation_code_created_at",
                )
            },
        ),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Dates importantes"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "company", "password1", "password2"),
            },
        ),
    )
    search_fields = ("username", "email", "professional_id", "company__name")
    readonly_fields = ("professional_id", "confirmation_code", "confirmation_code_created_at")


@admin.register(ExpertProfile)
class ExpertProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "headline", "country", "cv_template", "trust_score")
    search_fields = ("user__username", "user__professional_id", "headline")
    list_filter = ("cv_template", "country")
    inlines = [
        TrainingInline,
        PositionInline,
        MandateInline,
        PublicationInline,
        TeachingInline,
        MediaInline,
    ]


admin.site.register(Skill)
