# 小红书自动化工具：从 MCP 到 Claude Code Skill

## 一、背景和诉求

### 在做什么

在远程 Linux 服务器上跑 Claude Code（Anthropic 的 AI 编程助手），让它能直接操作小红书——搜索内容、抓取笔记、下载图片/视频、发布图文。目的是把小红书操作变成 AI 可直接调用的本地能力，而不是每次手动打开浏览器。

### 现有方案的问题

之前用的是社区开源的 `xiaohongshu-mcp`（基于 Model Context Protocol），架构：

```
Claude Code → HTTP 请求 → xiaohongshu-mcp 服务器（独立进程）→ 控制浏览器 → 小红书
```

实际跑下来，三个硬伤：

1. **MCP 服务器不稳定**：独立进程经常自己挂掉，重启后登录态丢失，得重新扫码。没人盯着的时候一崩就废。
2. **搜索和操作频繁报错**：对小红书页面结构变化没有容错，一改版就全挂。错误信息不透明，排查困难。
3. **服务器没有图形界面**：headless Linux 上扫码登录本身就是难题，MCP 方案没有很好地解决。

### 想要什么

一套 **Claude Code Skill**（技能插件），装在服务器上，Claude Code 能够：

- 直接在终端里调用小红书的搜索、浏览、下载、发布功能
- 在无图形界面的服务器上完成扫码登录
- 自动模拟真人操作节奏，降低封号风险
- 不依赖外部 MCP 服务器，减少故障点

### 项目定位

**面向 Claude Code 的小红书半自动化能力组件**——不是全自动无人值守运营系统。

只读操作（搜索、详情、下载）走自动化；写入操作（发布）走半自动流程，由人工最终确认。两类功能都做，但风控力度不同。

---

## 二、为什么从 MCP 换成 Skill

| 维度 | MCP 方案 | Skill 方案 |
|------|---------|-----------|
| 架构 | 独立服务器进程，Claude Code 通过 HTTP 调用 | Python 脚本直接嵌入 Claude Code 工作流 |
| 稳定性 | 服务器崩了全断，需人工重启 | 异常可捕获，不存在"服务器挂了" |
| 登录态 | 进程重启后丢失 | 浏览器 profile 持久化，重启后自动恢复 |
| 调试 | 黑盒，出错只看到"调用失败" | 每步有日志和截图，可直接诊断 |
| 频率控制 | 写死在服务器代码里 | 装饰器模式，参数可配置 |
| 部署 | 需单独启动和维护 MCP 服务器 | 装一次 skill 就行 |

```
MCP 方案：
Claude Code → HTTP → MCP Server（独立进程）→ Playwright → 小红书
                          ↑
                    这个进程会崩、会断、登录态会丢

Skill 方案：
Claude Code → bash 调用 Python 脚本 → Playwright → 小红书
                     ↑
               直接调用，没有中间商，异常直接捕获
```

去掉了中间进程，从"远程调用"变成"本地调用"。但要明确一点：**去掉 MCP 不等于自动化本身就会稳定**。真正决定长期可用性的是：登录状态能否稳定持久化、页面解析是否只依赖脆弱的 DOM 选择器、是否有可观测的运行机制。

---

## 三、技术方案

### 3.1 整体架构

```
用户 ↔ Claude Code（AI）
            ↓ 调用 Skill
      xiaohongshu skill（Python 脚本）
            ↓
      Playwright（无头浏览器，persistent context 复用）
            ↓
      小红书网页版
```

关键设计决策：

- **没有中间服务器**。Claude Code 直接通过 Python 脚本控制 Playwright
- **脚本独立执行，但共享持久化的浏览器 profile**。不搞复杂的调度框架，但通过 persistent context 实现状态复用，避免每次都冷启动浏览器
- **profile 加锁**，防止多个脚本同时操作同一个浏览器目录

### 3.2 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 浏览器自动化 | **Playwright** | 比 Selenium 更现代，原生支持 headless 和 persistent context |
| 语言 | **Python** | Claude Code 主力语言，Playwright Python binding 成熟 |
| 数据存储 | **JSONL + SQLite** | JSONL 方便追加和流式处理，SQLite 做索引和去重 |
| 登录态 | **浏览器 profile 持久化** | 比纯 Cookie 更完整，覆盖 localStorage/IndexedDB |
| 接口形式 | **Claude Code Skill（CLI 脚本）** | 通过 bash 调用，直接适配 |

