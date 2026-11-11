"""Django settings for Flowbridge.

Values that differ between environments come from environment variables,
so the same code runs on a laptop, in Docker Compose and in CI.
"""
import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-change-me" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is off.")

ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Render sets RENDER_EXTERNAL_HOSTNAME to the service's public host name (for example
# flowbridge.onrender.com), so a hosted test copy needs no host settings of its own.
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.projects",
    "apps.approvals",
    "apps.audit",
    "apps.notifications",
    "apps.discussion",
    "apps.evaluation",
]

MIDDLEWARE = [
    "config.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "apps.notifications.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "flowbridge"),
        "USER": env("POSTGRES_USER", "flowbridge"),
        "PASSWORD": env("POSTGRES_PASSWORD", "flowbridge"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        # A hosted database may close idle connections (Neon suspends after five minutes idle).
        "CONN_HEALTH_CHECKS": True,
    }
}

# Hosted databases (Neon, Render and others) give a single connection URL instead, such as
# postgresql://user:password@host/dbname?sslmode=require. Its query options, such as
# sslmode, are passed to the PostgreSQL driver.
DATABASE_URL = (env("DATABASE_URL") or "").strip()
# Tolerate the string as Neon's Connect box shows it in its "psql" form: psql 'postgresql://…'
if DATABASE_URL.startswith("psql "):
    DATABASE_URL = DATABASE_URL[5:].strip()
DATABASE_URL = DATABASE_URL.strip("'\"")
if env("RENDER") and not DATABASE_URL:
    # Render sets RENDER=true. Without DATABASE_URL the app would look for a database on its own machine.
    raise RuntimeError("DATABASE_URL is empty. Set it to the Neon connection string under Environment on Render.")
if DATABASE_URL:
    _url = urlparse(DATABASE_URL)
    if _url.scheme not in ("postgres", "postgresql") or not _url.hostname:
        raise RuntimeError("DATABASE_URL must look like postgresql://user:password@host/dbname?sslmode=require")
    DATABASES["default"].update({
        "NAME": unquote(_url.path.lstrip("/")),
        "USER": unquote(_url.username or ""),
        "PASSWORD": unquote(_url.password or ""),
        "HOST": _url.hostname or "",
        "PORT": str(_url.port or 5432),
        "OPTIONS": dict(parse_qsl(_url.query)),
    })
    # A pooled address (Neon's "-pooler" host, PgBouncer in transaction mode) cannot keep the
    # server-side cursors Django uses for .iterator(), so they are switched off there.
    if "-pooler" in (_url.hostname or ""):
        DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Nginx serves static files in the Docker Compose stack. Where there is no Nginx, WhiteNoise
# serves the same collected files from the application, compressed.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Uploaded documents live in private storage outside the web root.
# There is deliberately no MEDIA_URL: files are only served by a permission-checked view.
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media"))).resolve()
DOCUMENT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# "filesystem" (the default) or "database", for hosts whose local disk is wiped on restart.
DOCUMENT_STORAGE = env("DOCUMENT_STORAGE", "filesystem")
DOCUMENT_ALLOWED_EXTENSIONS = [
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "png", "jpg", "jpeg",
]

# Email (FR13, optional). Users opt in from their preferences page.
# The console backend prints messages instead of sending them; set EMAIL_BACKEND
# to django.core.mail.backends.smtp.EmailBackend and the EMAIL_* variables to use SMTP.
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Flowbridge <no-reply@ztl.example>")
EMAIL_NOTIFICATIONS_ENABLED = env_bool("EMAIL_NOTIFICATIONS_ENABLED", True)
EMAIL_MAX_ATTEMPTS = 3
SITE_URL = env("SITE_URL", f"https://{RENDER_EXTERNAL_HOSTNAME}" if RENDER_EXTERNAL_HOSTNAME else "http://localhost:8000")

# Overdue stages: an approver is reminded at most once per interval (send_reminders command).
REMINDER_INTERVAL_HOURS = int(env("REMINDER_INTERVAL_HOURS", "24"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security headers and cookies.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
# Nginx adds the Content-Security-Policy and Permissions-Policy headers in the Docker Compose stack.
# Where the app runs without Nginx, the application adds them instead (config/middleware.py).
SECURITY_HEADERS_IN_APP = env_bool("SECURITY_HEADERS_IN_APP", False)
SESSION_COOKIE_AGE = 60 * 60 * 8
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    # Nginx also redirects HTTP to HTTPS; Django does too, except for the internal health check.
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
    # HSTS for subdomains and browser preload lists depend on the real domain a deployment uses,
    # so they are a deployment decision rather than an application default.
    SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

MESSAGE_TAGS = {40: "danger"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
