"""登录态管理：扫码登录、状态检查、二维码推送"""

import asyncio
import base64
import json
import subprocess
import threading
import http.server
import functools
import socket
from pathlib import Path

from .browser import open_browser
from .logger import save_screenshot, log_task


XHS_HOME = "https://www.xiaohongshu.com"


async def _dismiss_popups(page):
    """关掉 cookie banner 和登录弹窗等所有遮挡"""
    # 1. Cookie banner
    try:
        accept_btn = page.locator('.cookie-banner__btn--primary')
        if await accept_btn.count() > 0 and await accept_btn.is_visible():
            await accept_btn.click()
            await asyncio.sleep(1)
    except Exception:
        pass

    # 2. JS 一次性清理所有遮挡
    await page.evaluate("""
        // cookie banner
        document.querySelectorAll('.cookie-banner, .cookie-banner-overlay, .cookie-banner--web').forEach(e => e.remove());
        // 登录弹窗
        document.querySelectorAll('.login-modal, .reds-modal-open, .reds-mask').forEach(e => e.remove());
        // 恢复滚动
        document.body.style.overflow = 'auto';
        document.documentElement.style.overflow = 'auto';
    """)


# 保持旧名字兼容
_dismiss_cookie_banner = _dismiss_popups


def _data_dir():
    return Path(__file__).resolve().parent.parent / "data"


def _config():
    config_file = Path(__file__).resolve().parent.parent / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text())
    return {}


async def check_login(account: str = "default") -> dict:
    """
    检查登录状态。三层判断：
    1. cookie 里有 web_session → 已登录（最可靠，不依赖页面渲染）
    2. 页面上有用户头像 → 已登录
    3. 都没有 → 未登录
    """
    try:
        async with open_browser(account) as (ctx, page):
            await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 第一层：查 cookie（最可靠）
            cookies = await ctx.cookies()
            cookie_names = {c["name"] for c in cookies if "xiaohongshu" in c.get("domain", "")}
            has_session = "web_session" in cookie_names

            if has_session:
                return {
                    "logged_in": True,
                    "detail": "已登录（web_session cookie 有效）",
                    "cookies": sorted(cookie_names),
                }

            # 第二层：查页面元素
            user_avatar = page.locator('[class*="user-avatar"], [class*="avatar"], .sidebar-avatar, img.ava')
            if await user_avatar.count() > 0 and await user_avatar.first.is_visible():
                return {"logged_in": True, "detail": "已登录（页面有用户头像）", "cookies": sorted(cookie_names)}

            # 第三层：没登录
            return {
                "logged_in": False,
                "detail": "未登录，需要扫码",
                "cookies": sorted(cookie_names),
            }

    except Exception as e:
        return {"logged_in": False, "detail": f"检查失败: {e}"}


