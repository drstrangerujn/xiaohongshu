---
name: xiaohongshu
description: 在远程服务器上操作小红书——搜索、浏览笔记、下载图片视频、半自动发帖。用于调研、情报搜集和内容规划。
---

# 小红书工具

操作小红书的 Skill，通过 Playwright 控制无头浏览器。所有脚本在 `~/.claude/skills/xiaohongshu/scripts/` 下。

## 使用前提

1. 已运行 `bash scripts/setup.sh` 安装依赖
2. 已运行 `python scripts/login.py` 完成扫码登录

## 可用命令

### 检查状态

```bash
python scripts/status.py [--account ACCOUNT]
```

输出登录状态和今日各操作的剩余配额。**每次使用其他命令前先跑一下这个。**

### 搜索笔记

```bash
python scripts/search.py --keyword "关键词" [--sort general|latest|popular] [--limit 20] [--output results.jsonl]
```

返回 JSON 格式的笔记列表（id、标题、作者、点赞数、链接）。

### 获取笔记详情

```bash
python scripts/detail.py --url "https://www.xiaohongshu.com/explore/xxxxx" [--output note.json]
```

返回笔记完整信息（标题、正文、话题、图片/视频 URL、互动数据、评论）。

### 下载图片/视频

```bash
python scripts/download.py --url "https://www.xiaohongshu.com/explore/xxxxx" [--output ./downloads/]
```

下载笔记的所有图片和视频，自动跳过已下载的文件。

### 半自动发帖

```bash
python scripts/publish.py --title "标题" --content "正文" --images img1.jpg img2.jpg [--topics "话题1" "话题2"]
```

自动填充标题、正文、图片和话题，但**不会自动点发布按钮**。会生成预览截图，需要用户确认后才发布。

## 注意事项

- 所有操作有频率限制（搜索 50 次/天、详情 100 次/天、下载 200 次/天、发帖 3 条/天），超限会自动拒绝
- 出现验证码或 403 时会自动停止并报错，不要硬重试，等一段时间或人工处理
- 日志在 `data/logs/`，截图在 `data/snapshots/`，排障时可以看
- 配置在 `config.json`，频率限制参数可以调

## 异常处理

| 错误 | 做法 |
|------|------|
| "今日已达上限" | 等明天，或改 config.json 里的限制 |
| "页面异常 level 3" | 可能触发了风控，暂停操作，过一段时间再试 |
| "未能提取笔记内容" | 小红书可能改版了，看 data/snapshots/ 里的截图和 HTML |
| "profile 正在被另一个进程使用" | 等前一个操作跑完 |
| "登录失效" | 重新跑 `python scripts/login.py` |
