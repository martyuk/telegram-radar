---
name: telegram-channel-radar
description: Find popular public Telegram channels for a user query using TGStat and other public catalogs, rank them with cited evidence, then ask how often and how to monitor the selected channels.
---

# Telegram Channel Radar

Use this skill when the user asks to find Telegram channels, monitor Telegram channels, compare channel popularity, collect Telegram agenda items, or build recurring briefs from public Telegram channels.

This plugin can work in two modes:

- Browser/catalog mode for discovery through TGStat, Telemetr, Telega.in, TelegramDB, Combot, and public web search.
- Local Telegram client mode for reading posts from public channels via Telethon after the user configures a separate Telegram account locally.
- Seed similarity crawl mode for starting from one channel and recursively exploring Telegram similar-channel recommendations against a user-defined fit criterion.
- Direct message mode for sending a single explicit Telegram message through the locally authorized Telethon session.

The core contract is: discovery must produce monitorable channel identifiers. A list of channel names without `@username`, `https://t.me/...`, or a private invite URL is incomplete.

## Required Behavior

1. Treat channel discovery as current web research. Search the web and cite every source used.
2. Start from the user's phrase exactly as given, then expand it into 3-6 search variants:
   - Russian and English forms where useful.
   - Topic variants, for example `маркетинг`, `digital`, `бренды`, `SMM`.
   - Geography variants, for example `Москва`, `Moscow`, `московские`.
3. Use at least two independent discovery surfaces when available:
   - TGStat: `tgstat.ru`
   - Telemetr: `telemetr.me`
   - Telega.in catalog: `telega.in/catalog`
   - TelegramDB: `telegramdb.org`
   - Combot analytics/catalog pages: `combot.org`
   - Telegram similar channels via `scripts/telegram_client.py recommendations`
   - public Telegram channel lists and search engine results with `site:t.me`, `site:tgstat.ru`, or `site:telemetr.me`
4. Do not invent subscriber counts, ERR, views, usernames, or channel descriptions. If a metric is missing, write `unknown`.
5. Prefer public channels and public catalog pages. Do not try to bypass paywalls, logins, private groups, or access controls.
6. Deduplicate channels by Telegram username first, then by normalized title.
7. Never ask the user to paste Telegram login codes, passwords, or session contents into chat. If authentication is needed, instruct the user to run the local setup command in their terminal.
8. Always preserve a machine-readable channel list in the answer or in an `out/*.json` artifact when posts may be collected later.
9. For direct messages, only send to a recipient explicitly provided by the user and only with message text explicitly provided or confirmed by the user. Do not perform bulk outreach, scraping-to-DM workflows, spam, harassment, impersonation, or attempts to bypass Telegram privacy limits.

## Discovery Workflow

1. Search targeted catalogs first:
   - `site:tgstat.ru "<query>" telegram channel`
   - `site:telemetr.me "<query>" канал telegram`
   - `site:telega.in/catalog "<query>"`
   - `site:telegramdb.org "<query>" telegram`
2. Search the open web next:
   - `"<query>" "t.me/" канал`
   - `"<query>" "Telegram" "TGStat"`
   - For local intent: `"<query>" Москва Telegram канал`, `"<query>" московский канал`.
3. When the user provides seed channels, expand the candidate set with Telegram's similar channels:

```bash
.venv/bin/python scripts/telegram_client.py recommendations @seed_channel --limit 20 --timeout 30 --out out/recommendations.json
```

   - Treat empty recommendations as valid data, not as a failure.
   - Similar-channel results are Telegram recommendations, not TGStat popularity rankings.
   - Resolve and deduplicate these channels before mixing them into the candidate list.
4. Build a candidate table with:
   - Channel title
   - Username, public `https://t.me/...` URL, or private invite URL
   - TGStat/Telemetr/catalog URL
   - Topic/category
   - Subscriber count or audience signal
   - Average views or engagement signal if available
   - Why it matches the query
   - Source links
   - Confidence: high, medium, low
5. Resolve monitorable identifiers before finalizing:
   - Prefer a public `@username` or `https://t.me/username`.
   - If TGStat links to `t.me`, open that target and capture the username.
   - If TGStat only shows a private invite link such as `https://t.me/+...`, keep it but mark `monitoring_status: private_or_invite`.
   - If only a title is available, mark `username: unknown` and `monitoring_status: unresolved`; do not pretend it can be monitored.
   - When the local Telegram session is configured, test public usernames with:

```bash
.venv/bin/python scripts/telegram_client.py resolve @channel --timeout 20
```