def _get_local_ip():
    """获取本机外网可达 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _start_qr_server(qr_path: str, port: int = 18088) -> str:
    """启动临时 HTTP 服务，让二维码图片可通过 URL 访问"""
    qr_dir = str(Path(qr_path).parent)
    qr_filename = Path(qr_path).name

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=qr_dir)

    # 静默日志
    class QuietHandler(handler):
        def log_message(self, format, *args):
            pass

    try:
        server = http.server.HTTPServer(("0.0.0.0", port), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        ip = _get_local_ip()
        return f"http://{ip}:{port}/{qr_filename}"
    except OSError:
        # 端口被占用就算了
        return None


def _push_qr_image(qr_path: str, qr_url: str = None) -> dict:
    """
    尝试通过各种渠道推送二维码图片。
    按优先级尝试：ntfy → Telegram → 仅返回 URL。
    配置在 config.json 的 "notify" 字段。
    """
    config = _config().get("notify", {})
    results = {}

    # 1. ntfy.sh —— 最简单，不需要 token
    ntfy_topic = config.get("ntfy_topic")
    if ntfy_topic:
        try:
            import requests
            resp = requests.put(
                f"https://ntfy.sh/{ntfy_topic}",
                data=open(qr_path, "rb"),
                headers={
                    "Filename": "qrcode.png",
                    "Title": "小红书扫码登录",
                    "Tags": "key",
                },
                timeout=10,
            )
            if resp.ok:
                results["ntfy"] = f"已推送到 ntfy.sh/{ntfy_topic}"
        except Exception as e:
            results["ntfy"] = f"推送失败: {e}"

    # 2. Telegram Bot API —— 如果配了 token
    tg_token = config.get("telegram_bot_token")
    tg_chat_id = config.get("telegram_chat_id")
    if tg_token and tg_chat_id:
        try:
            import requests
            resp = requests.post(
                f"https://api.telegram.org/bot{tg_token}/sendPhoto",
                data={"chat_id": tg_chat_id, "caption": "小红书扫码登录 - 请用手机扫码"},
                files={"photo": open(qr_path, "rb")},
                timeout=10,
            )
            if resp.ok:
                results["telegram"] = "已发送到 Telegram"
        except Exception as e:
            results["telegram"] = f"发送失败: {e}"

    # 3. 返回 URL（如果临时 HTTP 服务启动了）
    if qr_url:
        results["url"] = qr_url

    # 4. 返回 base64（兜底，agent 可以用任何方式处理）
    try:
        b64 = base64.b64encode(open(qr_path, "rb").read()).decode()
        results["base64"] = b64
        results["base64_length"] = len(b64)
    except Exception:
        pass

    return results


async def qr_login(account: str = "default", serve_port: int = 18088) -> dict:
    """
    打开登录页，截取二维码，推送给用户，等待扫码。
    返回 {"success": bool, "qr_path": str, "qr_url": str, "push": dict, "detail": str}
    """
    async with open_browser(account) as (ctx, page):
        await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 干掉 cookie banner / 隐私弹窗（点"同意"或直接关掉）
        await _dismiss_cookie_banner(page)

        # 小红书关掉 cookie banner 后会自动弹出登录弹窗（.login-modal）
        # 如果没弹出来，再手动点登录按钮
        login_modal = page.locator('.login-modal, .login-container')
        if await login_modal.count() == 0 or not await login_modal.first.is_visible():
            for sel in ['button.login-btn', '.side-bar-component.login-btn', '[class*="login-btn"]']:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(force=True)  # force 跳过遮罩检查
                    await asyncio.sleep(2)
                    break

        await asyncio.sleep(2)

        # 二维码在登录弹窗里，class="qrcode-img"
        qr_element = page.locator('img.qrcode-img').first
        if await qr_element.count() == 0:
            # 兜底：试试其他选择器
            for sel in ['.qrcode-img', '[class*="qrcode"] img', 'canvas']:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    qr_element = loc
                    break

        qr_path = str(_data_dir() / "snapshots" / "qrcode.png")
        Path(qr_path).parent.mkdir(parents=True, exist_ok=True)

        if qr_element:
            await qr_element.screenshot(path=qr_path)
        else:
            await page.screenshot(path=qr_path)

        # 启动临时 HTTP 服务
        qr_url = _start_qr_server(qr_path, serve_port)

        # 推送二维码
        push_results = _push_qr_image(qr_path, qr_url)

        # 输出信息（JSON 格式，方便 agent 解析）
        output = {
            "status": "waiting_for_scan",
            "qr_path": qr_path,
            "qr_url": qr_url,
            "push": push_results,
            "message": "请用手机小红书 App 扫描二维码登录",
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

        # 轮询等待登录成功
        for i in range(60):  # 120秒
            await asyncio.sleep(2)

            url = page.url
            avatar = page.locator('[class*="user-avatar"], [class*="avatar"], .sidebar-avatar, img.ava')
            login_el = page.locator('div.login-container, [class*="login-btn"]')

            if await avatar.count() > 0 or (await login_el.count() == 0 and "explore" in url):
                await save_screenshot(page, "login_success")
                log_task("login", {"account": account}, "success")
                return {
                    "success": True,
                    "qr_path": qr_path,
                    "qr_url": qr_url,
                    "push": push_results,
                    "detail": "登录成功",
                }

            # 每 20 秒刷新二维码
            if i > 0 and i % 10 == 0:
                if qr_element and await qr_element.count() > 0:
                    await qr_element.screenshot(path=qr_path)
                else:
                    await page.screenshot(path=qr_path)

        log_task("login", {"account": account}, "timeout")
        return {
            "success": False,
            "qr_path": qr_path,
            "qr_url": qr_url,
            "push": push_results,
            "detail": "扫码超时（120秒）",
        }
