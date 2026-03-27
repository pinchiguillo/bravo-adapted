import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator

from Core import settings as core_settings


class SettingsEnvHelpersTests(SimpleTestCase):
    def test_env_bool_recognizes_truthy_values(self):
        with patch.dict("os.environ", {"BOOL_FLAG": "true"}, clear=False):
            self.assertTrue(core_settings.env_bool("BOOL_FLAG"))

    def test_env_int_raises_for_invalid_values(self):
        with patch.dict("os.environ", {"INT_FLAG": "invalid"}, clear=False):
            with self.assertRaises(ImproperlyConfigured):
                core_settings.env_int("INT_FLAG", 0)

    def test_env_list_splits_and_strips_values(self):
        with patch.dict("os.environ", {"LIST_FLAG": " a, b ,,c "}, clear=False):
            self.assertEqual(core_settings.env_list("LIST_FLAG"), ["a", "b", "c"])

    def test_require_env_raises_when_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ImproperlyConfigured):
                core_settings.require_env("MISSING_VAR")

    def test_auth_bypass_email_verification_defaults_to_true_in_development(self):
        with patch.dict("os.environ", {"APP_MODE": "development"}, clear=True):
            self.assertTrue(
                core_settings.env_bool(
                    "AUTH_BYPASS_EMAIL_VERIFICATION",
                    default=os.environ.get("APP_MODE", "development").strip().lower() != "production",
                )
            )

    def test_auth_bypass_email_verification_defaults_to_false_in_production(self):
        with patch.dict("os.environ", {"APP_MODE": "production"}, clear=True):
            self.assertFalse(
                core_settings.env_bool(
                    "AUTH_BYPASS_EMAIL_VERIFICATION",
                    default=os.environ.get("APP_MODE", "development").strip().lower() != "production",
                )
            )

    def test_bypass_admin_login_defaults_to_false_in_development(self):
        with patch.dict("os.environ", {"APP_MODE": "development"}, clear=True):
            self.assertFalse(
                core_settings.env_bool(
                    "BYPASS_ADMIN_LOGIN",
                    default=False,
                )
            )

    def test_disable_in_production_bool_forces_false_in_production(self):
        with patch.object(core_settings, "IS_PRODUCTION", True):
            self.assertFalse(core_settings.disable_in_production_bool(True))

    def test_disable_in_production_bool_keeps_value_outside_production(self):
        with patch.object(core_settings, "IS_PRODUCTION", False):
            self.assertTrue(core_settings.disable_in_production_bool(True))

    def test_read_project_version_reads_version_file(self):
        self.assertEqual(core_settings.read_project_version(), "0.0.2")


class OpenApiSecuritySchemaTests(SimpleTestCase):
    @staticmethod
    def _get_operation(path, method):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        return schema["paths"][path][method]

    def test_public_endpoints_do_not_require_auth_in_schema(self):
        public_operations = (
            ("/api/auth/login/", "post"),
            ("/api/auth/register/", "post"),
            ("/api/auth/token/refresh/", "post"),
            ("/api/auth/verify-email/", "post"),
            ("/api/announcements/", "get"),
            ("/api/organizations/{uuid}/", "get"),
            ("/api/organizations/{organization_uuid}/jobs/", "get"),
            ("/api/organizations/{organization_uuid}/jobs/{job_uuid}/services/", "get"),
        )

        for path, method in public_operations:
            with self.subTest(path=path, method=method):
                operation = self._get_operation(path, method)
                self.assertNotIn("security", operation)

    def test_private_endpoints_keep_jwt_auth_in_schema(self):
        private_operations = (
            ("/api/auth/me/", "get"),
            ("/api/organizations/me/", "get"),
        )

        for path, method in private_operations:
            with self.subTest(path=path, method=method):
                operation = self._get_operation(path, method)
                self.assertEqual(operation.get("security"), [{"jwtAuth": []}])

    def test_schema_uses_project_version_from_version_file(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        self.assertEqual(schema["info"]["version"], "0.0.2")
