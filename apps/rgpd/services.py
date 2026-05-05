from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from .models import (
    RgpdAnonymousConsent,
    RgpdConsent,
    RgpdDataRequest,
    RgpdPolicyAcceptance,
    RgpdPolicyDocument,
    RgpdPolicyVersion,
)

CONSENT_FIELD_TO_POLICY_TYPE = {
    "privacy_policy_accepted": RgpdPolicyDocument.DocumentType.PRIVACY_POLICY,
    "terms_and_conditions_accepted": RgpdPolicyDocument.DocumentType.TERMS_AND_CONDITIONS,
    "cookies_accepted": RgpdPolicyDocument.DocumentType.COOKIES_POLICY,
}

CONSENT_VERSION_FIELDS = {
    "privacy_policy_accepted": "privacy_policy_version",
    "terms_and_conditions_accepted": "terms_and_conditions_version",
    "cookies_accepted": "cookies_version",
}

REQUIRED_POLICY_TYPES = (
    RgpdPolicyDocument.DocumentType.PRIVACY_POLICY,
    RgpdPolicyDocument.DocumentType.TERMS_AND_CONDITIONS,
)


@dataclass(frozen=True)
class PolicyAcceptanceSnapshot:
    accepted: bool
    accepted_at: str | None
    version: str
    title: str | None
    published_at: str | None


def is_rgpd_installed():
    return django_apps.is_installed("apps.rgpd")


def get_current_policy_versions():
    versions = (
        RgpdPolicyVersion.objects.select_related("document")
        .filter(is_published=True, is_current=True)
        .all()
    )
    return {
        version.document.document_type: version
        for version in versions
    }


def get_current_policy_version(document_type):
    return get_current_policy_versions().get(document_type)


def get_missing_required_policy_types():
    active_versions = get_current_policy_versions()
    return [
        document_type
        for document_type in REQUIRED_POLICY_TYPES
        if document_type not in active_versions
    ]


def get_policy_acceptances_for_subject(*, user=None, anonymous_consent=None):
    queryset = RgpdPolicyAcceptance.objects.select_related("policy_version__document")
    if user is not None:
        queryset = queryset.filter(user=user)
    elif anonymous_consent is not None:
        queryset = queryset.filter(anonymous_consent=anonymous_consent)
    else:
        return {}

    acceptances = {}
    for acceptance in queryset.order_by("-accepted_at", "-id"):
        document_type = acceptance.policy_version.document.document_type
        acceptances.setdefault(document_type, acceptance)
    return acceptances


def build_policy_acceptance_snapshot(*, user=None, anonymous_consent=None):
    current_versions = get_current_policy_versions()
    acceptances = get_policy_acceptances_for_subject(
        user=user,
        anonymous_consent=anonymous_consent,
    )
    snapshot = {}

    for document_type in RgpdPolicyDocument.DocumentType.values:
        acceptance = acceptances.get(document_type)
        current_version = current_versions.get(document_type)
        snapshot[document_type] = {
            "accepted": (
                acceptance is not None
                and current_version is not None
                and acceptance.policy_version_id == current_version.id
            ),
            "accepted_at": (
                acceptance.accepted_at.isoformat().replace("+00:00", "Z")
                if acceptance is not None
                else None
            ),
            "version": current_version.version if current_version is not None else "",
            "title": current_version.title if current_version is not None else "",
            "published_at": (
                current_version.published_at.isoformat().replace("+00:00", "Z")
                if current_version is not None and current_version.published_at is not None
                else None
            ),
        }

    required_documents = []
    for document_type in REQUIRED_POLICY_TYPES:
        current_version = current_versions.get(document_type)
        required_documents.append(
            {
                "type": document_type,
                "version": current_version.version if current_version is not None else "",
                "title": current_version.title if current_version is not None else "",
                "published_at": (
                    current_version.published_at.isoformat().replace("+00:00", "Z")
                    if current_version is not None and current_version.published_at is not None
                    else None
                ),
            }
        )

    requires_reacceptance = any(
        not snapshot[document_type]["accepted"] for document_type in REQUIRED_POLICY_TYPES
    )

    return {
        "accepted_documents": snapshot,
        "required_documents": required_documents,
        "requires_reacceptance": requires_reacceptance,
    }


