import importlib
import os

from django.conf import settings
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
                    "DATABASE_URL": "postgresql://postgres:postgres@postgres:5432/auth_db",
                    "REDIS_URL": "redis://redis:6379/0",
                    "AWS_DEFAULT_REGION": "us-east-1",
                    "AWS_ACCESS_KEY_ID": "test",
                    "AWS_SECRET_ACCESS_KEY": "test",
                    "AWS_STORAGE_BUCKET_NAME": "bravo-media",
                    "AWS_LEGAL_DOCUMENTS_BUCKET_NAME": "bravo-legal-documents",
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

    def test_production_forces_debug_off_and_password_rules_on(self):
        original_env = os.environ.copy()
        settings_module = importlib.import_module("Core.settings")

        try:
            os.environ.update(
                {
                    "APP_MODE": "production",
                    "DEBUG": "1",
                    "AUTH_ENFORCE_PASSWORD_RESTRICTIONS": "0",
                    "ALLOWED_HOSTS": "api.example.com",
                    "SECRET_KEY": "production-secret-key-with-enough-entropy-1234567890",
                    "DATABASE_URL": "postgresql://postgres:postgres@postgres:5432/auth_db",
                    "REDIS_URL": "redis://redis:6379/0",
                    "AWS_DEFAULT_REGION": "us-east-1",
                    "AWS_ACCESS_KEY_ID": "test",
                    "AWS_SECRET_ACCESS_KEY": "test",
                    "AWS_STORAGE_BUCKET_NAME": "bravo-media",
                    "AWS_LEGAL_DOCUMENTS_BUCKET_NAME": "bravo-legal-documents",
                }
            )
            settings_module = importlib.reload(settings_module)

            self.assertFalse(settings_module.DEBUG)
            self.assertTrue(settings_module.AUTH_ENFORCE_PASSWORD_RESTRICTIONS)
            validator_names = [validator["NAME"] for validator in settings_module.AUTH_PASSWORD_VALIDATORS]
            self.assertIn("django.contrib.auth.password_validation.MinimumLengthValidator", validator_names)
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

    def test_default_media_url_uses_public_s3_proxy_path(self):
        original_env = os.environ.copy()
        settings_module = importlib.import_module("Core.settings")

        try:
            os.environ.pop("MEDIA_PUBLIC_BASE_URL", None)
            os.environ["USE_S3_STORAGE"] = "1"
            os.environ["AWS_STORAGE_BUCKET_NAME"] = "bravo-media"
            settings_module = importlib.reload(settings_module)

            self.assertEqual(settings_module.MEDIA_URL, "/s3/bravo-media/")
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(settings_module)

    def test_legal_documents_storage_uses_separate_bucket_configuration(self):
        original_env = os.environ.copy()
        settings_module = importlib.import_module("Core.settings")

        try:
            os.environ["USE_S3_STORAGE"] = "1"
            os.environ["AWS_STORAGE_BUCKET_NAME"] = "bravo-media"
            os.environ["AWS_LEGAL_DOCUMENTS_BUCKET_NAME"] = "bravo-legal-documents"
            settings_module = importlib.reload(settings_module)

            self.assertEqual(
                settings_module.AWS_LEGAL_DOCUMENTS_BUCKET_NAME,
                "bravo-legal-documents",
            )
            self.assertEqual(
                settings_module.STORAGES["legal_documents"]["OPTIONS"]["bucket_name"],
                "bravo-legal-documents",
            )
            self.assertNotEqual(
                settings_module.AWS_LEGAL_DOCUMENTS_BUCKET_NAME,
                settings_module.AWS_STORAGE_BUCKET_NAME,
            )
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(settings_module)

    def test_rest_framework_default_pagination_is_enabled(self):
        settings_module = importlib.import_module("Core.settings")

        self.assertEqual(
            settings_module.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"],
            "common.pagination.DefaultPageNumberPagination",
        )
        self.assertEqual(settings_module.REST_FRAMEWORK["PAGE_SIZE"], 20)

    def test_rgpd_module_is_always_enabled(self):
        self.assertTrue(settings.RGPD_MODULE_ENABLED)
        self.assertIn("apps.rgpd.apps.RgpdConfig", settings.INSTALLED_APPS)

    def test_rgpd_endpoint_is_registered(self):
        response = self.client.get("/api/rgpd/me/")

        self.assertNotEqual(response.status_code, 404)
