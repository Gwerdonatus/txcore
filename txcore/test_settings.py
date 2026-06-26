from txcore.settings import *  # noqa

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Silence staticfiles warning in tests
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
