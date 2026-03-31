---
name: xiaohongshu
description: 在远程服务器上操作小红书——搜索笔记、浏览详情、下载图片视频、发帖。用于调研、情报搜集和内容规划。
---

# 小红书工具

通过 Playwright 控制无头浏览器操作小红书。

**脚本目录**: `~/.claude/skills/xiaohongshu/scripts/`
**运行时必须先 cd 到 skill 目录**:

```bash
cd ~/.claude/skills/xiaohongshu
```

## 使用前提

1. 已运行 `bash scripts/setup.sh` 安装依赖（Playwright + Chromium）
2. 已运行 `python3 scripts/login.py` 完成扫码登录

## 可用命令

所有命令都在 `~/.claude/skills/xiaohongshu/` 目录下执行。

### 检查状态

```bash
cd ~/.claude/skills/xiaohongshu && python3 scripts/status.py
```

输出登录状态和今日各操作的剩余配额。**每次操作前先跑这个确认登录还有效。**

### 搜索笔记

```bash
cd ~/.claude/skills/xiaohongshu && python3 scripts/search.py --keyword "关键词" [--sort general|latest|popular] [--limit 20] [--output results.jsonl]
```

返回 JSON 格式的笔记列表（id、标题、作者、点赞数、链接）。

### 获取笔记详情

```bash
cd ~/.claude/skills/xiaohongshu && python3 scripts/detail.py --url "https://www.xiaohongshu.com/explore/xxxxx" [--output note.json]
```

返回笔记完整信息：标题、正文、话题、图片/视频 URL、互动数据、评论、作者。

### 下载图片/视频

```bash
cd ~/.claude/skills/xiaohongshu && python3 scripts/download.py --url "https://www.xiaohongshu.com/explore/xxxxx" [--output ./downloads/]
```

下载笔记所有图片和视频，已下载的自动跳过。

### 发帖

```bash
cd ~/.claude/skills/xiaohongshu && python3 scripts/publish.py --title "标题" --content "正文" --images img1.jpg img2.jpg [--topics "话题1" "话题2"]
```

自动填充标题、正文、图片、话题，然后发布。加 `--preview` 只填充不发布，先截图看。

## 注意事项

- 所有操作有频率限制（搜索 50 次/天、详情 100 次/天、下载 200 次/天、发帖 3 条/天），超限自动拒绝
- 出现验证码或 403 时自动停止并报错，不要硬重试
- 日志: `data/logs/`，截图: `data/snapshots/`
- 频率配置可改: `config.json`

## 异常处理

| 错误 | 做法 |
|------|------|
| "今日已达上限" | 等明天，或改 config.json |
| "页面异常 level 3" | 触发风控，暂停，过段时间再试 |
| "未能提取笔记内容" | 可能改版了，看 data/snapshots/ 截图 |
| "profile 正在被另一个进程使用" | 等前一个操作跑完 |
| "登录失效" | 重跑 `python3 scripts/login.py` |
