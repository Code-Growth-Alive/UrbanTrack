from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Company, ExpertProfile, Skill, Training, User


class TrainingInline(admin.TabularInline):
    model = Training
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


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
            _("Personal info"),
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
                    "confirmation_code",
                    "confirmation_code_created_at",
                )
            },
        ),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
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
    inlines = [TrainingInline]


admin.site.register(Skill)
