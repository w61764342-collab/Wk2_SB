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
PHONE_COLUMN_ALIASES = frozenset(
    {
        "mobile number",
        "mobile_number",
        "telephone",
        "phone",
        "phone number",
        "contact number",
        "whatsapp",
    }
)
PUBLISHED_COLUMN_ALIASES = frozenset(
    {
        "date published",
        "date_published",
        "published at",
        "published_at",
    }
)
LEVEL3_COLUMN_ALIASES = frozenset({"level 3", "level_3", "brand", "model"})


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


def _find_col_by_alias(columns: list[Any], aliases: frozenset[str]) -> str | None:
    for col in columns:
        if _norm_col(col) in aliases:
            return col
    return None


def _normalize_phone(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 6:
        return ""
    return digits


def _extract_hour(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return int(value.hour)
    if hasattr(value, "hour") and isinstance(getattr(value, "hour", None), int):
        return int(value.hour)

    text = str(value).strip()
    if not text:
        return None

    # Fast path for HH:MM(:SS) patterns without pandas parsing overhead.
    import re

    m = re.search(r"\b([01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\b", text)
    if m:
        return int(m.group(1))

    # Try explicit known formats first to avoid parser warnings/noise.
    for fmt in (
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if not pd.isna(parsed):
            return int(parsed.hour)

    # Fallback for other parsable variants. dayfirst=True matches dd-mm-yyyy data.
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return int(parsed.hour)


def _peak_from_hourly(hourly: dict[int, int]) -> tuple[int | None, int]:
    if not hourly:
        return None, 0
    peak_hour = min(hourly.keys())
    peak_ads = -1
    for hour, count in hourly.items():
        if count > peak_ads or (count == peak_ads and hour < peak_hour):
            peak_hour = hour
            peak_ads = count
    return peak_hour, peak_ads


def _count_from_excel_files(
    excel_downloads: list[tuple[str, bytes]],
) -> dict:
    """Return ad/phone/hierarchy metrics from Excel bytes."""
    all_ids: set[str] = set()
    all_phones: set[str] = set()
    total_rows = 0
    saw_id_column = False
    subcategory_breakdown: list[dict[str, Any]] = []
    scraper_hourly: dict[int, int] = {}

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

            columns = list(df.columns)
            id_col = _find_id_column(columns)
            phone_col = _find_col_by_alias(columns, PHONE_COLUMN_ALIASES)
            date_col = _find_col_by_alias(columns, PUBLISHED_COLUMN_ALIASES)
            level3_col = _find_col_by_alias(columns, LEVEL3_COLUMN_ALIASES)

            sheet_ids: set[str] = set()
            if id_col is not None:
                saw_id_column = True
                for val in df[id_col].dropna():
                    text = str(val).strip()
                    if text:
                        sheet_ids.add(text)
                        all_ids.add(text)

            sheet_phones: set[str] = set()
            if phone_col is not None:
                for val in df[phone_col].dropna():
                    phone = _normalize_phone(val)
                    if phone:
                        sheet_phones.add(phone)
                        all_phones.add(phone)

            sheet_hourly: dict[int, int] = {}
            if date_col is not None:
                for val in df[date_col].dropna():
                    hour = _extract_hour(val)
                    if hour is None:
                        continue
                    sheet_hourly[hour] = sheet_hourly.get(hour, 0) + 1
                    scraper_hourly[hour] = scraper_hourly.get(hour, 0) + 1

            level3_breakdown: list[dict[str, Any]] = []
            if level3_col is not None:
                level3_series = df[level3_col].fillna("").astype(str).str.strip()
                for level3 in sorted({v for v in level3_series.tolist() if v}):
                    mask = level3_series == level3
                    lvl_rows = int(mask.sum())
                    if lvl_rows <= 0:
                        continue
                    if id_col is not None:
                        lvl_ads = (
                            df.loc[mask, id_col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().nunique()
                        )
                        ads_count = int(lvl_ads) if lvl_ads else lvl_rows
                    else:
                        ads_count = lvl_rows
                    level3_breakdown.append(
                        {
                            "level_3": level3,
                            "ads_count": ads_count,
                            "sheet_rows": lvl_rows,
                            "sheets_count": 1,
                        }
                    )

            sheet_unique_ads = len(sheet_ids) if sheet_ids else n
            peak_hour, peak_ads = _peak_from_hourly(sheet_hourly)
            subcategory_breakdown.append(
                {
                    "subcategory": str(sheet_name),
                    "ads_count": int(sheet_unique_ads),
                    "sheet_rows": int(n),
                    "sheets_count": 1,
                    "unique_phones": int(len(sheet_phones)),
                    "peak_hour": peak_hour,
                    "peak_ads": int(peak_ads),
                    "level_3_breakdown": level3_breakdown,
                }
            )

    if saw_id_column and all_ids:
        ads_source = "excel_ids"
        unique_ads = len(all_ids)
    elif total_rows > 0:
        ads_source = "excel_rows"
        unique_ads = total_rows
    else:
        ads_source = "none"
        unique_ads = 0

    scraper_peak_hour, scraper_peak_ads = _peak_from_hourly(scraper_hourly)
    hourly_ads = [
        {"hour": h, "ads_count": int(scraper_hourly[h])}
        for h in sorted(scraper_hourly.keys())
    ]
    return {
        "unique_ads": int(unique_ads),
        "total_rows": int(total_rows),
        "ads_source": ads_source,
        "unique_phones": int(len(all_phones)),
        "subcategory_breakdown": subcategory_breakdown,
        "hourly_ads": hourly_ads,
        "peak_hour": scraper_peak_hour,
        "peak_ads": int(scraper_peak_ads),
    }

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
    excel_stats = _count_from_excel_files(excel_downloads)
    if excel_stats["ads_source"] == "excel_ids":
        return {
            "unique_ads": excel_stats["unique_ads"],
            "total_rows": excel_stats["total_rows"],
            "ads_source": "excel_ids",
            "unique_phones": excel_stats["unique_phones"],
            "subcategory_breakdown": excel_stats["subcategory_breakdown"],
            "hourly_ads": excel_stats["hourly_ads"],
            "peak_hour": excel_stats["peak_hour"],
            "peak_ads": excel_stats["peak_ads"],
        }

    json_count = _count_from_json_summaries(r2_client, bucket, r2_base, partition_dt)
    if json_count is not None:
        return {
            "unique_ads": json_count,
            "total_rows": excel_stats["total_rows"] or json_count,
            "ads_source": "json_summary",
            "unique_phones": excel_stats["unique_phones"],
            "subcategory_breakdown": excel_stats["subcategory_breakdown"],
            "hourly_ads": excel_stats["hourly_ads"],
            "peak_hour": excel_stats["peak_hour"],
            "peak_ads": excel_stats["peak_ads"],
        }

    if excel_stats["ads_source"] == "excel_rows":
        return {
            "unique_ads": excel_stats["unique_ads"],
            "total_rows": excel_stats["total_rows"],
            "ads_source": "excel_rows",
            "unique_phones": excel_stats["unique_phones"],
            "subcategory_breakdown": excel_stats["subcategory_breakdown"],
            "hourly_ads": excel_stats["hourly_ads"],
            "peak_hour": excel_stats["peak_hour"],
            "peak_ads": excel_stats["peak_ads"],
        }

    return {
        "unique_ads": 0,
        "total_rows": 0,
        "ads_source": "none",
        "unique_phones": 0,
        "subcategory_breakdown": [],
        "hourly_ads": [],
        "peak_hour": None,
        "peak_ads": 0,
    }
