"""
Urban Track - Django settings (single-module).

Urban Track is the trust layer for the African urban development sector:
experiences are certified exclusively through cross-confirmation between the
company that publishes a project and the experts who contributed to it
(ResearchGate-style logic).

Configuration is driven by environment variables loaded from a `.env` file
at the repository root (see `.env.example`). Database is SQLite per project
decision; async work runs synchronously (no Celery/Redis); styling uses the
Tailwind browser JS build configured in `templates/base.html`.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Read the .env file when present (no-op if absent; real environment
# variables always take precedence over .env values).
load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    """Read an environment variable with an optional default."""
    return os.environ.get(key, default)


SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-key-do-not-use-in-production",
)

DEBUG = env("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    # Urban Track apps
    "accounts.apps.AccountsConfig",
    "projects.apps.ProjectsConfig",
    "certification.apps.CertificationConfig",
    "cv_generator.apps.CvGeneratorConfig",
    "jobs.apps.JobsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "urbantrack.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "urbantrack.wsgi.application"


# Database
# SQLite by explicit project decision (strong relational integrity at the
# Django ORM level; no PostgreSQL server required).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / env("SQLITE_DB_NAME", "db.sqlite3"),
    }
}


# Authentication
# https://docs.djangoproject.com/en/6.1/topics/auth/customizing/

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Django REST Framework (API-first architecture)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}


# Internationalization

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# Email
# Transactional provider decision: SendGrid (documented in README).
# Default backend is console so development never sends real email;
# production overrides via environment variables (SMTP relay).
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@urbantrack.africa")
if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
    EMAIL_HOST = env("EMAIL_HOST", "smtp.sendgrid.net")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "apikey")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = True


# Urban Track business constants

# Permanent professional ID format: OX-XXXXXX (spec 02-stack.md section 1).
PROFESSIONAL_ID_PREFIX = "OX"
PROFESSIONAL_ID_LENGTH = 6
PROFESSIONAL_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no O/0/I/1 ambiguity

# Expert invitations (certification cross-confirmation flow).
INVITATION_EXPIRY_DAYS = 14  # ~14 days before an invitation expires
INVITATION_MAX_REMINDERS = 2  # up to 2 automatic reminders before expiry
INVITATION_REMINDER_AFTER_DAYS = 5  # days of silence before each reminder

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Test-suite speed-up: PBKDF2 (default, ~600k iterations) dominates runtime;
# a weak hasher is acceptable because tests never persist real credentials.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
