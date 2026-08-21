from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom User: role filters and professional ID column."""

    list_display = (
        "username",
        "email",
        "role",
        "professional_id",
        "organisation_name",
        "is_staff",
    )
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
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
                    "organisation_name",
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
                "fields": ("username", "email", "role", "password1", "password2"),
            },
        ),
    )
    search_fields = ("username", "email", "professional_id", "organisation_name")
    readonly_fields = ("professional_id",)