def apply_current_policy_versions_to_snapshot(validated_data):
    current_versions = get_current_policy_versions()
    for boolean_field, document_type in CONSENT_FIELD_TO_POLICY_TYPE.items():
        if boolean_field not in validated_data:
            continue

        version_field = CONSENT_VERSION_FIELDS[boolean_field]
        if validated_data[boolean_field]:
            current_version = current_versions.get(document_type)
            if current_version is None:
                raise ValueError(f"Missing published current policy version for {document_type}.")
            validated_data[version_field] = current_version.version
        else:
            validated_data[version_field] = ""

    return current_versions


def record_policy_acceptances(*, validated_data, source="", ip_address=None, user_agent="", user=None, anonymous_consent=None):
    current_versions = apply_current_policy_versions_to_snapshot(validated_data)
    now = timezone.now()

    acceptances_to_create = []
    for boolean_field, document_type in CONSENT_FIELD_TO_POLICY_TYPE.items():
        if validated_data.get(boolean_field) is not True:
            continue

        current_version = current_versions[document_type]
        filters = {
            "policy_version": current_version,
        }
        if user is not None:
            filters["user"] = user
        else:
            filters["anonymous_consent"] = anonymous_consent

        if RgpdPolicyAcceptance.objects.filter(**filters).exists():
            continue

        acceptances_to_create.append(
            RgpdPolicyAcceptance(
                user=user,
                anonymous_consent=anonymous_consent,
                policy_version=current_version,
                source=source[:64],
                ip_address=ip_address,
                user_agent=user_agent,
                accepted_at=now,
            )
        )

    if acceptances_to_create:
        RgpdPolicyAcceptance.objects.bulk_create(acceptances_to_create)


@transaction.atomic
def create_user_rgpd_consent(*, user, consent_data, ip_address=None, user_agent=""):
    consent, _ = RgpdConsent.objects.get_or_create(user=user)
    validated_data = dict(consent_data)
    validated_data["ip_address"] = ip_address
    validated_data["user_agent"] = user_agent
    consent.apply_acceptance_changes(validated_data)
    consent.save()
    from .models import RgpdConsentEvent

    action = RgpdConsentEvent.Action.UPSERT if consent.events.exists() else RgpdConsentEvent.Action.CREATE
    RgpdConsentEvent.objects.create(
        consent=consent,
        action=action,
        **consent.build_event_payload(),
    )
    record_policy_acceptances(
        validated_data=validated_data,
        source=validated_data.get("source", ""),
        ip_address=ip_address,
        user_agent=user_agent,
        user=user,
    )
    return consent


def publish_policy_version(policy_version):
    with transaction.atomic():
        RgpdPolicyVersion.objects.filter(document=policy_version.document).exclude(
            pk=policy_version.pk
        ).update(is_current=False)
        policy_version.is_published = True
        policy_version.is_current = True
        policy_version.published_at = timezone.now()
        policy_version.save(update_fields=["is_published", "is_current", "published_at", "updated_at"])
    return policy_version


def set_data_request_status(*, data_request, status_value, resolved_by=None, resolution_notes=None):
    data_request.status = status_value
    if resolution_notes is not None:
        data_request.resolution_notes = resolution_notes

    if status_value in {RgpdDataRequest.Status.COMPLETED, RgpdDataRequest.Status.REJECTED}:
        data_request.resolved_at = timezone.now()
        data_request.resolved_by = resolved_by
    else:
        data_request.resolved_at = None
        data_request.resolved_by = None

    data_request.save(
        update_fields=[
            "status",
            "resolution_notes",
            "resolved_at",
            "resolved_by",
            "updated_at",
        ]
    )
    return data_request
