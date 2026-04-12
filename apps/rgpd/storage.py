from django.conf import settings
from storages.backends.s3 import S3Storage


class LegalDocumentsStorage(S3Storage):
    bucket_name = settings.AWS_LEGAL_DOCUMENTS_BUCKET_NAME
    default_acl = None
    file_overwrite = False
    querystring_auth = True
