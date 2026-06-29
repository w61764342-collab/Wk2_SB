#!/usr/bin/env python3
"""
Count all objects under R2 prefixes for monitor report.json.

Shared with the Pro1-Os monitor hub — keep in sync when the hub copy changes.
"""

from __future__ import annotations


def _normalize_prefix(prefix: str) -> str:
    return prefix.strip("/")


def _count_objects(client, bucket: str, prefix: str) -> int:
    """Paginated list_objects_v2 count; excludes S3 folder-marker keys."""
    normalized = _normalize_prefix(prefix)
    if not normalized:
        return 0

    list_prefix = f"{normalized}/"
    count = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith("/"):
                continue
            count += 1
    return count


def count_scraper_r2_files(client, bucket: str, r2_base: str) -> int:
    """Count every object under a scraper's R2 data prefix (all dates/formats)."""
    return _count_objects(client, bucket, r2_base)


def count_site_r2_files(client, bucket: str, r2_prefix: str) -> int:
    """Count every object under the site R2 prefix (includes monitor/ artifacts)."""
    return _count_objects(client, bucket, r2_prefix)
