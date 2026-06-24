#!/usr/bin/env python3
"""
Count unique ads for monitor report.json.

Shared with the Pro1-Os monitor hub — keep in sync when the hub copy changes.
"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any

import pandas as pd

SKIP_SHEETS = frozenset({"info", "no data"})
ID_COLUMN_ALIASES = frozenset(
    {
        "id",
        "listing id",
        "listing_id",
        "user adv id",
        "user_adv_id",
        "ad id",
        "ad_id",
    }
)
JSON_COUNT_KEYS = ("total_listings", "total_ads", "listings_count")


def _norm_col(name: Any) -> str:
    if name is None:
        return ""
    return str(name).strip().lower().replace("_", " ")


def _should_skip_sheet(name: str) -> bool:
    lower = name.strip().lower()
    return lower in SKIP_SHEETS or name in ("Info", "No Data")


def _find_id_column(columns: list[Any]) -> str | None:
    for col in columns:
        if _norm_col(col) in ID_COLUMN_ALIASES:
            return col
    return None


def _count_from_excel_files(
    excel_downloads: list[tuple[str, bytes]],
) -> tuple[int, int, str | None]:
    """Return (unique_ads, total_rows, source) from Excel bytes."""
    all_ids: set[str] = set()
    total_rows = 0
    saw_id_column = False

    for _key, raw in excel_downloads:
        try:
            sheets = pd.read_excel(BytesIO(raw), sheet_name=None, engine="openpyxl")
        except Exception:
            continue

        for sheet_name, df in sheets.items():
            if _should_skip_sheet(sheet_name):
                continue
            if df is None or df.empty:
                continue

            n = len(df)
            total_rows += n
            id_col = _find_id_column(list(df.columns))
            if id_col is None:
                continue

            saw_id_column = True
            for val in df[id_col].dropna():
                text = str(val).strip()
                if text:
                    all_ids.add(text)

    if saw_id_column and all_ids:
        return len(all_ids), total_rows, "excel_ids"
    if total_rows > 0:
        return total_rows, total_rows, "excel_rows"
    return 0, 0, None


def _extract_count_from_json(data: dict) -> int | None:
    for key in JSON_COUNT_KEYS:
        val = data.get(key)
        if isinstance(val, (int, float)) and val >= 0:
            return int(val)

    subcats = data.get("subcategories") or data.get("categories") or []
    if not isinstance(subcats, list) or not subcats:
        return None

    total = 0
    found = False
    for item in subcats:
        if not isinstance(item, dict):
            continue
        for key in ("listings_count", "count", "total"):
            val = item.get(key)
            if isinstance(val, (int, float)) and val >= 0:
                total += int(val)
                found = True
                break
    return total if found else None


def _list_json_keys(client, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".json"):
                keys.append(key)
    return keys


def _count_from_json_summaries(
    client,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
) -> int | None:
    partition = (
        f"year={partition_dt.year}/month={partition_dt.month:02d}/day={partition_dt.day:02d}"
    )
    prefixes = [
        f"{r2_base}/{partition}/json-files/",
        f"{r2_base}/{partition}/json files/",
    ]

    counts: list[int] = []
    for prefix in prefixes:
        for key in _list_json_keys(client, bucket, prefix):
            try:
                resp = client.get_object(Bucket=bucket, Key=key)
                data = json.loads(resp["Body"].read())
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            count = _extract_count_from_json(data)
            if count is not None:
                counts.append(count)

    if not counts:
        return None
    return sum(counts)


def count_scraper_ads(
    r2_client,
    bucket: str,
    r2_base: str,
    partition_dt: datetime,
    excel_downloads: list[tuple[str, bytes]],
) -> dict:
    """
    Count unique ads for one scraper partition.

    Priority: excel_ids → json_summary → excel_rows → none
    """
    unique, total_rows, excel_source = _count_from_excel_files(excel_downloads)
    if excel_source == "excel_ids":
        return {
            "unique_ads": unique,
            "total_rows": total_rows,
            "ads_source": "excel_ids",
        }

    json_count = _count_from_json_summaries(r2_client, bucket, r2_base, partition_dt)
    if json_count is not None:
        return {
            "unique_ads": json_count,
            "total_rows": total_rows or json_count,
            "ads_source": "json_summary",
        }

    if excel_source == "excel_rows":
        return {
            "unique_ads": unique,
            "total_rows": total_rows,
            "ads_source": "excel_rows",
        }

    return {"unique_ads": 0, "total_rows": 0, "ads_source": "none"}