6. Rank candidates with a transparent heuristic:
   - Relevance to the user query: 0-5
   - Popularity/audience signal: 0-5
   - Freshness/active posting evidence: 0-3
   - Source confidence: 0-3
   - Total: 0-16
7. Return 10-25 channels unless the user asked for a different count.

## Candidate JSON

When the user may continue into monitoring, write the candidate list to `out/channel-candidates.json` or include equivalent JSON in the response. Use this shape:

```json
[
  {
    "title": "Channel title",
    "username": "@example",
    "telegram_url": "https://t.me/example",
    "catalog_url": "https://tgstat.ru/channel/%40example",
    "source": "tgstat",
    "category": "Marketing, PR, advertising",
    "subscribers": 123456,
    "avg_views": null,
    "last_seen": "unknown",
    "fit": "Why this matches the query",
    "monitoring_status": "ready",
    "confidence": "high"
  }
]
```

Allowed `monitoring_status` values:

- `ready`: public username or URL can be passed to `telegram_client.py posts`.
- `private_or_invite`: invite URL exists, but access depends on the configured Telegram account.
- `unresolved`: no monitorable Telegram identifier found yet.
- `failed`: tested but Telegram could not resolve it.

## Seed Similarity Crawl Mode

Use this mode when the user provides a seed channel and asks for similar channels by topic, tone, authorship, audience, engagement, or any custom criterion. Example requests:

- `найди похожие на @seed по теме маркетинга`
- `найди каналы с такой же тональностью`
- `найди небольшие авторские каналы рядом с @seed`
- `найди похожие каналы, но с высокой вовлеченностью`

Goal: discover smaller, more authorial, or high-engagement channels that may not appear in top TGStat rankings.

Default crawl limits:

- `max_depth`: 5 graph hops from the seed.
- `max_channels_evaluated`: 50 total channel profiles unless the user asks otherwise.
- `recommendations_per_channel`: 20.
- `posts_per_channel`: 20.
- `timeout_per_call`: 30 seconds.
- Stop earlier if there are no new recommendations, too many failures, or Telegram rate-limits the account.

Workflow:

1. Interpret the user's criterion as an evaluation rubric. If the criterion is vague, infer a conservative rubric and state it.
2. Fetch the seed profile, latest posts, and recommendations:

```bash
.venv/bin/python scripts/telegram_client.py profile @seed --timeout 30 --out out/seed-profile.json
.venv/bin/python scripts/telegram_client.py posts @seed --limit 20 --timeout 30 --out out/seed-posts.json
.venv/bin/python scripts/telegram_client.py recommendations @seed --limit 20 --timeout 30 --out out/seed-recommendations.json
```

3. For each recommended channel not already visited:
   - Resolve/profile it.
   - Read its description and latest 20 text posts.
   - Evaluate it against the criterion.
   - Save an evidence record with matched phrases, representative post links, audience size, and engagement signals.
4. Only expand from channels that pass or are near-pass. Do not expand from irrelevant channels just because Telegram recommended them.
5. Repeat until `max_depth` or `max_channels_evaluated` is reached.
6. Prefer channels with:
   - Clear topical fit.
   - Distinct authorial voice.
   - Non-generic original posts.
   - Recent posting activity.
   - Healthy engagement relative to audience size, such as views/subscribers, replies, forwards, or discussion signals when available.
7. Penalize channels that are mostly reposts, ads, giveaway farms, empty shells, bot directories, unrelated crypto/gambling, or have unclear authorship unless the user's criterion explicitly asks for them.
8. Keep a visited set by username/id and a frontier queue with `depth`, `source_channel`, and `reason_added`.

Evaluation output shape:

```json
{
  "seed": "@seed",
  "criterion": "same marketing topic and ironic authorial tone",
  "limits": {
    "max_depth": 5,
    "max_channels_evaluated": 50,
    "posts_per_channel": 20
  },
  "accepted": [
    {
      "title": "Channel title",
      "username": "@example",
      "telegram_url": "https://t.me/example",
      "depth": 2,
      "source_channel": "@parent",
      "subscribers": 12345,
      "avg_views_sample": 2345,
      "engagement_sample": 0.19,
      "fit_score": 14,
      "fit_reason": "Matches marketing topic and uses similar short ironic commentary.",
      "evidence_links": ["https://t.me/example/123"]
    }
  ],
  "rejected": [
    {
      "username": "@other",
      "reason": "Mostly unrelated crypto promos.",
      "depth": 1
    }
  ]
}
```

Fit score rubric, 0-16:

- Topic fit: 0-5.
- Tone/style fit: 0-4.
- Originality/authorship: 0-3.
- Engagement/activity: 0-2.
- Source confidence: 0-2.

