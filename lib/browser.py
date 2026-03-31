"""浏览器 persistent context 管理 + profile 锁"""

import fcntl
import json
from pathlib import Path
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright

from .fingerprint import get_or_create_profile


def _data_dir():
    return Path(__file__).resolve().parent.parent / "data"


class ProfileLock:
    """文件锁，防止多个脚本同时操作同一个 profile"""

    def __init__(self, account: str):
        lock_dir = _data_dir() / "profiles" / account
        lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = lock_dir / ".lock"
        self._fd = None

    def acquire(self):
        self._fd = open(self.lock_path, "w")
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fd.close()
            raise RuntimeError(
                "该账号的浏览器 profile 正在被另一个进程使用，等它跑完再试"
            )

    def release(self):
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None


@asynccontextmanager
async def open_browser(account: str = "default", headless: bool = True):
    """
    打开带持久化 profile 的浏览器。
    用法:
        async with open_browser("my_account") as (context, page):
            await page.goto("https://www.xiaohongshu.com")
    """
    lock = ProfileLock(account)
    lock.acquire()

    fp = get_or_create_profile(account)
    profile_dir = _data_dir() / "profiles" / account / "browser_data"
    profile_dir.mkdir(parents=True, exist_ok=True)

    pw = await async_playwright().start()
    try:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            user_agent=fp["user_agent"],
            viewport=fp["viewport"],
            locale=fp["locale"],
            timezone_id=fp["timezone_id"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        # 去掉 webdriver 标记
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = context.pages[0] if context.pages else await context.new_page()
        yield context, page

        await context.close()
    finally:
        await pw.stop()
        lock.release()
