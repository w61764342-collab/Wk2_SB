import os
import boto3
from botocore.config import Config

BUCKET = os.environ["CF_R2_BUCKET_NAME"]
ENDPOINT = os.environ["CF_R2_ENDPOINT_URL"]

client = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"],
    config=Config(signature_version="s3v4"),
    region_name="auto",
)

# Get top-level folders
response = client.list_objects_v2(
    Bucket=BUCKET,
    Delimiter="/",
)

folders = [p["Prefix"] for p in response.get("CommonPrefixes", [])]

if not folders:
    print("No folders found.")
    exit(0)

print(f"{'Folder':40} {'Files':>10}")
print("-" * 55)

for folder in folders:
    paginator = client.get_paginator("list_objects_v2")

    total = 0

    for page in paginator.paginate(
        Bucket=BUCKET,
        Prefix=folder,
    ):
        total += len(page.get("Contents", []))

    # Ignore folder marker if it exists
    if total > 0:
        total -= 1

    print(f"{folder:40} {total:10}")