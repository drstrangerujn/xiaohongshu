#!/usr/bin/env python3
"""发布小红书图文笔记（默认自动发，--preview 可以先看再发）"""

import argparse
import asyncio
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.browser import open_browser
from lib.rate_limiter import rate_limit
from lib.human_sim import random_delay, type_text
from lib.watchdog import check_page_anomaly
from lib.logger import log_task, save_screenshot


@rate_limit("publish")
async def do_publish(
    account: str,
    title: str,
    content: str,
    images: list,
    topics: list = None,
    preview_only: bool = False,
) -> dict:
    """
    填充内容并发布。
    preview_only=True 时只填充不点发布，截图后退出。
    """

    async with open_browser(account) as (ctx, page):
        # 直接进创作者发布页
        await page.goto("https://creator.xiaohongshu.com/publish/publish",
                        wait_until="domcontentloaded", timeout=30000)
        await random_delay(2, 4)

        anomaly = await check_page_anomaly(page)
        if not anomaly["ok"] and anomaly["level"] >= 3:
            raise RuntimeError(f"页面异常: {anomaly['issue']}")

        # 上传图片
        for img_path in images:
            img_path = os.path.abspath(img_path)
            if not os.path.exists(img_path):
                raise FileNotFoundError(f"图片不存在: {img_path}")

            upload_selectors = [
                'input[type="file"]',
                '[class*="upload"] input[type="file"]',
            ]
            for sel in upload_selectors:
                upload = page.locator(sel)
                if await upload.count() > 0:
                    await upload.first.set_input_files(img_path)
                    await random_delay(2, 5)
                    break

        await random_delay(3, 5)

        # 填标题
        title_selectors = [
            '[placeholder*="标题"]',
            '[class*="title"] input',
            '[class*="title"] textarea',
            '#title',
        ]
        for sel in title_selectors:
            el = page.locator(sel)
            if await el.count() > 0:
                await el.first.click()
                await el.first.fill("")
                await el.first.type(title, delay=80)
                await random_delay(1, 2)
                break

        # 填正文
        content_selectors = [
            '[placeholder*="正文"]',
            '[placeholder*="内容"]',
            '[class*="content"] [contenteditable]',
            '[class*="editor"] [contenteditable]',
            '#content',
        ]
        for sel in content_selectors:
            el = page.locator(sel)
            if await el.count() > 0:
                await el.first.click()
                await el.first.type(content, delay=60)
                await random_delay(1, 3)
                break

        # 添加话题
        if topics:
            for topic in topics:
                topic_input_selectors = [
                    '[placeholder*="话题"]',
                    '[class*="topic"] input',
                    '[class*="tag"] input',
                ]
                for sel in topic_input_selectors:
                    el = page.locator(sel)
                    if await el.count() > 0:
                        await el.first.click()
                        await el.first.type(topic, delay=80)
                        await random_delay(1, 2)
                        suggestion = page.locator('[class*="suggest"] li, [class*="topic-item"]').first
                        if await suggestion.count() > 0:
                            await suggestion.click()
                            await random_delay(0.5, 1)
                        break

        await random_delay(2, 4)
        screenshot_path = await save_screenshot(page, "publish_preview")

        if preview_only:
            return {
                "status": "preview",
                "screenshot": screenshot_path,
                "title": title,
                "detail": "预览模式，未点发布",
            }

        # 点发布按钮
        publish_selectors = [
            'button:has-text("发布")',
            '[class*="submit"] button',
            '[class*="publish"] button',
            'button.submit',
        ]
        published = False
        for sel in publish_selectors:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click()
                published = True
                await random_delay(3, 6)
                break

        if not published:
            return {
                "status": "error",
                "screenshot": screenshot_path,
                "title": title,
                "detail": "找不到发布按钮，内容已填好，截图可查看",
            }

        # 检查是否发布成功
        await random_delay(2, 4)
        success_screenshot = await save_screenshot(page, "publish_result")

        return {
            "status": "published",
            "screenshot": success_screenshot,
            "title": title,
            "images_count": len(images),
            "detail": "已发布",
        }


async def main():
    parser = argparse.ArgumentParser(description="发布小红书图文笔记")
    parser.add_argument("--title", "-t", required=True, help="标题")
    parser.add_argument("--content", "-c", required=True, help="正文")
    parser.add_argument("--images", "-i", nargs="+", required=True, help="图片路径")
    parser.add_argument("--topics", nargs="*", default=[], help="话题标签")
    parser.add_argument("--account", default="default", help="使用的账号")
    parser.add_argument("--preview", action="store_true", help="只填充内容不发布，截图预览")
    args = parser.parse_args()

    try:
        result = await do_publish(
            args.account, args.title, args.content,
            args.images, args.topics, preview_only=args.preview,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

        status = "preview" if args.preview else result["status"]
        log_task("publish", {"title": args.title}, status)

    except Exception as e:
        log_task("publish", {"title": args.title}, "error", error=str(e))
        print(f"发布失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
