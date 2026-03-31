"""异常检测：验证码、风控、页面变化"""

from .logger import save_screenshot, save_failure_snapshot


async def check_page_anomaly(page) -> dict:
    """
    检查页面是否出现异常状态。
    返回 {"ok": bool, "issue": str|None, "level": 1|2|3}

    level 1: 可重试（网络问题）
    level 2: 需记录（页面结构变了）
    level 3: 需人工处理（验证码、风控）
    """
    url = page.url
    title = await page.title()

    # 用 body 可见文本判断，而不是整个 HTML（避免 class 名误触发）
    try:
        body_text = await page.locator("body").inner_text()
    except Exception:
        body_text = ""
    text_lower = body_text.lower()

    # 403 / 限流
    if "403" in title or "forbidden" in text_lower or "access denied" in text_lower:
        path = await save_screenshot(page, "forbidden")
        return {
            "ok": False,
            "issue": "403 Forbidden",
            "level": 3,
            "screenshot": path,
        }

    # 验证码 / 滑块
    # 注意：登录弹窗里的"获取验证码"不是风控验证码，要排除
    is_login_popup = "手机号登录" in body_text or "扫码登录" in body_text or "登录后推荐" in body_text
    if not is_login_popup:
        captcha_signals = ["滑块验证", "安全验证", "人机验证", "机器人", "robot check", "请完成验证"]
        for signal in captcha_signals:
            if signal in text_lower:
                path = await save_screenshot(page, "captcha_detected")
                return {
                    "ok": False,
                    "issue": f"检测到验证码/风控 (信号: {signal})",
                    "level": 3,
                    "screenshot": path,
                }
    elif is_login_popup:
        # 登录弹窗不是异常，但说明需要登录
        return {
            "ok": False,
            "issue": "需要登录，请先运行 login.py 扫码",
            "level": 2,
        }

    # 空白页 / 加载失败
    if len(body_text.strip()) < 50:
        path = await save_screenshot(page, "empty_page")
        return {
            "ok": False,
            "issue": "页面内容过少，可能加载失败",
            "level": 1,
            "screenshot": path,
        }

    return {"ok": True, "issue": None, "level": 0}
