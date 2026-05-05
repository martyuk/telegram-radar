#!/usr/bin/env python3
"""Rank Telegram channel candidates from a JSON file.

Input JSON shape:
[
  {
    "title": "Channel title",
    "url": "https://t.me/example",
    "relevance": 5,
    "popularity": 4,
    "freshness": 2,
    "source_confidence": 3
  }
]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCORE_FIELDS = ("relevance", "popularity", "freshness", "source_confidence")


def normalize_url(url: str) -> str:
    return url.strip().replace("http://", "https://").rstrip("/")


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = normalize_url(str(row.get("url", ""))) or str(row.get("title", "")).lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        row["url"] = key
        output.append(row)
    return output


def score(row: dict[str, Any]) -> int:
    total = 0
    for field in SCORE_FIELDS:
        try:
            total += int(row.get(field, 0))
        except (TypeError, ValueError):
            continue
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    rows = json.loads(args.input.read_text())
    ranked = sorted(dedupe(rows), key=score, reverse=True)[: args.limit]
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
        row["score"] = score(row)
    print(json.dumps(ranked, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