Accept channels scoring 11+ by default. Mark 8-10 as `maybe` if the user asked for broad exploration.

## Direct Message Mode

Use this mode only when the user explicitly asks to send a Telegram message from the locally authorized account.

Safety rules:

- Do not ask the user to paste login codes, passwords, API hashes, or session contents into chat.
- Do not send unsolicited bulk messages or outreach campaigns.
- Do not infer recipients from discovery results unless the user explicitly chooses the exact recipient.
- Do not send messages that are harassing, deceptive, threatening, or designed to evade Telegram restrictions.
- If Telegram returns a flood wait or privacy/rate-limit error, stop and report the wait time or error.
- Prefer dry-run validation first unless the user clearly asked to send now.

Dry-run recipient check:

```bash
.venv/bin/python scripts/telegram_client.py send-message @recipient --text "Message text" --timeout 30
```

Actually send one message:

```bash
.venv/bin/python scripts/telegram_client.py send-message @recipient --text "Message text" --confirm-send --timeout 30
```

Send from a local text file when the message is long:

```bash
.venv/bin/python scripts/telegram_client.py send-message @recipient --text-file out/message.txt --confirm-send --timeout 30 --out out/send-result.json
```

The command returns JSON with `ok`, `dry_run`, `message_id`, `date`, and `error`. It does not print or store Telegram secrets.

## Monitoring Setup

After presenting the shortlist, ask the user what recurring monitoring they want. Ask for both schedule and output goal if either is missing.

Useful options to offer:

- Daily summary of the main agenda across all selected channels.
- Daily list of the most-mentioned news hooks, grouped by theme.
- Daily list of unique or under-discussed hooks that appeared in only a small number of channels.
- Competitive content map: which channels pushed which narratives.
- Alerts when a topic, company, person, or phrase appears.
- Weekly digest of recurring themes and emerging topics.

When the user confirms schedule and goal, create a Codex automation if the `automation_update` tool is available. Use a self-contained prompt that includes:

- Channel list with URLs/usernames.
- Monitoring objective.
- Required output format.
- Schedule.
- Source and citation requirements.
- Date range for each run.

## Local Telegram Client

Use `scripts/telegram_client.py` when channel usernames are known and the task requires recent public posts.

Required environment variables:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_PATH`

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create local `.env`:

```bash
.venv/bin/python scripts/setup_telegram_env.py
```

Authorize or verify the Telegram session:

```bash
.venv/bin/python scripts/telegram_client.py auth
```

Check status:

```bash
.venv/bin/python scripts/telegram_client.py status
```

Fetch recent posts:

```bash
.venv/bin/python scripts/telegram_client.py posts @channel1 @channel2 --limit 50 --days 1 --timeout 30 --out out/posts.json
```

Fetch channel profile and description:

```bash
.venv/bin/python scripts/telegram_client.py profile @channel --timeout 30 --out out/profile.json
```

Resolve candidate channels before monitoring:

```bash
.venv/bin/python scripts/telegram_client.py resolve @channel1 @channel2 --timeout 30 --out out/resolve.json
```

Fetch Telegram similar/recommended channels:

```bash
.venv/bin/python scripts/telegram_client.py recommendations @channel --limit 20 --timeout 30 --out out/recommendations.json
```

Rules for this mode:

- Read only public channels or channels the configured account can lawfully access.
- Keep the session file local and out of git.
- Use conservative limits and avoid repeated scraping loops.
- If Telegram returns rate-limit or flood-wait errors, stop and report the wait time.
- Cite channel URLs and message links where possible.
- Keep `.env`, `.venv/`, session files, and `out/` artifacts out of git.

## Post Collection Workflow

When the user asks to collect posts from discovered channels:

1. Use only candidates with `monitoring_status: ready` unless the user explicitly wants to try invite/private links.
2. Run a bounded collection command:

```bash
.venv/bin/python scripts/telegram_client.py posts @channel1 @channel2 --limit 50 --days 1 --timeout 30 --out out/posts.json
```

3. Report:
   - Number of channels requested.
   - Number of channels resolved.
   - Number of text posts collected.
   - Channels that failed or timed out.
   - Path to the JSON artifact.
4. Summarize posts according to the user's objective: main agenda, repeated hooks, unique hooks, competitive narrative map, or alerts.
5. Include source message links whenever the client returns them.

## Monitoring Brief: Info Hooks & Brand Activities

When producing a daily monitoring brief from collected posts, follow these rules.

### What to collect

1. **Brand activations & special projects** — new campaigns, limited editions, collabs, product launches, seasonal promos, merch drops, packaging stunts, in-app mechanics (nudge, gamification), influencer mailings/seedings.
2. **PR info hooks** — scandals, lawsuits, executive changes, M&A deals, regulatory actions affecting brands/businesses.
3. **UGC & social media trends** — viral user-generated content involving brands, new platform features (Reels, Shorts, TikTok trends), creator economy stories, AI/creative tools going viral.
4. **Business & industry news** — market shifts, budget cuts, agency moves, new tech/products, regulatory changes that affect marketing/advertising.

### What NOT to collect

- General news without a brand/business angle (politics, weather alerts, infrastructure outages unless directly tied to brand activity).
- Lifestyle/psychology tips without a marketing context.
- Pure memes without a brand reference.

### Geography split

Every item must be tagged as **🇷🇺 Россия** or **🌍 Зарубежье**. Group the brief into these two sections.

### Required fields per item

Each item in the brief must include:

- **Title** — what happened, in one line.
- **Description** — 2–4 sentences explaining the activation/hook and why it matters.
- **Brand/Company** — who did it.
- **Source links** — direct `https://t.me/channel/123` links to the original Telegram posts that mention it. Always include these; never omit them.
- **Views** — total views across source posts (approximate).

