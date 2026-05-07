#!/usr/bin/env python3
"""Read public Telegram channel posts through a local Telethon session.

Secrets are read from environment variables. Keep the generated session file out of git.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


@dataclass
class ChannelPost:
    channel: str
    channel_title: str
    message_id: int
    date: str
    text: str
    views: int | None
    forwards: int | None
    replies: int | None
    url: str | None


@dataclass
class ChannelResolve:
    input: str
    ok: bool
    title: str | None
    username: str | None
    id: int | None
    error: str | None


@dataclass
class ChannelRecommendation:
    source: str
    title: str | None
    username: str | None
    id: int | None
    participants_count: int | None
    verified: bool | None
    telegram_url: str | None


@dataclass
class ChannelProfile:
    input: str
    title: str | None
    username: str | None
    id: int | None
    about: str | None
    participants_count: int | None
    verified: bool | None
    megagroup: bool | None
    broadcast: bool | None
    telegram_url: str | None


@dataclass
class SendMessageResult:
    recipient: str
    ok: bool
    dry_run: bool
    message_id: int | None
    date: str | None
    error: str | None


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def require_env() -> tuple[int, str, Path]:
    load_dotenv(Path.cwd() / ".env")
    missing = [
        key
        for key in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_PATH")
        if not os.environ.get(key)
    ]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"Missing required environment variables: {joined}")
    return (
        int(os.environ["TELEGRAM_API_ID"]),
        os.environ["TELEGRAM_API_HASH"],
        Path(os.environ["TELEGRAM_SESSION_PATH"]).expanduser(),
    )


def session_files(session_path: Path) -> list[Path]:
    candidates = [session_path]
    if session_path.suffix != ".session":
        candidates.append(session_path.with_name(f"{session_path.name}.session"))
    else:
        candidates.append(session_path.with_suffix(""))

    output: list[Path] = []
    for candidate in candidates:
        output.append(candidate)
        output.append(candidate.with_name(f"{candidate.name}-journal"))
    return output


def has_session_file(session_path: Path) -> bool:
    return any(path.exists() and path.name.endswith(".session") for path in session_files(session_path))


def import_telethon() -> Any:
    try:
        from telethon import TelegramClient
        from telethon.errors import FloodWaitError
    except ImportError as exc:
        raise SystemExit(
            "Telethon is not installed. Run: python3 -m pip install -r requirements.txt"
        ) from exc
    return TelegramClient, FloodWaitError


def normalize_channel(channel: str) -> str:
    value = channel.strip()
    if value.startswith("https://t.me/"):
        value = value.removeprefix("https://t.me/")
    if value.startswith("http://t.me/"):
        value = value.removeprefix("http://t.me/")
    return value.strip("/")


def read_message_text(args: argparse.Namespace) -> str:
    if args.text_file:
        text = Path(args.text_file).read_text()
    else:
        text = args.text or ""
    if not text.strip():
        raise SystemExit("Message text is empty.")
    return text


def public_message_url(username: str, message_id: int) -> str | None:
    clean = normalize_channel(username).lstrip("@")
    if not clean or clean.startswith("+"):
        return None
    return f"https://t.me/{clean}/{message_id}"


def message_replies_count(message: Any) -> int | None:
    replies = getattr(message, "replies", None)
    if replies is None:
        return None
    return getattr(replies, "replies", None)


def mask_account(value: str) -> str:
    if not value:
        return "unknown"
    if value.isdigit() and len(value) > 4:
        return f"{value[:2]}***{value[-2:]}"
    if len(value) > 4:
        return f"{value[:2]}***"
    return "***"


async def build_client() -> Any:
    api_id, api_hash, session_path = require_env()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    TelegramClient, _ = import_telethon()
    return TelegramClient(str(session_path), api_id, api_hash)


async def auth() -> None:
    client = await build_client()
    async with client:
        me = await client.get_me()
        username = getattr(me, "username", None) or getattr(me, "phone", "unknown")
        print(json.dumps({"authorized": True, "account": mask_account(str(username))}, ensure_ascii=False))


async def status() -> None:
    api_id, api_hash, session_path = require_env()
    files = session_files(session_path)
    payload: dict[str, Any] = {
        "api_id_present": bool(api_id),
        "api_hash_present": bool(api_hash),
        "session_path": str(session_path),
        "session_files": [
            {"path": str(path), "exists": path.exists(), "bytes": path.stat().st_size if path.exists() else 0}
            for path in files
        ],
    }

    existing_session = has_session_file(session_path)
    if existing_session:
        client = await build_client()
        async with client:
            payload["authorized"] = await client.is_user_authorized()
            if payload["authorized"]:
                me = await client.get_me()
                account = getattr(me, "username", None) or getattr(me, "phone", "unknown")
                payload["account"] = mask_account(str(account))
    else:
        payload["authorized"] = False

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_date_window(date_value: str | None, timezone_name: str) -> tuple[datetime | None, datetime | None]:
    if not date_value:
        return None, None
    local_timezone = ZoneInfo(timezone_name)
    local_start = datetime.strptime(date_value, "%Y-%m-%d").replace(tzinfo=local_timezone)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


async def fetch_posts(
    channels: list[str],
    limit: int,
    days: int | None,
    date_value: str | None,
    timezone_name: str,
) -> list[ChannelPost]:
    _, _, session_path = require_env()
    if not has_session_file(session_path):
        raise SystemExit("Telegram session is not authorized yet. Run: .venv/bin/python scripts/telegram_client.py auth")

    client = await build_client()
    _, FloodWaitError = import_telethon()
    since, before = parse_date_window(date_value, timezone_name)
    if days is not None:
        if date_value:
            raise SystemExit("--days and --date cannot be used together")
        since = datetime.now(timezone.utc) - timedelta(days=days)

    output: list[ChannelPost] = []
    async with client:
        for raw_channel in channels:
            channel = normalize_channel(raw_channel)
            try:
                entity = await client.get_entity(channel)
                title = getattr(entity, "title", channel)
                username = getattr(entity, "username", None) or channel
                async for message in client.iter_messages(entity, limit=limit, offset_date=before):
                    if since and message.date and message.date < since:
                        if before:
                            break
                        continue
                    if before and message.date and message.date >= before:
                        continue
                    text = message.message or ""
                    if not text.strip():
                        continue
                    output.append(
                        ChannelPost(
                            channel=f"@{username.lstrip('@')}",
                            channel_title=title,
                            message_id=message.id,
                            date=message.date.isoformat() if message.date else "",
                            text=text,
                            views=getattr(message, "views", None),
                            forwards=getattr(message, "forwards", None),
                            replies=message_replies_count(message),
                            url=public_message_url(username, message.id),
                        )
                    )
            except FloodWaitError as exc:
                raise SystemExit(f"Telegram flood wait: retry after {exc.seconds} seconds") from exc
    return output


async def resolve_channels(channels: list[str]) -> list[ChannelResolve]:
    _, _, session_path = require_env()
    if not has_session_file(session_path):
        raise SystemExit("Telegram session is not authorized yet. Run: .venv/bin/python scripts/telegram_client.py auth")

    client = await build_client()
    output: list[ChannelResolve] = []
    async with client:
        for raw_channel in channels:
            channel = normalize_channel(raw_channel)
            try:
                entity = await client.get_entity(channel)
                output.append(
                    ChannelResolve(
                        input=raw_channel,
                        ok=True,
                        title=getattr(entity, "title", None) or getattr(entity, "first_name", None),
                        username=getattr(entity, "username", None),
                        id=getattr(entity, "id", None),
                        error=None,
                    )
                )
            except Exception as exc:
                output.append(
                    ChannelResolve(
                        input=raw_channel,
                        ok=False,
                        title=None,
                        username=None,
                        id=None,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
    return output


async def resolve(args: argparse.Namespace) -> None:
    try:
        rows = await asyncio.wait_for(resolve_channels(args.channels), timeout=args.timeout)
    except asyncio.TimeoutError as exc:
        raise SystemExit(f"Telegram resolve timed out after {args.timeout} seconds") from exc
    payload = [asdict(row) for row in rows]
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(data)
    else:
        print(data)


async def get_recommendations(channel: str) -> list[ChannelRecommendation]:
    _, _, session_path = require_env()
    if not has_session_file(session_path):
        raise SystemExit("Telegram session is not authorized yet. Run: .venv/bin/python scripts/telegram_client.py auth")

    client = await build_client()
    from telethon import functions

    output: list[ChannelRecommendation] = []
    async with client:
        source = normalize_channel(channel)
        entity = await client.get_entity(source)
        result = await client(functions.channels.GetChannelRecommendationsRequest(channel=entity))
        for chat in getattr(result, "chats", []):
            username = getattr(chat, "username", None)
            output.append(
                ChannelRecommendation(
                    source=f"@{source.lstrip('@')}",
                    title=getattr(chat, "title", None),
                    username=f"@{username}" if username else None,
                    id=getattr(chat, "id", None),
                    participants_count=getattr(chat, "participants_count", None),
                    verified=getattr(chat, "verified", None),
                    telegram_url=f"https://t.me/{username}" if username else None,
                )
            )
    return output


async def get_profile(channel: str) -> ChannelProfile:
    _, _, session_path = require_env()
    if not has_session_file(session_path):
        raise SystemExit("Telegram session is not authorized yet. Run: .venv/bin/python scripts/telegram_client.py auth")

    client = await build_client()
    from telethon import functions

    async with client:
        normalized = normalize_channel(channel)
        entity = await client.get_entity(normalized)
        username = getattr(entity, "username", None)
        about = None
        participants_count = getattr(entity, "participants_count", None)
        try:
            full = await client(functions.channels.GetFullChannelRequest(channel=entity))
            about = getattr(full.full_chat, "about", None)
            participants_count = getattr(full.full_chat, "participants_count", participants_count)
        except Exception:
            pass

        return ChannelProfile(
            input=channel,
            title=getattr(entity, "title", None) or getattr(entity, "first_name", None),
            username=f"@{username}" if username else None,
            id=getattr(entity, "id", None),
            about=about,
            participants_count=participants_count,
            verified=getattr(entity, "verified", None),
            megagroup=getattr(entity, "megagroup", None),
            broadcast=getattr(entity, "broadcast", None),
            telegram_url=f"https://t.me/{username}" if username else None,
        )


async def send_message_to_recipient(
    recipient: str,
    text: str,
    confirm_send: bool,
) -> SendMessageResult:
    _, _, session_path = require_env()
    if not has_session_file(session_path):
        raise SystemExit("Telegram session is not authorized yet. Run: .venv/bin/python scripts/telegram_client.py auth")

    client = await build_client()
    _, FloodWaitError = import_telethon()
    normalized = normalize_channel(recipient)

    async with client:
        try:
            entity = await client.get_entity(normalized)
            if not confirm_send:
                return SendMessageResult(
                    recipient=recipient,
                    ok=True,
                    dry_run=True,
                    message_id=None,
                    date=None,
                    error=None,
                )

            message = await client.send_message(entity, text)
            return SendMessageResult(
                recipient=recipient,
                ok=True,
                dry_run=False,
                message_id=getattr(message, "id", None),
                date=message.date.isoformat() if getattr(message, "date", None) else None,
                error=None,
            )
        except FloodWaitError as exc:
            raise SystemExit(f"Telegram flood wait: retry after {exc.seconds} seconds") from exc
        except Exception as exc:
            return SendMessageResult(
                recipient=recipient,
                ok=False,
                dry_run=not confirm_send,
                message_id=None,
                date=None,
                error=f"{type(exc).__name__}: {exc}",
            )


async def send_message(args: argparse.Namespace) -> None:
    text = read_message_text(args)
    try:
        row = await asyncio.wait_for(
            send_message_to_recipient(args.recipient, text, args.confirm_send),
            timeout=args.timeout,
        )
    except asyncio.TimeoutError as exc:
        raise SystemExit(f"Telegram send-message timed out after {args.timeout} seconds") from exc

    data = json.dumps(asdict(row), ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(data)
    else:
        print(data)


async def profile(args: argparse.Namespace) -> None:
    try:
        row = await asyncio.wait_for(get_profile(args.channel), timeout=args.timeout)
    except asyncio.TimeoutError as exc:
        raise SystemExit(f"Telegram profile timed out after {args.timeout} seconds") from exc
    data = json.dumps(asdict(row), ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(data)
    else:
        print(data)


async def recommendations(args: argparse.Namespace) -> None:
    try:
        rows = await asyncio.wait_for(get_recommendations(args.channel), timeout=args.timeout)
    except asyncio.TimeoutError as exc:
        raise SystemExit(f"Telegram recommendations timed out after {args.timeout} seconds") from exc
    payload = [asdict(row) for row in rows[: args.limit]]
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(data)
    else:
        print(data)


async def posts(args: argparse.Namespace) -> None:
    try:
        rows = await asyncio.wait_for(
            fetch_posts(args.channels, args.limit, args.days, args.date, args.timezone),
            timeout=args.timeout,
        )
    except asyncio.TimeoutError as exc:
        raise SystemExit(f"Telegram request timed out after {args.timeout} seconds") from exc
    payload = [asdict(row) for row in rows]
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(data)
    else:
        print(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("auth", help="Create or verify the local Telegram session.")
    subparsers.add_parser("status", help="Check local configuration and session status.")

    posts_parser = subparsers.add_parser("posts", help="Fetch recent public channel posts.")
    posts_parser.add_argument("channels", nargs="+", help="@username or https://t.me/username")
    posts_parser.add_argument("--limit", type=int, default=50)
    posts_parser.add_argument("--days", type=int, default=None)
    posts_parser.add_argument("--date", default=None, help="Fetch posts for one local calendar day, YYYY-MM-DD.")
    posts_parser.add_argument("--timezone", default="Europe/Moscow", help="Timezone for --date.")
    posts_parser.add_argument("--out", default=None)
    posts_parser.add_argument("--timeout", type=int, default=30)

    resolve_parser = subparsers.add_parser("resolve", help="Check that usernames or t.me URLs resolve.")
    resolve_parser.add_argument("channels", nargs="+", help="@username or https://t.me/username")
    resolve_parser.add_argument("--out", default=None)
    resolve_parser.add_argument("--timeout", type=int, default=30)

    profile_parser = subparsers.add_parser(
        "profile",
        help="Fetch Telegram channel title, description, and audience metadata.",
    )
    profile_parser.add_argument("channel", help="@username or https://t.me/username")
    profile_parser.add_argument("--out", default=None)
    profile_parser.add_argument("--timeout", type=int, default=30)

    recommendations_parser = subparsers.add_parser(
        "recommendations",
        help="Fetch Telegram similar/recommended channels for a public channel.",
    )
    recommendations_parser.add_argument("channel", help="@username or https://t.me/username")
    recommendations_parser.add_argument("--limit", type=int, default=20)
    recommendations_parser.add_argument("--out", default=None)
    recommendations_parser.add_argument("--timeout", type=int, default=30)

    send_parser = subparsers.add_parser(
        "send-message",
        help="Send one Telegram message to an explicit user/chat recipient. Defaults to dry-run.",
    )
    send_parser.add_argument("recipient", help="@username, https://t.me/username, numeric id, or saved contact")
    text_group = send_parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument("--text", help="Message text to send.")
    text_group.add_argument("--text-file", help="Path to a UTF-8 text file with the message body.")
    send_parser.add_argument(
        "--confirm-send",
        action="store_true",
        help="Actually send the message. Without this flag the command only verifies the recipient.",
    )
    send_parser.add_argument("--out", default=None)
    send_parser.add_argument("--timeout", type=int, default=30)

    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.command == "auth":
        await auth()
    elif args.command == "status":
        await status()
    elif args.command == "posts":
        await posts(args)
    elif args.command == "resolve":
        await resolve(args)
    elif args.command == "profile":
        await profile(args)
    elif args.command == "recommendations":
        await recommendations(args)
    elif args.command == "send-message":
        await send_message(args)


if __name__ == "__main__":
    asyncio.run(main())
