# 小红书自动化工具

在远程 Linux 服务器（VPS/VDS）上通过 Claude Code 操作小红书——搜索、看帖、下载、偶尔发帖。主要用来做调研、搜集信息、辅助内容规划。

## 为什么要做这个

之前用的是社区的 `xiaohongshu-mcp`，跑在服务器上通过 MCP 协议让 Claude Code 调小红书。实际体验：

- MCP 服务进程三天两头挂，挂了登录态就没了，得重新扫码
- 搜索经常报错或没响应，排查还看不到有用的错误信息
- 服务器没有图形界面，扫码登录本身就麻烦

```
之前的链路：
Claude Code → HTTP → MCP 服务器（独立进程）→ 浏览器 → 小红书
                          ↑
                    这个东西经常挂
```

折腾够了，想换个省心的方案。

## 思路

把 MCP 服务器去掉，改成 Claude Code Skill——Claude Code 直接调 Python 脚本控制 Playwright 浏览器，操作小红书。

```
现在的链路：
Claude Code → Python 脚本 → Playwright → 小红书
```

少一层就少一个挂的地方。脚本跑完就退出，不需要一个服务进程常驻。浏览器状态（登录、cookie、本地存储）全部持久化在磁盘上的 profile 目录里，脚本重启、机器重启都不丢。

去掉 MCP 不代表就不会出问题了——Playwright 会崩、小红书会改版、登录态会过期——但至少问题会更集中、更好查，不用再猜"是 MCP 服务挂了还是小红书变了还是网络断了"。

## 这个工具是什么、不是什么

**是**：一个个人用的半自动化辅助工具，搜索和浏览自动跑，发帖需要人确认。

**不是**：
- 不是无人值守的自动运营系统
- 不追求多账号并发
- 不保证对小红书前端改版免维护
- 不把反风控当成完全可控的事

## 技术选型

| 组件 | 选择 | 为什么 |
|------|------|--------|
| 浏览器自动化 | Playwright | 原生支持 headless 和 persistent context，比 Selenium 好用 |
| 语言 | Python | Playwright 的 Python binding 成熟 |
| 数据存储 | JSONL + SQLite | JSONL 追加方便，SQLite 做去重和查询 |
| 登录态 | 浏览器 profile 持久化 | 比纯 cookie 稳，覆盖 localStorage/IndexedDB |

## 目录结构

```
~/.claude/skills/xiaohongshu/
├── SKILL.md                    # Skill 定义，Claude Code 读这个
├── scripts/
│   ├── setup.sh                # 一键装依赖
│   ├── login.py                # 扫码登录
│   ├── search.py               # 搜索
│   ├── detail.py               # 笔记详情
│   ├── download.py             # 下载图片/视频
│   ├── publish.py              # 发帖（半自动）
│   └── status.py               # 检查登录状态和今日用量
├── lib/
│   ├── browser.py              # 浏览器 persistent context + profile 锁
│   ├── auth.py                 # 登录态管理
│   ├── rate_limiter.py         # 频率控制
│   ├── human_sim.py            # 操作节奏控制（延迟、滚动）
│   ├── parser.py               # 数据提取
│   ├── fingerprint.py          # 账号级浏览器画像
│   ├── watchdog.py             # 异常检测
│   └── logger.py               # 日志 + 截图
├── data/
│   ├── profiles/               # 浏览器 profile（每账号一个）
│   ├── cache/                  # 搜索结果
│   ├── downloads/              # 下载的图片/视频
│   ├── logs/                   # 任务日志
│   └── snapshots/              # 截图 + 失败时的 HTML 快照
└── config.json                 # 配置
```

## 核心功能

### 登录

服务器没显示器，扫码流程：

1. Playwright 打开小红书登录页，截取二维码截图
2. 图片保存到 `data/snapshots/qrcode.png`（通过 Syncthing 同步到本地电脑看），同时尝试终端 ASCII 展示
3. 手机扫码
4. 成功后整个浏览器 profile 持久化到 `data/profiles/`

登录态管理用**完整浏览器 profile**（Playwright persistent context），不只存 cookie。小红书的登录状态可能涉及 localStorage、IndexedDB 等，只存 cookie 不一定够。每次操作前先做一次真实页面访问验证登录是否还有效。

Profile 目录加文件锁，防止多个脚本同时操作。

### 搜索

```bash
python scripts/search.py --keyword "护肤推荐" --sort "latest" --limit 20
```

数据提取策略：优先从网络响应里拿结构化 JSON（小红书搜索页加载时会请求接口），DOM 选择器作为备选。网络层数据比 DOM 稳定，前端改版时不容易挂。

实施上先用 DOM 跑通，同时录网络请求分析哪些接口能用，逐步切换。

### 笔记详情

```bash
python scripts/detail.py --url "https://www.xiaohongshu.com/explore/xxxxx"
```

