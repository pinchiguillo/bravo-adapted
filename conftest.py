import boto3
import pytest
from django.conf import settings
from django.core.cache import caches
from moto import mock_aws


@pytest.fixture(scope="session", autouse=True)
def aws():
    """Mock S3 and SES for the whole session and create the configured buckets."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=settings.AWS_DEFAULT_REGION)
        for bucket in {settings.AWS_STORAGE_BUCKET_NAME, settings.AWS_LEGAL_DOCUMENTS_BUCKET_NAME}:
            s3.create_bucket(Bucket=bucket)
        ses = boto3.client("ses", region_name=settings.AWS_DEFAULT_REGION)
        ses.verify_email_identity(EmailAddress=settings.DEFAULT_FROM_EMAIL)
        yield


@pytest.fixture(autouse=True)
def clear_caches():
    """Throttle counters live in the cache; never let them leak between tests."""
    for cache in caches.all(initialized_only=True):
        cache.clear()
