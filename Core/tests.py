import importlib
import os
import re
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, URLPattern, URLResolver, clear_url_caches, get_resolver, resolve, reverse
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.test import APIClient

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

    def test_disable_in_production_bool_forces_false_in_production(self):
        with patch.object(core_settings, "IS_PRODUCTION", True):
            self.assertFalse(core_settings.disable_in_production_bool(True))

    def test_disable_in_production_bool_keeps_value_outside_production(self):
        with patch.object(core_settings, "IS_PRODUCTION", False):
            self.assertTrue(core_settings.disable_in_production_bool(True))

    def test_hide_api_docs_defaults_to_true_in_production(self):
        with patch.dict("os.environ", {"APP_MODE": "production"}, clear=True):
            self.assertTrue(
                core_settings.env_bool(
                    "HIDE_API_DOCS",
                    default=os.environ.get("APP_MODE", "development").strip().lower() == "production",
                )
            )

    def test_hide_api_docs_defaults_to_false_in_development(self):
        with patch.dict("os.environ", {"APP_MODE": "development"}, clear=True):
            self.assertFalse(
                core_settings.env_bool(
                    "HIDE_API_DOCS",
                    default=os.environ.get("APP_MODE", "development").strip().lower() == "production",
                )
            )

    def test_read_project_version_reads_version_file(self):
        expected_version = (core_settings.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(core_settings.read_project_version(), expected_version)


class OpenApiSecuritySchemaTests(SimpleTestCase):
    @staticmethod
    def _get_operation(path, method):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        return schema["paths"][path][method]

    @staticmethod
    def _reverse_path(name, **kwargs):
        return reverse(name, kwargs=kwargs)

    def test_public_endpoints_do_not_require_auth_in_schema(self):
        public_operations = (
            ("/api/auth/login/", "post"),
            ("/api/auth/register/", "post"),
            ("/api/auth/token/refresh/", "post"),
            ("/api/auth/verify-email/", "post"),
            ("/api/announcements/", "get"),
            ("/api/organizations/{uuid}/", "get"),
        )

        for path, method in public_operations:
            with self.subTest(path=path, method=method):
                operation = self._get_operation(path, method)
                self.assertNotIn("security", operation)

    def test_private_endpoints_keep_jwt_auth_in_schema(self):
        private_operations = (
            ("/api/auth/me/", "get"),
            (self._reverse_path("job-list"), "get"),
            (self._reverse_path("organization-me"), "get"),
            (self._reverse_path("organization-me"), "patch"),
            (self._reverse_path("organization-me"), "delete"),
        )

        for path, method in private_operations:
            with self.subTest(path=path, method=method):
                operation = self._get_operation(path, method)
                self.assertEqual(operation.get("security"), [{"jwtAuth": []}])

    def test_schema_uses_project_version_from_version_file(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        expected_version = (core_settings.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(schema["info"]["version"], expected_version)

    def test_schema_declares_tags_in_expected_order(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)

        self.assertEqual(
            [tag["name"] for tag in schema.get("tags", [])],
            [
                "Auth",
                "Catalog",
                "Announcements",
                "Organizations",
                "Services",
                "Management / Users",
                "Management / Organizations",
                "Management / Jobs",
                "Management / Feature Flags",
                "Management / Categories",
                "Management / Allowed Cities",
                "RGPD",
            ],
        )

    def test_management_users_list_documents_search_and_filter_query_params(self):
        operation = self._get_operation("/api/management/users/", "get")

        parameter_names = {parameter["name"] for parameter in operation.get("parameters", [])}

        self.assertTrue({"search", "status", "email_verified"}.issubset(parameter_names))

    def test_schema_groups_endpoints_by_domain_tags(self):
        tagged_operations = (
            ("/api/auth/login/", "post", ["Auth"]),
            ("/api/categories/", "get", ["Catalog"]),
            (
                "/api/announcements/{announcement_uuid}/subservices/",
                "get",
                ["Services"],
            ),
            ("/api/services/", "get", ["Catalog"]),
            ("/api/announcements/", "get", ["Announcements"]),
            ("/api/management/users/", "get", ["Management / Users"]),
        )

        for path, method, expected_tags in tagged_operations:
            with self.subTest(path=path, method=method):
                operation = self._get_operation(path, method)
                self.assertEqual(operation.get("tags"), expected_tags)

    def test_schema_does_not_expose_organization_search_endpoint(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)

        self.assertNotIn("/api/organizations/search/", schema["paths"])

    def test_schema_exposes_only_get_for_organization_detail(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)

        self.assertEqual(set(schema["paths"]["/api/organizations/{uuid}/"].keys()), {"get"})


class ApiDocsRoutingTests(SimpleTestCase):
    def _reload_urlconf(self):
        from Core import urls as core_urls

        clear_url_caches()
        importlib.reload(core_urls)

    @override_settings(HIDE_API_DOCS=False)
    def test_docs_routes_are_registered_when_not_hidden(self):
        self._reload_urlconf()
        self.assertEqual(reverse("api-schema"), "/api/schema/")
        self.assertEqual(reverse("api-docs"), "/api/docs/")

    @override_settings(HIDE_API_DOCS=False)
    def test_docs_route_resolves_to_swagger_view(self):
        self._reload_urlconf()

        match = resolve("/api/docs/")

        self.assertIs(match.func.view_class, SpectacularSwaggerView)

    @override_settings(HIDE_API_DOCS=False)
    def test_job_routes_keep_jobs_prefix(self):
        self._reload_urlconf()
        self.assertEqual(
            reverse("job-detail", kwargs={"uuid": "11111111-1111-1111-1111-111111111111"}),
            "/api/jobs/11111111-1111-1111-1111-111111111111/",
        )

    @override_settings(HIDE_API_DOCS=True)
    def test_docs_routes_are_not_registered_when_hidden(self):
        self._reload_urlconf()
        try:
            with self.assertRaises(NoReverseMatch):
                reverse("api-schema")
            with self.assertRaises(NoReverseMatch):
                reverse("api-docs")
        finally:
            self._reload_urlconf()


class VersionEndpointTests(SimpleTestCase):
    def test_api_version_endpoint_returns_version_file_value(self):
        expected_version = (core_settings.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()

        response = self.client.get(reverse("api-version"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"version": expected_version})

    def test_schema_exposes_api_version_endpoint(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)

        self.assertIn("/api/version/", schema["paths"])
        self.assertIn("get", schema["paths"]["/api/version/"])


def _iter_view_classes(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _iter_view_classes(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            view_class = getattr(pattern.callback, "cls", None)
            if view_class is not None:
                yield view_class


class ThrottleScopeConfigurationTests(SimpleTestCase):
    def test_every_scope_used_by_an_action_scoped_view_has_a_rate(self):
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        missing = set()
        checked = 0
        for view_class in set(_iter_view_classes(get_resolver().url_patterns)):
            prefix = getattr(view_class, "throttle_scope_prefix", None)
            if prefix is None:
                continue
            checked += 1
            scopes = set(view_class.throttle_scope_action_map.values()) | {f"{prefix}_default"}
            missing |= {f"{view_class.__name__}: {scope}" for scope in scopes if scope not in rates}

        self.assertGreater(checked, 10)
        self.assertEqual(missing, set())


class AnonymousAccessSurfaceTests(TestCase):
    """Pins the set of API operations that answer anonymous requests.

    Every other operation in the OpenAPI schema must return 401 to an anonymous
    caller. Adding a public endpoint means adding it here on purpose.
    """

    PUBLIC_OPERATIONS = {
        ("get", "/api/allowed-cities/"),
        ("get", "/api/announcements/"),
        ("get", "/api/announcements/{uuid}/"),
        ("get", "/api/announcements/{uuid}/images/{image_uuid}/base64/"),
        ("get", "/api/announcements/{announcement_uuid}/subservices/"),
        ("get", "/api/announcements/{announcement_uuid}/subservices/{subservice_uuid}/"),
        ("get", "/api/announcements/{announcement_uuid}/subservices/{subservice_uuid}/prices/"),
        ("get", "/api/announcements/{announcement_uuid}/subservices/{subservice_uuid}/prices/{price_uuid}/"),
        ("get", "/api/categories/"),
        ("get", "/api/organizations/{uuid}/"),
        ("get", "/api/plan-tiers/"),
        ("get", "/api/rgpd/documents/"),
        ("get", "/api/rgpd/documents/active/"),
        ("get", "/api/schema/"),
        ("get", "/api/services/"),
        ("get", "/api/services/{category_uuid}/"),
        ("get", "/api/version/"),
        ("post", "/api/auth/login/"),
        ("post", "/api/auth/logout/"),
        ("post", "/api/auth/register/"),
        ("post", "/api/auth/token/refresh/"),
        ("post", "/api/auth/verify-email/"),
        ("post", "/api/rgpd/anonymous/"),
    }

    def test_only_allowlisted_operations_are_reachable_anonymously(self):
        client = APIClient()
        schema = SchemaGenerator().get_schema(request=None, public=True)
        reachable = set()
        for path, methods in schema["paths"].items():
            concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
            for method in methods:
                if method == "parameters":
                    continue
                response = getattr(client, method)(concrete, {}, format="json")
                if response.status_code != 401:
                    reachable.add((method, path))

        self.assertEqual(reachable, self.PUBLIC_OPERATIONS)

    def test_views_are_private_unless_they_opt_out(self):
        from rest_framework.settings import api_settings

        from common.permissions import IsActiveAccount

        self.assertEqual(api_settings.DEFAULT_PERMISSION_CLASSES, [IsActiveAccount])
