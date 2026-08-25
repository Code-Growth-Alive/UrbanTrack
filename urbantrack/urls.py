"""
URL configuration for Urban Track.

Server-rendered pages live at the root; the DRF API is mounted under
``api/`` (API-first architecture for external connectors and the future
mobile app). No health-check or versioned endpoints by project decision.
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "",
        TemplateView.as_view(template_name="home.html"),
        name="home",
    ),
    path("", include("accounts.urls")),
    path("", include("projects.urls")),
    path("", include("certification.urls")),
    path("jobs/", include("jobs.urls")),
    path("cv/", include("cv_generator.urls")),
    path("about/", TemplateView.as_view(template_name="about.html"), name="about"),
    # Browsable-API login/logout for the DRF surface.
    path("api/", include("rest_framework.urls")),
]

handler404 = "urbantrack.views.handler404"
handler500 = "urbantrack.views.handler500"
