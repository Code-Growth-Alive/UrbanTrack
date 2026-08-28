"""
URL configuration for Urban Track.

Server-rendered pages live at the root; the DRF API is mounted under
``api/`` (API-first architecture for external connectors and the future
mobile app). No health-check or versioned endpoints by project decision.
"""

from django.conf import settings
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

# In development, serve uploaded media (project pictures, CVs, documents)
# directly; the staticfiles app already serves static assets during runserver,
# and production reverse-proxies both from a CDN/web server.
if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = "urbantrack.views.handler400"
handler403 = "urbantrack.views.handler403"
handler404 = "urbantrack.views.handler404"
handler500 = "urbantrack.views.handler500"
