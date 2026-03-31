---
name: xiaohongshu
description: Use this skill whenever the user wants to interact with Xiaohongshu (小红书/RED). This includes searching for notes/posts, viewing note details, downloading images/videos from notes, publishing image-text posts, or checking account login status. Trigger when user mentions 小红书, RED, xiaohongshu, or asks to search/post/download content on that platform.
metadata: {"openclaw":{"requires":{"bins":["python3","playwright"]},"os":["linux","darwin"]}}
---

# Xiaohongshu Tool

Operate Xiaohongshu (小红书) via headless Playwright browser. Search notes, view details, download media, publish posts.

## Locate Skill Directory

Find where this skill is installed (use the first that exists):

```bash
SKILL_DIR="${OPENCLAW_WORKSPACE:-$HOME/.openclaw}/skills/xiaohongshu"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.claude/skills/xiaohongshu"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.agents/skills/xiaohongshu"
```

All commands below run inside `$SKILL_DIR`.

## Rules

1. **Always run status.py first** to check login state and remaining quota.
2. All scripts use `python3` and output JSON to stdout.
3. On error, check `$SKILL_DIR/data/snapshots/` for screenshots and `$SKILL_DIR/data/logs/` for logs.

## Commands

### Check Status (run before every operation)

```bash
cd "$SKILL_DIR" && python3 scripts/status.py
```

```json
{"tool": "exec", "command": "python3 scripts/status.py", "workdir": "<SKILL_DIR>"}
```

If output shows "未登录", the user needs to scan a QR code. Run login.py (see below).

### Login (QR Code Scan)

```bash
cd "$SKILL_DIR" && python3 scripts/login.py
```

```json
{"tool": "exec", "command": "python3 scripts/login.py", "workdir": "<SKILL_DIR>", "timeout": 150}
```

login.py outputs JSON with these fields:
- `qr_url`: HTTP URL to the QR code image (a temp HTTP server is auto-started on port 18088)
- `qr_path`: local file path of the QR code PNG
- `push`: results from push notifications (if configured)
- `status`: `waiting_for_scan` while waiting, `already_logged_in` if already logged in

**Your job is to deliver the QR code image to the user so they can scan it with their phone.**

How to deliver the QR code depending on your runtime:

1. **OpenClaw + Telegram**: Use the channel's sendMessage with `mediaUrl` set to the `qr_url` value to send the QR image inline in chat.
2. **OpenClaw + other channels**: Send the `qr_url` as a clickable link so the user can open it in a browser.
3. **Claude Code / terminal**: The image is at `$SKILL_DIR/data/snapshots/qrcode.png` - read and display it.
4. **Fallback**: Just tell the user the `qr_url` and ask them to open it.

The script waits up to 120 seconds for the user to scan. Once scanned, it auto-detects success and saves the browser profile.

