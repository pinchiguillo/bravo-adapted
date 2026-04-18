import uuid

from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from ..models import Organization

service_price_uuid_parameter = OpenApiParameter(
    name="price_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="Service price identifier.",
)

organization_uuid_parameter = OpenApiParameter(
    name="organization_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the organization that owns the nested resource.",
)

announcement_uuid_parameter = OpenApiParameter(
    name="uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the announcement.",
)

announcement_nested_uuid_parameter = OpenApiParameter(
    name="announcement_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the announcement that owns the nested resource.",
)

service_uuid_parameter = OpenApiParameter(
    name="service_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the service that owns the nested subservice.",
)

subservice_uuid_parameter = OpenApiParameter(
    name="subservice_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the subservice.",
)

category_uuid_parameter = OpenApiParameter(
    name="category_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    required=True,
    description="UUID of the category.",
)

announcement_category_parameter = OpenApiParameter(
    name="category",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Single category UUID filter kept for backwards compatibility.",
)

announcement_uuid_query_parameter = OpenApiParameter(
    name="uuid",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Single announcement UUID filter.",
)

announcement_organization_parameter = OpenApiParameter(
    name="organization",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Single organization UUID filter.",
)

announcement_organizations_parameter = OpenApiParameter(
    name="organizations",
    type={"type": "array", "items": {"type": "string", "format": "uuid"}},
    location=OpenApiParameter.QUERY,
    required=False,
    explode=True,
    style="form",
    description="Optional list of organization UUIDs used to filter announcements.",
)

announcement_service_parameter = OpenApiParameter(
    name="service",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Single service catalog UUID filter.",
)

announcement_services_parameter = OpenApiParameter(
    name="services",
    type={"type": "array", "items": {"type": "string", "format": "uuid"}},
    location=OpenApiParameter.QUERY,
    required=False,
    explode=True,
    style="form",
    description="Optional list of service catalog UUIDs used to filter announcements.",
)

announcement_status_parameter = OpenApiParameter(
    name="status",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Single announcement status filter.",
)

announcement_statuses_parameter = OpenApiParameter(
    name="statuses",
    type={"type": "array", "items": {"type": "string"}},
    location=OpenApiParameter.QUERY,
    required=False,
    explode=True,
    style="form",
    description="Optional list of announcement statuses used to filter announcements.",
)

announcement_name_parameter = OpenApiParameter(
    name="name",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional text used to filter announcements by name.",
)

announcement_location_parameter = OpenApiParameter(
    name="location",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional text used to filter announcements by location.",
)

announcement_text_parameter = OpenApiParameter(
    name="title",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional text used to filter announcements by title.",
)

announcement_description_parameter = OpenApiParameter(
    name="description",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional text used to filter announcements by description.",
)

announcement_free_text_parameter = OpenApiParameter(
    name="free_text",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional text used to filter announcements by free text.",
)

announcement_has_coordinates_parameter = OpenApiParameter(
    name="has_coordinates",
    type=bool,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional boolean filter to include only announcements with or without coordinates.",
)

announcement_search_parameter = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description="Optional text used to filter announcements by their visible text fields.",
)

announcement_categories_parameter = OpenApiParameter(
    name="categories",
    type={"type": "array", "items": {"type": "string", "format": "uuid"}},
    location=OpenApiParameter.QUERY,
    required=False,
    explode=True,
    style="form",
    description="Optional list of category UUIDs used to filter announcements.",
)
class OrganizationVisibilityMixin:
    def get_url_organization(self):
        organization_uuid = self.kwargs.get("organization_uuid")
        if organization_uuid is None:
            return None
        organization = Organization.objects.select_related("user").filter(uuid=organization_uuid).first()
        if organization is None:
            raise NotFound("Organization not found.")
        return organization

    def can_access_unapproved_organization(self, organization):
        user = getattr(self.request, "user", None)
        return bool(
            organization.is_validated
            or (
                user is not None
                and user.is_authenticated
                and (user.is_staff or organization.user_id == user.id)
            )
        )

    def require_visible_organization(self):
        organization = self.get_url_organization()
        if organization is None:
            return None
        if not self.can_access_unapproved_organization(organization):
            raise NotFound("Organization not found.")
        return organization

    def ensure_organization_is_approved_for_write(self, organization):
        if getattr(settings, "BYPASS_ORGANIZATION_VALIDATION", False):
            return
        if not organization.is_validated:
            raise PermissionDenied("Organization must be approved for this action.")