### 3.3 目录结构

```
~/.claude/skills/xiaohongshu/
├── SKILL.md                    # Skill 定义（Claude Code 读这个来理解能力）
├── scripts/
│   ├── setup.sh                # 一键安装依赖
│   ├── login.py                # 扫码登录
│   ├── search.py               # 搜索笔记
│   ├── detail.py               # 笔记详情
│   ├── download.py             # 下载图片/视频
│   ├── publish.py              # 发布图文（半自动）
│   └── status.py               # 登录状态 + 今日配额
├── lib/
│   ├── browser.py              # 浏览器 persistent context 管理 + profile 锁
│   ├── auth.py                 # 登录态管理（profile 读写、状态检测）
│   ├── rate_limiter.py         # 频率控制（装饰器）
│   ├── human_sim.py            # 真人行为模拟（滚动、延迟）
│   ├── parser.py               # 数据提取（网络层优先，DOM 兜底）
│   ├── fingerprint.py          # 账号级浏览器画像（固定，非随机）
│   ├── watchdog.py             # 异常监控（验证码、封号预警）
│   └── logger.py               # 任务日志 + 关键截图 + 失败快照
├── data/
│   ├── profiles/               # 浏览器 profile（每账号一个目录）
│   ├── cache/                  # 搜索结果缓存
│   ├── downloads/              # 下载的图片/视频
│   ├── logs/                   # 任务日志（JSONL）
│   └── snapshots/              # 关键截图和失败时的 HTML 快照
└── config.json                 # 频率限制、保存路径等配置
```

### 3.4 Skill 定义

SKILL.md 告诉 Claude Code：
- 有哪些命令可以调用（`python scripts/search.py --keyword "xxx"` 等）
- 每个命令的参数和输出格式
- 调用前需要检查什么（登录态、配额）
- 出错了怎么处理（验证码、限流、登录过期）

---

## 四、核心功能详解

### 4.1 登录与身份管理

#### 扫码登录（headless 服务器）

服务器没有显示器，扫码方案：

```
1. Playwright 打开小红书登录页，截取二维码区域截图
2. 保存为图片文件（首选），同时生成终端 ASCII 二维码（备选）
3. 图片通过 Syncthing 同步到本地电脑，或由 Claude Code 直接读取展示
4. 用手机小红书 App 扫码
5. 扫码成功后，整个浏览器 profile 自动持久化
```

首选输出图片文件（稳定可靠），ASCII 终端展示作为备选——部分终端字体和缩放条件下 ASCII 二维码识别率不稳定。

#### 登录态持久化

**采用完整浏览器 profile 持久化，而非仅保存 Cookie。**

原因：小红书的登录状态不只依赖 Cookie，还涉及 localStorage、sessionStorage、IndexedDB 等浏览器存储。只存 Cookie 的话，重启后登录恢复不一定稳定。

具体做法：
- 每个账号维护独立 `user-data-dir`（Playwright persistent context）
- profile 目录加文件锁，禁止多个脚本同时使用同一账号
- 登录失败时，以整套 profile 重建为恢复单位，而不是只刷新 Cookie
- 保留 Cookie 导出能力，用于状态诊断
- 状态检查不只看 Cookie 时间，还执行一次真实页面访问验证

### 4.2 搜索笔记

```bash
python scripts/search.py --keyword "护肤推荐" --sort "latest" --limit 20
```

1. 检查登录态和频率配额
2. 打开小红书搜索页
3. 输入关键词，等待结果加载
4. **优先从网络响应中提取结构化数据**（搜索接口返回的 JSON），DOM 解析作为兜底
5. 如需翻页：滚动到底部，等待加载，重复解析
6. 输出 JSONL 格式结果，写入 SQLite 做去重
7. 关键步骤截图存入 snapshots/

### 4.3 笔记详情

```bash
python scripts/detail.py --url "https://www.xiaohongshu.com/explore/xxxxx"
```

抓取内容：
- 标题、正文、话题标签
- 图片/视频 URL
- 互动数据：点赞、收藏、评论数
- 评论列表（前 N 条）
- 作者信息

同样采用**网络层优先、DOM 兜底**的双通道解析策略。页面加载过程中拦截网络响应（`page.on('response')`），如果能拿到结构化 JSON 就直接用，比 DOM 选择器更稳定、对页面改版不敏感。

