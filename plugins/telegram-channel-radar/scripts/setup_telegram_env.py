#!/usr/bin/env python3
"""Create a local .env file for Telegram Channel Radar."""

from __future__ import annotations

import getpass
from pathlib import Path


DEFAULT_SESSION_PATH = "/Users/martyuk/.codex/telegram-channel-radar/session"


def prompt(default: str | None = None, label: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"

    api_id = prompt(label="TELEGRAM_API_ID")
    api_hash = getpass.getpass("TELEGRAM_API_HASH: ").strip()
    session_path = prompt(DEFAULT_SESSION_PATH, "TELEGRAM_SESSION_PATH")

    if not api_id or not api_hash or not session_path:
        raise SystemExit("All fields are required.")

    env_path.write_text(
        "\n".join(
            [
                f"TELEGRAM_API_ID={api_id}",
                f"TELEGRAM_API_HASH={api_hash}",
                f"TELEGRAM_SESSION_PATH={session_path}",
                "",
            ]
        )
    )
    print(f"Wrote {env_path}")


if __name__ == "__main__":
    main()
