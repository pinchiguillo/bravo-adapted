#!/bin/sh
set -eu

region="${AWS_DEFAULT_REGION:-us-east-1}"
bucket="${AWS_STORAGE_BUCKET_NAME:-bravo-media}"
legal_bucket="${AWS_LEGAL_DOCUMENTS_BUCKET_NAME:-${bucket}-legal}"
sender="${DEFAULT_FROM_EMAIL:-no-reply@bravo.local}"

create_bucket_if_missing() {
  target_bucket="$1"
  if ! awslocal s3api head-bucket --bucket "$target_bucket" >/dev/null 2>&1; then
    if [ "$region" = "us-east-1" ]; then
      awslocal s3api create-bucket --bucket "$target_bucket"
    else
      awslocal s3api create-bucket \
        --bucket "$target_bucket" \
        --create-bucket-configuration "LocationConstraint=$region"
    fi
  fi
}

create_bucket_if_missing "$bucket"
create_bucket_if_missing "$legal_bucket"

awslocal ses verify-email-identity --email-address "$sender" >/dev/null

echo "LocalStack bootstrap ready (S3 buckets: $bucket, $legal_bucket; SES sender: $sender)"
