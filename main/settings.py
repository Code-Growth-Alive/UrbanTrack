"""
Urban Track - Django settings (single-module).

Urban Track is the trust layer for the African urban development sector:
experiences are certified exclusively through cross-confirmation between the
company that publishes a project and the experts who contributed to it
(ResearchGate-style logic).

Configuration is driven by environment variables loaded from a `.env` file
at the repository root (see `.env.example`). Database is SQLite per project
decision; async work runs synchronously (no Celery/Redis); styling uses the
Tailwind browser JS build (vendored at `static/vendor/tailwind.js`)
configured in `templates/base.html`.
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


def env_bool(key, default=False):
    """Read a boolean environment variable (1/true/yes/on)."""
    return str(env(key, str(default))).strip().lower() in ("1", "true", "yes", "on")


TESTING = "test" in sys.argv

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-key-do-not-use-in-production",
)

DEBUG = True

ALLOWED_HOSTS = [
    h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
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
    "adminpanel.apps.AdminpanelConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.RequireEmailConfirmationMiddleware",
    "main.middleware.RequestLogMiddleware",
]

ROOT_URLCONF = "main.urls"

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
                "main.context_processors.branding",
            ],
        },
    },
]

WSGI_APPLICATION = "main.wsgi.application"


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

# Auth flow URLs (Epic 3: magic-link landing bounces anonymous actors here).
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "home"

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

LAUNCH_COUNTER_THRESHOLD = int(env("LAUNCH_COUNTER_THRESHOLD", "1"))

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# WhiteNoise serves the collected static files directly from the VPS (no nginx
# required); CompressedManifestStorage adds hashing + gzip/brotli compression.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media (user uploads: avatars, project media)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# Email
# Transactional provider decision: SendGrid (documented in README).
# Default backend is console so development never sends real email;
# production overrides via environment variables (SMTP relay).
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@urbantrack.africa")
EMAIL_HOST = env("EMAIL_HOST", "smtp.sendgrid.net")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "apikey")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = env("EMAIL_USE_SSL", "False").lower() in ("1", "true", "yes")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "False").lower() in ("1", "true", "yes")
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "20"))


# Absolute base URL used to build clickable links in transactional emails
# (localhost in development, a real domain in production).
SITE_BASE_URL = env("SITE_BASE_URL", "http://localhost:8000").rstrip("/")

# The app runs behind an nginx reverse proxy that terminates TLS. Django must
# trust the ``X-Forwarded-Proto`` header to detect HTTPS, otherwise password
# reset and other emails build ``http://`` links against an https-only site.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Urban Track business constants

# Permanent professional ID format: OX-XXXXXX (spec 02-stack.md section 1).
PROFESSIONAL_ID_PREFIX = "OX"
PROFESSIONAL_ID_LENGTH = 6
PROFESSIONAL_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no O/0/I/1 ambiguity

# Expert invitations (certification cross-confirmation flow).
INVITATION_EXPIRY_DAYS = 14  # ~14 days before an invitation expires
INVITATION_MAX_REMINDERS = 2  # up to 2 automatic reminders before expiry
INVITATION_REMINDER_AFTER_DAYS = 5  # days of silence before each reminder

# Email confirmation of new accounts.
CONFIRMATION_CODE_TTL_HOURS = 24  # a code (and unconfirmed account) lives 24h
CONFIRMATION_CODE_LENGTH = 6  # number of digits in the code

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Logging
# Console output is always available (systemd/journald captures gunicorn's
# stdout); rotating files are enabled outside the test suite. Set
# LOG_FORMAT=json for a log collector (one JSON object per line).
LOG_LEVEL = env("LOG_LEVEL", "INFO").strip().upper()
DJANGO_LOG_LEVEL = env("DJANGO_LOG_LEVEL", "INFO").strip().upper()
LOG_FORMAT = env("LOG_FORMAT", "text").strip().lower()
if LOG_FORMAT not in ("text", "json"):
    LOG_FORMAT = "text"
LOG_DIR = Path(env("LOG_DIR", "logs"))
if not LOG_DIR.is_absolute():
    LOG_DIR = BASE_DIR / LOG_DIR
LOG_TO_FILE = env_bool("LOG_TO_FILE", True) and not TESTING
LOG_MAX_BYTES = int(env("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(env("LOG_BACKUP_COUNT", "5"))
LOG_SKIP_PATHS = tuple(
    path.strip()
    for path in env("LOG_SKIP_PATHS", "/static/,/media/,/favicon.ico").split(",")
    if path.strip()
)

_log_handlers = ["null"] if TESTING else ["console"]
if LOG_TO_FILE:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        LOG_TO_FILE = False
    else:
        _log_handlers.extend(["file", "error_file"])

_log_formatter = "json" if LOG_FORMAT == "json" else "verbose"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "main.logging.RequestIDFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        "json": {"()": "main.logging.JsonFormatter"},
    },
    "handlers": {
        "null": {"class": "logging.NullHandler"},
        "console": {
            "class": "logging.StreamHandler",
            "formatter": _log_formatter,
            "filters": ["request_id"],
        },
    },
    "loggers": {
        "django": {
            "handlers": _log_handlers,
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "django.request": {
            "handlers": _log_handlers,
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": _log_handlers,
            "level": "WARNING",
            "propagate": False,
        },
        # Access logs, audit events and every app logger (accounts, projects...)
        "urbantrack": {
            "handlers": _log_handlers,
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {
        "handlers": _log_handlers,
        "level": LOG_LEVEL,
    },
}

if LOG_TO_FILE:
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_DIR / "urbantrack.log"),
        "maxBytes": LOG_MAX_BYTES,
        "backupCount": LOG_BACKUP_COUNT,
        "formatter": _log_formatter,
        "filters": ["request_id"],
        "encoding": "utf-8",
    }
    LOGGING["handlers"]["error_file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(LOG_DIR / "errors.log"),
        "maxBytes": LOG_MAX_BYTES,
        "backupCount": LOG_BACKUP_COUNT,
        "formatter": _log_formatter,
        "filters": ["request_id"],
        "encoding": "utf-8",
        "level": "ERROR",
    }


# Test-suite speed-up: PBKDF2 (default, ~600k iterations) dominates runtime;
# a weak hasher is acceptable because tests never persist real credentials.
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