class AnnouncementQueryParamFilterMixin:
    text_filter_fields = {}

    def _get_filter_values(self, single_param, multi_param):
        raw_values = self.request.query_params.getlist(multi_param)
        if not raw_values:
            single_value = str(self.request.query_params.get(single_param, "")).strip()
            return [single_value] if single_value else []

        values = []
        for raw_value in raw_values:
            for part in str(raw_value).split(","):
                normalized_value = part.strip()
                if normalized_value:
                    values.append(normalized_value)
        return values

    def _get_text_filter_value(self, param_name):
        return str(self.request.query_params.get(param_name, "")).strip()

    def _get_boolean_filter_value(self, param_name):
        raw_value = str(self.request.query_params.get(param_name, "")).strip().lower()
        if not raw_value:
            return None
        if raw_value in {"true", "1", "yes"}:
            return True
        if raw_value in {"false", "0", "no"}:
            return False
        raise ValidationError({param_name: "Use a boolean value: true or false."})

    def _apply_uuid_filters(self, queryset, filter_map):
        for single_param, multi_param, lookup in filter_map:
            values = self._get_filter_values(single_param, multi_param)
            if values:
                queryset = queryset.filter(**{f"{lookup}__in": values})
        return queryset

    def _apply_text_filters(self, queryset):
        for param_name, field_name in self.text_filter_fields.items():
            value = self._get_text_filter_value(param_name)
            if value:
                queryset = queryset.filter(**{f"{field_name}__icontains": value})
        return queryset

    def _apply_has_coordinates_filter(self, queryset):
        has_coordinates = self._get_boolean_filter_value("has_coordinates")
        if has_coordinates is None:
            return queryset
        if has_coordinates:
            return queryset.filter(latitude__isnull=False, longitude__isnull=False)
        return queryset.filter(latitude__isnull=True, longitude__isnull=True)

    def _apply_search_filter(self, queryset, search_fields, uuid_fields):
        search_query = self._get_text_filter_value("search")
        if not search_query:
            return queryset

        search_filter = Q()
        for field_name in search_fields:
            search_filter |= Q(**{f"{field_name}__icontains": search_query})

        search_uuid = self._parse_uuid(search_query)
        if search_uuid is not None:
            for field_name in uuid_fields:
                search_filter |= Q(**{field_name: search_uuid})

        return queryset.filter(search_filter)

    def _parse_uuid(self, raw_value):
        try:
            return uuid.UUID(raw_value)
        except (TypeError, ValueError, AttributeError):
            return None


class AnnouncementPublicFilterMixin(AnnouncementQueryParamFilterMixin):
    public_search_fields = (
        "name",
        "location",
        "announcement",
        "description",
        "free_text",
        "organization__name",
        "category__name",
        "subservices__service_catalog__name",
    )
    public_search_uuid_fields = (
        "uuid",
        "organization__uuid",
        "category__uuid",
        "subservices__service_catalog__uuid",
    )
    text_filter_fields = {
        "name": "name",
        "location": "location",
        "title": "announcement",
        "description": "description",
        "free_text": "free_text",
    }

    def filter_announcements(self, queryset):
        queryset = self._apply_uuid_filters(
            queryset,
            (
                ("uuid", "uuids", "uuid"),
                ("organization", "organizations", "organization__uuid"),
                ("category", "categories", "category__uuid"),
                ("service", "services", "subservices__service_catalog__uuid"),
            ),
        )
        queryset = self._apply_text_filters(queryset)
        queryset = self._apply_has_coordinates_filter(queryset)
        queryset = self._apply_search_filter(
            queryset,
            self.public_search_fields,
            self.public_search_uuid_fields,
        )
        return queryset.distinct()
