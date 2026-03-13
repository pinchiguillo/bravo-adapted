import importlib
import os

from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings


class SecuritySettingsTests(SimpleTestCase):
    def test_production_enforces_security_baseline_even_with_insecure_env_values(self):
        original_env = os.environ.copy()
        settings_module = importlib.import_module("Core.settings")

        try:
            os.environ.update(
                {
                    "APP_MODE": "production",
                    "DEBUG": "0",
                    "ALLOWED_HOSTS": "api.example.com",
                    "SECRET_KEY": "production-secret-key-with-enough-entropy-1234567890",
                    "SECURE_SSL_REDIRECT": "0",
                    "SECURE_HSTS_SECONDS": "0",
                    "SECURE_HSTS_INCLUDE_SUBDOMAINS": "0",
                    "SECURE_HSTS_PRELOAD": "0",
                    "SESSION_COOKIE_SECURE": "0",
                    "CSRF_COOKIE_SECURE": "0",
                }
            )
            settings_module = importlib.reload(settings_module)

            self.assertTrue(settings_module.SECURE_SSL_REDIRECT)
            self.assertEqual(settings_module.SECURE_HSTS_SECONDS, 31536000)
            self.assertTrue(settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
            self.assertTrue(settings_module.SECURE_HSTS_PRELOAD)
            self.assertTrue(settings_module.SESSION_COOKIE_SECURE)
            self.assertTrue(settings_module.CSRF_COOKIE_SECURE)
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(settings_module)

    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["api.example.com"],
        CSRF_TRUSTED_ORIGINS=["https://api.example.com"],
        SECRET_KEY="production-secret-key-with-enough-entropy-1234567890",
        SECURE_SSL_REDIRECT=True,
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_deploy_check_has_no_security_warnings_with_production_settings(self):
        security_warnings = [
            message.id
            for message in run_checks(include_deployment_checks=True)
            if message.id.startswith("security.W")
        ]

        self.assertEqual(security_warnings, [])

    def test_use_s3_storage_cannot_be_disabled(self):
        original_env = os.environ.copy()
        settings_module = importlib.import_module("Core.settings")

        try:
            os.environ["USE_S3_STORAGE"] = "0"
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(settings_module)
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(settings_module)

    def test_default_s3_endpoint_falls_back_to_localstack(self):
        original_env = os.environ.copy()
        settings_module = importlib.import_module("Core.settings")

        try:
            os.environ.pop("AWS_S3_ENDPOINT_URL", None)
            os.environ.pop("LOCALSTACK_ENDPOINT", None)
            os.environ["USE_S3_STORAGE"] = "1"
            settings_module = importlib.reload(settings_module)

            self.assertEqual(settings_module.AWS_S3_ENDPOINT_URL, "http://localstack:4566")
            self.assertTrue(settings_module.USE_S3_STORAGE)
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(settings_module)

    def test_rest_framework_default_pagination_is_enabled(self):
        settings_module = importlib.import_module("Core.settings")

        self.assertEqual(
            settings_module.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"],
            "Core.pagination.DefaultPageNumberPagination",
        )
        self.assertEqual(settings_module.REST_FRAMEWORK["PAGE_SIZE"], 20)
