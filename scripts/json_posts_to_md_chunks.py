#!/usr/bin/env python3
"""Convert collected Telegram posts JSON into Markdown chunks for LLM reading."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def format_datetime(value: str, timezone_name: str) -> str:
    if not value:
        return "unknown time"
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M")


def post_to_markdown(index: int, post: dict, timezone_name: str) -> str:
    text = (post.get("text") or "").strip()
    url = post.get("url") or "no public url"
    views = post.get("views")
    forwards = post.get("forwards")
    replies = post.get("replies")
    metrics = ", ".join(
        f"{label}: {value}"
        for label, value in (
            ("views", views),
            ("forwards", forwards),
            ("replies", replies),
        )
        if value is not None
    )
    if not metrics:
        metrics = "metrics: n/a"

    return "\n".join(
        [
            f"## {index}. {post.get('channel_title') or post.get('channel')} ({post.get('channel')})",
            "",
            f"- Time: {format_datetime(post.get('date', ''), timezone_name)}",
            f"- URL: {url}",
            f"- Message ID: {post.get('message_id')}",
            f"- {metrics}",
            "",
            text,
            "",
        ]
    )


def chunk_posts(posts: Iterable[str], max_chars: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_size = 0

    for post in posts:
        post_size = len(post)
        if current and current_size + post_size > max_chars:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(post)
        current_size += post_size

    if current:
        chunks.append(current)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Path to *.posts.json.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--max-chars", type=int, default=45000)
    parser.add_argument("--timezone", default="Europe/Moscow")
    args = parser.parse_args()

    rows = json.loads(args.input.read_text())
    if not isinstance(rows, list):
        raise SystemExit("Input JSON must be a list of posts.")

    stem = args.input.name.removesuffix(".posts.json")
    out_dir = args.out_dir or args.input.with_name(f"{stem}.chunks")
    out_dir.mkdir(parents=True, exist_ok=True)

    posts = [post_to_markdown(index, row, args.timezone) for index, row in enumerate(rows, start=1)]
    chunks = chunk_posts(posts, args.max_chars)

    manifest = {
        "source": str(args.input),
        "out_dir": str(out_dir),
        "posts": len(rows),
        "chunks": len(chunks),
        "max_chars": args.max_chars,
        "timezone": args.timezone,
        "files": [],
    }

    for chunk_index, chunk in enumerate(chunks, start=1):
        path = out_dir / f"{stem}.part-{chunk_index:02d}.md"
        first_post = sum(len(previous) for previous in chunks[: chunk_index - 1]) + 1
        last_post = first_post + len(chunk) - 1
        body = "\n".join(
            [
                f"# Telegram posts for {stem}, part {chunk_index:02d}",
                "",
                f"Source: `{args.input}`",
                f"Posts: {first_post}-{last_post} of {len(rows)}",
                "",
                *chunk,
            ]
        )
        path.write_text(body)
        manifest["files"].append(
            {
                "path": str(path),
                "posts": len(chunk),
                "chars": len(body),
                "first_post": first_post,
                "last_post": last_post,
            }
        )

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
