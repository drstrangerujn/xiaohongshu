# 小红书自动化工具方案：从 MCP 到 Claude Code Skill

## 一、背景和诉求

### 我们在做什么

在远程 Linux 服务器上跑 Claude Code（Anthropic 的 AI 编程助手），让它能直接操作小红书——搜索内容、抓取笔记、下载图片/视频、发布图文。目标是把小红书变成 AI 可调用的"能力"，而不是每次都手动打开浏览器去操作。

### 现有方案的问题

之前用的是社区开源的 `xiaohongshu-mcp`（基于 Model Context Protocol），架构是这样的：

```
Claude Code → HTTP 请求 → xiaohongshu-mcp 服务器（独立进程）→ 控制浏览器 → 小红书
```

实际跑下来，三个硬伤：

1. **MCP 服务器不稳定**：独立进程，经常自己挂掉，重启后登录态丢失，得重新扫码。服务器没人盯着的时候一崩就废了。
2. **搜索和操作频繁报错**：MCP 对小红书的页面结构变化没有容错，一改版就全挂。错误信息还不透明，排查困难。
3. **服务器没有图形界面**：远程服务器是 headless Linux，扫码登录本身就是个难题。MCP 方案没有很好地解决这个问题。

### 我们想要什么

一套 **Claude Code Skill**（技能插件），装在服务器上，让 Claude Code 能够：

- 直接在终端里调用小红书的搜索、浏览、下载、发布功能
- 在无图形界面的服务器上完成扫码登录
- 自动模拟真人操作节奏，降低封号风险
- 不依赖外部 MCP 服务器，减少故障点

---

## 二、为什么换成 Skill 而不继续用 MCP

| 维度 | MCP 方案 | Skill 方案 |
|------|---------|-----------|
| 架构 | 独立服务器进程，Claude Code 通过 HTTP 调用 | Python 库直接嵌入 Claude Code 工作流，单进程 |
| 稳定性 | 服务器崩了就全断，需人工重启 | 异常可捕获，自动恢复，不存在"服务器挂了"的问题 |
| 登录态 | 进程重启后丢失 | Cookie 持久化到本地文件，重启后自动加载 |
| 调试 | 黑盒，出错只看到"调用失败" | 每一步有日志，Claude Code 能直接读取和诊断 |
| 频率控制 | 写死在服务器代码里，改不了 | 装饰器模式，参数可配置 |
| 部署 | 需要单独启动和维护 MCP 服务器 | 装一次 skill 就行，跟着 Claude Code 走 |

一句话：MCP 多了一个故障点（独立服务器进程），而 Skill 把能力直接内嵌到 Claude Code 里，少一层就稳一层。

---

## 三、技术方案

### 3.1 整体架构

```
用户 ↔ Claude Code（AI）
            ↓ 调用 Skill
      xiaohongshu skill（Python 脚本）
            ↓
      Playwright（无头浏览器）
            ↓
      小红书网页版
```

关键点：**没有中间服务器**。Claude Code 直接通过 Python 脚本控制 Playwright 浏览器，操作小红书。

### 3.2 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 浏览器自动化 | **Playwright** | 比 Selenium 更现代，原生支持 headless，API 更简洁，反检测能力更强 |
| 语言 | **Python** | Claude Code 生态主力语言，Playwright 的 Python binding 成熟 |
| 数据存储 | **JSON + SQLite** | 轻量，不需要额外数据库服务 |
| Cookie 管理 | **本地加密文件** | 持久化登录态，重启不丢失 |
| 接口形式 | **Claude Code Skill（CLI 脚本）** | Claude Code 通过 bash 调用 Python 脚本，天然适配 |

### 3.3 目录结构

```
~/.claude/skills/xiaohongshu/
├── SKILL.md                    # Skill 定义文件（Claude Code 读这个来理解能力）
├── scripts/
│   ├── setup.sh                # 一键安装依赖（Playwright + 浏览器）
│   ├── login.py                # 登录（扫码 → 保存 cookie）
│   ├── search.py               # 搜索笔记
│   ├── detail.py               # 获取笔记详情
│   ├── download.py             # 下载图片/视频
│   ├── publish.py              # 发布图文笔记
│   └── status.py               # 检查登录状态和今日配额
├── lib/
│   ├── browser.py              # 浏览器会话管理（单例模式）
│   ├── auth.py                 # 登录态管理（cookie 读写、过期检测）
│   ├── rate_limiter.py         # 频率控制（装饰器）
│   ├── human_sim.py            # 真人行为模拟（滚动、延迟、打字）
│   ├── fingerprint.py          # 浏览器指纹随机化
│   └── watchdog.py             # 异常监控（验证码检测、封号预警）
├── data/
│   ├── cookies/                # 加密的 cookie 文件
│   ├── cache/                  # 搜索结果缓存
│   └── downloads/              # 下载的图片/视频
└── config.json                 # 配置文件（频率限制参数、保存路径等）
```

