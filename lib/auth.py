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


def _data_dir():
    return Path(__file__).resolve().parent.parent / "data"


def _config():
    config_file = Path(__file__).resolve().parent.parent / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text())
    return {}


async def check_login(account: str = "default") -> dict:
    """检查登录状态，返回 {"logged_in": bool, "detail": str}"""
    try:
        async with open_browser(account) as (ctx, page):
            await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            login_btn = page.locator('div.login-container, [class*="login-btn"], [class*="LoginBtn"]')
            if await login_btn.count() > 0:
                return {"logged_in": False, "detail": "未登录，需要扫码"}

            user_avatar = page.locator('[class*="user-avatar"], [class*="avatar"], .sidebar-avatar, img.ava')
            if await user_avatar.count() > 0:
                return {"logged_in": True, "detail": "已登录"}

            path = await save_screenshot(page, "login_check")
            return {"logged_in": False, "detail": f"状态不确定，截图: {path}"}

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

        # 点击登录按钮
        for sel in ['div.login-container', '[class*="login-btn"]', '[class*="LoginBtn"]']:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(2)
                break

        # 切到扫码登录
        for sel in ['text=扫码登录', '[class*="qrcode"]', '[class*="QRCode"]']:
            tab = page.locator(sel)
            if await tab.count() > 0:
                await tab.first.click()
                await asyncio.sleep(2)
                break

        # 截取二维码
        qr_selectors = [
            '[class*="qrcode"] img', '[class*="QRCode"] img',
            'canvas[class*="qr"]', '.qrcode-img', '#qrcode img',
        ]
        qr_element = None
        for sel in qr_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                qr_element = loc.first
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
