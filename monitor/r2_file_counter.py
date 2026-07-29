#!/usr/bin/env python3
"""
Count all objects under R2 prefixes for monitor report.json.

Shared with the Pro1-Os monitor hub — keep in sync when the hub copy changes.

When multiple scrapers share one R2 base path (e.g. boshamlan properties rent/sale/exchange),
pass category_slug so only that category's Excel files and images are counted.
"""

from __future__ import annotations

_EXCEL_FOLDERS = ("excel files", "excel-files")

# r2_base -> list of non-folder objects (cached for shared prefixes like properties/)
_PREFIX_OBJECT_CACHE: dict[str, list[dict[str, int | str]]] = {}


def _normalize_prefix(prefix: str) -> str:
    return prefix.strip("/")


def _object_size_bytes(obj: dict) -> int:
    size = obj.get("Size", 0)
    try:
        return int(size)
    except (TypeError, ValueError):
        return 0


def category_slug_from_excel_pattern(pattern: str) -> str | None:
    """rent.xlsx -> rent; wildcard patterns -> None (count full prefix)."""
    if not pattern or "{" in pattern:
        return None
    filename = pattern.split("/")[-1].strip()
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        return filename[: -len(".xlsx")].lower()
    return None


def _key_matches_category(key: str, category_slug: str) -> bool:
    """Match category Excel files and images under a shared properties prefix."""
    if key.endswith("/"):
        return False

    slug = category_slug.lower()
    key_lower = key.lower()

    for folder in _EXCEL_FOLDERS:
        if key_lower.endswith(f"/{folder}/{slug}.xlsx"):
            return True

    return f"/images/{slug}/" in key_lower


def _object_matches_category(obj: dict[str, int | str], category_slug: str) -> bool:
    key = str(obj.get("Key", ""))
    return _key_matches_category(key, category_slug)


def _list_objects(client, bucket: str, r2_base: str) -> list[dict[str, int | str]]:
    normalized = _normalize_prefix(r2_base)
    if not normalized:
        return []

    if normalized in _PREFIX_OBJECT_CACHE:
        return _PREFIX_OBJECT_CACHE[normalized]

    objects: list[dict[str, int | str]] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{normalized}/"):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if not key.endswith("/"):
                objects.append({"Key": key, "Size": _object_size_bytes(obj)})

    _PREFIX_OBJECT_CACHE[normalized] = objects
    return objects


def clear_prefix_cache() -> None:
    """Reset cached listings (useful in tests)."""
    _PREFIX_OBJECT_CACHE.clear()


def count_scraper_r2_files(
    client,
    bucket: str,
    r2_base: str,
    category_slug: str | None = None,
) -> int:
    """Count objects for one scraper — full prefix, or one category when shared."""
    objects = _list_objects(client, bucket, r2_base)
    if category_slug:
        return sum(1 for obj in objects if _object_matches_category(obj, category_slug))
    return len(objects)


def count_scraper_r2_size_bytes(
    client,
    bucket: str,
    r2_base: str,
    category_slug: str | None = None,
) -> int:
    """Sum object sizes for one scraper — full prefix, or one category when shared."""
    objects = _list_objects(client, bucket, r2_base)
    if category_slug:
        return sum(_object_size_bytes(obj) for obj in objects if _object_matches_category(obj, category_slug))
    return sum(_object_size_bytes(obj) for obj in objects)


def count_site_r2_files(client, bucket: str, r2_prefix: str) -> int:
    """Count every object under the site R2 prefix (includes monitor/ artifacts)."""
    return len(_list_objects(client, bucket, r2_prefix))


def count_site_r2_size_bytes(client, bucket: str, r2_prefix: str) -> int:
    """Sum object sizes under the site R2 prefix (includes monitor/ artifacts)."""
    return sum(_object_size_bytes(obj) for obj in _list_objects(client, bucket, r2_prefix))