### 4.4 下载

```bash
python scripts/download.py --url "https://www.xiaohongshu.com/explore/xxxxx" --output ./data/downloads/
```

- 图片：提取原图 CDN URL 直接下载
- 视频：解析视频源地址，下载原始文件
- 下载记录写入 SQLite：来源笔记、下载时间、媒体类型、URL、文件 hash
- 失败可重试，已下载的自动跳过

### 4.5 发布图文（半自动）

```bash
python scripts/publish.py --title "标题" --content "正文" --images ./img1.jpg ./img2.jpg --topics "话题1" "话题2"
```

**发布采用半自动确认流程，不会全自动走完：**

1. 模拟点击进入发布页（走正常导航路径）
2. 上传图片：逐张上传，每张间隔 2-5 秒
3. 填写标题和正文（模拟输入节奏）
4. 添加话题
5. 生成预览截图，**停在待确认状态**
6. 截图通过 Syncthing 同步或 Claude Code 展示，由人工决定是否发布
7. 确认后才执行最终提交

这样既保留了自动填充的效率，又避免了误发和异常发布风险。全程 3-5 分钟，接近真人编辑节奏。

---

## 五、安全防护

### 5.1 核心原则

安全策略的重点不是"伪装得像真人"，而是**降低行为异常度**：

1. 降低频率，不做高并发
2. 保持账号环境画像稳定
3. 保持操作链条接近正常浏览顺序
4. 高风险操作人工接管，不强行自动重试

### 5.2 浏览器画像（账号级固定，非随机）

**不采用"每次随机化"策略，改为"账号级稳定画像"。**

原因：一个固定账号每次登录呈现不同的 UA、分辨率、时区、指纹，不会更像真人，反而构成环境漂移。对平台来说，持续一致的设备画像比高频随机变化更自然。

做法：
- 每个账号首次初始化时生成一套固定画像（UA、viewport、语言、时区）
- 存入 profile 配置，后续一直复用
- 尽量保持出口 IP 稳定，至少地区一致
- 不做 Canvas/WebGL 指纹噪声注入——收益不明确，反而可能触发检测

### 5.3 频率控制

装饰器模式，所有操作经过频率控制：

```python
@rate_limit(min_delay=5, max_delay=30, daily_limit=50, distribution="normal")
def search(keyword):
    ...
```

默认配置：

```json
{
  "rate_limits": {
    "search":   { "min_delay": 5,   "max_delay": 30,  "daily_limit": 50  },
    "detail":   { "min_delay": 3,   "max_delay": 15,  "daily_limit": 100 },
    "download": { "min_delay": 2,   "max_delay": 10,  "daily_limit": 200 },
    "publish":  { "min_delay": 300, "max_delay": 600,  "daily_limit": 3   }
  }
}
```

发布最严格：每次间隔 5-10 分钟，每天最多 3 条。

### 5.4 行为模拟

保持适度拟人，不过度：

| 行为 | 做法 |
|------|------|
| 页面停留 | 正态分布随机时间（3-15 秒） |
| 滚动 | 变速滚动，偶尔回滚 |
| 输入 | 适度延迟，不需要模拟"打错再删" |
| 操作顺序 | 搜索后先浏览几条再点详情，不立刻批量抓 |

不做贝塞尔曲线鼠标轨迹——实现成本高，对 headless 浏览器意义不大。

### 5.5 异常处理（分级）

不一律自动重试，按严重程度分级：

| 级别 | 情况 | 处理 |
|------|------|------|
| 一级 | 网络波动、超时 | 自动重试 3 次，间隔递增（10s/30s/60s） |
| 二级 | 页面元素缺失、选择器失效 | 截图 + 保存 HTML 快照，终止当前任务 |
| 三级 | 验证码、403、疑似风控 | 立即暂停账号，通知人工处理 |

### 5.6 风险评估

| 操作 | 频率建议 | 封号概率 | 说明 |
|------|---------|---------|------|
| 搜索浏览 | 50 次/天 | 极低 | 正常用户行为 |
| 查看详情 | 100 次/天 | 极低 | 正常浏览行为 |
| 下载 | 200 次/天 | 低 | 走 CDN |
| 发布 1-3 条/天 | 1-3 条/天 | 低 | 真人也会日更 2-3 条 |
| 发布 5 条+/天 | 不建议 | 中高 | 即使真人也可能被限流 |

