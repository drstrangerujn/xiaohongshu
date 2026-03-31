---
name: xiaohongshu
description: Use this skill whenever the user wants to interact with Xiaohongshu (小红书/RED). This includes searching for notes/posts, viewing note details, downloading images/videos from notes, publishing image-text posts, or checking account login status. Trigger when user mentions 小红书, RED, xiaohongshu, or asks to search/post/download content on that platform.
metadata: {"openclaw":{"requires":{"bins":["python3","playwright"]},"os":["linux","darwin"]}}
---

# 小红书操作工具

通过 Playwright 无头浏览器操作小红书网页版。支���搜索笔记、查看详情、下载图片视频、发布图文。

本 skill 的所有脚本位于 skill 安装目录下的 `scripts/`。执行时需要先确定 skill 目录路径。

## 确定 Skill 目录

按以下顺序查找本 skill 的安装位置（哪个存在���哪个）：

```bash
# OpenClaw
SKILL_DIR="${OPENCLAW_WORKSPACE:-$HOME/.openclaw}/skills/xiaohongshu"

# Claude Code
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.claude/skills/xiaohongshu"

# 通用 .agents 路径
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.agents/skills/xiaohongshu"
```

后续所有命令都用 `exec` 工具或 bash 在该目录下运行。

## 执行规则

1. **每次操作前**，先运行 `status.py` 确认登录有效且配额够用
2. 如果��登录，告诉用户需要手动运行 `login.py` 扫码（需要用户用手机扫二维码，不能自动完成）
3. 所有脚本用 `python3` 执行
4. 输���是 JSON 格式，可直接解析
5. 出错时查看 `$SKILL_DIR/data/snapshots/` 截���和 `$SKILL_DIR/data/logs/` 日志

## 命令参考

### 检查状���（每次操作前必跑）

```bash
cd "$SKILL_DIR" && python3 scripts/status.py
```

或使用 exec 工具：
```json
{"tool": "exec", "command": "python3 scripts/status.py", "workdir": "<SKILL_DIR>"}
```

输出示例：
```
账号: default
登录: ✓ 已登录

今日配额:
  search       3/50 (剩余 47)
  detail       5/100 (剩余 95)
  download     0/200 (剩余 200)
  publish      0/3 (剩余 3)
```

如果���示"未登录"，告诉用户执行��
```bash
cd "$SKILL_DIR" && python3 scripts/login.py
```
二维码截���保存在 `$SKILL_DIR/data/snapshots/qrcode.png`，用户需要用手机小红书 App 扫码。

### 搜索笔记

```bash
cd "$SKILL_DIR" && python3 scripts/search.py --keyword "搜索词" --limit 20
```

```json
{"tool": "exec", "command": "python3 scripts/search.py --keyword '搜索词' --sort general --limit 20", "workdir": "<SKILL_DIR>"}
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--keyword` / `-k` | 搜索关键词 | 必填 |
| `--sort` | `general`（综合）/ `latest`（最新）/ `popular`（热门） | general |
| `--limit` / `-n` | 最多返回条数 | 20 |
| `--output` / `-o` | 保存��� JSONL 文件 | stdout |
| `--account` | 指定账号 | default |

输出：JSON 数组，每条含 `id`、`title`、`user.nickname`、`liked_count`、`url`。

### 获取笔记详情

```bash
cd "$SKILL_DIR" && python3 scripts/detail.py --url "https://www.xiaohongshu.com/explore/笔记ID"
```

```json
{"tool": "exec", "command": "python3 scripts/detail.py --url 'https://www.xiaohongshu.com/explore/笔记ID'", "workdir": "<SKILL_DIR>"}
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--url` / `-u` | 笔记链接 | 必填 |
| `--output` / `-o` | 保存到 JSON 文件 | stdout |
| `--account` | 指定账号 | default |