**Optional push notifications** (config.json `notify` section):
- `ntfy_topic`: Set a ntfy.sh topic name (e.g. `my-xhs`). QR image is auto-pushed to ntfy app on phone. Zero setup, free.
- `telegram_bot_token` + `telegram_chat_id`: Direct Telegram Bot API push (backup if channel-based delivery doesn't work).

### Search Notes

```bash
cd "$SKILL_DIR" && python3 scripts/search.py --keyword "keyword" --limit 20
```

```json
{"tool": "exec", "command": "python3 scripts/search.py --keyword 'keyword' --sort general --limit 20", "workdir": "<SKILL_DIR>"}
```

| Param | Description | Default |
|-------|-------------|---------|
| `--keyword` / `-k` | Search keyword | required |
| `--sort` | `general` / `latest` / `popular` | general |
| `--limit` / `-n` | Max results | 20 |
| `--output` / `-o` | Save to JSONL file | stdout |
| `--account` | Account name | default |

Output: JSON array. Each item has `id`, `title`, `user.nickname`, `liked_count`, `url`.

### Get Note Detail

```bash
cd "$SKILL_DIR" && python3 scripts/detail.py --url "https://www.xiaohongshu.com/explore/NOTE_ID"
```

```json
{"tool": "exec", "command": "python3 scripts/detail.py --url 'https://www.xiaohongshu.com/explore/NOTE_ID'", "workdir": "<SKILL_DIR>"}
```

| Param | Description | Default |
|-------|-------------|---------|
| `--url` / `-u` | Note URL | required |
| `--output` / `-o` | Save to JSON file | stdout |
| `--account` | Account name | default |

Output: JSON object with `title`, `desc`, `tags`, `images` (URL list), `video` (URL), `liked_count`, `collected_count`, `comment_count`, `user`.

### Download Images/Videos

```bash
cd "$SKILL_DIR" && python3 scripts/download.py --url "https://www.xiaohongshu.com/explore/NOTE_ID"
```

```json
{"tool": "exec", "command": "python3 scripts/download.py --url 'https://www.xiaohongshu.com/explore/NOTE_ID' --output ./data/downloads/", "workdir": "<SKILL_DIR>"}
```

| Param | Description | Default |
|-------|-------------|---------|
| `--url` / `-u` | Note URL | required |
| `--output` / `-o` | Save directory | data/downloads/ |
| `--account` | Account name | default |

Creates a subdirectory per note. Skips already-downloaded files. Saves `meta.json` with note metadata.

### Publish Post

```bash
cd "$SKILL_DIR" && python3 scripts/publish.py --title "Title" --content "Body text" --images /path/img1.jpg /path/img2.jpg --topics "topic1" "topic2"
```

```json
{"tool": "exec", "command": "python3 scripts/publish.py --title 'Title' --content 'Body' --images /path/img.jpg --topics 'topic'", "workdir": "<SKILL_DIR>"}
```

| Param | Description | Default |
|-------|-------------|---------|
| `--title` / `-t` | Post title | required |
| `--content` / `-c` | Post body | required |
| `--images` / `-i` | Image paths (multiple ok) | required |
| `--topics` | Topic tags (multiple ok) | optional |
| `--account` | Account name | default |
| `--preview` | Fill content but don't click publish | auto-publish |

Image paths must be absolute.

## Rate Limits

Built-in rate control. Exceeding limits auto-rejects the operation.

| Operation | Interval | Daily Limit |
|-----------|----------|-------------|
| Search | 5-30s | 50 |
| Detail | 3-15s | 100 |
| Download | 2-10s | 200 |
| Publish | 5-10min | 3 |

Configurable in `$SKILL_DIR/config.json`.

## Error Handling

| Error | Cause | Action |
|-------|-------|--------|
| "今日已达上限" | Rate limit hit | Wait until tomorrow or adjust config.json |
| "页面异常 (level 3)" | Captcha/risk control | Stop all operations, wait 1+ hours |
| "未能提取笔记内容" | Page structure changed | Check data/snapshots/ for screenshots |
| "profile 正在被另一个进程使用" | Concurrent access | Wait for the other process to finish |
| "未登录" | Session expired | Run login.py, deliver QR to user |

## Example Workflows

User says "search Xiaohongshu for XX":

```bash
cd "$SKILL_DIR" && python3 scripts/status.py
cd "$SKILL_DIR" && python3 scripts/search.py -k "XX" -n 10
cd "$SKILL_DIR" && python3 scripts/detail.py -u "https://www.xiaohongshu.com/explore/NOTE_ID"
cd "$SKILL_DIR" && python3 scripts/download.py -u "https://www.xiaohongshu.com/explore/NOTE_ID"
```

User says "post something on Xiaohongshu":

```bash
cd "$SKILL_DIR" && python3 scripts/status.py
cd "$SKILL_DIR" && python3 scripts/publish.py -t "Title" -c "Content" -i /path/to/img.jpg
```

## Installation

```bash
git clone https://github.com/drstrangerujn/xiaohongshu.git ~/.openclaw/skills/xiaohongshu
# or: git clone https://github.com/drstrangerujn/xiaohongshu.git ~/.claude/skills/xiaohongshu

cd <skill_dir> && bash scripts/setup.sh
python3 scripts/login.py
```
