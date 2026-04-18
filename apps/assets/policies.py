from django.conf import settings


def get_kind_rules(kind: str) -> dict:
    """Return upload policy rules for a given asset kind."""
    rules = {
        "announcement_image": {
            "visibility": "public",
            "max_size": settings.ORGANIZATION_ANNOUNCEMENT_IMAGE_MAX_BYTES,
            "allowed_content_types": set(settings.ORGANIZATION_ANNOUNCEMENT_IMAGE_ALLOWED_CONTENT_TYPES),
            "ttl_seconds": settings.ORGANIZATION_ANNOUNCEMENT_IMAGE_UPLOAD_URL_TTL_SECONDS,
            "pending_max_age_seconds": settings.ORGANIZATION_ANNOUNCEMENT_IMAGE_PENDING_MAX_AGE_SECONDS,
        },
        "job_chat_attachment": {
            "visibility": "protected",
            "max_size": settings.JOB_CHAT_ATTACHMENT_MAX_BYTES,
            "allowed_content_types": set(settings.JOB_CHAT_ATTACHMENT_ALLOWED_CONTENT_TYPES),
            "ttl_seconds": settings.JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS,
            "pending_max_age_seconds": 3600,
        },
        "legal_document": {
            "visibility": "private",
            "max_size": settings.LEGAL_DOCUMENT_MAX_BYTES,
            "allowed_content_types": set(settings.LEGAL_DOCUMENT_ALLOWED_CONTENT_TYPES),
            "ttl_seconds": 300,
            "pending_max_age_seconds": 3600,
        },
        "generic_upload": {
            "visibility": "public",
            "max_size": 10 * 1024 * 1024,
            "allowed_content_types": set(),  # empty = no restriction
            "ttl_seconds": 300,
            "pending_max_age_seconds": 3600,
        },
    }
    return rules[kind]
