from django.contrib import admin

from .models import Client, Country, Funder, Project, ProjectTag


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "official_name",
        "client",
        "country",
        "funder",
        "phase",
        "published_by",
        "status",
        "visibility",
    )
    list_filter = ("status", "visibility", "phase", "client", "country", "funder", "tags")
    search_fields = (
        "official_name",
        "client__name",
        "published_by__company__name",
        "country__name",
        "funder__name",
    )
    date_hierarchy = "duration_start"
    filter_horizontal = ("tags",)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "iso3")
    search_fields = ("name", "iso3")


@admin.register(Funder)
class FunderAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(ProjectTag)
class ProjectTagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