### Workflow: save first, analyze from file

1. **Collect** posts via `telegram_client.py posts` and save to `out/posts-YYYY-MM-DD.json`.
   - The script automatically saves each post's `url` field (e.g. `https://t.me/channel/123`).
   - This URL is the **authoritative link** to the original post. Always use it in the brief.
2. **Filter** by date and save filtered set to `out/posts-YYYY-MM-DD-filtered.json`.
3. **Analyze** from the filtered JSON file — do NOT re-fetch from Telegram during analysis.
   - When matching posts to brief items, always verify by reading the actual `text` and `url` fields from the JSON, not by keyword matching alone.
   - Never guess or construct URLs. Only use URLs that exist in the collected data.
4. **Produce brief** from the file. If you need to re-check a detail, read the file again.
5. **Save brief** to `out/brief-YYYY-MM-DD.md` (or the workspace path the user specifies).

This ensures idempotency and avoids unnecessary API calls.

### Brief structure

```markdown
# 📊 Telegram Radar — Brief for YYYY-MM-DD

**Channels:** N | **Posts:** N | **Date collected:** YYYY-MM-DD HH:MM

---

## 🇷🇺 Россия

### Спецпроекты и бренд-активности

**1. [Title]**
[Description]
🏢 Brand: ...
👁 Views: ~N
🔗 [Channel name](t.me/link) · [Channel name](t.me/link)

### PR-инфоповоды

**N. [Title]**
...

### UGC и соцсети
...

### Бизнес и индустрия
...

---

## 🌍 Зарубежье

### Спецпроекты и бренд-активности
...

### PR-инфоповоды
...

### UGC и соцсети
...

### Бизнес и индустрия
...

---

*Source file: out/posts-YYYY-MM-DD-filtered.json*
```

**Critical rule: continuous numbering.** Item numbers must be sequential across the entire brief, starting from 1 and never resetting between sections or geography splits. This lets the user reference items by number (e.g. "2, 8, 15, 17") for follow-up tasks like reel script writing.

## Output Format

For channel discovery, use:

```markdown
| Rank | Channel | Username | Telegram URL | Audience | Monitoring | Fit | Sources |
| --- | --- | --- | --- | --- | --- | --- | --- |
```

Then add:

- `Method`: one short paragraph describing sources searched and ranking logic.
- `Caveats`: missing metrics, paywalled metrics, stale pages, or ambiguous matches.
- `Saved artifact`: path to `out/channel-candidates.json` when created.
- `Next question`: ask how often to monitor and what kind of brief to produce.

For monitoring briefs, use:

```markdown
## Main Agenda
## Repeated Hooks
## Unique Hooks
## Notable Channel Differences
## Source Links
```

For seed similarity crawl, use:

```markdown
## Accepted Channels
| Channel | Username | Depth | Subscribers | Sample Engagement | Fit | Evidence |
| --- | --- | ---: | ---: | ---: | --- | --- |

## Maybe
## Rejected Summary
## Crawl Limits And Caveats
## Saved Artifacts
```

## Quality Bar

- Mention the exact date of research in the answer.
- Prefer primary catalog pages and public channel pages over listicles.
- Keep Russian-language user requests in Russian unless the user asks otherwise.
- If the query is too broad, still return a first pass, then suggest narrower filters such as geography, audience size, politics/business/culture, or B2B/B2C.
