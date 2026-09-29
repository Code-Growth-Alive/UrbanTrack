"""Template context processors exposing site-wide branding URLs.

Images referenced from templates (``<link rel="icon">``, ``og:image``, email
headers) must be absolute URLs, while ``{% static %}`` yields a root-relative
path. This processor joins both so templates never build URLs by hand.
"""

from django.conf import settings
from django.templatetags.static import static

#: Site name, used as the default social image when a page has no specific one.
DEFAULT_SEO_IMAGE = "img/logo_og.png"


def _site_base_url():
    base = settings.SITE_BASE_URL
    if base and "://" not in base:
        base = f"https://{base}"
    return base.rstrip("/")


def branding(request):
    """Return absolute site/logo URLs for every template."""
    base = _site_base_url()
    return {
        "site_base_url": base,
        "default_seo_image": f"{base}{static(DEFAULT_SEO_IMAGE)}",
    }
