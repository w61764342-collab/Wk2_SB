import os
import io
import argparse
from collections import defaultdict

import boto3
import pandas as pd


# -------------------------------------------------
# Arguments
# -------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--date", required=True, help="YYYY-MM-DD")
args = parser.parse_args()

year, month, day = args.date.split("-")

# -------------------------------------------------
# Cloudflare R2
# -------------------------------------------------
ACCESS_KEY = os.environ["CF_R2_ACCESS_KEY_ID"]
SECRET_KEY = os.environ["CF_R2_SECRET_ACCESS_KEY"]
ENDPOINT = os.environ["CF_R2_ENDPOINT_URL"]
BUCKET = os.environ["CF_R2_BUCKET_NAME"]

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
)

# -------------------------------------------------
# Statistics
# -------------------------------------------------
overall = {
    "files": 0,
    "sheets": 0,
    "total_ads": 0,
    "total_phones": 0,
    "ids": set(),
    "phones": set(),
}

categories = defaultdict(
    lambda: {
        "files": 0,
        "sheets": 0,
        "total_ads": 0,
        "total_phones": 0,
        "ids": set(),
        "phones": set(),
    }
)

# -------------------------------------------------
# List all Excel files
# -------------------------------------------------
prefix = "4sale-data/"

continuation_token = None

while True:

    kwargs = {
        "Bucket": BUCKET,
        "Prefix": prefix,
    }

    if continuation_token:
        kwargs["ContinuationToken"] = continuation_token

    response = s3.list_objects_v2(**kwargs)

    for obj in response.get("Contents", []):

        key = obj["Key"]

        if (
            f"year={year}/month={month}/day={day}/" not in key
        ):
            continue

        if not key.lower().endswith((".xlsx", ".xls")):
            continue

        parts = key.split("/")

        if len(parts) < 2:
            continue

        category = parts[1]

        print(f"Processing: {key}")

        categories[category]["files"] += 1
        overall["files"] += 1

        try:
            file = s3.get_object(Bucket=BUCKET, Key=key)
            data = io.BytesIO(file["Body"].read())

            excel = pd.ExcelFile(data)

            for sheet in excel.sheet_names:

                categories[category]["sheets"] += 1
                overall["sheets"] += 1

                try:
                    df = pd.read_excel(excel, sheet_name=sheet)

                except Exception as e:
                    print(f"Cannot read sheet {sheet}: {e}")
                    continue

                cols = {c.lower().strip(): c for c in df.columns}

                if "id" not in cols or "phone" not in cols:
                    continue

                id_col = cols["id"]
                phone_col = cols["phone"]

                ids = (
                    df[id_col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                )

                phones = (
                    df[phone_col]
                    .dropna()
                    .astype(str)
                    .str.strip()
                )

                overall["total_ads"] += len(ids)
                overall["total_phones"] += len(phones)

                categories[category]["total_ads"] += len(ids)
                categories[category]["total_phones"] += len(phones)

                overall["ids"].update(ids)
                overall["phones"].update(phones)

                categories[category]["ids"].update(ids)
                categories[category]["phones"].update(phones)

        except Exception as e:
            print(e)

    if response.get("IsTruncated"):
        continuation_token = response["NextContinuationToken"]
    else:
        break

# -------------------------------------------------
# Print report
# -------------------------------------------------
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"Date              : {args.date}")
print(f"Files             : {overall['files']}")
print(f"Sheets            : {overall['sheets']}")
print()

print(f"Total Ads         : {overall['total_ads']:,}")
print(f"Unique Ads        : {len(overall['ids']):,}")
print()

print(f"Total Phones      : {overall['total_phones']:,}")
print(f"Unique Phones     : {len(overall['phones']):,}")

print()
print("=" * 70)
print("PER CATEGORY")
print("=" * 70)

for cat in sorted(categories.keys()):

    s = categories[cat]

    print()
    print(cat)
    print("-" * len(cat))
    print(f"Files             : {s['files']}")
    print(f"Sheets            : {s['sheets']}")
    print(f"Total Ads         : {s['total_ads']:,}")
    print(f"Unique Ads        : {len(s['ids']):,}")
    print(f"Total Phones      : {s['total_phones']:,}")
    print(f"Unique Phones     : {len(s['phones']):,}")