---

## 六、可观测性设计

这部分决定了项目能不能从"能演示"走到"能维护"。

### 6.1 任务级日志

每个任务生成唯一 task_id，记录到 JSONL：

```json
{
  "task_id": "search_20260331_143022",
  "command": "search",
  "args": {"keyword": "护肤推荐", "limit": 20},
  "account": "account_1",
  "start_time": "2026-03-31T14:30:22",
  "end_time": "2026-03-31T14:31:05",
  "status": "success",
  "result_count": 20,
  "error": null
}
```

### 6.2 关键步骤截图

至少在以下节点自动截图：

- 登录页二维码
- 搜索结果页
- 笔记详情页
- 发布预览页
- 任何异常页面

### 6.3 失败时自动保存

- HTML 快照（当前页面完整 DOM）
- 浏览器控制台错误
- 关键网络请求摘要
- 当前浏览器环境信息

有了这些，小红书页面改版时能快速定位是哪里变了、怎么改。

---

## 七、数据提取策略

### 双通道方案

**网络层优先，DOM 兜底。**

小红书网页版在加载过程中会请求结构化接口，返回 JSON 数据。如果能从网络响应中直接提取笔记标题、作者、互动数据、媒体 URL，就不需要解析 DOM。

```python
# 拦截网络响应
async def on_response(response):
    if "/api/sns/web/v1/search" in response.url:
        data = await response.json()
        # 直接拿结构化数据，比 DOM 稳定得多
```

好处：
1. 结构化数据比 DOM 选择器稳定
2. 前端样式改版不影响
3. 解析逻辑可测试
4. DOM 兜底提升兼容性，不是唯一依赖

实施节奏：先用 DOM 跑通，同时用 `page.on('response')` 录下网络请求分析，确认哪些接口有结构化数据后逐步切换。

---

## 八、部署流程

```bash
# 1. 安装依赖
cd ~/.claude/skills/xiaohongshu
bash scripts/setup.sh
# pip install playwright && playwright install chromium

# 2. 首次登录
python scripts/login.py
# 二维码图片保存到 data/snapshots/qrcode.png
# 同时尝试终端 ASCII 展示
# 用手机扫码，成功后 profile 自动持久化

# 3. 验证
python scripts/status.py
# 登录状态: ✓ | Profile: account_1 | 今日操作: 0/50

# 4. Claude Code 即可调用
```

---

## 九、开发计划

| 阶段 | 内容 | 交付标准 |
|------|------|---------|
| **P0 基础设施** | 浏览器 persistent context + 扫码登录 + profile 持久化 + 锁 | 能稳定登录并复用状态，异常有截图和日志 |
| **P1 只读能力** | 搜索 + 笔记详情 | 搜索稳定，详情可复现，结果可导出 JSONL，重复抓取自动去重 |
| **P2 下载** | 图片/视频下载 | 下载有队列，文件命名规范，失败可重试，元数据可追溯 |
| **P3 半自动发布** | 自动填充 + 预览截图 + 人工确认 | 能自动填充标题正文话题，停在发布确认前，不自动点最终按钮 |
| **P4 集成** | SKILL.md + Claude Code 调试 | 命令调用顺畅，状态/日志/异常信息可读 |

每阶段先在服务器上手动跑通，确认稳定后再接入 Claude Code。

---

## 十、后续可扩展

先做核心功能，稳定后可以加：

- **定时发布**：配合 cron 发布草稿
- **数据分析**：关键词分析、热度趋势
- **批量采集**：关键词队列 + 去重
- **多账号管理**：不同 profile 对应不同账号
- **评论互动**：风险较高，需更保守的频率控制

---

## 十一、需要讨论的问题

1. **发布功能优先级**：如果核心诉求是采集分析，发布可以延后到只读能力稳定之后
2. **多账号需求**：是否需要支持多个小红书账号切换
3. **数据存储格式**：JSONL + SQLite 够用，还是需要 Excel 导出
4. **扫码方式**：图片文件同步（Syncthing）vs 终端 ASCII，哪个更方便
5. **服务器环境**：Python 版本、是否允许安装 Chromium、磁盘空间
6. **解析策略投入**：一开始就做网络层提取（前期稍重但长期稳），还是先 DOM 跑通再迭代
