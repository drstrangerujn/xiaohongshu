"""登录态管理：扫码登录、状态检查"""

import asyncio
from pathlib import Path

from .browser import open_browser
from .logger import save_screenshot, log_task


XHS_HOME = "https://www.xiaohongshu.com"
XHS_LOGIN = "https://www.xiaohongshu.com"


async def check_login(account: str = "default") -> dict:
    """检查登录状态，返回 {"logged_in": bool, "detail": str}"""
    try:
        async with open_browser(account) as (ctx, page):
            await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 检查是否有登录按钮（未登录时存在）
            login_btn = page.locator('div.login-container, [class*="login-btn"], [class*="LoginBtn"]')
            if await login_btn.count() > 0:
                return {"logged_in": False, "detail": "未登录，需要扫码"}

            # 检查是否有用户头像（已登录标志）
            user_avatar = page.locator('[class*="user-avatar"], [class*="avatar"], .sidebar-avatar, img.ava')
            if await user_avatar.count() > 0:
                return {"logged_in": True, "detail": "已登录"}

            # 不确定——截图看看
            path = await save_screenshot(page, "login_check")
            return {"logged_in": False, "detail": f"状态不确定，截图: {path}"}

    except Exception as e:
        return {"logged_in": False, "detail": f"检查失败: {e}"}


async def qr_login(account: str = "default") -> dict:
    """
    打开登录页，截取二维码，等待用户扫码。
    返回 {"success": bool, "qr_path": str, "detail": str}
    """
    async with open_browser(account) as (ctx, page):
        await page.goto(XHS_HOME, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 点击登录按钮（如果存在）
        login_triggers = [
            'div.login-container',
            '[class*="login-btn"]',
            '[class*="LoginBtn"]',
        ]
        for sel in login_triggers:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(2)
                break

        # 尝试找到并点击"扫码登录"选项
        qr_tab_selectors = [
            'text=扫码登录',
            '[class*="qrcode"]',
            '[class*="QRCode"]',
        ]
        for sel in qr_tab_selectors:
            tab = page.locator(sel)
            if await tab.count() > 0:
                await tab.first.click()
                await asyncio.sleep(2)
                break

        # 截取二维码区域
        qr_selectors = [
            '[class*="qrcode"] img',
            '[class*="QRCode"] img',
            'canvas[class*="qr"]',
            '.qrcode-img',
            '#qrcode img',
        ]

        qr_element = None
        for sel in qr_selectors:
            loc = page.locator(sel)
            if await loc.count() > 0:
                qr_element = loc.first
                break

        # 截整页也行，用户能看到二维码就行
        data_dir = Path(__file__).resolve().parent.parent / "data"
        qr_path = str(data_dir / "snapshots" / "qrcode.png")
        Path(qr_path).parent.mkdir(parents=True, exist_ok=True)

        if qr_element:
            await qr_element.screenshot(path=qr_path)
        else:
            await page.screenshot(path=qr_path)

        # 尝试在终端显示 ASCII 二维码
        _print_ascii_hint(qr_path)

        print(f"\n二维码已保存: {qr_path}")
        print("请用手机小红书 App 扫码...")
        print("等待扫码确认（最长 120 秒）...\n")

        # 轮询等待登录成功
        for i in range(60):  # 120秒，每2秒检查一次
            await asyncio.sleep(2)

            # 检查是否跳转到了首页 / 出现了用户头像
            url = page.url
            avatar = page.locator('[class*="user-avatar"], [class*="avatar"], .sidebar-avatar, img.ava')
            login_el = page.locator('div.login-container, [class*="login-btn"]')

            if await avatar.count() > 0 or (await login_el.count() == 0 and "explore" in url):
                # 登录成功，profile 会自动持久化（persistent context）
                await save_screenshot(page, "login_success")
                log_task("login", {"account": account}, "success")
                print("登录成功!")
                return {
                    "success": True,
                    "qr_path": qr_path,
                    "detail": "扫码登录成功，profile 已持久化",
                }

            # 每 20 秒刷新一下二维码截图（可能过期）
            if i > 0 and i % 10 == 0:
                if qr_element and await qr_element.count() > 0:
                    await qr_element.screenshot(path=qr_path)
                else:
                    await page.screenshot(path=qr_path)
                print(f"二维码已刷新 ({i * 2}s)...")

        log_task("login", {"account": account}, "timeout")
        return {
            "success": False,
            "qr_path": qr_path,
            "detail": "扫码超时（120秒），请重试",
        }


def _print_ascii_hint(image_path: str):
    """尝试在终端打印提示，不强求 ASCII 二维码"""
    try:
        from PIL import Image
        img = Image.open(image_path)
        # 简单缩放后用字符表示
        w, h = img.size
        aspect = h / w
        new_w = 60
        new_h = int(new_w * aspect * 0.5)
        img = img.resize((new_w, new_h)).convert("L")

        chars = " .:-=+*#%@"
        pixels = list(img.getdata())
        ascii_img = ""
        for i, px in enumerate(pixels):
            ascii_img += chars[px * (len(chars) - 1) // 255]
            if (i + 1) % new_w == 0:
                ascii_img += "\n"
        print(ascii_img)
    except Exception:
        print("（终端 ASCII 预览不可用，请查看图片文件）")
