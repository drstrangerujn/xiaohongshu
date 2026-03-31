"""操作节奏控制——延迟、滚动、输入"""

import asyncio
import random


async def random_delay(min_s: float = 1, max_s: float = 5):
    """正态分布随机延迟"""
    mean = (min_s + max_s) / 2
    std = (max_s - min_s) / 4
    delay = max(min_s, min(max_s, random.gauss(mean, std)))
    await asyncio.sleep(delay)


async def type_text(page, selector: str, text: str, min_interval: int = 50, max_interval: int = 150):
    """模拟输入，每个字符有随机间隔"""
    element = page.locator(selector)
    await element.click()
    for char in text:
        await element.type(char, delay=random.randint(min_interval, max_interval))


async def scroll_page(page, times: int = 3, direction: str = "down"):
    """变速滚动"""
    for _ in range(times):
        delta = random.randint(300, 800)
        if direction == "up":
            delta = -delta
        await page.mouse.wheel(0, delta)
        await random_delay(0.5, 2)


async def scroll_to_bottom(page, max_scrolls: int = 10, wait_s: float = 2):
    """滚动到底部，等待加载"""
    prev_height = 0
    for _ in range(max_scrolls):
        height = await page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await random_delay(1, wait_s)