抓标题、正文、话题、图片/视频 URL、点赞收藏评论数、评论列表、作者信息。同样网络层优先、DOM 备选。

### 下载

```bash
python scripts/download.py --url "https://www.xiaohongshu.com/explore/xxxxx" --output ./data/downloads/
```

尝试从页面资源请求中提取原始媒体地址直接下载。这条路能不能走通取决于小红书当前的资源访问策略（签名、鉴权、CDN 规则），可能需要根据实际情况适配。

下载记录写入 SQLite，已下载的自动跳过。

### 发帖（半自动）

```bash
python scripts/publish.py --title "标题" --content "正文" --images ./img1.jpg ./img2.jpg --topics "话题1" "话题2"
```

流程：
1. 自动打开发布页、上传图片、填标题正文、加话题
2. 生成预览截图，**停住，不自动点发布**
3. 截图同步到本地确认，人工决定发不发

不做全自动发布。发帖风险最高，让人看一眼再点总比出了问题回头查好。

## 防封号

核心不是"伪装成真人"，是**别做得太异常**：

- 频率压低，不批量不并发
- 账号环境保持稳定（固定 UA、viewport、语言、时区，不每次随机换）
- 操作顺序正常（搜完先翻几条再点进去，不是搜完直接批量抓）
- 出问题就停，不硬冲

### 频率控制

装饰器模式，所有操作经过限速：

```python
@rate_limit(min_delay=5, max_delay=30, daily_limit=50)
def search(keyword):
    ...
```

初始配置（保守值，跑一段时间根据实际情况调）：

| 操作 | 最短间隔 | 每日上限 | 说明 |
|------|---------|---------|------|
| 搜索 | 5-30s | 50 次 | 日常用够了 |
| 详情 | 3-15s | 100 次 | 正常浏览节奏 |
| 下载 | 2-10s | 200 次 | 走资源请求 |
| 发帖 | 5-10min | 3 条 | 偶尔发，不日更 |

这些数字不是"保证安全"的结论，是初始值。跑起来看实际情况再调。

### 浏览器画像

每个账号首次初始化时生成一套固定参数（UA、viewport、语言、时区），之后一直用这套。不做"每次启动随机化所有指纹"——一个账号每天换一套设备参数，比固定用一台设备更可疑。

### 异常处理

| 情况 | 做法 |
|------|------|
| 网络波动、超时 | 自动重试 3 次（10s/30s/60s） |
| 页面元素找不到、选择器失效 | 截图 + 存 HTML 快照，停掉这个任务 |
| 验证码、403、疑似风控 | 立刻暂停，通知人处理 |
| 登录失效 | 不强刷，走重新扫码流程 |
| 发帖异常 | 保留草稿状态，不重复提交 |

## 日志和排障

出了问题能查，比出问题少更重要。

- **任务日志**：每次操作记一条 JSONL（命令、参数、账号、起止时间、成功/失败、错误信息）
- **关键截图**：登录二维码、搜索结果页、笔记详情页、发帖预览页、所有异常页面
- **失败快照**：HTML 快照、控制台错误、关键网络请求摘要

小红书改版的时候，有截图和 HTML 快照才能快速定位哪里变了。

## 需要跑起来才能确认的事

方案里有些假设不是拍脑袋就能定的，得实际验证：

1. headless 环境下二维码截图能不能稳定被手机识别
2. profile 持久化后登录态实际能撑多久，什么操作会导致失效
3. 搜索和详情页的网络响应里到底有多少结构化数据能直接用
4. 下载链路是否有时效签名或额外鉴权
5. 发帖流程在低频使用下的实际稳定性

这些只能边做边验证，先把基础搭起来再说。

## 开发顺序

| 阶段 | 内容 | 怎么算做完 |
|------|------|-----------|
| P0 | 浏览器 + 扫码登录 + profile 持久化 | 能稳定登录，重启后状态还在 |
| P1 | 搜索 + 笔记详情 | 搜索能用，详情能抓，结果能导出 |
| P2 | 下载 | 图片视频能下，失败能重试 |
| P3 | 发帖（半自动） | 能自动填充，停在确认步，人点了才发 |
| P4 | Skill 集成 | Claude Code 调命令顺畅，日志能看 |

每步先手动跑通再接 Claude Code。

## 后面可以加的

- 定时发布（配合 cron）
- 关键词批量采集 + 去重
- 多账号切换
- 数据分析和趋势整理

## 部署

```bash
# 装依赖
cd ~/.claude/skills/xiaohongshu
bash scripts/setup.sh

# 首次登录
python scripts/login.py
# 二维码截图存到 data/snapshots/qrcode.png，拿手机扫

# 检查状态
python scripts/status.py
# 登录: ✓ | 今日操作: 0/50
```
