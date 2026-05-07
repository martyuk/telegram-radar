#!/bin/zsh
set -euo pipefail

REPO_DIR="/Users/martyuk/Documents/telegram-radar"
PLUGIN_DIR="$REPO_DIR/plugins/telegram-channel-radar"
PYTHON="$REPO_DIR/.venv/bin/python"
CHANNELS_FILE="$REPO_DIR/config/monitoring-channels.txt"
LOG_DIR="$REPO_DIR/logs"
DATE_VALUE="${1:-$(TZ=Europe/Moscow date +%F)}"
OUT_FILE="$REPO_DIR/out/corpus/${DATE_VALUE}.posts.json"
CHUNKS_DIR="$REPO_DIR/out/corpus/${DATE_VALUE}.chunks"
RAW_URL="https://raw.githubusercontent.com/martyuk/telegram-radar/main/out/corpus/${DATE_VALUE}.posts.json"
GITHUB_URL="https://github.com/martyuk/telegram-radar/blob/main/out/corpus/${DATE_VALUE}.posts.json"
MANIFEST_URL="https://raw.githubusercontent.com/martyuk/telegram-radar/main/out/corpus/${DATE_VALUE}.chunks/manifest.json"

mkdir -p "$LOG_DIR" "$REPO_DIR/out/corpus"

send_telegram() {
  local text="$1"
  cd "$PLUGIN_DIR"
  "$PYTHON" scripts/telegram_client.py send-message @martyuk \
    --text "$text" \
    --confirm-send \
    --timeout 60 \
    --out "$LOG_DIR/send-${DATE_VALUE}.json" >/dev/null
}

on_error() {
  local exit_code=$?
  send_telegram "Telegram Radar: сбор за ${DATE_VALUE} упал с кодом ${exit_code}. Лог: ${LOG_DIR}/daily-${DATE_VALUE}.log" || true
  exit "$exit_code"
}

trap on_error ERR

if [[ ! -x "$PYTHON" ]]; then
  python3 -m venv "$REPO_DIR/.venv"
  "$PYTHON" -m pip install -r "$PLUGIN_DIR/requirements.txt"
fi

cd "$REPO_DIR"
git pull --ff-only origin main

cd "$PLUGIN_DIR"
"$PYTHON" scripts/telegram_client.py posts $(tr '\n' ' ' < "$CHANNELS_FILE") \
  --limit 250 \
  --date "$DATE_VALUE" \
  --timezone Europe/Moscow \
  --timeout 300 \
  --out "$OUT_FILE"

rm -rf "$CHUNKS_DIR"
"$PYTHON" "$REPO_DIR/scripts/json_posts_to_md_chunks.py" "$OUT_FILE" \
  --max-chars 35000 \
  --timezone Europe/Moscow \
  --out-dir "$CHUNKS_DIR" >/dev/null

read -r POST_COUNT CHANNEL_COUNT MISSING_CHANNELS < <("$PYTHON" - "$OUT_FILE" "$CHANNELS_FILE" <<'PY'
import json
import sys
from pathlib import Path

posts_path = Path(sys.argv[1])
channels_path = Path(sys.argv[2])
rows = json.loads(posts_path.read_text())
requested = [line.strip().lower() for line in channels_path.read_text().splitlines() if line.strip()]
seen = {row["channel"].lower() for row in rows}
missing = ",".join(channel for channel in requested if channel not in seen) or "-"
print(len(rows), len(seen), missing)
PY
)

cd "$REPO_DIR"
CHUNK_LINKS="$("$PYTHON" - "$CHUNKS_DIR/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
links = []
for item in manifest["files"]:
    path = item["path"]
    links.append(
        "Chunk {first}-{last}: https://raw.githubusercontent.com/martyuk/telegram-radar/main/{path}".format(
            first=item["first_post"],
            last=item["last_post"],
            path=path,
        )
    )
print("\n".join(links))
PY
)"

git add "$OUT_FILE" "$CHUNKS_DIR"
if git diff --cached --quiet; then
  COMMIT_STATUS="без изменений в git"
else
  git commit -m "Add posts for ${DATE_VALUE}"
  git push origin main
  COMMIT_STATUS="загружено в GitHub"
fi

send_telegram "Telegram Radar: посты за ${DATE_VALUE} собраны.
Постов: ${POST_COUNT}
Каналов: ${CHANNEL_COUNT}
Без постов: ${MISSING_CHANNELS}
Статус: ${COMMIT_STATUS}
Raw: ${RAW_URL}
GitHub: ${GITHUB_URL}
Manifest: ${MANIFEST_URL}
${CHUNK_LINKS}"
