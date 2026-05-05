# Telegram Channel Radar

Local Codex plugin for finding Telegram channels and collecting public posts.

## Typical Prompts

```text
Используй telegram-channel-radar. Найди 20 популярных каналов про маркетинг и бизнес. Обязательно сохрани @username, t.me URL и TGStat URL, чтобы потом собрать посты.
```

```text
Используй telegram-channel-radar. Проверь, какие из найденных каналов резолвятся в Telegram, и собери последние 10 постов из каждого рабочего канала.
```

```text
Используй telegram-channel-radar. Каждый день читай посты за последние 24 часа из @channel1 @channel2 и делай сводку инфоповодов со ссылками.
```

```text
Используй telegram-channel-radar. Возьми @memtc как seed и найди похожие небольшие авторские каналы с похожей тональностью. Иди по similar channels до глубины 5, читай описание и последние 20 постов каждого кандидата.
```

```text
Используй telegram-channel-radar. Проверь dry-run, что можно отправить сообщение @username, а затем отправь ему этот текст: ...
```

## Local Commands

```bash
.venv/bin/python scripts/telegram_client.py status
.venv/bin/python scripts/telegram_client.py profile @petyaetoya --timeout 20
.venv/bin/python scripts/telegram_client.py resolve @petyaetoya --timeout 20
.venv/bin/python scripts/telegram_client.py recommendations @telegram --limit 10 --timeout 20
.venv/bin/python scripts/telegram_client.py posts @petyaetoya --limit 10 --timeout 20 --out out/posts.json
.venv/bin/python scripts/telegram_client.py send-message @username --text "Message text" --timeout 30
.venv/bin/python scripts/telegram_client.py send-message @username --text "Message text" --confirm-send --timeout 30
```

Discovery output should include monitorable identifiers:

- `username`
- `telegram_url`
- `catalog_url`
- `monitoring_status`

`send-message` defaults to dry-run. It only sends after `--confirm-send` is passed and is intended for single explicit recipients, not bulk outreach.
