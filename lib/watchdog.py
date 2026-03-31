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
    content = await page.content()
    content_lower = content.lower()

    # 验证码 / 滑块
    captcha_signals = [
        "captcha", "验证", "滑块", "slider", "verify",
        "robot", "机器人", "安全验证",
    ]
    for signal in captcha_signals:
        if signal in content_lower:
            path = await save_screenshot(page, "captcha_detected")
            return {
                "ok": False,
                "issue": f"检测到验证码/风控 (信号: {signal})",
                "level": 3,
                "screenshot": path,
            }

    # 403 / 限流
    if "403" in title or "forbidden" in content_lower:
        path = await save_screenshot(page, "forbidden")
        return {
            "ok": False,
            "issue": "403 Forbidden",
            "level": 3,
            "screenshot": path,
        }

    # 空白页 / 加载失败
    body_text = await page.locator("body").inner_text()
    if len(body_text.strip()) < 50:
        path = await save_screenshot(page, "empty_page")
        return {
            "ok": False,
            "issue": "页面内容过少，可能加载失败",
            "level": 1,
            "screenshot": path,
        }

    return {"ok": True, "issue": None, "level": 0}
