---
name: xiaohongshu
description: Use this skill whenever the user wants to interact with Xiaohongshu (小红书/RED). This includes searching for notes/posts, viewing note details, downloading images/videos from notes, publishing image-text posts, or checking account status. Trigger when user mentions 小红书, RED, xiaohongshu, or asks to search/post/download content on that platform.
---

# 小红书操作指南

本 Skill 通过 Playwright 无头浏览器操作小红书。所有脚本位于本 Skill 目录的 `scripts/` 下。

**重要：所有命令必须在 Skill 目录下执行。**

```bash
SKILL_DIR="$HOME/.claude/skills/xiaohongshu"
```

## 执行规则

1. **每次操作前**，先运行 `status.py` 确认登录状态和配额
2. 如果未登录，提示用户运行 `python3 "$SKILL_DIR/scripts/login.py"` 扫码（需要用户手动扫码，不能自动完成）
3. 所有 python 命令用 `python3` 执行
4. 输出默认是 JSON，可以直接解析和使用
5. 出错时先看 `$SKILL_DIR/data/snapshots/` 和 `$SKILL_DIR/data/logs/` 里的截图和日志排查原因

## 命令参考

### 检查状态（每次操作前必跑）

```bash
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/status.py
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

如果显示"未登录"，告诉用户需要扫码登录：
```bash
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/login.py
```
登录需要用户用手机小红书 App 扫描二维码，二维码图片保存在 `data/snapshots/qrcode.png`。

### 搜索笔记

```bash
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/search.py --keyword "搜索词" --sort general --limit 20
```

参数：
- `--keyword` / `-k`：搜索关键词（必填）
- `--sort`：排序方式，`general`（综合）、`latest`（最新）、`popular`（热门），默认 `general`
- `--limit` / `-n`：最多返回条数，默认 20
- `--output` / `-o`：保存到 JSONL 文件
- `--account`：指定账号，默认 `default`

输出：JSON 数组，每条包含 `id`、`title`、`user.nickname`、`liked_count`、`url` 等字段。

### 获取笔记详情

```bash
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/detail.py --url "https://www.xiaohongshu.com/explore/笔记ID"
```

参数：
- `--url` / `-u`：笔记链接（必填）
- `--output` / `-o`：保存到 JSON 文件
- `--account`：指定账号，默认 `default`

输出：JSON 对象，包含 `title`、`desc`（正文）、`tags`、`images`（图片URL列表）、`video`（视频URL）、`liked_count`、`collected_count`、`comment_count`、`user` 等。

### 下载图片/视频

```bash
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/download.py --url "https://www.xiaohongshu.com/explore/笔记ID" --output ./目标目录/
```

参数：
- `--url` / `-u`：笔记链接（必填）
- `--output` / `-o`：保存目录，默认 `data/downloads/`
- `--account`：指定账号，默认 `default`

会自动创建子目录，按笔记 ID 和标题命名。已下载的文件自动跳过。同时保存 `meta.json` 记录笔记元数据。

### 发帖

```bash
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/publish.py --title "标题" --content "正文内容" --images /path/to/img1.jpg /path/to/img2.jpg --topics "话题1" "话题2"
```

参数：
- `--title` / `-t`：标题（必填）
- `--content` / `-c`：正文（必填）
- `--images` / `-i`：图片路径，可多个（必填）
- `--topics`：话题标签，可多个（可选）
- `--account`：指定账号，默认 `default`
- `--preview`：加上后只填充内容不点发布按钮，截图预览

默认行为是自动发布。图片路径必须是绝对路径或相对于当前目录的有效路径。

## 频率限制

所有操作内置频率控制，超限会报错拒绝执行：

| 操作 | 每次间隔 | 每日上限 |
|------|---------|---------|
| 搜索 | 5-30 秒 | 50 次 |
| 详情 | 3-15 秒 | 100 次 |
| 下载 | 2-10 秒 | 200 次 |
| 发帖 | 5-10 分钟 | 3 条 |

配置文件 `config.json` 可调整。

## 错误处理

| 错误信息 | 原因 | 处理 |
|---------|------|------|
| "今日已达上限 X 次" | 频率限制 | 等明天，或调 config.json |
| "页面异常 (level 3)" | 验证码/风控 | 暂停所有操作，至少等 1 小时 |
| "未能提取笔记内容" | 页面结构变了或加载失败 | 查看 `data/snapshots/` 截图诊断 |
| "profile 正在被另一个进程使用" | 有其他脚本在跑 | 等它结束 |
| "未登录，需要扫码" | 登录态失效 | 让用户跑 login.py 重新扫码 |

## 典型使用流程

用户说"帮我搜一下小红书上关于 XX 的帖子"时：

```bash
# 1. 先检查状态
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/status.py

# 2. 确认登录有效后搜索
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/search.py -k "XX" -n 10

# 3. 如果用户想看某条笔记的详情
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/detail.py -u "https://www.xiaohongshu.com/explore/笔记ID"

# 4. 如果用户想下载某条笔记的图片
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/download.py -u "https://www.xiaohongshu.com/explore/笔记ID"
```

用户说"帮我发一条小红书"时：

```bash
# 1. 检查状态和发帖配额
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/status.py

# 2. 发帖（图片必须先准备好）
cd "$HOME/.claude/skills/xiaohongshu" && python3 scripts/publish.py -t "标题" -c "正文" -i /path/to/img.jpg
```