### 3.4 Skill 定义（SKILL.md 核心内容）

Claude Code 通过 SKILL.md 来理解这个 Skill 能做什么、怎么调用。大致结构：

```yaml
---
name: xiaohongshu
description: 在远程服务器上操作小红书——搜索、浏览、下载、发布，模拟真人行为防封号
---
```

SKILL.md 里会告诉 Claude Code：
- 有哪些命令可以调用（`python scripts/search.py --keyword "xxx"` 等）
- 每个命令的参数和输出格式
- 调用前需要检查什么（登录态是否有效、今日配额剩余）
- 出错了怎么处理（验证码、限流、登录过期）

---

## 四、核心功能详解

### 4.1 扫码登录（headless 服务器的关键难题）

服务器没有显示器，怎么扫码？方案：

```
步骤 1：Playwright 打开小红书登录页，截取二维码区域的截图
步骤 2：将截图转成 ASCII 字符画（或 base64），直接输出到终端
步骤 3：用手机小红书 App 扫这个二维码
步骤 4：扫码成功后，Playwright 捕获 cookie，加密保存到本地
步骤 5：后续所有操作复用这个 cookie，无需重复登录
```

**备选方案**：如果终端显示 ASCII 二维码效果不好，也可以把截图保存为文件，通过 Syncthing 同步到本地电脑查看（我们的服务器已经配了 Syncthing）。

**Cookie 续期**：每次操作前检查 cookie 是否快过期，如果是则自动刷新（访问一次首页即可续期）。经验上小红书的 cookie 有效期约 30 天。

### 4.2 搜索笔记

```bash
python scripts/search.py --keyword "护肤推荐" --sort "latest" --limit 20
```

流程：
1. 检查登录态和频率配额
2. 打开小红书搜索页
3. 模拟输入关键词（逐字输入，每个字间隔 100-300ms）
4. 等待结果加载（随机 3-8 秒）
5. 解析结果列表（标题、作者、点赞数、链接）
6. 如需翻页：模拟滚动到底部，等待加载，重复解析
7. 输出 JSON 格式结果

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

### 4.4 下载

```bash
python scripts/download.py --url "https://www.xiaohongshu.com/explore/xxxxx" --output ./data/downloads/
```

- 图片：提取原图 URL，直接下载
- 视频：解析视频源地址，下载原始文件
- 去水印：小红书图片水印在前端叠加层，直接拿原始 CDN 链接即可绕过

### 4.5 发布图文

```bash
python scripts/publish.py --title "标题" --content "正文" --images ./img1.jpg ./img2.jpg --topics "话题1" "话题2"
```

这是封号风险最高的操作，流程设计得最保守：

1. 模拟点击进入发布页（不直接访问 URL，走正常导航路径）
2. 上传图片：逐张上传，每张间隔 2-5 秒
3. 填写标题：模拟打字速度（50-150ms/字）
4. 填写正文：同上，中间有随机停顿（像在思考措辞）
5. 添加话题：搜索并选择
6. 预览：停留 5-10 秒（像在检查内容）
7. 发布

**全程 3-5 分钟**，跟真人编辑一条笔记的节奏一致。

---

## 五、安全防护（防封号）

### 5.1 频率控制

采用装饰器模式，所有对小红书的操作都经过频率控制：

```python
@rate_limit(
    min_delay=5,      # 最短间隔 5 秒
    max_delay=30,     # 最长间隔 30 秒
    daily_limit=50,   # 每天最多 50 次操作
    distribution="normal"  # 正态分布，大多数在 10-20 秒
)
def search(keyword):
    ...
```

配置文件可调：

```json
{
  "rate_limits": {
    "search": { "min_delay": 5, "max_delay": 30, "daily_limit": 50 },
    "detail": { "min_delay": 3, "max_delay": 15, "daily_limit": 100 },
    "download": { "min_delay": 2, "max_delay": 10, "daily_limit": 200 },
    "publish": { "min_delay": 300, "max_delay": 600, "daily_limit": 3 }
  }
}
```

发布操作的限制最严格：每次间隔 5-10 分钟，每天最多 3 条。

### 5.2 真人行为模拟

