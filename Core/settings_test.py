"""Settings for the test suite.

Tests must not depend on network services: caches and channel layers are
in-process, and S3/SES calls hit the moto mock started in conftest.py.
"""

from Core.settings import *  # noqa: F403

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "bravo-tests",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Talk to the default AWS endpoints so moto can intercept every call.
AWS_S3_ENDPOINT_URL = None
AWS_SES_ENDPOINT_URL = None
