"""Isolated tests: never connect to the configured application database."""
import os
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-for-deployment")
for name in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
    os.environ.setdefault(name, "unused")
from .settings import *  # noqa: F403
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SECURE_SSL_REDIRECT = False
ALLOWED_HOSTS = ["testserver"]
