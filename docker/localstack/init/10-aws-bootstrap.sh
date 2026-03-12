#!/bin/sh
set -eu

region="${AWS_DEFAULT_REGION:-us-east-1}"
bucket="${AWS_STORAGE_BUCKET_NAME:-bravo-media}"
sender="${DEFAULT_FROM_EMAIL:-no-reply@bravo.local}"

if ! awslocal s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
  if [ "$region" = "us-east-1" ]; then
    awslocal s3api create-bucket --bucket "$bucket"
  else
    awslocal s3api create-bucket \
      --bucket "$bucket" \
      --create-bucket-configuration "LocationConstraint=$region"
  fi
fi

awslocal ses verify-email-identity --email-address "$sender" >/dev/null

echo "LocalStack bootstrap ready (S3 bucket: $bucket, SES sender: $sender)"