| 行为 | 模拟方式 |
|------|---------|
| 鼠标移动 | 贝塞尔曲线轨迹，不走直线 |
| 滚动 | 变速滚动，偶尔回滚 |
| 打字 | 50-150ms/字，偶尔"打错"再删除 |
| 页面停留 | 正态分布随机时间，不会每页都一样 |
| 操作顺序 | 搜索后先浏览几条，再点进详情，不是搜完立刻抓数据 |

### 5.3 浏览器指纹随机化

每次启动浏览器会话时随机化：
- User-Agent（从真实 UA 池中选取）
- 屏幕分辨率
- 时区和语言设置
- WebGL 渲染器信息
- Canvas 指纹噪声

使用 Playwright 的 `browser.new_context()` 可以方便地设置这些参数。

### 5.4 异常处理

```
出现验证码 → 截图保存，暂停操作，通知用户手动处理
被限流（403/频繁重定向）→ 自动降速到最低频率，1 小时后恢复
登录失效（cookie 过期）→ 保存当前任务状态，提示重新扫码
网络异常 → 重试 3 次，间隔递增（10s/30s/60s）
页面结构变化（选择器失效）→ 记录失败详情，不强行操作
```

### 5.5 风险评估

| 操作 | 频率建议 | 封号概率 | 说明 |
|------|---------|---------|------|
| 搜索浏览 | 50 次/天 | 极低 | 跟正常用户一样 |
| 查看笔记详情 | 100 次/天 | 极低 | 正常浏览行为 |
| 下载图片/视频 | 200 次/天 | 低 | 走 CDN，小红书不太追踪 |
| 发布 1-2 条/天 | 1-2 条/天 | 低 | 加延迟后接近真人 |
| 发布 5 条+/天 | 不建议 | 中高 | 即使真人也可能被限流 |

---

## 六、与 MCP 方案的本质区别

```
MCP 方案（之前）：
Claude Code → HTTP → MCP Server（独立进程）→ Playwright → 小红书
     ↑                    ↑
  AI 这边           这个进程会崩、会断、登录态会丢

Skill 方案（现在）：
Claude Code → bash 调用 Python 脚本 → Playwright → 小红书
     ↑              ↑
  AI 这边      直接调用，没有中间商，异常直接捕获
```

去掉了中间的 MCP 服务器进程，从"远程调用"变成"本地调用"。每次操作都是一次独立的脚本执行，不存在"服务器挂了"的问题。Cookie 持久化在文件里，脚本重启、机器重启都不丢。

---

## 七、部署流程

```bash
# 1. 安装依赖（一键脚本）
cd ~/.claude/skills/xiaohongshu
bash scripts/setup.sh
# 内部执行：pip install playwright && playwright install chromium

# 2. 首次登录（扫码）
python scripts/login.py
# 终端会显示二维码（ASCII），用手机扫码
# 扫码成功后 cookie 自动保存

# 3. 验证
python scripts/status.py
# 输出：登录状态: ✓ | Cookie有效期: 29天 | 今日操作: 0/50

# 4. Claude Code 即可调用
# Claude Code 读取 SKILL.md 后，自动知道怎么调用上述脚本
```

---

## 八、后续可扩展

先做核心功能（搜索、详情、下载、发布），稳定后可以加：

- **定时发布**：配合 cron，指定时间自动发布草稿
- **数据分析**：对抓取的笔记做关键词分析、热度趋势
- **多账号管理**：不同 cookie 文件对应不同账号，切换使用
- **评论互动**：自动回复评论（风险较高，需要更保守的频率控制）

---

## 九、开发计划

| 阶段 | 内容 | 预计工作量 |
|------|------|-----------|
| P0 | 浏览器管理 + 扫码登录 + Cookie 持久化 | 核心基础 |
| P1 | 搜索 + 笔记详情 | 最常用功能 |
| P2 | 下载（图片/视频） | 实用功能 |
| P3 | 发布图文 | 风险最高，放最后做，反复测试 |
| P4 | SKILL.md 编写 + Claude Code 集成测试 | 整合 |

每个阶段做完都先在服务器上手动跑通，确认稳定后再接入 Claude Code。

---

## 十、需要讨论的问题

1. **发布功能是否需要**：发布的封号风险最高，如果只是做内容采集，可以先不做发布模块
2. **多账号需求**：是否需要支持多个小红书账号切换
3. **数据存储格式**：JSON 够用还是需要 SQLite/Excel
4. **扫码方式偏好**：终端 ASCII 二维码 vs 图片文件同步到本地
5. **服务器环境确认**：Python 版本、是否允许安装 Chromium、磁盘空间
