from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "official_name",
        "client_name",
        "published_by",
        "status",
        "visibility",
        "duration_start",
        "duration_end",
    )
    list_filter = ("status", "visibility")
    search_fields = ("official_name", "client_name", "published_by__organisation_name")
    date_hierarchy = "duration_start"