输出：JSON 对象，含 `title`、`desc`（正文）、`tags`、`images`（图片URL列表）、`video`（视频URL）、`liked_count`、`collected_count`、`comment_count`、`user`。

### 下载图片/视频

```bash
cd "$SKILL_DIR" && python3 scripts/download.py --url "https://www.xiaohongshu.com/explore/笔记ID"
```

```json
{"tool": "exec", "command": "python3 scripts/download.py --url 'https://www.xiaohongshu.com/explore/笔记ID' --output ./data/downloads/", "workdir": "<SKILL_DIR>"}
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--url` / `-u` | 笔记链接 | 必填 |
| `--output` / `-o` | 保存目录 | data/downloads/ |
| `--account` | 指定账号 | default |

自动创建子目录（笔记ID_标题��，已下���文���跳过。同时���存 `meta.json`。

### 发布图文

```bash
cd "$SKILL_DIR" && python3 scripts/publish.py --title "标题" --content "正文" --images /path/img1.jpg /path/img2.jpg --topics "话题1" "话题2"
```

```json
{"tool": "exec", "command": "python3 scripts/publish.py --title '标题' --content '正文' --images /path/img1.jpg --topics '话题'", "workdir": "<SKILL_DIR>"}
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--title` / `-t` | 标题 | 必填 |
| `--content` / `-c` | 正文 | 必填 |
| `--images` / `-i` | 图片路径（可多个） | 必填 |
| `--topics` | 话题标签（可多个） | 可选 |
| `--account` | 指定账号 | default |
| `--preview` | 只填充不发布，截图预览 | 默认自动发布 |

图片路径必须是绝对路径。

## 频率限制

所有操作内置限速，超限自动拒绝：

| 操作 | 每次间隔 | 每日上限 |
|------|---------|---------|
| 搜索 | 5-30 秒 | 50 次 |
| 详情 | 3-15 秒 | 100 次 |
| 下载 | 2-10 秒 | 200 次 |
| 发帖 | 5-10 分钟 | 3 条 |

可在 `$SKILL_DIR/config.json` 调��。

## 错误处理

| 错误信息 | 原因 | 处理 |
|---------|------|------|
| "今日已达上限 X 次" | 频率限制 | 等明天或调 config.json |
| "页��异常 (level 3)" | 验证码/风控 | 暂停所有操作，等至少 1 小时 |
| "未能提取笔记内容" | 页面结构变了 | 查看 data/snapshots/ 截图诊断 |
| "profile ���在被另一个进程使用" | 并发冲突 | 等前一个������结束 |
| "未登录，需��扫码" | 登录态过期 | 让用户跑 login.py 扫码 |

## 典型流程

用��说"搜一下小红书上关于 XX 的帖子"：

```bash
# 1. 检查状态
cd "$SKILL_DIR" && python3 scripts/status.py

# 2. 搜索
cd "$SKILL_DIR" && python3 scripts/search.py -k "XX" -n 10

# 3. 看某条���情
cd "$SKILL_DIR" && python3 scripts/detail.py -u "https://www.xiaohongshu.com/explore/笔记ID"

# 4. 下载图片
cd "$SKILL_DIR" && python3 scripts/download.py -u "https://www.xiaohongshu.com/explore/笔记ID"
```

用户说"帮我发一条小红书"：

```bash
# 1. 检查发帖配额
cd "$SKILL_DIR" && python3 scripts/status.py

# 2. 发帖
cd "$SKILL_DIR" && python3 scripts/publish.py -t "标题" -c "正文" -i /path/to/img.jpg
```

## 安装

```bash
# 克隆到 skill 目录
git clone https://github.com/drstrangerujn/xiaohongshu.git ~/.openclaw/skills/xiaohongshu
# 或
git clone https://github.com/drstrangerujn/xiaohongshu.git ~/.claude/skills/xiaohongshu

# 安装依赖
cd <skill目��> && bash scripts/setup.sh

# 首次登录
python3 scripts/login.py
```
